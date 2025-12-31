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
LangGraph instrumentation for OpenTelemetry.

This instrumentation provides automatic tracing of LangGraph workflow executions,
including:
- Graph invocations (invoke/ainvoke)
- Streaming operations (stream/astream) with stream mode capture
- Batch operations (batch/abatch)
- State operations (get_state/update_state)
- Tool node execution
- create_react_agent (from both langgraph.prebuilt and langchain.agents)

This is a standalone instrumentation that works independently of LangChain
instrumentation. It directly wraps LangGraph's Pregel execution engine.

Supports LangGraph 0.2.0+ including LangGraph 1.0.

Usage
-----
.. code:: python

    from opentelemetry.instrumentation.langgraph import LangGraphInstrumentor
    from langgraph.graph import StateGraph, START, END
    from typing import TypedDict

    LangGraphInstrumentor().instrument()

    class State(TypedDict):
        value: str

    def my_node(state: State) -> dict:
        return {"value": state["value"] + " processed"}

    graph = StateGraph(State)
    graph.add_node("process", my_node)
    graph.add_edge(START, "process")
    graph.add_edge("process", END)

    compiled = graph.compile()
    result = compiled.invoke({"value": "hello"})

    LangGraphInstrumentor().uninstrument()

API
---
"""

import logging
from typing import Any, Collection

from wrapt import wrap_function_wrapper  # type: ignore[import-untyped]

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.langgraph.package import _instruments
from opentelemetry.instrumentation.langgraph.patch import (
    create_abatch_wrapper,
    create_aget_state_wrapper,
    create_ainvoke_wrapper,
    create_astream_wrapper,
    create_async_tool_node_wrapper,
    create_aupdate_state_wrapper,
    create_batch_wrapper,
    create_get_state_wrapper,
    create_invoke_wrapper,
    create_react_agent_wrapper,
    create_stream_wrapper,
    create_tool_node_wrapper,
    create_update_state_wrapper,
)
from opentelemetry.instrumentation.langgraph.version import __version__
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.metrics import get_meter
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer

logger = logging.getLogger(__name__)


class LangGraphInstrumentor(BaseInstrumentor):
    """OpenTelemetry instrumentor for LangGraph.

    This instrumentor wraps LangGraph's Pregel execution engine to capture
    telemetry for workflow executions.

    Features:
        - Automatic span creation for graph invocations
        - Support for sync and async operations
        - Streaming operation support
        - Graph name and ID capture

    Example:
        >>> from opentelemetry.instrumentation.langgraph import LangGraphInstrumentor
        >>> instrumentor = LangGraphInstrumentor()
        >>> instrumentor.instrument()
        >>> # Use LangGraph as normal
        >>> instrumentor.uninstrument()

    Note:
        This instrumentation is independent of LangChain instrumentation.
        If both are enabled, you may see overlapping spans for LangGraph
        operations that also trigger LangChain callbacks.
    """

    def __init__(self) -> None:
        """Initialize the LangGraph instrumentor."""
        super().__init__()

    def instrumentation_dependencies(self) -> Collection[str]:
        """Return the instrumented package dependencies."""
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable LangGraph instrumentation.

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

        workflow_duration = meter.create_histogram(
            name="gen_ai.langgraph.workflow.duration",
            description="Duration of LangGraph workflow execution",
            unit="s",
        )

        # Wrap Pregel methods (core execution)
        wrap_function_wrapper(
            module="langgraph.pregel",
            name="Pregel.invoke",
            wrapper=create_invoke_wrapper(tracer, workflow_duration),
        )

        wrap_function_wrapper(
            module="langgraph.pregel",
            name="Pregel.ainvoke",
            wrapper=create_ainvoke_wrapper(tracer, workflow_duration),
        )

        wrap_function_wrapper(
            module="langgraph.pregel",
            name="Pregel.stream",
            wrapper=create_stream_wrapper(tracer),
        )

        wrap_function_wrapper(
            module="langgraph.pregel",
            name="Pregel.astream",
            wrapper=create_astream_wrapper(tracer),
        )

        # Wrap batch methods (available in newer versions)
        self._safe_wrap(
            "langgraph.pregel",
            "Pregel.batch",
            create_batch_wrapper(tracer),
        )

        self._safe_wrap(
            "langgraph.pregel",
            "Pregel.abatch",
            create_abatch_wrapper(tracer),
        )

        # Wrap state operations (for human-in-the-loop visibility)
        self._safe_wrap(
            "langgraph.pregel",
            "Pregel.get_state",
            create_get_state_wrapper(tracer),
        )

        self._safe_wrap(
            "langgraph.pregel",
            "Pregel.aget_state",
            create_aget_state_wrapper(tracer),
        )

        self._safe_wrap(
            "langgraph.pregel",
            "Pregel.update_state",
            create_update_state_wrapper(tracer),
        )

        self._safe_wrap(
            "langgraph.pregel",
            "Pregel.aupdate_state",
            create_aupdate_state_wrapper(tracer),
        )

        # Wrap ToolNode methods for tool call tracing
        self._safe_wrap(
            "langgraph.prebuilt.tool_node",
            "ToolNode._func",
            create_tool_node_wrapper(tracer),
        )

        self._safe_wrap(
            "langgraph.prebuilt.tool_node",
            "ToolNode._afunc",
            create_async_tool_node_wrapper(tracer),
        )

        # Wrap create_react_agent from langgraph.prebuilt (deprecated but still used)
        self._safe_wrap(
            "langgraph.prebuilt.chat_agent_executor",
            "create_react_agent",
            create_react_agent_wrapper(tracer),
        )

        # Wrap create_agent from langchain.agents (new location in LangGraph 1.0+)
        self._safe_wrap(
            "langchain.agents",
            "create_agent",
            create_react_agent_wrapper(tracer),
        )

    def _safe_wrap(
        self, module: str, name: str, wrapper: Any
    ) -> None:
        """Safely wrap a function, ignoring errors if module/function not found.

        This allows backwards compatibility with older LangGraph versions that
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
        """Disable LangGraph instrumentation."""
        import langgraph.pregel

        # Unwrap core Pregel methods
        unwrap(langgraph.pregel.Pregel, "invoke")
        unwrap(langgraph.pregel.Pregel, "ainvoke")
        unwrap(langgraph.pregel.Pregel, "stream")
        unwrap(langgraph.pregel.Pregel, "astream")

        # Unwrap batch methods (if available)
        self._safe_unwrap(langgraph.pregel.Pregel, "batch")
        self._safe_unwrap(langgraph.pregel.Pregel, "abatch")

        # Unwrap state operations (if available)
        self._safe_unwrap(langgraph.pregel.Pregel, "get_state")
        self._safe_unwrap(langgraph.pregel.Pregel, "aget_state")
        self._safe_unwrap(langgraph.pregel.Pregel, "update_state")
        self._safe_unwrap(langgraph.pregel.Pregel, "aupdate_state")

        # Unwrap ToolNode methods
        try:
            from langgraph.prebuilt import tool_node

            self._safe_unwrap(tool_node.ToolNode, "_func")
            self._safe_unwrap(tool_node.ToolNode, "_afunc")
        except (ImportError, ModuleNotFoundError):
            pass

        # Unwrap create_react_agent from langgraph.prebuilt
        try:
            from langgraph.prebuilt import chat_agent_executor

            self._safe_unwrap(chat_agent_executor, "create_react_agent")
        except (ImportError, ModuleNotFoundError):
            pass

        # Unwrap create_agent from langchain.agents
        try:
            import langchain.agents as langchain_agents

            self._safe_unwrap(langchain_agents, "create_agent")
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
