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

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from uuid import UUID

from opentelemetry import trace
from opentelemetry._events import Event
from opentelemetry.context import Context, get_current
from opentelemetry.metrics import Meter
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

from .data import Error
from .instruments import Instruments
from .types import LLMInvocation


@dataclass
class _SpanState:
    span: Span
    span_context: Context
    start_time: float
    request_model: Optional[str] = None
    system: Optional[str] = None
    db_system: Optional[str] = None
    children: List[UUID] = field(default_factory=list)


def _get_property_value(obj, property_name) -> object:
    if isinstance(obj, dict):
        return obj.get(property_name, None)

    return getattr(obj, property_name, None)


def _message_to_event(message, system, framework) -> Optional[Event]:
    content = _get_property_value(message, "content")
    if content:
        message_type = _get_property_value(message, "type")
        message_type = "user" if message_type == "human" else message_type
        body = {"content": content}
        attributes = {
            # TODO: add below to opentelemetry.semconv._incubating.attributes.gen_ai_attributes
            "gen_ai.framework": framework,
            GenAI.GEN_AI_SYSTEM: system,
        }

        return Event(
            name=f"gen_ai.{message_type}.message",
            attributes=attributes,
            body=body or None,
        )


def _chat_generation_to_event(
    chat_generation, index, system, framework
) -> Optional[Event]:
    if chat_generation.content:
        attributes = {
            # TODO: add below to opentelemetry.semconv._incubating.attributes.gen_ai_attributes
            "gen_ai.framework": framework,
            GenAI.GEN_AI_SYSTEM: system,
        }

        message = {
            "content": chat_generation.content,
            "type": chat_generation.type,
        }
        body = {
            "index": index,
            "finish_reason": chat_generation.finish_reason or "error",
            "message": message,
        }

        return Event(
            name="gen_ai.choice",
            attributes=attributes,
            body=body or None,
        )


def _get_metric_attributes(
    request_model: Optional[str],
    response_model: Optional[str],
    operation_name: Optional[str],
    system: Optional[str],
    framework: Optional[str],
) -> Dict:
    attributes = {
        # TODO: add below to opentelemetry.semconv._incubating.attributes.gen_ai_attributes
        "gen_ai.framework": framework,
    }
    if system:
        attributes[GenAI.GEN_AI_SYSTEM] = system
    if operation_name:
        attributes[GenAI.GEN_AI_OPERATION_NAME] = operation_name
    if request_model:
        attributes[GenAI.GEN_AI_REQUEST_MODEL] = request_model
    if response_model:
        attributes[GenAI.GEN_AI_RESPONSE_MODEL] = response_model

    return attributes


class BaseExporter:
    """
    Abstract base for exporters mapping GenAI types -> OpenTelemetry.
    """

    def init(self, invocation: LLMInvocation):
        raise NotImplementedError

    def export(self, invocation: LLMInvocation):
        raise NotImplementedError

    def error(self, error: Error, invocation: LLMInvocation):
        raise NotImplementedError


