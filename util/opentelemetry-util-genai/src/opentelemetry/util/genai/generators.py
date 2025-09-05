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
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

from opentelemetry import trace
from opentelemetry._logs import Logger
from opentelemetry.context import Context, get_current
from opentelemetry.metrics import Histogram, Meter, get_meter
from opentelemetry.sdk._logs._internal import LogRecord as SDKLogRecord
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
from opentelemetry.util.types import AttributeValue

from .data import ChatGeneration, Error
from .instruments import Instruments
from .types import InputMessage, LLMInvocation


@dataclass
class _SpanState:
    span: Span
    context: Context
    start_time: float
    request_model: Optional[str] = None
    system: Optional[str] = None
    children: List[UUID] = field(default_factory=list)


def _message_to_log_record(
    message: InputMessage,
    provider_name: Optional[str],
    framework: Optional[str],
    capture_content: bool,
) -> Optional[SDKLogRecord]:
    """Build an SDK LogRecord for an input message.

    Returns an SDK-level LogRecord configured with:
    - body: structured payload for the message (when capture_content is True)
    - attributes: includes semconv fields and attributes["event.name"]
    - event_name: mirrors the event name for SDK consumers
    """

    body = {}
    if capture_content:
        body = asdict(message)

    attributes: Dict[str, Any] = {
        # TODO: add below to opentelemetry.semconv._incubating.attributes.gen_ai_attributes
        "gen_ai.framework": framework,
        # TODO: Convert below to constant once opentelemetry.semconv._incubating.attributes.gen_ai_attributes is available
        "gen_ai.provider.name": provider_name,
        # Prefer structured logs; include event name as an attribute.
        "event.name": "gen_ai.client.inference.operation.details",
    }

    if capture_content:  # TODO: Use utils env check
        attributes["gen_ai.input.messages"] = asdict(message)

    return SDKLogRecord(
        body=body or None,
        attributes=attributes,
        event_name="gen_ai.client.inference.operation.details",
    )


def _chat_generation_to_log_record(
    chat_generation: ChatGeneration,
    index: int,
    provider_name: Optional[str],
    framework: Optional[str],
    capture_content: bool,
) -> Optional[SDKLogRecord]:
    """Build an SDK LogRecord for a chat generation (choice) item.

    Sets both the SDK event_name and attributes["event.name"] to "gen_ai.choice",
    and includes structured fields in body (index, finish_reason, message).
    """
    if not chat_generation:
        return None
    attributes = {
        # TODO: add below to opentelemetry.semconv._incubating.attributes.gen_ai_attributes
        "gen_ai.framework": framework,
        # TODO: Convert below to constant once opentelemetry.semconv._incubating.attributes.gen_ai_attributes is available
        "gen_ai.provider.name": provider_name,
        # Prefer structured logs; include event name as an attribute.
        "event.name": "gen_ai.choice",
    }

    message = {
        "type": chat_generation.type,
    }
    if capture_content and chat_generation.content:
        message["content"] = chat_generation.content

    body = {
        "index": index,
        "finish_reason": chat_generation.finish_reason or "error",
        "message": message,
    }

    return SDKLogRecord(
        body=body or None,
        attributes=attributes,
        event_name="gen_ai.choice",
    )


def _get_metric_attributes(
    request_model: Optional[str],
    response_model: Optional[str],
    operation_name: Optional[str],
    system: Optional[str],
    framework: Optional[str],
) -> Dict[str, AttributeValue]:
    attributes: Dict[str, AttributeValue] = {}
    # TODO: add below to opentelemetry.semconv._incubating.attributes.gen_ai_attributes
    if framework is not None:
        attributes["gen_ai.framework"] = framework
    if system:
        attributes["gen_ai.provider.name"] = system
    if operation_name:
        attributes[GenAI.GEN_AI_OPERATION_NAME] = operation_name
    if request_model:
        attributes[GenAI.GEN_AI_REQUEST_MODEL] = request_model
    if response_model:
        attributes[GenAI.GEN_AI_RESPONSE_MODEL] = response_model

    return attributes


# ----------------------
# Helper utilities (module-private) to reduce complexity in emitters
# ----------------------


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
        # Deprecated: use "gen_ai.provider.name"
        span.set_attribute(GenAI.GEN_AI_SYSTEM, system)
        span.set_attribute("gen_ai.provider.name", system)


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


def _emit_chat_generation_logs(
    logger: Optional[Logger],
    generations: List[ChatGeneration],
    provider_name: Optional[str],
    framework: Optional[str],
    capture_content: bool,
) -> List[str]:
    finish_reasons: List[str] = []
    for index, chat_generation in enumerate(generations):
        log = _chat_generation_to_log_record(
            chat_generation,
            index,
            provider_name,
            framework,
            capture_content=capture_content,
        )
        if log and logger:
            logger.emit(log)
        if chat_generation.finish_reason is not None:
            finish_reasons.append(chat_generation.finish_reason)
    return finish_reasons


def _collect_finish_reasons(generations: List[ChatGeneration]) -> List[str]:
    finish_reasons: List[str] = []
    for gen in generations:
        if gen.finish_reason is not None:
            finish_reasons.append(gen.finish_reason)
    return finish_reasons


def _maybe_set_input_messages(
    span: Span, messages: List[InputMessage], capture: bool
) -> None:
    if not capture:
        return
    message_parts: List[Dict[str, Any]] = [
        asdict(message) for message in messages
    ]
    if message_parts:
        span.set_attribute("gen_ai.input.messages", json.dumps(message_parts))


