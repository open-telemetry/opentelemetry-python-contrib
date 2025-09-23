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
"""Span + Metrics generator.

Refactored to subclass BaseSpanGenerator to avoid duplication of span lifecycle
logic. Adds duration & token usage metrics plus richer response attributes while
still optionally capturing input/output messages on the span (no events emitted).
"""

from __future__ import annotations

from typing import Optional

from opentelemetry import trace
from opentelemetry.metrics import Histogram, Meter, get_meter
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.trace import Tracer
from opentelemetry.trace.status import Status, StatusCode

from ..instruments import Instruments
from ..types import Error, LLMInvocation
from .base_span_generator import BaseSpanGenerator
from .utils import (
    _collect_finish_reasons,
    _get_metric_attributes,
    _maybe_set_input_messages,
    _record_duration,
    _record_token_metrics,
    _set_chat_generation_attrs,
    _set_response_and_usage_attributes,
)


class SpanMetricGenerator(BaseSpanGenerator):
    """Spans + metrics (no events)."""

    def __init__(
        self,
        tracer: Optional[Tracer] = None,
        meter: Optional[Meter] = None,
        capture_content: bool = False,
    ):
        super().__init__(
            tracer=tracer or trace.get_tracer(__name__),
            capture_content=capture_content,
        )
        _meter: Meter = meter or get_meter(__name__)
        instruments = Instruments(_meter)
        self._duration_histogram: Histogram = (
            instruments.operation_duration_histogram
        )
        self._token_histogram: Histogram = instruments.token_usage_histogram

    # Hooks -----------------------------------------------------------------
    def _on_before_end(
        self, invocation: LLMInvocation, error: Optional[Error]
    ):  # type: ignore[override]
        span = invocation.span
        if span is None:
            return
        # Normalize unified lists for helper expectations.
        if not invocation.messages:
            invocation.messages = invocation.input_messages
        if not invocation.chat_generations:
            invocation.chat_generations = invocation.output_messages
        if error is None:
            # Finish reasons & usage/response attrs only on success path
            finish_reasons = _collect_finish_reasons(
                invocation.chat_generations
            )
            if finish_reasons:
                span.set_attribute(
                    GenAI.GEN_AI_RESPONSE_FINISH_REASONS, finish_reasons
                )
            _set_response_and_usage_attributes(
                span,
                invocation.response_model_name,
                invocation.response_id,
                invocation.input_tokens,
                invocation.output_tokens,
            )
            # Input / output messages captured by BaseSpanGenerator already for content; ensure input if capture enabled
            _maybe_set_input_messages(
                span, invocation.messages, self._capture_content
            )
            _set_chat_generation_attrs(span, invocation.chat_generations)
        else:
            # Error status already set by BaseSpanGenerator.error; no extra generation attrs
            span.set_attribute(
                ErrorAttributes.ERROR_TYPE, error.type.__qualname__
            )
        # Metrics (record tokens only if available & not error)
        metric_attrs = _get_metric_attributes(
            invocation.request_model,
            invocation.response_model_name,
            GenAI.GenAiOperationNameValues.CHAT.value,
            invocation.provider,
            invocation.attributes.get("framework"),
        )
        if error is None:
            _record_token_metrics(
                self._token_histogram,
                invocation.input_tokens,
                invocation.output_tokens,
                metric_attrs,
            )
        _record_duration(self._duration_histogram, invocation, metric_attrs)

    # Override error to ensure span status + hook logic executes once
    def error(self, error: Error, invocation: LLMInvocation) -> None:  # type: ignore[override]
        span = invocation.span
        if span is None:
            # Start a span if start() not called
            self.start(invocation)
            span = invocation.span
        if span is None:
            return
        span.set_status(Status(StatusCode.ERROR, error.message))
        # Call before_end hook with error
        self._on_before_end(invocation, error)
        # End span after context exit
        if invocation.context_token is not None:
            try:
                invocation.context_token.__exit__(None, None, None)
            except Exception:  # pragma: no cover
                pass
        span.end()
