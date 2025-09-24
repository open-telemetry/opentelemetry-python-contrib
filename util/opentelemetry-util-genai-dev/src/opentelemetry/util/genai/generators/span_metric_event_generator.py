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

import os
from typing import Dict, Optional
from uuid import UUID

from opentelemetry import trace
from opentelemetry._logs import Logger, get_logger
from opentelemetry.metrics import Histogram, Meter, get_meter
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.trace import SpanKind, Tracer, use_span
from opentelemetry.trace.status import Status, StatusCode

from ..instruments import Instruments
from ..types import Error, LLMInvocation
from .base_generator import BaseTelemetryGenerator
from .utils import (
    _collect_finish_reasons,
    _emit_chat_generation_logs,
    _get_metric_attributes,
    _message_to_log_record,
    _record_duration,
    _record_token_metrics,
    _set_response_and_usage_attributes,
    _SpanState,
)

_ENV_VAR = "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"


class SpanMetricEventGenerator(BaseTelemetryGenerator):
    """
    Generates spans + metrics + structured log events (instead of attaching
    conversation content to span attributes).

    NOTE: ``capture_content`` controls whether the *event bodies* (input message
    parts and choice content) include textual content. Span attributes will NOT
    include serialized messages regardless of ``capture_content``.
    """

    def __init__(
        self,
        logger: Optional[Logger] = None,
        tracer: Optional[Tracer] = None,
        meter: Optional[Meter] = None,
        capture_content: bool = False,
    ):
        self._tracer: Tracer = tracer or trace.get_tracer(__name__)
        _meter: Meter = meter or get_meter(__name__)
        instruments = Instruments(_meter)
        self._duration_histogram: Histogram = (
            instruments.operation_duration_histogram
        )
        self._token_histogram: Histogram = instruments.token_usage_histogram
        self._logger: Logger = logger or get_logger(__name__)
        self._capture_content: bool = capture_content
        # Retain for potential hierarchical extensions
        self.spans: Dict[UUID, _SpanState] = {}

    # ---------------- Public lifecycle API ----------------
    def start(self, invocation: LLMInvocation):  # type: ignore[override]
        span_name = f"chat {invocation.request_model}"
        span = self._tracer.start_span(name=span_name, kind=SpanKind.CLIENT)
        invocation.span = span
        cm = use_span(span, end_on_exit=False)
        cm.__enter__()
        invocation.context_token = cm  # type: ignore[assignment]

        # Base semantic attributes.
        span.set_attribute(
            GenAI.GEN_AI_OPERATION_NAME,
            GenAI.GenAiOperationNameValues.CHAT.value,
        )
        span.set_attribute(
            GenAI.GEN_AI_REQUEST_MODEL, invocation.request_model
        )
        if invocation.provider:
            span.set_attribute("gen_ai.provider.name", invocation.provider)

        for k, v in invocation.attributes.items():
            span.set_attribute(k, v)

        # Emit input message events/logs (structured) – gated by environment var
        if invocation.input_messages and self._logger and os.getenv(_ENV_VAR):
            for msg in invocation.input_messages:
                log_record = _message_to_log_record(
                    msg,
                    provider_name=invocation.provider,
                    framework=invocation.attributes.get("framework"),
                    capture_content=self._capture_content,
                )
                if log_record:
                    try:  # pragma: no cover - defensive
                        self._logger.emit(log_record)
                    except Exception:
                        pass

    def finish(self, invocation: LLMInvocation):  # type: ignore[override]
        span = invocation.span
        if span is None:
            # Defensive fallback if start wasn't called
            span = self._tracer.start_span(
                name=f"chat {invocation.request_model}", kind=SpanKind.CLIENT
            )
            invocation.span = span

        # Use input_messages and output_messages directly

        # Update any new attributes added after start
        for k, v in invocation.attributes.items():
            span.set_attribute(k, v)

        # Finish reasons & response / usage attrs
        finish_reasons = _collect_finish_reasons(invocation.output_messages)
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

        # Emit per-choice generation events (gated by environment var)
        if invocation.output_messages and self._logger and os.getenv(_ENV_VAR):
            try:
                _emit_chat_generation_logs(
                    self._logger,
                    invocation.output_messages,
                    provider_name=invocation.provider,
                    framework=invocation.attributes.get("framework"),
                    capture_content=self._capture_content,
                )
            except Exception:
                pass

        # Record metrics (duration + tokens)
        metric_attrs = _get_metric_attributes(
            invocation.request_model,
            invocation.response_model_name,
            GenAI.GenAiOperationNameValues.CHAT.value,
            invocation.provider,
            invocation.attributes.get("framework"),
        )
        _record_token_metrics(
            self._token_histogram,
            invocation.input_tokens,
            invocation.output_tokens,
            metric_attrs,
        )
        _record_duration(self._duration_histogram, invocation, metric_attrs)

        # Close span context & end
        if invocation.context_token is not None:
            cm = invocation.context_token
            if hasattr(cm, "__exit__"):
                try:  # pragma: no cover
                    cm.__exit__(None, None, None)  # type: ignore[misc]
                except Exception:  # pragma: no cover
                    pass
        span.end()

    def error(self, error: Error, invocation: LLMInvocation):  # type: ignore[override]
        span = invocation.span
        if span is None:
            span = self._tracer.start_span(
                name=f"chat {invocation.request_model}", kind=SpanKind.CLIENT
            )
            invocation.span = span
        span.set_status(Status(StatusCode.ERROR, error.message))
        if span.is_recording():
            span.set_attribute(
                ErrorAttributes.ERROR_TYPE, error.type.__qualname__
            )
        # propagate latest attributes even on error
        for k, v in invocation.attributes.items():
            span.set_attribute(k, v)
        # Duration metric if possible
        if invocation.end_time is not None:
            metric_attrs = _get_metric_attributes(
                invocation.request_model,
                invocation.response_model_name,
                GenAI.GenAiOperationNameValues.CHAT.value,
                invocation.provider,
                invocation.attributes.get("framework"),
            )
            _record_duration(
                self._duration_histogram, invocation, metric_attrs
            )
        if invocation.context_token is not None:
            cm = invocation.context_token
            if hasattr(cm, "__exit__"):
                try:  # pragma: no cover
                    cm.__exit__(None, None, None)  # type: ignore[misc]
                except Exception:  # pragma: no cover
                    pass
        span.end()
