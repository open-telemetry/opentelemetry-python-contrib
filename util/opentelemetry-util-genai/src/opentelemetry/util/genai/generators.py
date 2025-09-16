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
from typing import Any, Dict, List, Optional
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


def _apply_common_span_attributes(
    span: Span, invocation: LLMInvocation
) -> None:
    """Apply attributes shared by finish() and error() and compute metrics.

    Returns (genai_attributes) for use with metrics.
    """
    request_model = invocation.attributes.get("request_model")
    provider = invocation.attributes.get("provider")

    span.set_attribute(
        GenAI.GEN_AI_OPERATION_NAME, GenAI.GenAiOperationNameValues.CHAT.value
    )
    if request_model:
        span.set_attribute(GenAI.GEN_AI_REQUEST_MODEL, request_model)
    if provider is not None:
        # TODO: clean provider name to match GenAiProviderNameValues?
        span.set_attribute(GenAI.GEN_AI_PROVIDER_NAME, provider)

    finish_reasons: List[str] = []
    for gen in invocation.chat_generations:
        finish_reasons.append(gen.finish_reason)
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


def _maybe_set_span_messages(
    span: Span,
    input_messages: List[InputMessage],
    output_messages: List[OutputMessage],
) -> None:
    if not is_experimental_mode() or get_content_capturing_mode() not in (
        ContentCapturingMode.SPAN_ONLY,
        ContentCapturingMode.SPAN_AND_EVENT,
    ):
        return
    message_parts: List[Dict[str, Any]] = [
        asdict(message) for message in input_messages
    ]
    if message_parts:
        span.set_attribute("gen_ai.input.messages", json.dumps(message_parts))

    generation_parts: List[Dict[str, Any]] = [
        asdict(generation) for generation in output_messages
    ]
    if generation_parts:
        span.set_attribute(
            "gen_ai.output.messages", json.dumps(generation_parts)
        )


def _apply_finish_attributes(span: Span, invocation: LLMInvocation) -> None:
    """Apply attributes/messages common to finish() paths."""
    _apply_common_span_attributes(span, invocation)
    _maybe_set_span_messages(
        span, invocation.messages, invocation.chat_generations
    )


def _apply_error_attributes(span: Span, error: Error) -> None:
    """Apply status and error attributes common to error() paths."""
    span.set_status(Status(StatusCode.ERROR, error.message))
    if span.is_recording():
        span.set_attribute(ErrorAttributes.ERROR_TYPE, error.type.__qualname__)


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

        # TODO: Map from run_id -> _SpanState, to keep track of spans and parent/child relationships
        self.spans: Dict[UUID, _SpanState] = {}

    def _start_span(
        self,
        name: str,
        kind: SpanKind,
        parent_run_id: Optional[UUID] = None,
    ) -> Span:
        parent_span = (
            self.spans.get(parent_run_id)
            if parent_run_id is not None
            else None
        )
        if parent_span is not None:
            ctx = set_span_in_context(parent_span.span)
            span = self._tracer.start_span(name=name, kind=kind, context=ctx)
        else:
            # top-level or missing parent
            span = self._tracer.start_span(name=name, kind=kind)
            set_span_in_context(span)

        return span

    def _end_span(self, run_id: UUID):
        state = self.spans[run_id]
        for child_id in state.children:
            child_state = self.spans.get(child_id)
            if child_state:
                child_state.span.end()
        state.span.end()
        del self.spans[run_id]

    def start(self, invocation: LLMInvocation):
        # Create/register the span; keep it active but do not end it here.
        with self._start_span_for_invocation(invocation):
            pass

    @contextmanager
    def _start_span_for_invocation(self, invocation: LLMInvocation):
        """Create/register a span for the invocation and yield it.

        The span is not ended automatically on exiting the context; callers
        must finalize via _finalize_invocation.
        """
        # Establish parent/child relationship if a parent span exists.
        parent_state = (
            self.spans.get(invocation.parent_run_id)
            if invocation.parent_run_id is not None
            else None
        )
        if parent_state is not None:
            parent_state.children.append(invocation.run_id)
        span = self._start_span(
            name=f"{GenAI.GenAiOperationNameValues.CHAT.value} {invocation.request_model}",
            kind=SpanKind.CLIENT,
            parent_run_id=invocation.parent_run_id,
        )
        with use_span(span, end_on_exit=False) as span:
            span_state = _SpanState(
                span=span,
            )
            self.spans[invocation.run_id] = span_state
            yield span

    def finish(self, invocation: LLMInvocation):
        state = self.spans.get(invocation.run_id)
        if state is None:
            with self._start_span_for_invocation(invocation) as span:
                _apply_finish_attributes(span, invocation)
            self._end_span(invocation.run_id)
            return

        span = state.span
        _apply_finish_attributes(span, invocation)
        self._end_span(invocation.run_id)

    def error(self, error: Error, invocation: LLMInvocation):
        state = self.spans.get(invocation.run_id)
        if state is None:
            with self._start_span_for_invocation(invocation) as span:
                _apply_error_attributes(span, error)
            self._end_span(invocation.run_id)
            return

        span = state.span
        _apply_error_attributes(span, error)
        self._end_span(invocation.run_id)
