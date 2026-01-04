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
Agno instrumentation for OpenTelemetry.

This instrumentation provides automatic tracing of Agno framework executions,
including:
- Agent run operations (sync and async)
- Team run operations (sync and async)
- Tool/Function call executions
- Streaming responses

Agno is an open-source AI agent framework that supports multi-agent systems.

Usage
-----
.. code:: python

    from opentelemetry.instrumentation.agno import AgnoInstrumentor
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat

    AgnoInstrumentor().instrument()

    # Create an agent
    agent = Agent(
        name="Assistant",
        model=OpenAIChat(id="gpt-4"),
        instructions="You are a helpful assistant."
    )

    # Run the agent
    result = agent.run("Hello, how are you?")

    AgnoInstrumentor().uninstrument()

API
---
"""

import logging
from typing import Any, Collection

from wrapt import wrap_function_wrapper  # type: ignore[import-untyped]

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.agno.package import _instruments
from opentelemetry.instrumentation.agno.patch import (
    AgentARunWrapper,
    AgentRunWrapper,
    FunctionCallAExecuteWrapper,
    FunctionCallExecuteWrapper,
    TeamARunWrapper,
    TeamRunWrapper,
)
from opentelemetry.instrumentation.agno.version import __version__
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.metrics import get_meter
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer

logger = logging.getLogger(__name__)


class AgnoInstrumentor(BaseInstrumentor):
    """OpenTelemetry instrumentor for Agno.

    This instrumentor wraps Agno's Agent, Team, and FunctionCall classes to
    capture telemetry for workflow executions.

    Features:
        - Automatic span creation for agent runs
        - Team execution tracing
        - Tool execution tracing
        - Support for both sync and async operations
        - Streaming response support
        - Token usage metrics

    Example:
        >>> from opentelemetry.instrumentation.agno import AgnoInstrumentor
        >>> instrumentor = AgnoInstrumentor()
        >>> instrumentor.instrument()
        >>> # Use Agno as normal
        >>> instrumentor.uninstrument()

    Attributes:
        All spans use the `gen_ai.agno.*` namespace for custom attributes,
        following OpenTelemetry semantic conventions.
    """

    def __init__(self) -> None:
        """Initialize the Agno instrumentor."""
        super().__init__()

    def instrumentation_dependencies(self) -> Collection[str]:
        """Return the instrumented package dependencies."""
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable Agno instrumentation.

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

        # Wrap Agent methods
        wrap_function_wrapper(
            module="agno.agent",
            name="Agent.run",
            wrapper=AgentRunWrapper(tracer, duration_histogram, token_histogram),
        )

        wrap_function_wrapper(
            module="agno.agent",
            name="Agent.arun",
            wrapper=AgentARunWrapper(tracer, duration_histogram, token_histogram),
        )

        # Wrap Team methods if available
        self._safe_wrap(
            "agno.team",
            "Team.run",
            TeamRunWrapper(tracer, duration_histogram, token_histogram),
        )

        self._safe_wrap(
            "agno.team",
            "Team.arun",
            TeamARunWrapper(tracer, duration_histogram, token_histogram),
        )

        # Wrap FunctionCall methods for tool execution
        self._safe_wrap(
            "agno.tools",
            "FunctionCall.execute",
            FunctionCallExecuteWrapper(tracer, duration_histogram, token_histogram),
        )

        self._safe_wrap(
            "agno.tools",
            "FunctionCall.aexecute",
            FunctionCallAExecuteWrapper(tracer, duration_histogram, token_histogram),
        )

    def _safe_wrap(self, module: str, name: str, wrapper: Any) -> None:
        """Safely wrap a function, ignoring errors if module/function not found.

        This allows backwards compatibility with different Agno versions.

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
        """Disable Agno instrumentation."""
        # Unwrap Agent methods
        try:
            import agno.agent
            unwrap(agno.agent.Agent, "run")
            unwrap(agno.agent.Agent, "arun")
        except (ImportError, ModuleNotFoundError):
            pass

        # Unwrap Team methods
        try:
            import agno.team
            self._safe_unwrap(agno.team.Team, "run")
            self._safe_unwrap(agno.team.Team, "arun")
        except (ImportError, ModuleNotFoundError):
            pass

        # Unwrap FunctionCall methods
        try:
            import agno.tools
            self._safe_unwrap(agno.tools.FunctionCall, "execute")
            self._safe_unwrap(agno.tools.FunctionCall, "aexecute")
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