class SpanMetricEventExporter(BaseExporter):
    """
    Emits spans, metrics and events for a full telemetry picture.
    """

    def __init__(
        self, event_logger, tracer: Tracer = None, meter: Meter = None
    ):
        self._tracer = tracer or trace.get_tracer(__name__)
        instruments = Instruments(meter)
        self._duration_histogram = instruments.operation_duration_histogram
        self._token_histogram = instruments.token_usage_histogram
        self._event_logger = event_logger

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
            if child_state and child_state.span._end_time is None:
                child_state.span.end()
        if state.span._end_time is None:
            state.span.end()

    def init(self, invocation: LLMInvocation):
        if (
            invocation.parent_run_id is not None
            and invocation.parent_run_id in self.spans
        ):
            self.spans[invocation.parent_run_id].children.append(
                invocation.run_id
            )

        for message in invocation.messages:
            system = invocation.attributes.get("system")
            self._event_logger.emit(
                _message_to_event(
                    message=message,
                    system=system,
                    framework=invocation.attributes.get("framework"),
                )
            )

    def export(self, invocation: LLMInvocation):
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
            span_state = _SpanState(
                span=span,
                span_context=get_current(),
                request_model=request_model,
                system=system,
                start_time=invocation.start_time,
            )
            self.spans[invocation.run_id] = span_state

            span.set_attribute(
                GenAI.GEN_AI_OPERATION_NAME,
                GenAI.GenAiOperationNameValues.CHAT.value,
            )

            if request_model:
                span.set_attribute(GenAI.GEN_AI_REQUEST_MODEL, request_model)

            # TODO: add below to opentelemetry.semconv._incubating.attributes.gen_ai_attributes
            framework = invocation.attributes.get("framework")
            if framework is not None:
                span.set_attribute("gen_ai.framework", framework)

            if system is not None:
                span.set_attribute(GenAI.GEN_AI_SYSTEM, system)

            finish_reasons = []
            for index, chat_generation in enumerate(
                invocation.chat_generations
            ):
                self._event_logger.emit(
                    _chat_generation_to_event(
                        chat_generation, index, system, framework
                    )
                )
                finish_reasons.append(chat_generation.finish_reason)

            if finish_reasons is not None and len(finish_reasons) > 0:
                span.set_attribute(
                    GenAI.GEN_AI_RESPONSE_FINISH_REASONS, finish_reasons
                )

            response_model = invocation.attributes.get("response_model_name")
            if response_model is not None:
                span.set_attribute(GenAI.GEN_AI_RESPONSE_MODEL, response_model)

            response_id = invocation.attributes.get("response_id")
            if response_id is not None:
                span.set_attribute(GenAI.GEN_AI_RESPONSE_ID, response_id)

            # usage
            prompt_tokens = invocation.attributes.get("input_tokens")
            if prompt_tokens is not None:
                span.set_attribute(
                    GenAI.GEN_AI_USAGE_INPUT_TOKENS, prompt_tokens
                )

            completion_tokens = invocation.attributes.get("output_tokens")
            if completion_tokens is not None:
                span.set_attribute(
                    GenAI.GEN_AI_USAGE_OUTPUT_TOKENS, completion_tokens
                )

            metric_attributes = _get_metric_attributes(
                request_model,
                response_model,
                GenAI.GenAiOperationNameValues.CHAT.value,
                system,
                framework,
            )

            # Record token usage metrics
            prompt_tokens_attributes = {
                GenAI.GEN_AI_TOKEN_TYPE: GenAI.GenAiTokenTypeValues.INPUT.value,
            }
            prompt_tokens_attributes.update(metric_attributes)
            self._token_histogram.record(
                prompt_tokens, attributes=prompt_tokens_attributes
            )

            completion_tokens_attributes = {
                GenAI.GEN_AI_TOKEN_TYPE: GenAI.GenAiTokenTypeValues.COMPLETION.value
            }
            completion_tokens_attributes.update(metric_attributes)
            self._token_histogram.record(
                completion_tokens, attributes=completion_tokens_attributes
            )

            # End the LLM span
            self._end_span(invocation.run_id)

            # Record overall duration metric
            elapsed = invocation.end_time - invocation.start_time
            self._duration_histogram.record(
                elapsed, attributes=metric_attributes
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
                span_context=get_current(),
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
            elapsed = invocation.end_time - invocation.start_time
            self._duration_histogram.record(
                elapsed, attributes=metric_attributes
            )


class SpanMetricExporter(BaseExporter):
    """
    Emits only spans and metrics (no events).
    """

    def __init__(self, tracer: Tracer = None, meter: Meter = None):
        self._tracer = tracer or trace.get_tracer(__name__)
        instruments = Instruments(meter)
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
            if child_state and child_state.span._end_time is None:
                child_state.span.end()
        if state.span._end_time is None:
            state.span.end()

    def init(self, invocation: LLMInvocation):
        if (
            invocation.parent_run_id is not None
            and invocation.parent_run_id in self.spans
        ):
            self.spans[invocation.parent_run_id].children.append(
                invocation.run_id
            )

    def export(self, invocation: LLMInvocation):
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
            span_state = _SpanState(
                span=span,
                span_context=get_current(),
                request_model=request_model,
                system=system,
                start_time=invocation.start_time,
            )
            self.spans[invocation.run_id] = span_state

            span.set_attribute(
                GenAI.GEN_AI_OPERATION_NAME,
                GenAI.GenAiOperationNameValues.CHAT.value,
            )

            if request_model is not None:
                span.set_attribute(GenAI.GEN_AI_REQUEST_MODEL, request_model)

            # TODO: add below to opentelemetry.semconv._incubating.attributes.gen_ai_attributes
            framework = invocation.attributes.get("framework")
            if framework is not None:
                span.set_attribute(
                    "gen_ai.framework", invocation.attributes.get("framework")
                )
            span.set_attribute(GenAI.GEN_AI_SYSTEM, system)

            finish_reasons = []
            for index, chat_generation in enumerate(
                invocation.chat_generations
            ):
                finish_reasons.append(chat_generation.finish_reason)
            if finish_reasons is not None and len(finish_reasons) > 0:
                span.set_attribute(
                    GenAI.GEN_AI_RESPONSE_FINISH_REASONS, finish_reasons
                )

            response_model = invocation.attributes.get("response_model_name")
            if response_model is not None:
                span.set_attribute(GenAI.GEN_AI_RESPONSE_MODEL, response_model)

            response_id = invocation.attributes.get("response_id")
            if response_id is not None:
                span.set_attribute(GenAI.GEN_AI_RESPONSE_ID, response_id)

            # usage
            prompt_tokens = invocation.attributes.get("input_tokens")
            if prompt_tokens is not None:
                span.set_attribute(
                    GenAI.GEN_AI_USAGE_INPUT_TOKENS, prompt_tokens
                )

            completion_tokens = invocation.attributes.get("output_tokens")
            if completion_tokens is not None:
                span.set_attribute(
                    GenAI.GEN_AI_USAGE_OUTPUT_TOKENS, completion_tokens
                )

            for index, message in enumerate(invocation.messages):
                content = message.content
                message_type = message.type
                span.set_attribute(f"gen_ai.prompt.{index}.content", content)
                span.set_attribute(f"gen_ai.prompt.{index}.role", message_type)

            for index, chat_generation in enumerate(
                invocation.chat_generations
            ):
                span.set_attribute(
                    f"gen_ai.completion.{index}.content",
                    chat_generation.content,
                )
                span.set_attribute(
                    f"gen_ai.completion.{index}.role", chat_generation.type
                )

            metric_attributes = _get_metric_attributes(
                request_model,
                response_model,
                GenAI.GenAiOperationNameValues.CHAT.value,
                system,
                framework,
            )

            # Record token usage metrics
            prompt_tokens_attributes = {
                GenAI.GEN_AI_TOKEN_TYPE: GenAI.GenAiTokenTypeValues.INPUT.value
            }
            prompt_tokens_attributes.update(metric_attributes)
            self._token_histogram.record(
                prompt_tokens, attributes=prompt_tokens_attributes
            )

            completion_tokens_attributes = {
                GenAI.GEN_AI_TOKEN_TYPE: GenAI.GenAiTokenTypeValues.COMPLETION.value
            }
            completion_tokens_attributes.update(metric_attributes)
            self._token_histogram.record(
                completion_tokens, attributes=completion_tokens_attributes
            )

            # End the LLM span
            self._end_span(invocation.run_id)

            # Record overall duration metric
            elapsed = invocation.end_time - invocation.start_time
            self._duration_histogram.record(
                elapsed, attributes=metric_attributes
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
                span_context=get_current(),
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
            elapsed = invocation.end_time - invocation.start_time
            self._duration_histogram.record(
                elapsed, attributes=metric_attributes
            )
