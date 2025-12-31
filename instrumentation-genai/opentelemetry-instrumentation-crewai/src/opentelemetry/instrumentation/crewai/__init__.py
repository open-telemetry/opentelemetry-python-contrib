# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
CrewAI instrumentation for OpenTelemetry.

This instrumentation provides automatic tracing of CrewAI workflow executions,
including:
- Crew kickoff operations (workflow level)
- Agent task executions
- Individual task executions
- LLM calls

Usage
-----
.. code:: python

    from opentelemetry.instrumentation.crewai import CrewAIInstrumentor
    from crewai import Agent, Task, Crew

    CrewAIInstrumentor().instrument()

    # Define your agents and tasks
    researcher = Agent(
        role="Researcher",
        goal="Research and provide accurate information",
        backstory="You are an experienced researcher."
    )

    task = Task(
        description="Research the topic",
        expected_output="A detailed report",
        agent=researcher
    )

    crew = Crew(agents=[researcher], tasks=[task])
    result = crew.kickoff()

    CrewAIInstrumentor().uninstrument()

API
---
"""

import logging
from typing import Any, Collection

from wrapt import wrap_function_wrapper  # type: ignore[import-untyped]

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.crewai.package import _instruments
from opentelemetry.instrumentation.crewai.patch import (
    create_agent_execute_task_wrapper,
    create_kickoff_wrapper,
    create_llm_call_wrapper,
    create_task_execute_wrapper,
)
from opentelemetry.instrumentation.crewai.version import __version__
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.metrics import get_meter
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer

logger = logging.getLogger(__name__)


class CrewAIInstrumentor(BaseInstrumentor):
    """OpenTelemetry instrumentor for CrewAI.

    This instrumentor wraps CrewAI's core classes to capture telemetry
    for workflow executions.

    Features:
        - Automatic span creation for crew kickoff
        - Agent execution tracing with role information
        - Task execution tracing with description
        - LLM call tracing with model parameters
        - Token usage metrics

    Example:
        >>> from opentelemetry.instrumentation.crewai import CrewAIInstrumentor
        >>> instrumentor = CrewAIInstrumentor()
        >>> instrumentor.instrument()
        >>> # Use CrewAI as normal
        >>> instrumentor.uninstrument()

    Attributes:
        All spans use the `gen_ai.crewai.*` namespace for custom attributes,
        following OpenTelemetry semantic conventions.
    """

    def __init__(self) -> None:
        """Initialize the CrewAI instrumentor."""
        super().__init__()

    def instrumentation_dependencies(self) -> Collection[str]:
        """Return the instrumented package dependencies."""
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable CrewAI instrumentation.

        Args:
            **kwargs: Additional configuration options.
                - tracer_provider: Custom TracerProvider
                - meter_provider: Custom MeterProvider
        """
        tracer_provider = kwargs.get("tracer_provider")
        meter_provider = kwargs.get("meter_provider")

        tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=Schemas.V1_28_0.value,
        )

        # Create meter and histograms for metrics
        meter = get_meter(
            __name__,
            __version__,
            meter_provider,
            schema_url=Schemas.V1_28_0.value,
        )

        duration_histogram = meter.create_histogram(
            name="gen_ai.client.operation.duration",
            description="Duration of GenAI operations",
            unit="s",
        )

        token_histogram = meter.create_histogram(
            name="gen_ai.client.token.usage",
            description="Number of tokens used in GenAI operations",
            unit="token",
        )

        # Wrap Crew.kickoff
        wrap_function_wrapper(
            module="crewai.crew",
            name="Crew.kickoff",
            wrapper=create_kickoff_wrapper(
                tracer, duration_histogram, token_histogram
            ),
        )

        # Wrap Agent.execute_task
        wrap_function_wrapper(
            module="crewai.agent",
            name="Agent.execute_task",
            wrapper=create_agent_execute_task_wrapper(
                tracer, duration_histogram, token_histogram
            ),
        )

        # Wrap Task.execute_sync
        wrap_function_wrapper(
            module="crewai.task",
            name="Task.execute_sync",
            wrapper=create_task_execute_wrapper(
                tracer, duration_histogram, token_histogram
            ),
        )

        # Wrap LLM.call
        self._safe_wrap(
            "crewai.llm",
            "LLM.call",
            create_llm_call_wrapper(tracer, duration_histogram, token_histogram),
        )

    def _safe_wrap(
        self, module: str, name: str, wrapper: Any
    ) -> None:
        """Safely wrap a function, ignoring errors if module/function not found.

        This allows backwards compatibility with older CrewAI versions that
        may not have all the methods we want to instrument.

        Args:
            module: The module path.
            name: The function/method name to wrap.
            wrapper: The wrapper function.
        """
        try:
            wrap_function_wrapper(module=module, name=name, wrapper=wrapper)
        except (ImportError, AttributeError, ModuleNotFoundError):
            logger.debug(
                "Could not wrap %s.%s - may not be available in this version",
                module,
                name,
            )

    def _uninstrument(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Disable CrewAI instrumentation."""
        import crewai.crew
        import crewai.agent
        import crewai.task

        # Unwrap core methods
        unwrap(crewai.crew.Crew, "kickoff")
        unwrap(crewai.agent.Agent, "execute_task")
        unwrap(crewai.task.Task, "execute_sync")

        # Unwrap LLM.call (if available)
        try:
            import crewai.llm
            self._safe_unwrap(crewai.llm.LLM, "call")
        except (ImportError, ModuleNotFoundError):
            pass

    def _safe_unwrap(self, obj: Any, name: str) -> None:
        """Safely unwrap a function, ignoring errors if not wrapped.

        Args:
            obj: The object containing the wrapped function.
            name: The function/method name to unwrap.
        """
        try:
            unwrap(obj, name)
        except (AttributeError, ValueError):
            pass
