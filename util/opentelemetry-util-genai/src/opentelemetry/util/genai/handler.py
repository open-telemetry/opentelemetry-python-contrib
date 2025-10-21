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
    handler.start_llm(invocation)

    # Populate outputs and any additional attributes, then stop (closes the span)
    invocation.output_messages = [...]
    invocation.attributes.update({"more": "attrs"})
    handler.stop_llm(invocation)

    # Or, in case of error
    handler.fail_llm(invocation, Error(type="...", message="..."))
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from opentelemetry import context as otel_context
from opentelemetry.metrics import MeterProvider, get_meter
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
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
    _apply_error_attributes,
    _apply_finish_attributes,
)
from opentelemetry.util.genai.types import Error, LLMInvocation
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
    ):
        self._tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=Schemas.V1_36_0.value,
        )
        self._metrics_recorder: Optional[InvocationMetricsRecorder] = None
        try:
            meter = get_meter(__name__, meter_provider=meter_provider)
            self._metrics_recorder = InvocationMetricsRecorder(meter)
        except Exception:  # pragma: no cover - defensive fallback  # pylint: disable=broad-exception-caught
            self._metrics_recorder = None

    def _record_llm_metrics(
        self,
        invocation: LLMInvocation,
        span: Optional[Span],
        *,
        error_type: Optional[str] = None,
    ) -> None:
        if self._metrics_recorder is None or span is None:
            return
        try:
            self._metrics_recorder.record(
                span,
                invocation,
                error_type=error_type,
            )
        except Exception:  # pragma: no cover - defensive fallback  # pylint: disable=broad-exception-caught
            pass

    def start_llm(
        self,
        invocation: LLMInvocation,
    ) -> LLMInvocation:
        """Start an LLM invocation and create a pending span entry."""
        # Create a span and attach it as current; keep the token to detach later
        span = self._tracer.start_span(
            name=f"{GenAI.GenAiOperationNameValues.CHAT.value} {invocation.request_model}",
            kind=SpanKind.CLIENT,
        )
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
        _apply_finish_attributes(span, invocation)
        self._record_llm_metrics(invocation, span)
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
        _apply_error_attributes(span, error)
        error_type = getattr(error.type, "__qualname__", None)
        self._record_llm_metrics(invocation, span, error_type=error_type)
        # Detach context and end span
        otel_context.detach(invocation.context_token)
        span.end()
        return invocation

    @contextmanager
    def llm(
        self, invocation: Optional[LLMInvocation] = None
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
) -> TelemetryHandler:
    """
    Returns a singleton TelemetryHandler instance.
    """
    handler: Optional[TelemetryHandler] = getattr(
        get_telemetry_handler, "_default_handler", None
    )
    if handler is None:
        handler = TelemetryHandler(
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
        )
        setattr(get_telemetry_handler, "_default_handler", handler)
    return handler
