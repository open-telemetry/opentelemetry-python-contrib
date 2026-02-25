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
Telemetry handler for GenAI invocations.

This module exposes the `TelemetryHandler` class, which manages the lifecycle of
GenAI (Generative AI) invocations and emits telemetry data (spans and related attributes).
It supports starting, stopping, and failing LLM invocations and tool call executions.

Classes:
    - TelemetryHandler: Manages GenAI invocation lifecycles and emits telemetry.

Functions:
    - get_telemetry_handler: Returns a singleton `TelemetryHandler` instance.

Usage - LLM Invocations:
    handler = get_telemetry_handler()

    # Use the context manager to manage the lifecycle of an LLM invocation.
    with handler.llm(invocation) as invocation:
        # Populate outputs and any additional attributes
        invocation.output_messages = [...]
        invocation.attributes.update({"more": "attrs"})

    # Or, if you prefer to manage the lifecycle manually
    invocation = LLMInvocation(
        request_model="my-model",
        input_messages=[...],
        provider="my-provider",
        attributes={"custom": "attr"},
    )
    handler.start_llm(invocation)
    invocation.output_messages = [...]
    handler.stop_llm(invocation)

Usage - Tool Call Executions:
    handler = get_telemetry_handler()

    # Use the context manager to manage the lifecycle of a tool call.
    tool = ToolCall(name="get_weather", arguments={"location": "Paris"}, id="call_123")
    with handler.tool_call(tool) as tc:
        # Execute tool logic
        tc.tool_result = {"temp": 20, "condition": "sunny"}

    # Or, manage the lifecycle manually
    tool = ToolCall(name="get_weather", arguments={"location": "Paris"})
    handler.start_tool_call(tool)
    tool.tool_result = {"temp": 20}
    handler.stop_tool_call(tool)