def _set_chat_generation_attrs(
    span: Span, generations: List[ChatGeneration]
) -> None:
    for index, chat_generation in enumerate(generations):
        # Upcoming semconv fields
        span.set_attribute(
            f"gen_ai.completion.{index}.content", chat_generation.content
        )
        span.set_attribute(
            f"gen_ai.completion.{index}.role", chat_generation.type
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


class SpanMetricEventGenerator(BaseTelemetryGenerator):
    """
    Generates spans, metrics and events for a full telemetry picture.
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
        self._duration_histogram = instruments.operation_duration_histogram
        self._token_histogram = instruments.token_usage_histogram
        self._logger: Optional[Logger] = logger
        self._capture_content = capture_content

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

        for message in invocation.messages:
            system = invocation.attributes.get("system")
            log = _message_to_log_record(
                message=message,
                provider_name=system,
                framework=invocation.attributes.get("framework"),
                capture_content=self._capture_content,
            )
            if log and self._logger:
                # _message_to_log_record returns an SDKLogRecord
                self._logger.emit(log)

    def finish(self, invocation: LLMInvocation):
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

            framework = invocation.attributes.get("framework")
            _set_initial_span_attributes(
                span, request_model, system, framework
            )

            finish_reasons = _emit_chat_generation_logs(
                self._logger,
                invocation.chat_generations,
                system,
                framework,
                self._capture_content,
            )
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
            _record_token_metrics(
                self._token_histogram,
                prompt_tokens,
                completion_tokens,
                metric_attributes,
            )

            self._end_span(invocation.run_id)
            _record_duration(
                self._duration_histogram, invocation, metric_attributes
            )

    def error(self, error: Error, invocation: LLMInvocation):
        system = invocation.attributes.get("system")
        span = self._start_span(
            name=f"{system}.chat",
            kind=SpanKind.CLIENT,
            parent_run_id=invocation.parent_run_id,
        )

        with use_span(
            span,
            end_on_exit=False,
        ) as span:
            request_model = invocation.attributes.get("request_model")
            system = invocation.attributes.get("system")

            span_state = _SpanState(
                span=span,
                context=get_current(),
                request_model=request_model,
                system=system,
                start_time=invocation.start_time,
            )
            self.spans[invocation.run_id] = span_state

            span.set_status(Status(StatusCode.ERROR, error.message))
            if span.is_recording():
                span.set_attribute(
                    ErrorAttributes.ERROR_TYPE, error.type.__qualname__
                )

            self._end_span(invocation.run_id)

            response_model = invocation.attributes.get("response_model_name")
            framework = invocation.attributes.get("framework")

            metric_attributes = _get_metric_attributes(
                request_model,
                response_model,
                GenAI.GenAiOperationNameValues.CHAT.value,
                system,
                framework,
            )

            # Record overall duration metric
            if invocation.end_time is not None:
                elapsed: float = invocation.end_time - invocation.start_time
                self._duration_histogram.record(
                    elapsed, attributes=metric_attributes
                )


class SpanMetricGenerator(BaseTelemetryGenerator):
    """
    Generates only spans and metrics (no events).
    """

    def __init__(
        self,
        tracer: Optional[Tracer] = None,
        meter: Optional[Meter] = None,
        capture_content: bool = False,
    ):
        self._tracer: Tracer = tracer or trace.get_tracer(__name__)
        _meter: Meter = meter or get_meter(__name__)
        instruments = Instruments(_meter)
        self._duration_histogram = instruments.operation_duration_histogram
        self._token_histogram = instruments.token_usage_histogram
        self._capture_content = capture_content

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

    def finish(self, invocation: LLMInvocation):
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

            framework = invocation.attributes.get("framework")
            _set_initial_span_attributes(
                span, request_model, system, framework
            )

            finish_reasons = _collect_finish_reasons(
                invocation.chat_generations
            )
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

            _maybe_set_input_messages(
                span, invocation.messages, self._capture_content
            )
            _set_chat_generation_attrs(span, invocation.chat_generations)

            metric_attributes = _get_metric_attributes(
                request_model,
                response_model,
                GenAI.GenAiOperationNameValues.CHAT.value,
                system,
                framework,
            )
            _record_token_metrics(
                self._token_histogram,
                prompt_tokens,
                completion_tokens,
                metric_attributes,
            )

            self._end_span(invocation.run_id)
            _record_duration(
                self._duration_histogram, invocation, metric_attributes
            )

    def error(self, error: Error, invocation: LLMInvocation):
        system = invocation.attributes.get("system")
        span = self._start_span(
            name=f"{system}.chat",
            kind=SpanKind.CLIENT,
            parent_run_id=invocation.parent_run_id,
        )

        with use_span(
            span,
            end_on_exit=False,
        ) as span:
            request_model = invocation.attributes.get("request_model")
            system = invocation.attributes.get("system")

            span_state = _SpanState(
                span=span,
                context=get_current(),
                request_model=request_model,
                system=system,
                start_time=invocation.start_time,
            )
            self.spans[invocation.run_id] = span_state

            span.set_status(Status(StatusCode.ERROR, error.message))
            if span.is_recording():
                span.set_attribute(
                    ErrorAttributes.ERROR_TYPE, error.type.__qualname__
                )

            self._end_span(invocation.run_id)

            response_model = invocation.attributes.get("response_model_name")
            framework = invocation.attributes.get("framework")

            metric_attributes = _get_metric_attributes(
                request_model,
                response_model,
                GenAI.GenAiOperationNameValues.CHAT.value,
                system,
                framework,
            )

            # Record overall duration metric
            if invocation.end_time is not None:
                elapsed: float = invocation.end_time - invocation.start_time
                self._duration_histogram.record(
                    elapsed, attributes=metric_attributes
                )
