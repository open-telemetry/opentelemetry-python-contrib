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

"""Method wrappers for Agno instrumentation."""

from __future__ import annotations

import time
from typing import Any, Callable

from opentelemetry import context as context_api
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
from opentelemetry.metrics import Histogram
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.trace.status import Status, StatusCode

from opentelemetry.instrumentation.agno.streaming import AgnoAsyncStream, AgnoStream
from opentelemetry.instrumentation.agno.utils import (
    dont_throw,
    safe_json_serialize,
    should_capture_content,
)

# Custom semantic attributes for Agno (following gen_ai.* namespace)
GENAI_OPERATION_NAME = "gen_ai.operation.name"

# Agent-specific attributes
AGNO_AGENT_NAME = "gen_ai.agno.agent.name"
AGNO_ENTITY_INPUT = "gen_ai.agno.entity.input"
AGNO_ENTITY_OUTPUT = "gen_ai.agno.entity.output"
AGNO_RUN_ID = "gen_ai.agno.run.id"

# Team-specific attributes
AGNO_TEAM_NAME = "gen_ai.agno.team.name"

# Tool-specific attributes
AGNO_TOOL_NAME = "gen_ai.agno.tool.name"
AGNO_TOOL_DESCRIPTION = "gen_ai.agno.tool.description"
AGNO_TOOL_INPUT = "gen_ai.agno.tool.input"
AGNO_TOOL_OUTPUT = "gen_ai.agno.tool.output"