"""

from __future__ import annotations

import timeit
from contextlib import contextmanager
from typing import Iterator

from opentelemetry import context as otel_context
from opentelemetry._logs import (
    LoggerProvider,
    get_logger,
)
from opentelemetry.metrics import MeterProvider, get_meter
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import (
    Span,
    SpanKind,
    TracerProvider,
    get_tracer,
    set_span_in_context,
)
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util.genai.metrics import InvocationMetricsRecorder
from opentelemetry.util.genai.span_utils import (
    _apply_error_attributes,
    _apply_llm_finish_attributes,
    _apply_tool_call_attributes,
    _finish_tool_call_span,
    _get_tool_call_span_name,
    _maybe_emit_llm_event,
)
from opentelemetry.util.genai.types import Error, LLMInvocation, ToolCall
from opentelemetry.util.genai.version import __version__


class TelemetryHandler:
    """
    High-level handler managing GenAI invocation lifecycles and emitting
    them as spans, metrics, and events.
    """

    def __init__(
        self,
        tracer_provider: TracerProvider | None = None,
        meter_provider: MeterProvider | None = None,
        logger_provider: LoggerProvider | None = None,
    ):
        schema_url = Schemas.V1_37_0.value
        self._tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=schema_url,
        )
        self._metrics_recorder: InvocationMetricsRecorder | None = None
        meter = get_meter(
            __name__, meter_provider=meter_provider, schema_url=schema_url
        )
        self._metrics_recorder = InvocationMetricsRecorder(meter)
        self._logger = get_logger(
            __name__,
            __version__,
            logger_provider,
            schema_url=schema_url,
        )

    def _record_llm_metrics(
        self,
        invocation: LLMInvocation,
        span: Span | None = None,
        *,
        error_type: str | None = None,
    ) -> None:
        if self._metrics_recorder is None or span is None:
            return
        self._metrics_recorder.record(
            span,
            invocation,
            error_type=error_type,
        )

    def start_llm(
        self,
        invocation: LLMInvocation,
    ) -> LLMInvocation:
        """Start an LLM invocation and create a pending span entry."""
        # Create a span and attach it as current; keep the token to detach later
        span = self._tracer.start_span(
            name=f"{invocation.operation_name} {invocation.request_model}",
            kind=SpanKind.CLIENT,
        )
        # Record a monotonic start timestamp (seconds) for duration
        # calculation using timeit.default_timer.
        invocation.monotonic_start_s = timeit.default_timer()
        invocation.span = span
        invocation.context_token = otel_context.attach(
            set_span_in_context(span)
        )
        return invocation

    def stop_llm(self, invocation: LLMInvocation) -> LLMInvocation:  # pylint: disable=no-self-use
        """Finalize an LLM invocation successfully and end its span."""
        if invocation.context_token is None or invocation.span is None:
            # TODO: Provide feedback that this invocation was not started
            return invocation

        span = invocation.span
        _apply_llm_finish_attributes(span, invocation)
        self._record_llm_metrics(invocation, span)
        _maybe_emit_llm_event(self._logger, span, invocation)
        # Detach context and end span
        otel_context.detach(invocation.context_token)
        span.end()
        return invocation

    def fail_llm(  # pylint: disable=no-self-use
        self, invocation: LLMInvocation, error: Error
    ) -> LLMInvocation:
        """Fail an LLM invocation and end its span with error status."""
        if invocation.context_token is None or invocation.span is None:
            # TODO: Provide feedback that this invocation was not started
            return invocation

        span = invocation.span
        _apply_llm_finish_attributes(invocation.span, invocation)
        _apply_error_attributes(invocation.span, error)
        error_type = getattr(error.type, "__qualname__", None)
        self._record_llm_metrics(invocation, span, error_type=error_type)
        _maybe_emit_llm_event(self._logger, span, invocation, error)
        # Detach context and end span
        otel_context.detach(invocation.context_token)
        span.end()
        return invocation

    def start_tool_call(
        self,
        tool_call: ToolCall,
    ) -> ToolCall:
        """Start a tool call execution and create a span.

        Creates an execute_tool span per span.gen_ai.execute_tool.internal spec:
        - Span kind: INTERNAL
        - Span name: "execute_tool {tool_name}"
        - Required attribute: gen_ai.operation.name = "execute_tool"

        Args:
            tool_call: ToolCall instance to track

        Returns:
            The same ToolCall with span and context_token set
        """
        # Create span with INTERNAL kind per spec
        span = self._tracer.start_span(
            name=_get_tool_call_span_name(tool_call),
            kind=SpanKind.INTERNAL,
        )

        # Apply initial attributes (but not result yet)
        # capture_content=False for start, only structure attributes
        _apply_tool_call_attributes(span, tool_call, capture_content=False)

        # Record monotonic start time for duration calculation
        tool_call.monotonic_start_s = timeit.default_timer()

        # Attach to context
        tool_call.span = span
        tool_call.context_token = otel_context.attach(
            set_span_in_context(span)
        )

        return tool_call

    def stop_tool_call(self, tool_call: ToolCall) -> ToolCall:  # pylint: disable=no-self-use
        """Finalize a tool call execution successfully.

        Applies final attributes including tool_result, sets OK status, and ends span.

        Args:
            tool_call: ToolCall instance with span to finalize

        Returns:
            The same ToolCall
        """
        if tool_call.context_token is None or tool_call.span is None:
            # TODO: Provide feedback that this invocation was not started
            return tool_call

        span = tool_call.span

        # Finalize span with result (capture_content=True allows result if mode permits)
        _finish_tool_call_span(span, tool_call, capture_content=True)

        # Detach context and end span
        otel_context.detach(tool_call.context_token)
        span.end()

        return tool_call

    def fail_tool_call(  # pylint: disable=no-self-use
        self, tool_call: ToolCall, error: Error
    ) -> ToolCall:
        """Fail a tool call execution with error.

        Sets error attributes, ERROR status, and ends span.

        Args:
            tool_call: ToolCall instance with span to fail
            error: Error details

        Returns:
            The same ToolCall
        """
        if tool_call.context_token is None or tool_call.span is None:
            # TODO: Provide feedback that this invocation was not started
            return tool_call

        span = tool_call.span

        # Set error_type on tool_call so it's included in attributes
        tool_call.error_type = error.type.__qualname__

        # Finalize span with error
        _finish_tool_call_span(span, tool_call, capture_content=True)

        # Apply additional error status with message
        span.set_status(Status(StatusCode.ERROR, error.message))

        # Detach context and end span
        otel_context.detach(tool_call.context_token)
        span.end()

        return tool_call

    @contextmanager
    def tool_call(
        self, tool_call: ToolCall | None = None
    ) -> Iterator[ToolCall]:
        """Context manager for tool call invocations.

        Only set data attributes on the tool_call object, do not modify the span or context.

        Starts the span on entry. On normal exit, finalizes the tool call and ends the span.
        If an exception occurs inside the context, marks the span as error, ends it, and
        re-raises the original exception.

        Example:
            with handler.tool_call(ToolCall(name="get_weather", arguments={"location": "Paris"})) as tc:
                # Execute tool logic
                tc.tool_result = {"temp": 20, "condition": "sunny"}
        """
        if tool_call is None:
            tool_call = ToolCall(
                name="",
                arguments={},
                id=None,
            )
        self.start_tool_call(tool_call)
        try:
            yield tool_call
        except Exception as exc:
            self.fail_tool_call(
                tool_call, Error(message=str(exc), type=type(exc))
            )
            raise
        self.stop_tool_call(tool_call)

    @contextmanager
    def llm(
        self, invocation: LLMInvocation | None = None
    ) -> Iterator[LLMInvocation]:
        """Context manager for LLM invocations.

        Only set data attributes on the invocation object, do not modify the span or context.

        Starts the span on entry. On normal exit, finalizes the invocation and ends the span.
        If an exception occurs inside the context, marks the span as error, ends it, and
        re-raises the original exception.
        """
        if invocation is None:
            invocation = LLMInvocation(
                request_model="",
            )
        self.start_llm(invocation)
        try:
            yield invocation
        except Exception as exc:
            self.fail_llm(invocation, Error(message=str(exc), type=type(exc)))
            raise
        self.stop_llm(invocation)


def get_telemetry_handler(
    tracer_provider: TracerProvider | None = None,
    meter_provider: MeterProvider | None = None,
    logger_provider: LoggerProvider | None = None,
) -> TelemetryHandler:
    """
    Returns a singleton TelemetryHandler instance.
    """
    handler: TelemetryHandler | None = getattr(
        get_telemetry_handler, "_default_handler", None
    )
    if handler is None:
        handler = TelemetryHandler(
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
            logger_provider=logger_provider,
        )
        setattr(get_telemetry_handler, "_default_handler", handler)
    return handler
