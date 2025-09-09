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
Span generation utilities for GenAI telemetry.

This module maps GenAI (Generative AI) invocations to OpenTelemetry spans and
applies GenAI semantic convention attributes.

Classes:
    - BaseTelemetryGenerator: Abstract base for GenAI telemetry emitters.
    - SpanGenerator: Concrete implementation that creates and finalizes spans
      for LLM operations (e.g., chat) and records input/output messages when
      experimental mode and content capture settings allow.

Usage:
    See `opentelemetry/util/genai/handler.py` for `TelemetryHandler`, which
    constructs `LLMInvocation` objects and delegates to `SpanGenerator.start`,
    `SpanGenerator.finish`, and `SpanGenerator.error` to produce spans that
    follow the GenAI semantic conventions.
"""

import json
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from opentelemetry import trace
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
    is_experimental_mode,
)
from opentelemetry.util.types import AttributeValue

from .types import Error, InputMessage, LLMInvocation, OutputMessage


@dataclass
class _SpanState:
    span: Span
    children: List[UUID] = field(default_factory=list)


def _get_genai_attributes(
    request_model: Optional[str],
    response_model: Optional[str],
    operation_name: Optional[str],
    system: Optional[str],
) -> Dict[str, AttributeValue]:
    attributes: Dict[str, AttributeValue] = {}
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
) -> None:
    span.set_attribute(
        GenAI.GEN_AI_OPERATION_NAME, GenAI.GenAiOperationNameValues.CHAT.value
    )
    if request_model:
        span.set_attribute(GenAI.GEN_AI_REQUEST_MODEL, request_model)
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
    if not is_experimental_mode() or get_content_capturing_mode() not in (
        ContentCapturingMode.SPAN_ONLY,
        ContentCapturingMode.SPAN_AND_EVENT,
    ):
        return
    message_parts: List[Dict[str, Any]] = [
        asdict(message) for message in messages
    ]
    if message_parts:
        span.set_attribute("gen_ai.input.messages", json.dumps(message_parts))


def _maybe_set_span_output_messages(
    span: Span, generations: List[OutputMessage]
) -> None:
    if not is_experimental_mode() or get_content_capturing_mode() not in (
        ContentCapturingMode.SPAN_ONLY,
        ContentCapturingMode.SPAN_AND_EVENT,
    ):
        return
    generation_parts: List[Dict[str, Any]] = [
        asdict(generation) for generation in generations
    ]
    if generation_parts:
        span.set_attribute(
            "gen_ai.output.messages", json.dumps(generation_parts)
        )


def _maybe_set_additional_span_attributes(
    span: Span, invocation: LLMInvocation
) -> None:
    if "top_p" in invocation.attributes:
        span.set_attribute(
            GenAI.GEN_AI_REQUEST_TOP_P,
            invocation.attributes["top_p"],
        )

    if "frequency_penalty" in invocation.attributes:
        span.set_attribute(
            GenAI.GEN_AI_REQUEST_FREQUENCY_PENALTY,
            invocation.attributes["frequency_penalty"],
        )

    if "presence_penalty" in invocation.attributes:
        span.set_attribute(
            GenAI.GEN_AI_REQUEST_PRESENCE_PENALTY,
            invocation.attributes["presence_penalty"],
        )

    if "stop" in invocation.attributes:
        span.set_attribute(
            GenAI.GEN_AI_REQUEST_STOP_SEQUENCES,
            invocation.attributes["stop"],
        )

    if "seed" in invocation.attributes:
        span.set_attribute(
            GenAI.GEN_AI_REQUEST_SEED,
            invocation.attributes["seed"],
        )

    if "temperature" in invocation.attributes:
        span.set_attribute(
            GenAI.GEN_AI_REQUEST_TEMPERATURE,
            invocation.attributes["temperature"],
        )

    if "max_completion_tokens" in invocation.attributes:
        span.set_attribute(
            GenAI.GEN_AI_REQUEST_MAX_TOKENS,
            invocation.attributes["max_completion_tokens"],
        )


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


class SpanGenerator(BaseTelemetryGenerator):
    """
    Generates only spans.
    """

    def __init__(
        self,
        tracer: Optional[Tracer] = None,
    ):
        self._tracer: Tracer = tracer or trace.get_tracer(__name__)

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
        request_model = invocation.attributes.get("request_model")
        span = self._start_span(
            name=f"{GenAI.GenAiOperationNameValues.CHAT.value} {request_model}",
            kind=SpanKind.CLIENT,
            parent_run_id=invocation.parent_run_id,
        )
        with use_span(span, end_on_exit=False) as span:
            span_state = _SpanState(
                span=span,
            )
            self.spans[invocation.run_id] = span_state
            yield span

    @staticmethod
    def _apply_common_span_attributes(
        span: Span, invocation: LLMInvocation
    ) -> Tuple[Dict[str, AttributeValue]]:
        """Apply attributes shared by finish() and error() and compute metrics.

        Returns (genai_attributes).
        """
        request_model = invocation.attributes.get("request_model")
        system = invocation.attributes.get("system")

        _set_initial_span_attributes(span, request_model, system)

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
        _maybe_set_additional_span_attributes(span, invocation)
        genai_attributes = _get_genai_attributes(
            request_model,
            response_model,
            GenAI.GenAiOperationNameValues.CHAT.value,
            system,
        )
        return (genai_attributes,)

    def _finalize_invocation(self, invocation: LLMInvocation) -> None:
        """End span(s) and record duration for the invocation."""
        self._end_span(invocation.run_id)

    def finish(self, invocation: LLMInvocation):
        with self._span_for_invocation(invocation) as span:
            _ = self._apply_common_span_attributes(
                span, invocation
            )  # return value to be used with metrics
            _maybe_set_span_input_messages(span, invocation.messages)
            _maybe_set_span_output_messages(span, invocation.chat_generations)
        self._finalize_invocation(invocation)

    def error(self, error: Error, invocation: LLMInvocation):
        with self._span_for_invocation(invocation) as span:
            span.set_status(Status(StatusCode.ERROR, error.message))
            if span.is_recording():
                span.set_attribute(
                    ErrorAttributes.ERROR_TYPE, error.type.__qualname__
                )
        self._finalize_invocation(invocation)
