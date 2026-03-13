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
It supports starting, stopping, and failing LLM invocations.

Classes:
    - TelemetryHandler: Manages GenAI invocation lifecycles and emits telemetry.

Functions:
    - get_telemetry_handler: Returns a singleton `TelemetryHandler` instance.

Usage:
    handler = get_telemetry_handler()

    # Create an invocation object with your request data
    # The span and context_token attributes are set by the TelemetryHandler, and
    # managed by the TelemetryHandler during the lifecycle of the span.

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

    # Start the invocation (opens a span)
    handler.start(invocation)

    # Populate outputs and any additional attributes, then stop (closes the span)
    invocation.output_messages = [...]
    invocation.attributes.update({"more": "attrs"})
    handler.stop(invocation)

    # Or, in case of error
    handler.fail(invocation, Error(type="...", message="..."))
"""

from __future__ import annotations

import timeit
from contextlib import contextmanager
from typing import Iterator, TypeVar

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
from opentelemetry.util.genai.metrics import InvocationMetricsRecorder
from opentelemetry.util.genai.span_utils import (
    _apply_embedding_finish_attributes,
    _apply_error_attributes,
    _apply_llm_finish_attributes,
    _get_embedding_span_name,
    _get_llm_span_name,
    _maybe_emit_llm_event,
)
from opentelemetry.util.genai.types import (
    EmbeddingInvocation,
    Error,
    GenAIInvocation,
    LLMInvocation,
)
from opentelemetry.util.genai.version import __version__

_T = TypeVar("_T", bound=GenAIInvocation)


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

    @staticmethod
    def _record_embedding_metrics(
        invocation: EmbeddingInvocation,
        span: Span | None = None,
        *,
        error_type: str | None = None,
    ) -> None:
        # Metrics recorder currently supports LLMInvocation fields only.
        # Keep embedding metrics as a no-op until dedicated embedding
        # metric support is added.
        return

    def _start(self, invocation: _T) -> _T:
        """Start a GenAI invocation and create a pending span entry."""
        if isinstance(invocation, LLMInvocation):
            span_name = _get_llm_span_name(invocation)
        elif isinstance(invocation, EmbeddingInvocation):
            span_name = _get_embedding_span_name(invocation)
        else:
            span_name = ""
        span = self._tracer.start_span(
            name=span_name,
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

    def _stop(self, invocation: _T) -> _T:
        """Finalize a GenAI invocation successfully and end its span."""
        if invocation.context_token is None or invocation.span is None:
            # TODO: Provide feedback that this invocation was not started
            return invocation

        span = invocation.span
        try:
            if isinstance(invocation, LLMInvocation):
                _apply_llm_finish_attributes(span, invocation)
                self._record_llm_metrics(invocation, span)
                _maybe_emit_llm_event(self._logger, span, invocation)
            elif isinstance(invocation, EmbeddingInvocation):
                _apply_embedding_finish_attributes(span, invocation)
                self._record_embedding_metrics(invocation, span)
        finally:
            # Detach context and end span even if finishing fails
            otel_context.detach(invocation.context_token)
            span.end()
        return invocation

    def _fail(self, invocation: _T, error: Error) -> _T:
        """Fail a GenAI invocation and end its span with error status."""
        if invocation.context_token is None or invocation.span is None:
            # TODO: Provide feedback that this invocation was not started
            return invocation

        span = invocation.span
        error_type = error.type.__qualname__
        try:
            if isinstance(invocation, LLMInvocation):
                _apply_llm_finish_attributes(span, invocation)
                _apply_error_attributes(span, error, error_type)
                self._record_llm_metrics(
                    invocation, span, error_type=error_type
                )
                _maybe_emit_llm_event(
                    self._logger, span, invocation, error_type
                )
            elif isinstance(invocation, EmbeddingInvocation):
                _apply_embedding_finish_attributes(span, invocation)
                _apply_error_attributes(span, error, error_type)
                self._record_embedding_metrics(
                    invocation, span, error_type=error_type
                )
        finally:
            # Detach context and end span even if finishing fails
            otel_context.detach(invocation.context_token)
            span.end()
        return invocation

    def start(
        self,
        invocation: _T,
    ) -> _T:
        """Start a GenAI invocation and create a pending span entry."""
        return self._start(invocation)

    def stop(self, invocation: _T) -> _T:
        """Finalize a GenAI invocation successfully and end its span."""
        return self._stop(invocation)

    def fail(self, invocation: _T, error: Error) -> _T:
        """Fail a GenAI invocation and end its span with error status."""
        return self._fail(invocation, error)

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
        self.start(invocation)
        try:
            yield invocation
        except Exception as exc:
            self.fail(invocation, Error(message=str(exc), type=type(exc)))
            raise
        self.stop(invocation)

    @contextmanager
    def embedding(
        self, invocation: EmbeddingInvocation | None = None
    ) -> Iterator[EmbeddingInvocation]:
        """Context manager for Embedding invocations.

        Only set data attributes on the invocation object, do not modify the span or context.

        Starts the span on entry. On normal exit, finalizes the invocation and ends the span.
        If an exception occurs inside the context, marks the span as error, ends it, and
        re-raises the original exception.
        """
        if invocation is None:
            invocation = EmbeddingInvocation()
        self.start(invocation)
        try:
            yield invocation
        except Exception as exc:
            self.fail(invocation, Error(message=str(exc), type=type(exc)))
            raise
        self.stop(invocation)


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
