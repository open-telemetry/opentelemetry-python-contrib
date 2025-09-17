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

import json
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.trace import (
    Span,
)
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util.genai.utils import (
    ContentCapturingMode,
    get_content_capturing_mode,
    is_experimental_mode,
)
from opentelemetry.util.types import AttributeValue

from .types import Error, InputMessage, LLMInvocation, OutputMessage


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


__all__ = [
    "_apply_finish_attributes",
    "_apply_error_attributes",
]
