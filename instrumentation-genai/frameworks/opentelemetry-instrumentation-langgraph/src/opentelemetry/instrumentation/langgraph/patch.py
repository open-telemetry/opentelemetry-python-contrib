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

"""Method wrappers for LangGraph instrumentation."""

from __future__ import annotations

import json
import logging
import time
import traceback
from contextlib import contextmanager
from typing import Any, AsyncIterator, Callable, Generator, Iterator, TypeVar

from opentelemetry.metrics import Histogram
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.trace.status import Status, StatusCode

# Custom semantic attributes for LangGraph (following gen_ai.* namespace)
LANGGRAPH_GRAPH_NAME = "gen_ai.langgraph.graph.name"
LANGGRAPH_GRAPH_ID = "gen_ai.langgraph.graph.id"
LANGGRAPH_NODE_NAME = "gen_ai.langgraph.node.name"
LANGGRAPH_STEP = "gen_ai.langgraph.step"

# Tool-related semantic attributes
LANGGRAPH_TOOL_NAME = "gen_ai.langgraph.tool.name"
LANGGRAPH_TOOL_CALL_ID = "gen_ai.langgraph.tool.call_id"
LANGGRAPH_TOOL_COUNT = "gen_ai.langgraph.tool.count"
LANGGRAPH_TOOL_INPUT = "gen_ai.langgraph.tool.input"
LANGGRAPH_TOOL_OUTPUT = "gen_ai.langgraph.tool.output"

# Stream-related semantic attributes
LANGGRAPH_STREAM_MODE = "gen_ai.langgraph.stream.mode"

# Batch-related semantic attributes
LANGGRAPH_BATCH_SIZE = "gen_ai.langgraph.batch.size"

# Agent-related semantic attributes
LANGGRAPH_AGENT_MODEL = "gen_ai.langgraph.agent.model"
LANGGRAPH_AGENT_TOOLS_COUNT = "gen_ai.langgraph.agent.tools_count"
LANGGRAPH_AGENT_HAS_CHECKPOINTER = "gen_ai.langgraph.agent.has_checkpointer"

# State operation semantic attributes
LANGGRAPH_STATE_OPERATION = "gen_ai.langgraph.state.operation"

# ============================================================================
# Enhanced tracing attributes for full workflow visibility
# ============================================================================

# Step/Loop tracking - for Pregel super-step visibility
LANGGRAPH_STEP_NUMBER = "gen_ai.langgraph.step.number"
LANGGRAPH_STEP_NODES = "gen_ai.langgraph.step.nodes"

# Node execution - for individual node tracing
LANGGRAPH_NODE_INPUT = "gen_ai.langgraph.node.input"
LANGGRAPH_NODE_OUTPUT = "gen_ai.langgraph.node.output"
LANGGRAPH_NODE_DURATION = "gen_ai.langgraph.node.duration"
LANGGRAPH_NODE_TRIGGERS = "gen_ai.langgraph.node.triggers"

# State tracking - for state evolution visibility
LANGGRAPH_STATE_CHANNELS_UPDATED = "gen_ai.langgraph.state.channels_updated"

# Routing decisions - for conditional edge visibility
LANGGRAPH_ROUTE_CONDITION = "gen_ai.langgraph.route.condition"
LANGGRAPH_ROUTE_RESULT = "gen_ai.langgraph.route.result"
LANGGRAPH_ROUTE_DESTINATIONS = "gen_ai.langgraph.route.destinations"

# Graph structure - for understanding the workflow topology
LANGGRAPH_GRAPH_NODES = "gen_ai.langgraph.graph.nodes"
LANGGRAPH_GRAPH_EDGES = "gen_ai.langgraph.graph.edges"

# Workflow input/output - for end-to-end debugging
LANGGRAPH_WORKFLOW_INPUT = "gen_ai.langgraph.workflow.input"
LANGGRAPH_WORKFLOW_OUTPUT = "gen_ai.langgraph.workflow.output"

# Checkpoint tracking - for persistence visibility
LANGGRAPH_CHECKPOINT_ID = "gen_ai.langgraph.checkpoint.id"
LANGGRAPH_CHECKPOINT_PARENT_ID = "gen_ai.langgraph.checkpoint.parent_id"

# Task tracking - for understanding execution units
LANGGRAPH_TASK_ID = "gen_ai.langgraph.task.id"
LANGGRAPH_TASK_PATH = "gen_ai.langgraph.task.path"

# Environment variable for content capture control
import os
CAPTURE_CONTENT = os.environ.get(
    "OTEL_INSTRUMENTATION_LANGGRAPH_CAPTURE_CONTENT", "true"
).lower() == "true"
MAX_CONTENT_LENGTH = int(os.environ.get(
    "OTEL_INSTRUMENTATION_LANGGRAPH_MAX_CONTENT_LENGTH", "2000"
))

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def _dont_throw(func: F) -> F:
    """Decorator that catches exceptions and logs them instead of raising.

    Args:
        func: The function to wrap.

    Returns:
        The wrapped function.
    """

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception:
            logger.debug(
                "LangGraph instrumentation failed in %s: %s",
                func.__name__,
                traceback.format_exc(),
            )
            return None

    return wrapper  # type: ignore[return-value]