class AgentRunWrapper:
    """Wrapper for Agent.run() method to capture synchronous agent execution."""

    def __init__(
        self,
        tracer: Tracer,
        duration_histogram: Histogram | None = None,
        token_histogram: Histogram | None = None,
    ) -> None:
        """Initialize the wrapper with OpenTelemetry instrumentation objects."""
        self._tracer = tracer
        self._duration_histogram = duration_histogram
        self._token_histogram = token_histogram

    @dont_throw
    def __call__(
        self,
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        """Wrap the Agent.run() call with tracing instrumentation."""
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        is_streaming = kwargs.get("stream", False)
        agent_name = getattr(instance, "name", "unknown")
        span_name = f"{agent_name}.agent"

        if is_streaming:
            span = self._tracer.start_span(span_name, kind=SpanKind.CLIENT)

            try:
                span.set_attribute(GenAIAttributes.GEN_AI_SYSTEM, "agno")
                span.set_attribute(GENAI_OPERATION_NAME, "agent")
                span.set_attribute(GenAIAttributes.GEN_AI_AGENT_NAME, agent_name)

                if hasattr(instance, "model") and instance.model:
                    model_name = getattr(
                        instance.model, "id", getattr(instance.model, "name", "unknown")
                    )
                    span.set_attribute(GenAIAttributes.GEN_AI_REQUEST_MODEL, model_name)

                if args and should_capture_content():
                    span.set_attribute(AGNO_ENTITY_INPUT, str(args[0]))

                start_time = time.time()
                response = wrapped(*args, **kwargs)

                return AgnoStream(
                    span,
                    response,
                    instance,
                    start_time,
                    self._duration_histogram,
                    self._token_histogram,
                )

            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                span.end()
                raise

        else:
            with self._tracer.start_as_current_span(
                span_name, kind=SpanKind.CLIENT
            ) as span:
                try:
                    span.set_attribute(GenAIAttributes.GEN_AI_SYSTEM, "agno")
                    span.set_attribute(GENAI_OPERATION_NAME, "agent")
                    span.set_attribute(GenAIAttributes.GEN_AI_AGENT_NAME, agent_name)

                    if hasattr(instance, "model") and instance.model:
                        model_name = getattr(
                            instance.model,
                            "id",
                            getattr(instance.model, "name", "unknown"),
                        )
                        span.set_attribute(
                            GenAIAttributes.GEN_AI_REQUEST_MODEL, model_name
                        )

                    if args and should_capture_content():
                        span.set_attribute(AGNO_ENTITY_INPUT, str(args[0]))

                    start_time = time.time()
                    result = wrapped(*args, **kwargs)
                    duration = time.time() - start_time

                    if hasattr(result, "content") and should_capture_content():
                        span.set_attribute(AGNO_ENTITY_OUTPUT, str(result.content))

                    if hasattr(result, "run_id"):
                        span.set_attribute(AGNO_RUN_ID, result.run_id)

                    if hasattr(result, "metrics"):
                        metrics = result.metrics
                        if hasattr(metrics, "input_tokens"):
                            span.set_attribute(
                                GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
                                metrics.input_tokens,
                            )
                        if hasattr(metrics, "output_tokens"):
                            span.set_attribute(
                                GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS,
                                metrics.output_tokens,
                            )

                    span.set_status(Status(StatusCode.OK))

                    if self._duration_histogram:
                        self._duration_histogram.record(
                            duration,
                            attributes={
                                GenAIAttributes.GEN_AI_SYSTEM: "agno",
                                GENAI_OPERATION_NAME: "agent",
                            },
                        )

                    return result

                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise


class AgentARunWrapper:
    """Wrapper for Agent.arun() method to capture asynchronous agent execution."""

    def __init__(
        self,
        tracer: Tracer,
        duration_histogram: Histogram | None = None,
        token_histogram: Histogram | None = None,
    ) -> None:
        """Initialize the wrapper with OpenTelemetry instrumentation objects."""
        self._tracer = tracer
        self._duration_histogram = duration_histogram
        self._token_histogram = token_histogram

    @dont_throw
    def __call__(
        self,
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        """Wrap the Agent.arun() call with tracing instrumentation."""
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        is_streaming = kwargs.get("stream", False)
        agent_name = getattr(instance, "name", "unknown")
        span_name = f"{agent_name}.agent"

        if is_streaming:
            span = self._tracer.start_span(span_name, kind=SpanKind.CLIENT)

            try:
                span.set_attribute(GenAIAttributes.GEN_AI_SYSTEM, "agno")
                span.set_attribute(GENAI_OPERATION_NAME, "agent")
                span.set_attribute(GenAIAttributes.GEN_AI_AGENT_NAME, agent_name)

                if hasattr(instance, "model") and instance.model:
                    model_name = getattr(
                        instance.model, "id", getattr(instance.model, "name", "unknown")
                    )
                    span.set_attribute(GenAIAttributes.GEN_AI_REQUEST_MODEL, model_name)

                if args and should_capture_content():
                    span.set_attribute(AGNO_ENTITY_INPUT, str(args[0]))

                start_time = time.time()
                response = wrapped(*args, **kwargs)

                return AgnoAsyncStream(
                    span,
                    response,
                    instance,
                    start_time,
                    self._duration_histogram,
                    self._token_histogram,
                )

            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                span.end()
                raise

        else:
            tracer = self._tracer
            duration_histogram = self._duration_histogram

            async def async_wrapper() -> Any:
                with tracer.start_as_current_span(
                    span_name, kind=SpanKind.CLIENT
                ) as span:
                    try:
                        span.set_attribute(GenAIAttributes.GEN_AI_SYSTEM, "agno")
                        span.set_attribute(GENAI_OPERATION_NAME, "agent")
                        span.set_attribute(
                            GenAIAttributes.GEN_AI_AGENT_NAME, agent_name
                        )

                        if hasattr(instance, "model") and instance.model:
                            model_name = getattr(
                                instance.model,
                                "id",
                                getattr(instance.model, "name", "unknown"),
                            )
                            span.set_attribute(
                                GenAIAttributes.GEN_AI_REQUEST_MODEL, model_name
                            )

                        if args and should_capture_content():
                            span.set_attribute(AGNO_ENTITY_INPUT, str(args[0]))

                        start_time = time.time()
                        result = await wrapped(*args, **kwargs)
                        duration = time.time() - start_time

                        if hasattr(result, "content") and should_capture_content():
                            span.set_attribute(AGNO_ENTITY_OUTPUT, str(result.content))

                        if hasattr(result, "run_id"):
                            span.set_attribute(AGNO_RUN_ID, result.run_id)

                        if hasattr(result, "metrics"):
                            metrics = result.metrics
                            if hasattr(metrics, "input_tokens"):
                                span.set_attribute(
                                    GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
                                    metrics.input_tokens,
                                )
                            if hasattr(metrics, "output_tokens"):
                                span.set_attribute(
                                    GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS,
                                    metrics.output_tokens,
                                )

                        span.set_status(Status(StatusCode.OK))

                        if duration_histogram:
                            duration_histogram.record(
                                duration,
                                attributes={
                                    GenAIAttributes.GEN_AI_SYSTEM: "agno",
                                    GENAI_OPERATION_NAME: "agent",
                                },
                            )

                        return result

                    except Exception as e:
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        span.record_exception(e)
                        raise

            return async_wrapper()


class TeamRunWrapper:
    """Wrapper for Team.run() method to capture synchronous team execution."""

    def __init__(
        self,
        tracer: Tracer,
        duration_histogram: Histogram | None = None,
        token_histogram: Histogram | None = None,
    ) -> None:
        """Initialize the wrapper with OpenTelemetry instrumentation objects."""
        self._tracer = tracer
        self._duration_histogram = duration_histogram
        self._token_histogram = token_histogram

    @dont_throw
    def __call__(
        self,
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        """Wrap the Team.run() call with tracing instrumentation."""
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        team_name = getattr(instance, "name", "unknown")
        span_name = f"{team_name}.team"

        with self._tracer.start_as_current_span(span_name, kind=SpanKind.CLIENT) as span:
            try:
                span.set_attribute(GenAIAttributes.GEN_AI_SYSTEM, "agno")
                span.set_attribute(GENAI_OPERATION_NAME, "workflow")
                span.set_attribute(AGNO_TEAM_NAME, team_name)

                if args and should_capture_content():
                    span.set_attribute(AGNO_ENTITY_INPUT, str(args[0]))

                start_time = time.time()
                result = wrapped(*args, **kwargs)
                duration = time.time() - start_time

                if hasattr(result, "content") and should_capture_content():
                    span.set_attribute(AGNO_ENTITY_OUTPUT, str(result.content))

                if hasattr(result, "run_id"):
                    span.set_attribute(AGNO_RUN_ID, result.run_id)

                span.set_status(Status(StatusCode.OK))

                if self._duration_histogram:
                    self._duration_histogram.record(
                        duration,
                        attributes={
                            GenAIAttributes.GEN_AI_SYSTEM: "agno",
                            GENAI_OPERATION_NAME: "workflow",
                        },
                    )

                return result

            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise


class TeamARunWrapper:
    """Wrapper for Team.arun() method to capture asynchronous team execution."""

    def __init__(
        self,
        tracer: Tracer,
        duration_histogram: Histogram | None = None,
        token_histogram: Histogram | None = None,
    ) -> None:
        """Initialize the wrapper with OpenTelemetry instrumentation objects."""
        self._tracer = tracer
        self._duration_histogram = duration_histogram
        self._token_histogram = token_histogram

    @dont_throw
    async def __call__(
        self,
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        """Wrap the Team.arun() call with tracing instrumentation."""
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return await wrapped(*args, **kwargs)

        team_name = getattr(instance, "name", "unknown")
        span_name = f"{team_name}.team"

        with self._tracer.start_as_current_span(span_name, kind=SpanKind.CLIENT) as span:
            try:
                span.set_attribute(GenAIAttributes.GEN_AI_SYSTEM, "agno")
                span.set_attribute(GENAI_OPERATION_NAME, "workflow")
                span.set_attribute(AGNO_TEAM_NAME, team_name)

                if args and should_capture_content():
                    span.set_attribute(AGNO_ENTITY_INPUT, str(args[0]))

                start_time = time.time()
                result = await wrapped(*args, **kwargs)
                duration = time.time() - start_time

                if hasattr(result, "content") and should_capture_content():
                    span.set_attribute(AGNO_ENTITY_OUTPUT, str(result.content))

                if hasattr(result, "run_id"):
                    span.set_attribute(AGNO_RUN_ID, result.run_id)

                span.set_status(Status(StatusCode.OK))

                if self._duration_histogram:
                    self._duration_histogram.record(
                        duration,
                        attributes={
                            GenAIAttributes.GEN_AI_SYSTEM: "agno",
                            GENAI_OPERATION_NAME: "workflow",
                        },
                    )

                return result

            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise


class FunctionCallExecuteWrapper:
    """Wrapper for FunctionCall.execute() method to capture synchronous tool execution."""

    def __init__(
        self,
        tracer: Tracer,
        duration_histogram: Histogram | None = None,
        token_histogram: Histogram | None = None,
    ) -> None:
        """Initialize the wrapper with OpenTelemetry instrumentation objects."""
        self._tracer = tracer
        self._duration_histogram = duration_histogram
        self._token_histogram = token_histogram

    @dont_throw
    def __call__(
        self,
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        """Wrap the FunctionCall.execute() call with tracing instrumentation."""
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        function_name = getattr(
            getattr(instance, "function", None), "name", "unknown"
        )
        span_name = f"{function_name}.tool"

        with self._tracer.start_as_current_span(span_name, kind=SpanKind.CLIENT) as span:
            try:
                span.set_attribute(GenAIAttributes.GEN_AI_SYSTEM, "agno")
                span.set_attribute(GENAI_OPERATION_NAME, "execute_tool")
                span.set_attribute(AGNO_TOOL_NAME, function_name)

                if hasattr(instance, "function"):
                    func = instance.function
                    if hasattr(func, "description") and func.description:
                        span.set_attribute(AGNO_TOOL_DESCRIPTION, func.description)

                # Capture input arguments
                if should_capture_content():
                    if hasattr(instance, "arguments") and instance.arguments:
                        span.set_attribute(
                            AGNO_TOOL_INPUT, safe_json_serialize(instance.arguments)
                        )
                    elif kwargs:
                        span.set_attribute(
                            AGNO_TOOL_INPUT, safe_json_serialize(kwargs)
                        )

                start_time = time.time()
                result = wrapped(*args, **kwargs)
                duration = time.time() - start_time

                if result is not None and should_capture_content():
                    span.set_attribute(AGNO_TOOL_OUTPUT, str(result))

                span.set_status(Status(StatusCode.OK))

                if self._duration_histogram:
                    self._duration_histogram.record(
                        duration,
                        attributes={
                            GenAIAttributes.GEN_AI_SYSTEM: "agno",
                            GENAI_OPERATION_NAME: "execute_tool",
                        },
                    )

                return result

            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise


class FunctionCallAExecuteWrapper:
    """Wrapper for FunctionCall.aexecute() method to capture async tool execution."""

    def __init__(
        self,
        tracer: Tracer,
        duration_histogram: Histogram | None = None,
        token_histogram: Histogram | None = None,
    ) -> None:
        """Initialize the wrapper with OpenTelemetry instrumentation objects."""
        self._tracer = tracer
        self._duration_histogram = duration_histogram
        self._token_histogram = token_histogram

    @dont_throw
    async def __call__(
        self,
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        """Wrap the FunctionCall.aexecute() call with tracing instrumentation."""
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return await wrapped(*args, **kwargs)

        function_name = getattr(
            getattr(instance, "function", None), "name", "unknown"
        )
        span_name = f"{function_name}.tool"

        with self._tracer.start_as_current_span(span_name, kind=SpanKind.CLIENT) as span:
            try:
                span.set_attribute(GenAIAttributes.GEN_AI_SYSTEM, "agno")
                span.set_attribute(GENAI_OPERATION_NAME, "execute_tool")
                span.set_attribute(AGNO_TOOL_NAME, function_name)

                if hasattr(instance, "function"):
                    func = instance.function
                    if hasattr(func, "description") and func.description:
                        span.set_attribute(AGNO_TOOL_DESCRIPTION, func.description)

                # Capture input arguments
                if should_capture_content():
                    if hasattr(instance, "arguments") and instance.arguments:
                        span.set_attribute(
                            AGNO_TOOL_INPUT, safe_json_serialize(instance.arguments)
                        )
                    elif kwargs:
                        span.set_attribute(
                            AGNO_TOOL_INPUT, safe_json_serialize(kwargs)
                        )

                start_time = time.time()
                result = await wrapped(*args, **kwargs)
                duration = time.time() - start_time

                if result is not None and should_capture_content():
                    span.set_attribute(AGNO_TOOL_OUTPUT, str(result))

                span.set_status(Status(StatusCode.OK))

                if self._duration_histogram:
                    self._duration_histogram.record(
                        duration,
                        attributes={
                            GenAIAttributes.GEN_AI_SYSTEM: "agno",
                            GENAI_OPERATION_NAME: "execute_tool",
                        },
                    )

                return result

            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
