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
Emitters for GenAI telemetry instrumentation.

This module defines classes and utilities for mapping GenAI (Generative AI) invocations
to OpenTelemetry spans, metrics, and events. Emitters manage the lifecycle of telemetry
data for LLM (Large Language Model) operations, including success and error reporting.

Classes:
    BaseEmitter: Abstract base class for GenAI telemetry emitters.
    SpanMetricEventEmitter: Emits spans, metrics, and events for full telemetry.
    SpanMetricEmitter: Emits only spans and metrics (no events).

Functions:
    _get_property_value: Utility to extract property values from objects or dicts.
    _message_to_log_record: Converts a GenAI message to an OpenTelemetry LogRecord.
    _chat_generation_to_log_record: Converts a chat generation to a LogRecord.
    _get_metric_attributes: Builds metric attributes for telemetry reporting.

"""

import json
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from opentelemetry import trace
from opentelemetry.context import Context, get_current
from opentelemetry.instrumentation._semconv import (
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _StabilityMode,
)
from opentelemetry.metrics import Histogram, Meter, get_meter
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.trace import (
    Span,
    SpanKind,
    Tracer,
    set_span_in_context,
    use_span,
)
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util.genai.utils import (
    ContentCapturingMode,
    get_content_capturing_mode,
)
from opentelemetry.util.types import AttributeValue

from .instruments import Instruments
from .types import Error, InputMessage, LLMInvocation, OutputMessage, Text


@dataclass
class _SpanState:
    span: Span
    context: Context
    start_time: float
    request_model: Optional[str] = None
    system: Optional[str] = None
    children: List[UUID] = field(default_factory=list)


def _get_metric_attributes(
    request_model: Optional[str],
    response_model: Optional[str],
    operation_name: Optional[str],
    system: Optional[str],
    framework: Optional[str],
) -> Dict[str, AttributeValue]:
    attributes: Dict[str, AttributeValue] = {}
    if framework is not None:
        attributes["gen_ai.framework"] = framework
    if system:
        attributes[GenAI.GEN_AI_PROVIDER_NAME] = system
    if operation_name:
        attributes[GenAI.GEN_AI_OPERATION_NAME] = operation_name
    if request_model:
        attributes[GenAI.GEN_AI_REQUEST_MODEL] = request_model
    if response_model:
        attributes[GenAI.GEN_AI_RESPONSE_MODEL] = response_model

    return attributes


def _set_initial_span_attributes(
    span: Span,
    request_model: Optional[str],
    system: Optional[str],
    framework: Optional[str],
) -> None:
    span.set_attribute(
        GenAI.GEN_AI_OPERATION_NAME, GenAI.GenAiOperationNameValues.CHAT.value
    )
    if request_model:
        span.set_attribute(GenAI.GEN_AI_REQUEST_MODEL, request_model)
    if framework is not None:
        span.set_attribute("gen_ai.framework", framework)
    if system is not None:
        # TODO: clean system name to match GenAiProviderNameValues?
        span.set_attribute(GenAI.GEN_AI_PROVIDER_NAME, system)


def _set_response_and_usage_attributes(
    span: Span,
    response_model: Optional[str],
    response_id: Optional[str],
    prompt_tokens: Optional[AttributeValue],
    completion_tokens: Optional[AttributeValue],
) -> None:
    if response_model is not None:
        span.set_attribute(GenAI.GEN_AI_RESPONSE_MODEL, response_model)
    if response_id is not None:
        span.set_attribute(GenAI.GEN_AI_RESPONSE_ID, response_id)
    if isinstance(prompt_tokens, (int, float)):
        span.set_attribute(GenAI.GEN_AI_USAGE_INPUT_TOKENS, prompt_tokens)
    if isinstance(completion_tokens, (int, float)):
        span.set_attribute(GenAI.GEN_AI_USAGE_OUTPUT_TOKENS, completion_tokens)


def _collect_finish_reasons(generations: List[OutputMessage]) -> List[str]:
    finish_reasons: List[str] = []
    for gen in generations:
        finish_reasons.append(gen.finish_reason)
    return finish_reasons


def _maybe_set_span_input_messages(
    span: Span, messages: List[InputMessage]
) -> None:
    # if GEN_AI stability mode is DEFAULT, do not capture message content
    if (
        _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
            _OpenTelemetryStabilitySignalType.GEN_AI,
        )
        == _StabilityMode.DEFAULT
    ):
        return
    if get_content_capturing_mode() not in (
        ContentCapturingMode.SPAN_ONLY,
        ContentCapturingMode.SPAN_AND_EVENT,
    ):
        return
    message_parts: List[Dict[str, Any]] = [
        asdict(message) for message in messages
    ]
    if message_parts:
        span.set_attribute("gen_ai.input.messages", json.dumps(message_parts))


def _set_chat_generation_attrs(
    span: Span, generations: List[OutputMessage]
) -> None:
    for index, chat_generation in enumerate(generations):
        # TODO: use dataclass to dict - Handle multiple responses
        content: Optional[str] = None
        for part in chat_generation.parts:
            if isinstance(part, Text):
                content = part.content
                break
        # Upcoming semconv fields
        span.set_attribute(f"gen_ai.completion.{index}.content", content or "")
        span.set_attribute(
            f"gen_ai.completion.{index}.role", chat_generation.role
        )


def _record_token_metrics(
    token_histogram: Histogram,
    prompt_tokens: Optional[AttributeValue],
    completion_tokens: Optional[AttributeValue],
    metric_attributes: Dict[str, AttributeValue],
) -> None:
    prompt_attrs: Dict[str, AttributeValue] = {
        GenAI.GEN_AI_TOKEN_TYPE: GenAI.GenAiTokenTypeValues.INPUT.value
    }
    prompt_attrs.update(metric_attributes)
    if isinstance(prompt_tokens, (int, float)):
        token_histogram.record(prompt_tokens, attributes=prompt_attrs)

    completion_attrs: Dict[str, AttributeValue] = {
        GenAI.GEN_AI_TOKEN_TYPE: GenAI.GenAiTokenTypeValues.COMPLETION.value
    }
    completion_attrs.update(metric_attributes)
    if isinstance(completion_tokens, (int, float)):
        token_histogram.record(completion_tokens, attributes=completion_attrs)


def _record_duration(
    duration_histogram: Histogram,
    invocation: LLMInvocation,
    metric_attributes: Dict[str, AttributeValue],
) -> None:
    if invocation.end_time is not None:
        elapsed: float = invocation.end_time - invocation.start_time
        duration_histogram.record(elapsed, attributes=metric_attributes)


class BaseTelemetryGenerator:
    """
    Abstract base for emitters mapping GenAI types -> OpenTelemetry.
    """

    def start(self, invocation: LLMInvocation) -> None:
        raise NotImplementedError

    def finish(self, invocation: LLMInvocation) -> None:
        raise NotImplementedError

    def error(self, error: Error, invocation: LLMInvocation) -> None:
        raise NotImplementedError


class SpanMetricGenerator(BaseTelemetryGenerator):
    """
    Generates only spans and metrics (no events).
    """

    def __init__(
        self,
        tracer: Optional[Tracer] = None,
        meter: Optional[Meter] = None,
    ):
        self._tracer: Tracer = tracer or trace.get_tracer(__name__)
        _meter: Meter = meter or get_meter(__name__)
        instruments = Instruments(_meter)
        self._duration_histogram = instruments.operation_duration_histogram
        self._token_histogram = instruments.token_usage_histogram

        # Map from run_id -> _SpanState, to keep track of spans and parent/child relationships
        self.spans: Dict[UUID, _SpanState] = {}

    def _start_span(
        self,
        name: str,
        kind: SpanKind,
        parent_run_id: Optional[UUID] = None,
    ) -> Span:
        if parent_run_id is not None and parent_run_id in self.spans:
            parent_span = self.spans[parent_run_id].span
            ctx = set_span_in_context(parent_span)
            span = self._tracer.start_span(name=name, kind=kind, context=ctx)
        else:
            # top-level or missing parent
            span = self._tracer.start_span(name=name, kind=kind)

        return span

    def _end_span(self, run_id: UUID):
        state = self.spans[run_id]
        for child_id in state.children:
            child_state = self.spans.get(child_id)
            if child_state:
                child_state.span.end()
        state.span.end()

    def start(self, invocation: LLMInvocation):
        if (
            invocation.parent_run_id is not None
            and invocation.parent_run_id in self.spans
        ):
            self.spans[invocation.parent_run_id].children.append(
                invocation.run_id
            )

    @contextmanager
    def _span_for_invocation(self, invocation: LLMInvocation):
        """Create/register a span for the invocation and yield it.

        The span is not ended automatically on exiting the context; callers
        must finalize via _finalize_invocation.
        """
        system = invocation.attributes.get("system")
        span = self._start_span(
            name=f"{system}.chat",
            kind=SpanKind.CLIENT,
            parent_run_id=invocation.parent_run_id,
        )
        with use_span(span, end_on_exit=False) as span:
            request_model = invocation.attributes.get("request_model")
            span_state = _SpanState(
                span=span,
                context=get_current(),
                request_model=request_model,
                system=system,
                start_time=invocation.start_time,
            )
            self.spans[invocation.run_id] = span_state
            yield span

    @staticmethod
    def _apply_common_span_attributes(
        span: Span, invocation: LLMInvocation
    ) -> Tuple[
        Dict[str, AttributeValue],
        Optional[AttributeValue],
        Optional[AttributeValue],
    ]:
        """Apply attributes shared by finish() and error() and compute metrics.

        Returns (metric_attributes, prompt_tokens, completion_tokens).
        """
        request_model = invocation.attributes.get("request_model")
        system = invocation.attributes.get("system")
        framework = invocation.attributes.get("framework")

        _set_initial_span_attributes(span, request_model, system, framework)

        finish_reasons = _collect_finish_reasons(invocation.chat_generations)
        if finish_reasons:
            span.set_attribute(
                GenAI.GEN_AI_RESPONSE_FINISH_REASONS, finish_reasons
            )

        response_model = invocation.attributes.get("response_model_name")
        response_id = invocation.attributes.get("response_id")
        prompt_tokens = invocation.attributes.get("input_tokens")
        completion_tokens = invocation.attributes.get("output_tokens")
        _set_response_and_usage_attributes(
            span,
            response_model,
            response_id,
            prompt_tokens,
            completion_tokens,
        )

        metric_attributes = _get_metric_attributes(
            request_model,
            response_model,
            GenAI.GenAiOperationNameValues.CHAT.value,
            system,
            framework,
        )
        return metric_attributes, prompt_tokens, completion_tokens

    def _finalize_invocation(
        self,
        invocation: LLMInvocation,
        metric_attributes: Dict[str, AttributeValue],
    ) -> None:
        """End span(s) and record duration for the invocation."""
        self._end_span(invocation.run_id)
        _record_duration(
            self._duration_histogram, invocation, metric_attributes
        )

    def finish(self, invocation: LLMInvocation):
        with self._span_for_invocation(invocation) as span:
            metric_attributes, prompt_tokens, completion_tokens = (
                self._apply_common_span_attributes(span, invocation)
            )
            _maybe_set_span_input_messages(span, invocation.messages)
            _set_chat_generation_attrs(span, invocation.chat_generations)
            _record_token_metrics(
                self._token_histogram,
                prompt_tokens,
                completion_tokens,
                metric_attributes,
            )
        self._finalize_invocation(invocation, metric_attributes)

    def error(self, error: Error, invocation: LLMInvocation):
        with self._span_for_invocation(invocation) as span:
            metric_attributes, _, _ = self._apply_common_span_attributes(
                span, invocation
            )
            span.set_status(Status(StatusCode.ERROR, error.message))
            if span.is_recording():
                span.set_attribute(
                    ErrorAttributes.ERROR_TYPE, error.type.__qualname__
                )
        self._finalize_invocation(invocation, metric_attributes)