def _get_graph_name(instance: Any) -> str:
    """Extract graph name from Pregel instance.

    Args:
        instance: The Pregel/CompiledGraph instance.

    Returns:
        The graph name or a default.
    """
    # Try to get name from various attributes
    name = getattr(instance, "name", None)
    if name:
        return str(name)

    # Try to get from builder if available
    builder = getattr(instance, "builder", None)
    if builder:
        builder_name = getattr(builder, "name", None)
        if builder_name:
            return str(builder_name)

    # Fall back to class name
    return instance.__class__.__name__


def _get_graph_id(instance: Any) -> str:
    """Extract graph ID from Pregel instance.

    Args:
        instance: The Pregel/CompiledGraph instance.

    Returns:
        The graph ID or empty string.
    """
    graph_id = getattr(instance, "graph_id", None)
    if graph_id:
        return str(graph_id)
    return ""


@contextmanager
def _workflow_span(
    tracer: Tracer, instance: Any, input_data: Any
) -> Generator[Any, None, None]:
    """Context manager for workflow-level span.

    Args:
        tracer: The OpenTelemetry tracer.
        instance: The Pregel instance.
        input_data: The input data to the workflow.

    Yields:
        The created span.
    """
    graph_name = _get_graph_name(instance)
    graph_id = _get_graph_id(instance)

    with tracer.start_as_current_span(
        name=f"langgraph.workflow {graph_name}",
        kind=SpanKind.INTERNAL,
    ) as span:
        span.set_attribute(LANGGRAPH_GRAPH_NAME, graph_name)
        if graph_id:
            span.set_attribute(LANGGRAPH_GRAPH_ID, graph_id)

        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise


def create_invoke_wrapper(
    tracer: Tracer,
    duration_histogram: Histogram | None = None,
) -> Callable[..., Any]:
    """Create wrapper for Pregel.invoke.

    Args:
        tracer: The OpenTelemetry tracer.
        duration_histogram: Optional histogram for recording duration.

    Returns:
        The wrapper function.
    """

    @_dont_throw
    def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        input_data = args[0] if args else kwargs.get("input")
        start_time = time.perf_counter()

        try:
            with _workflow_span(tracer, instance, input_data):
                result = wrapped(*args, **kwargs)
                return result
        finally:
            if duration_histogram is not None:
                duration = time.perf_counter() - start_time
                graph_name = _get_graph_name(instance)
                duration_histogram.record(
                    duration,
                    attributes={
                        LANGGRAPH_GRAPH_NAME: graph_name,
                        "operation": "invoke",
                    },
                )

    return wrapper


def create_ainvoke_wrapper(
    tracer: Tracer,
    duration_histogram: Histogram | None = None,
) -> Callable[..., Any]:
    """Create wrapper for Pregel.ainvoke.

    Args:
        tracer: The OpenTelemetry tracer.
        duration_histogram: Optional histogram for recording duration.

    Returns:
        The async wrapper function.
    """

    async def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        input_data = args[0] if args else kwargs.get("input")
        graph_name = _get_graph_name(instance)
        graph_id = _get_graph_id(instance)
        start_time = time.perf_counter()

        with tracer.start_as_current_span(
            name=f"langgraph.workflow {graph_name}",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute(LANGGRAPH_GRAPH_NAME, graph_name)
            if graph_id:
                span.set_attribute(LANGGRAPH_GRAPH_ID, graph_id)

            try:
                result = await wrapped(*args, **kwargs)
                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
            finally:
                if duration_histogram is not None:
                    duration = time.perf_counter() - start_time
                    duration_histogram.record(
                        duration,
                        attributes={
                            LANGGRAPH_GRAPH_NAME: graph_name,
                            "operation": "ainvoke",
                        },
                    )

    return wrapper


class _StreamWrapper:
    """Wrapper for streaming responses that maintains span context."""

    def __init__(
        self,
        stream: Iterator[Any],
        span: Any,
        tracer: Tracer,
        graph_name: str,
        stream_mode: str | None = None,
    ) -> None:
        self._stream = stream
        self._span = span
        self._tracer = tracer
        self._graph_name = graph_name
        self._stream_mode = stream_mode
        self._step = 0

    def __iter__(self) -> "_StreamWrapper":
        return self

    def __next__(self) -> Any:
        try:
            chunk = next(self._stream)
            self._step += 1
            return chunk
        except StopIteration:
            self._span.set_attribute(LANGGRAPH_STEP, self._step)
            self._span.set_status(Status(StatusCode.OK))
            self._span.end()
            raise
        except Exception as e:
            self._span.set_attribute(LANGGRAPH_STEP, self._step)
            self._span.set_status(Status(StatusCode.ERROR, str(e)))
            self._span.record_exception(e)
            self._span.end()
            raise


class _AsyncStreamWrapper:
    """Wrapper for async streaming responses that maintains span context."""

    def __init__(
        self,
        stream: Any,
        span: Any,
        tracer: Tracer,
        graph_name: str,
        stream_mode: str | None = None,
    ) -> None:
        self._stream = stream
        self._span = span
        self._tracer = tracer
        self._graph_name = graph_name
        self._stream_mode = stream_mode
        self._step = 0

    def __aiter__(self) -> "_AsyncStreamWrapper":
        return self

    async def __anext__(self) -> Any:
        try:
            chunk = await self._stream.__anext__()
            self._step += 1
            return chunk
        except StopAsyncIteration:
            self._span.set_attribute(LANGGRAPH_STEP, self._step)
            self._span.set_status(Status(StatusCode.OK))
            self._span.end()
            raise
        except Exception as e:
            self._span.set_attribute(LANGGRAPH_STEP, self._step)
            self._span.set_status(Status(StatusCode.ERROR, str(e)))
            self._span.record_exception(e)
            self._span.end()
            raise


def _get_stream_mode(kwargs: dict[str, Any]) -> str:
    """Extract and normalize stream_mode from kwargs.

    Args:
        kwargs: The keyword arguments passed to stream/astream.

    Returns:
        A string representation of the stream mode(s).
    """
    stream_mode_raw = kwargs.get("stream_mode", "values")
    if stream_mode_raw is None:
        return "values"
    if isinstance(stream_mode_raw, str):
        return stream_mode_raw
    # Handle list or tuple of stream modes
    try:
        if hasattr(stream_mode_raw, "__iter__"):
            modes: list[str] = []
            iterable: Any = stream_mode_raw
            for item in iterable:
                modes.append(str(item))
            return ",".join(modes)
    except (TypeError, AttributeError):
        pass
    return str(stream_mode_raw)


def create_stream_wrapper(tracer: Tracer) -> Callable[..., Any]:
    """Create wrapper for Pregel.stream.

    Args:
        tracer: The OpenTelemetry tracer.

    Returns:
        The wrapper function.
    """

    @_dont_throw
    def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        graph_name = _get_graph_name(instance)
        graph_id = _get_graph_id(instance)
        # Capture stream_mode (new in LangGraph - values, updates, messages,
        # checkpoints, tasks, debug)
        stream_mode = _get_stream_mode(kwargs)

        span = tracer.start_span(
            name=f"langgraph.workflow.stream {graph_name}",
            kind=SpanKind.INTERNAL,
        )
        span.set_attribute(LANGGRAPH_GRAPH_NAME, graph_name)
        if graph_id:
            span.set_attribute(LANGGRAPH_GRAPH_ID, graph_id)
        if stream_mode:
            span.set_attribute(LANGGRAPH_STREAM_MODE, str(stream_mode))

        try:
            stream = wrapped(*args, **kwargs)
            return _StreamWrapper(
                stream, span, tracer, graph_name, str(stream_mode)
            )
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            span.end()
            raise

    return wrapper


def create_astream_wrapper(tracer: Tracer) -> Callable[..., Any]:
    """Create wrapper for Pregel.astream.

    Args:
        tracer: The OpenTelemetry tracer.

    Returns:
        The async wrapper function.
    """

    async def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        graph_name = _get_graph_name(instance)
        graph_id = _get_graph_id(instance)
        # Capture stream_mode (new in LangGraph - values, updates, messages,
        # checkpoints, tasks, debug)
        stream_mode = _get_stream_mode(kwargs)

        span = tracer.start_span(
            name=f"langgraph.workflow.stream {graph_name}",
            kind=SpanKind.INTERNAL,
        )
        span.set_attribute(LANGGRAPH_GRAPH_NAME, graph_name)
        if graph_id:
            span.set_attribute(LANGGRAPH_GRAPH_ID, graph_id)
        if stream_mode:
            span.set_attribute(LANGGRAPH_STREAM_MODE, stream_mode)

        try:
            stream = await wrapped(*args, **kwargs)
            return _AsyncStreamWrapper(
                stream, span, tracer, graph_name, stream_mode
            )
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            span.end()
            raise

    return wrapper


def _safe_json_serialize(obj: Any) -> str:
    """Safely serialize an object to JSON string.

    Args:
        obj: The object to serialize.

    Returns:
        JSON string representation, or str(obj) if serialization fails.
    """
    try:
        return json.dumps(obj, default=str)
    except (TypeError, ValueError):
        return str(obj)


def _get_tool_name(tool_call: Any) -> str:
    """Extract tool name from a tool call.

    Args:
        tool_call: The tool call object (ToolCall or dict).

    Returns:
        The tool name.
    """
    if hasattr(tool_call, "name"):
        return str(tool_call.name)
    if isinstance(tool_call, dict):
        return str(tool_call.get("name", "unknown"))
    return "unknown"


def _get_tool_call_id(tool_call: Any) -> str:
    """Extract tool call ID from a tool call.

    Args:
        tool_call: The tool call object (ToolCall or dict).

    Returns:
        The tool call ID.
    """
    if hasattr(tool_call, "id"):
        return str(tool_call.id) if tool_call.id else ""
    if isinstance(tool_call, dict):
        return str(tool_call.get("id", ""))
    return ""


def _get_tool_args(tool_call: Any) -> Any:
    """Extract tool arguments from a tool call.

    Args:
        tool_call: The tool call object (ToolCall or dict).

    Returns:
        The tool arguments.
    """
    if hasattr(tool_call, "args"):
        return tool_call.args
    if isinstance(tool_call, dict):
        return tool_call.get("args", {})
    return {}


def create_tool_node_wrapper(tracer: Tracer) -> Callable[..., Any]:
    """Create wrapper for ToolNode._func (sync execution).

    This wrapper creates spans for tool node execution and individual
    tool invocations within the node.

    Args:
        tracer: The OpenTelemetry tracer.

    Returns:
        The wrapper function.
    """

    @_dont_throw
    def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        # Get input data
        input_data = args[0] if args else kwargs.get("input")

        # Try to get tool calls from input using instance's parse method
        tool_calls = []
        try:
            if hasattr(instance, "_parse_input"):
                parsed = instance._parse_input(input_data)
                if isinstance(parsed, tuple) and len(parsed) >= 1:
                    tool_calls = parsed[0] if parsed[0] else []
        except Exception:
            pass

        # Create parent span for ToolNode execution
        with tracer.start_as_current_span(
            name="langgraph.tool_node",
            kind=SpanKind.INTERNAL,
        ) as node_span:
            node_span.set_attribute(LANGGRAPH_NODE_NAME, "tools")
            node_span.set_attribute(LANGGRAPH_TOOL_COUNT, len(tool_calls))
            node_span.set_attribute(GenAIAttributes.GEN_AI_OPERATION_NAME, "task")

            try:
                # Execute the original function
                result = wrapped(*args, **kwargs)

                # Try to create spans for individual tools after execution
                # Since tools may run in parallel, we create spans post-hoc
                if tool_calls:
                    _record_tool_spans(tracer, tool_calls, result)

                node_span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                node_span.set_status(Status(StatusCode.ERROR, str(e)))
                node_span.record_exception(e)
                raise

    return wrapper


def create_async_tool_node_wrapper(tracer: Tracer) -> Callable[..., Any]:
    """Create wrapper for ToolNode._afunc (async execution).

    This wrapper creates spans for async tool node execution and individual
    tool invocations within the node.

    Args:
        tracer: The OpenTelemetry tracer.

    Returns:
        The async wrapper function.
    """

    async def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        # Get input data
        input_data = args[0] if args else kwargs.get("input")

        # Try to get tool calls from input using instance's parse method
        tool_calls = []
        try:
            if hasattr(instance, "_parse_input"):
                parsed = instance._parse_input(input_data)
                if isinstance(parsed, tuple) and len(parsed) >= 1:
                    tool_calls = parsed[0] if parsed[0] else []
        except Exception:
            pass

        # Create parent span for ToolNode execution
        with tracer.start_as_current_span(
            name="langgraph.tool_node",
            kind=SpanKind.INTERNAL,
        ) as node_span:
            node_span.set_attribute(LANGGRAPH_NODE_NAME, "tools")
            node_span.set_attribute(LANGGRAPH_TOOL_COUNT, len(tool_calls))
            node_span.set_attribute(GenAIAttributes.GEN_AI_OPERATION_NAME, "task")

            try:
                # Execute the original function
                result = await wrapped(*args, **kwargs)

                # Try to create spans for individual tools after execution
                if tool_calls:
                    _record_tool_spans(tracer, tool_calls, result)

                node_span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                node_span.set_status(Status(StatusCode.ERROR, str(e)))
                node_span.record_exception(e)
                raise

    return wrapper


def _record_tool_spans(
    tracer: Tracer,
    tool_calls: list[Any],
    results: Any,
) -> None:
    """Record individual tool execution spans.

    This function creates spans for each tool that was executed,
    capturing the tool name, call ID, input arguments, and output.

    Args:
        tracer: The OpenTelemetry tracer.
        tool_calls: List of tool calls that were executed.
        results: The results from tool execution (list of ToolMessages or similar).
    """
    # Convert results to list if not already
    result_list = []
    if isinstance(results, dict):
        # Results may be in a dict like {"messages": [...]}
        messages = results.get("messages", [])
        if isinstance(messages, list):
            result_list = messages
    elif isinstance(results, list):
        result_list = results
    else:
        result_list = [results] if results else []

    for i, tool_call in enumerate(tool_calls):
        tool_name = _get_tool_name(tool_call)
        tool_call_id = _get_tool_call_id(tool_call)
        tool_args = _get_tool_args(tool_call)

        # Try to find matching result
        tool_output = None
        for result in result_list:
            if hasattr(result, "tool_call_id"):
                if result.tool_call_id == tool_call_id:
                    tool_output = (
                        result.content
                        if hasattr(result, "content")
                        else str(result)
                    )
                    break
            elif hasattr(result, "id"):
                if result.id == tool_call_id:
                    tool_output = (
                        result.content
                        if hasattr(result, "content")
                        else str(result)
                    )
                    break

        # If no match found by ID, try to match by index
        if tool_output is None and i < len(result_list):
            result = result_list[i]
            tool_output = (
                result.content if hasattr(result, "content") else str(result)
            )

        # Create span for this tool execution
        with tracer.start_as_current_span(
            name=f"{tool_name}.tool",
            kind=SpanKind.INTERNAL,
        ) as tool_span:
            tool_span.set_attribute(LANGGRAPH_TOOL_NAME, tool_name)
            tool_span.set_attribute(GenAIAttributes.GEN_AI_OPERATION_NAME, "execute_tool")

            if tool_call_id:
                tool_span.set_attribute(LANGGRAPH_TOOL_CALL_ID, tool_call_id)

            # Capture input arguments
            if tool_args:
                tool_span.set_attribute(
                    LANGGRAPH_TOOL_INPUT, _safe_json_serialize(tool_args)
                )

            # Capture output
            if tool_output is not None:
                tool_span.set_attribute(
                    LANGGRAPH_TOOL_OUTPUT, _safe_json_serialize(tool_output)
                )

            tool_span.set_status(Status(StatusCode.OK))


def create_batch_wrapper(tracer: Tracer) -> Callable[..., Any]:
    """Create wrapper for Pregel.batch.

    Args:
        tracer: The OpenTelemetry tracer.

    Returns:
        The wrapper function.
    """

    @_dont_throw
    def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        graph_name = _get_graph_name(instance)
        graph_id = _get_graph_id(instance)
        # Get batch size from first argument (list of inputs)
        inputs = args[0] if args else kwargs.get("inputs", [])
        batch_size = len(inputs) if hasattr(inputs, "__len__") else 0

        with tracer.start_as_current_span(
            name=f"langgraph.workflow.batch {graph_name}",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute(LANGGRAPH_GRAPH_NAME, graph_name)
            if graph_id:
                span.set_attribute(LANGGRAPH_GRAPH_ID, graph_id)
            span.set_attribute(LANGGRAPH_BATCH_SIZE, batch_size)

            try:
                result = wrapped(*args, **kwargs)
                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    return wrapper


def create_abatch_wrapper(tracer: Tracer) -> Callable[..., Any]:
    """Create wrapper for Pregel.abatch.

    Args:
        tracer: The OpenTelemetry tracer.

    Returns:
        The async wrapper function.
    """

    async def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        graph_name = _get_graph_name(instance)
        graph_id = _get_graph_id(instance)
        # Get batch size from first argument (list of inputs)
        inputs = args[0] if args else kwargs.get("inputs", [])
        batch_size = len(inputs) if hasattr(inputs, "__len__") else 0

        with tracer.start_as_current_span(
            name=f"langgraph.workflow.batch {graph_name}",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute(LANGGRAPH_GRAPH_NAME, graph_name)
            if graph_id:
                span.set_attribute(LANGGRAPH_GRAPH_ID, graph_id)
            span.set_attribute(LANGGRAPH_BATCH_SIZE, batch_size)

            try:
                result = await wrapped(*args, **kwargs)
                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    return wrapper


def create_get_state_wrapper(tracer: Tracer) -> Callable[..., Any]:
    """Create wrapper for CompiledGraph.get_state.

    Args:
        tracer: The OpenTelemetry tracer.

    Returns:
        The wrapper function.
    """

    @_dont_throw
    def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        graph_name = _get_graph_name(instance)

        with tracer.start_as_current_span(
            name=f"langgraph.state.get {graph_name}",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute(LANGGRAPH_GRAPH_NAME, graph_name)
            span.set_attribute(LANGGRAPH_STATE_OPERATION, "get_state")

            try:
                result = wrapped(*args, **kwargs)
                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    return wrapper


def create_aget_state_wrapper(tracer: Tracer) -> Callable[..., Any]:
    """Create wrapper for CompiledGraph.aget_state.

    Args:
        tracer: The OpenTelemetry tracer.

    Returns:
        The async wrapper function.
    """

    async def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        graph_name = _get_graph_name(instance)

        with tracer.start_as_current_span(
            name=f"langgraph.state.get {graph_name}",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute(LANGGRAPH_GRAPH_NAME, graph_name)
            span.set_attribute(LANGGRAPH_STATE_OPERATION, "aget_state")

            try:
                result = await wrapped(*args, **kwargs)
                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    return wrapper


def create_update_state_wrapper(tracer: Tracer) -> Callable[..., Any]:
    """Create wrapper for CompiledGraph.update_state.

    Args:
        tracer: The OpenTelemetry tracer.

    Returns:
        The wrapper function.
    """

    @_dont_throw
    def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        graph_name = _get_graph_name(instance)

        with tracer.start_as_current_span(
            name=f"langgraph.state.update {graph_name}",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute(LANGGRAPH_GRAPH_NAME, graph_name)
            span.set_attribute(LANGGRAPH_STATE_OPERATION, "update_state")

            try:
                result = wrapped(*args, **kwargs)
                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    return wrapper


def create_aupdate_state_wrapper(tracer: Tracer) -> Callable[..., Any]:
    """Create wrapper for CompiledGraph.aupdate_state.

    Args:
        tracer: The OpenTelemetry tracer.

    Returns:
        The async wrapper function.
    """

    async def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        graph_name = _get_graph_name(instance)

        with tracer.start_as_current_span(
            name=f"langgraph.state.update {graph_name}",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute(LANGGRAPH_GRAPH_NAME, graph_name)
            span.set_attribute(LANGGRAPH_STATE_OPERATION, "aupdate_state")

            try:
                result = await wrapped(*args, **kwargs)
                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    return wrapper


def _get_model_name(model: Any) -> str:
    """Extract model name from a model object.

    Args:
        model: The model object (can be string, ChatModel, or callable).

    Returns:
        The model name or "unknown".
    """
    if isinstance(model, str):
        return model
    if hasattr(model, "model_name"):
        return str(model.model_name)
    if hasattr(model, "model"):
        return str(model.model)
    if hasattr(model, "__class__"):
        return model.__class__.__name__
    return "unknown"


def create_react_agent_wrapper(tracer: Tracer) -> Callable[..., Any]:
    """Create wrapper for create_react_agent function.

    This wraps both langgraph.prebuilt.create_react_agent and
    langchain.agents.create_agent to capture agent creation telemetry.

    Args:
        tracer: The OpenTelemetry tracer.

    Returns:
        The wrapper function.
    """

    @_dont_throw
    def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        # Extract agent configuration
        model = args[0] if args else kwargs.get("model")
        tools = args[1] if len(args) > 1 else kwargs.get("tools", [])
        checkpointer = kwargs.get("checkpointer")

        model_name = _get_model_name(model)
        tools_count = len(tools) if hasattr(tools, "__len__") else 0
        has_checkpointer = checkpointer is not None

        with tracer.start_as_current_span(
            name="langgraph.create_react_agent",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute(LANGGRAPH_AGENT_MODEL, model_name)
            span.set_attribute(LANGGRAPH_AGENT_TOOLS_COUNT, tools_count)
            span.set_attribute(LANGGRAPH_AGENT_HAS_CHECKPOINTER, has_checkpointer)
            span.set_attribute(GenAIAttributes.GEN_AI_OPERATION_NAME, "create_agent")

            try:
                result = wrapped(*args, **kwargs)
                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    return wrapper


# ============================================================================
# Enhanced Tracing - Helper Functions
# ============================================================================


def _truncate_content(content: str, max_length: int = MAX_CONTENT_LENGTH) -> str:
    """Truncate content to max length, adding ellipsis if truncated.

    Args:
        content: The content to truncate.
        max_length: Maximum length before truncation.

    Returns:
        Truncated content with ellipsis if needed.
    """
    if len(content) <= max_length:
        return content
    return content[:max_length] + "..."


def _safe_serialize_content(obj: Any) -> str:
    """Safely serialize content for span attributes.

    Args:
        obj: The object to serialize.

    Returns:
        JSON string, truncated if necessary.
    """
    if not CAPTURE_CONTENT:
        return "<content capture disabled>"
    try:
        serialized = json.dumps(obj, default=str)
        return _truncate_content(serialized)
    except (TypeError, ValueError):
        return _truncate_content(str(obj))


def _extract_graph_structure(instance: Any) -> tuple[list[str], list[dict]]:
    """Extract node names and edge definitions from a compiled graph.

    Args:
        instance: The Pregel/CompiledGraph instance.

    Returns:
        Tuple of (node_names, edge_definitions).
    """
    nodes = []
    edges = []

    try:
        # Try to get nodes from the graph
        if hasattr(instance, "nodes"):
            graph_nodes = instance.nodes
            if isinstance(graph_nodes, dict):
                nodes = list(graph_nodes.keys())
            elif hasattr(graph_nodes, "__iter__"):
                nodes = [str(n) for n in graph_nodes]

        # Try to get edges from the builder
        builder = getattr(instance, "builder", None)
        if builder:
            # Standard edges
            if hasattr(builder, "_edges"):
                for edge in builder._edges:
                    if isinstance(edge, tuple) and len(edge) >= 2:
                        edges.append({"from": str(edge[0]), "to": str(edge[1])})

            # Conditional edges (branches)
            if hasattr(builder, "_branches"):
                for source, branch_info in builder._branches.items():
                    if hasattr(branch_info, "ends") and branch_info.ends:
                        for dest in branch_info.ends.values():
                            edges.append({
                                "from": str(source),
                                "to": str(dest),
                                "conditional": True,
                            })
    except Exception:
        pass

    return nodes, edges


def _get_task_name(task: Any) -> str:
    """Extract task/node name from a task object.

    Args:
        task: The task object (PregelExecutableTask or similar).

    Returns:
        The task name.
    """
    # Try different attributes that might contain the name
    if hasattr(task, "name"):
        return str(task.name)
    if hasattr(task, "path"):
        path = task.path
        if isinstance(path, tuple) and path:
            return str(path[-1])
        return str(path)
    if isinstance(task, tuple) and len(task) >= 1:
        return str(task[0])
    return "unknown"


def _get_task_id(task: Any) -> str:
    """Extract task ID from a task object.

    Args:
        task: The task object.

    Returns:
        The task ID.
    """
    if hasattr(task, "id"):
        return str(task.id) if task.id else ""
    return ""


# ============================================================================
# Enhanced Tracing - Node Execution Wrapper
# ============================================================================


def create_node_execution_wrapper(tracer: Tracer) -> Callable[..., Any]:
    """Create wrapper for run_with_retry() to trace individual node execution.

    This wraps langgraph.pregel._retry.run_with_retry() which is the core
    function that actually executes nodes. The first argument is a
    PregelExecutableTask with task.name containing the node name.

    Args:
        tracer: The OpenTelemetry tracer.

    Returns:
        The wrapper function.
    """

    @_dont_throw
    def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        # run_with_retry signature:
        # run_with_retry(task, retry_policy, configurable=None)
        # task is PregelExecutableTask with:
        #   - task.name: node name ("draft", "execute_tools", "revise")
        #   - task.input: input data
        #   - task.id: unique task ID
        #   - task.proc: the callable (Runnable)
        task = args[0] if args else None

        # Extract node name from task
        node_name = "unknown"
        task_id = ""
        input_data = None

        if task is not None:
            # Get node name directly from task.name
            if hasattr(task, "name"):
                node_name = str(task.name)

            # Get task ID
            if hasattr(task, "id"):
                task_id = str(task.id) if task.id else ""

            # Get input data
            if hasattr(task, "input"):
                input_data = task.input

        start_time = time.perf_counter()

        with tracer.start_as_current_span(
            name=f"langgraph.node {node_name}",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute(LANGGRAPH_NODE_NAME, node_name)
            span.set_attribute(GenAIAttributes.GEN_AI_OPERATION_NAME, "task")

            if task_id:
                span.set_attribute(LANGGRAPH_TASK_ID, task_id)

            # Capture input if enabled
            if CAPTURE_CONTENT and input_data is not None:
                span.set_attribute(
                    LANGGRAPH_NODE_INPUT, _safe_serialize_content(input_data)
                )

            try:
                result = wrapped(*args, **kwargs)

                # Note: run_with_retry returns None, actual result is in task.writes
                # Record duration
                duration = time.perf_counter() - start_time
                span.set_attribute(LANGGRAPH_NODE_DURATION, duration)

                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                duration = time.perf_counter() - start_time
                span.set_attribute(LANGGRAPH_NODE_DURATION, duration)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    return wrapper


def create_async_node_execution_wrapper(tracer: Tracer) -> Callable[..., Any]:
    """Create async wrapper for arun_with_retry() to trace individual node execution.

    This wraps langgraph.pregel._retry.arun_with_retry() which is the async
    function that actually executes nodes. The first argument is a
    PregelExecutableTask with task.name containing the node name.

    Args:
        tracer: The OpenTelemetry tracer.

    Returns:
        The async wrapper function.
    """

    async def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        # arun_with_retry signature:
        # arun_with_retry(task, retry_policy, stream=False, ...)
        # task is PregelExecutableTask with:
        #   - task.name: node name ("draft", "execute_tools", "revise")
        #   - task.input: input data
        #   - task.id: unique task ID
        task = args[0] if args else None

        # Extract node name from task
        node_name = "unknown"
        task_id = ""
        input_data = None

        if task is not None:
            # Get node name directly from task.name
            if hasattr(task, "name"):
                node_name = str(task.name)

            # Get task ID
            if hasattr(task, "id"):
                task_id = str(task.id) if task.id else ""

            # Get input data
            if hasattr(task, "input"):
                input_data = task.input

        start_time = time.perf_counter()

        with tracer.start_as_current_span(
            name=f"langgraph.node {node_name}",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute(LANGGRAPH_NODE_NAME, node_name)
            span.set_attribute(GenAIAttributes.GEN_AI_OPERATION_NAME, "task")

            if task_id:
                span.set_attribute(LANGGRAPH_TASK_ID, task_id)

            if CAPTURE_CONTENT and input_data is not None:
                span.set_attribute(
                    LANGGRAPH_NODE_INPUT, _safe_serialize_content(input_data)
                )

            try:
                result = await wrapped(*args, **kwargs)

                # Note: arun_with_retry returns None, actual result is in task.writes
                duration = time.perf_counter() - start_time
                span.set_attribute(LANGGRAPH_NODE_DURATION, duration)

                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                duration = time.perf_counter() - start_time
                span.set_attribute(LANGGRAPH_NODE_DURATION, duration)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    return wrapper


# ============================================================================
# Enhanced Tracing - Routing Decision Wrapper
# ============================================================================


def create_route_wrapper(tracer: Tracer) -> Callable[..., Any]:
    """Create wrapper for BranchSpec._route to trace conditional routing.

    This captures which condition was evaluated and what routing
    decision was made.

    Args:
        tracer: The OpenTelemetry tracer.

    Returns:
        The wrapper function.
    """

    @_dont_throw
    def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        # Extract information about the routing
        condition_name = "unknown"
        if hasattr(instance, "path"):
            path = instance.path
            if hasattr(path, "__name__"):
                condition_name = path.__name__
            elif hasattr(path, "name"):
                condition_name = str(path.name)

        with tracer.start_as_current_span(
            name=f"langgraph.route {condition_name}",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute(LANGGRAPH_ROUTE_CONDITION, condition_name)
            span.set_attribute(GenAIAttributes.GEN_AI_OPERATION_NAME, "route")

            try:
                result = wrapped(*args, **kwargs)

                # Capture routing result
                if result is not None:
                    if isinstance(result, str):
                        span.set_attribute(LANGGRAPH_ROUTE_RESULT, result)
                        span.set_attribute(
                            LANGGRAPH_ROUTE_DESTINATIONS,
                            json.dumps([result]),
                        )
                    elif hasattr(result, "__iter__"):
                        destinations = [str(r) for r in result]
                        span.set_attribute(
                            LANGGRAPH_ROUTE_RESULT, ",".join(destinations)
                        )
                        span.set_attribute(
                            LANGGRAPH_ROUTE_DESTINATIONS,
                            json.dumps(destinations),
                        )

                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    return wrapper


def create_async_route_wrapper(tracer: Tracer) -> Callable[..., Any]:
    """Create async wrapper for BranchSpec._aroute to trace conditional routing.

    Args:
        tracer: The OpenTelemetry tracer.

    Returns:
        The async wrapper function.
    """

    async def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        condition_name = "unknown"
        if hasattr(instance, "path"):
            path = instance.path
            if hasattr(path, "__name__"):
                condition_name = path.__name__
            elif hasattr(path, "name"):
                condition_name = str(path.name)

        with tracer.start_as_current_span(
            name=f"langgraph.route {condition_name}",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute(LANGGRAPH_ROUTE_CONDITION, condition_name)
            span.set_attribute(GenAIAttributes.GEN_AI_OPERATION_NAME, "route")

            try:
                result = await wrapped(*args, **kwargs)

                if result is not None:
                    if isinstance(result, str):
                        span.set_attribute(LANGGRAPH_ROUTE_RESULT, result)
                        span.set_attribute(
                            LANGGRAPH_ROUTE_DESTINATIONS,
                            json.dumps([result]),
                        )
                    elif hasattr(result, "__iter__"):
                        destinations = [str(r) for r in result]
                        span.set_attribute(
                            LANGGRAPH_ROUTE_RESULT, ",".join(destinations)
                        )
                        span.set_attribute(
                            LANGGRAPH_ROUTE_DESTINATIONS,
                            json.dumps(destinations),
                        )

                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    return wrapper


# ============================================================================
# Enhanced Tracing - Task Execution Wrapper (for Pregel runner)
# ============================================================================


def create_task_execution_wrapper(tracer: Tracer) -> Callable[..., Any]:
    """Create wrapper for PregelRunner task execution.

    This wraps task execution to provide visibility into each
    executable task that runs in the Pregel loop.

    Args:
        tracer: The OpenTelemetry tracer.

    Returns:
        The wrapper function.
    """

    @_dont_throw
    def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        # Try to extract task info from args
        # Typically the task is passed as first argument
        task = args[0] if args else None
        task_name = _get_task_name(task)
        task_id = _get_task_id(task)

        start_time = time.perf_counter()

        with tracer.start_as_current_span(
            name=f"langgraph.task {task_name}",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute(LANGGRAPH_NODE_NAME, task_name)
            span.set_attribute(GenAIAttributes.GEN_AI_OPERATION_NAME, "task")

            if task_id:
                span.set_attribute(LANGGRAPH_TASK_ID, task_id)

            # Capture task path if available
            if task and hasattr(task, "path"):
                path = task.path
                if path:
                    span.set_attribute(LANGGRAPH_TASK_PATH, str(path))

            try:
                result = wrapped(*args, **kwargs)

                duration = time.perf_counter() - start_time
                span.set_attribute(LANGGRAPH_NODE_DURATION, duration)

                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                duration = time.perf_counter() - start_time
                span.set_attribute(LANGGRAPH_NODE_DURATION, duration)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    return wrapper


# ============================================================================
# Enhanced Workflow Span with I/O Capture
# ============================================================================


def create_enhanced_invoke_wrapper(
    tracer: Tracer,
    duration_histogram: Histogram | None = None,
) -> Callable[..., Any]:
    """Create enhanced wrapper for Pregel.invoke with I/O capture.

    This captures workflow input, output, and graph structure in addition
    to basic workflow tracing.

    Args:
        tracer: The OpenTelemetry tracer.
        duration_histogram: Optional histogram for recording duration.

    Returns:
        The wrapper function.
    """

    @_dont_throw
    def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        input_data = args[0] if args else kwargs.get("input")
        start_time = time.perf_counter()
        graph_name = _get_graph_name(instance)
        graph_id = _get_graph_id(instance)

        with tracer.start_as_current_span(
            name=f"langgraph.workflow {graph_name}",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute(LANGGRAPH_GRAPH_NAME, graph_name)
            if graph_id:
                span.set_attribute(LANGGRAPH_GRAPH_ID, graph_id)

            # Capture graph structure
            nodes, edges = _extract_graph_structure(instance)
            if nodes:
                span.set_attribute(LANGGRAPH_GRAPH_NODES, json.dumps(nodes))
            if edges:
                span.set_attribute(LANGGRAPH_GRAPH_EDGES, json.dumps(edges))

            # Capture input
            if CAPTURE_CONTENT and input_data is not None:
                span.set_attribute(
                    LANGGRAPH_WORKFLOW_INPUT, _safe_serialize_content(input_data)
                )

            try:
                result = wrapped(*args, **kwargs)

                # Capture output
                if CAPTURE_CONTENT and result is not None:
                    span.set_attribute(
                        LANGGRAPH_WORKFLOW_OUTPUT, _safe_serialize_content(result)
                    )

                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
            finally:
                if duration_histogram is not None:
                    duration = time.perf_counter() - start_time
                    duration_histogram.record(
                        duration,
                        attributes={
                            LANGGRAPH_GRAPH_NAME: graph_name,
                            "operation": "invoke",
                        },
                    )

    return wrapper


def create_enhanced_ainvoke_wrapper(
    tracer: Tracer,
    duration_histogram: Histogram | None = None,
) -> Callable[..., Any]:
    """Create enhanced async wrapper for Pregel.ainvoke with I/O capture.

    Args:
        tracer: The OpenTelemetry tracer.
        duration_histogram: Optional histogram for recording duration.

    Returns:
        The async wrapper function.
    """

    async def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        input_data = args[0] if args else kwargs.get("input")
        start_time = time.perf_counter()
        graph_name = _get_graph_name(instance)
        graph_id = _get_graph_id(instance)

        with tracer.start_as_current_span(
            name=f"langgraph.workflow {graph_name}",
            kind=SpanKind.INTERNAL,
        ) as span:
            span.set_attribute(LANGGRAPH_GRAPH_NAME, graph_name)
            if graph_id:
                span.set_attribute(LANGGRAPH_GRAPH_ID, graph_id)

            # Capture graph structure
            nodes, edges = _extract_graph_structure(instance)
            if nodes:
                span.set_attribute(LANGGRAPH_GRAPH_NODES, json.dumps(nodes))
            if edges:
                span.set_attribute(LANGGRAPH_GRAPH_EDGES, json.dumps(edges))

            # Capture input
            if CAPTURE_CONTENT and input_data is not None:
                span.set_attribute(
                    LANGGRAPH_WORKFLOW_INPUT, _safe_serialize_content(input_data)
                )

            try:
                result = await wrapped(*args, **kwargs)

                # Capture output
                if CAPTURE_CONTENT and result is not None:
                    span.set_attribute(
                        LANGGRAPH_WORKFLOW_OUTPUT, _safe_serialize_content(result)
                    )

                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
            finally:
                if duration_histogram is not None:
                    duration = time.perf_counter() - start_time
                    duration_histogram.record(
                        duration,
                        attributes={
                            LANGGRAPH_GRAPH_NAME: graph_name,
                            "operation": "ainvoke",
                        },
                    )

    return wrapper
