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

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
    server_attributes as ServerAttributes,
)
from opentelemetry.trace import (
    Span,
)
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util.genai.types import (
    Error,
    InputMessage,
    LLMInvocation,
    OutputMessage,
)
from opentelemetry.util.genai.utils import (
    ContentCapturingMode,
    gen_ai_json_dumps,
    get_content_capturing_mode,
    is_experimental_mode,
)


def _apply_common_span_attributes(
    span: Span, invocation: LLMInvocation
) -> None:
    """Apply attributes shared by finish() and error() and compute metrics.

    Returns (genai_attributes) for use with metrics.
    """
    span.update_name(
        f"{GenAI.GenAiOperationNameValues.CHAT.value} {invocation.request_model}".strip()
    )
    span.set_attribute(
        GenAI.GEN_AI_OPERATION_NAME, GenAI.GenAiOperationNameValues.CHAT.value
    )
    if invocation.request_model:
        span.set_attribute(
            GenAI.GEN_AI_REQUEST_MODEL, invocation.request_model
        )
    if invocation.provider is not None:
        # TODO: clean provider name to match GenAiProviderNameValues?
        span.set_attribute(GenAI.GEN_AI_PROVIDER_NAME, invocation.provider)

    if invocation.server_address:
        span.set_attribute(
            ServerAttributes.SERVER_ADDRESS, invocation.server_address
        )
    if invocation.server_port:
        span.set_attribute(ServerAttributes.SERVER_PORT, invocation.server_port)

    _apply_response_attributes(span, invocation)


def _maybe_set_span_messages(
    span: Span,
    input_messages: list[InputMessage],
    output_messages: list[OutputMessage],
) -> None:
    if not is_experimental_mode() or get_content_capturing_mode() not in (
        ContentCapturingMode.SPAN_ONLY,
        ContentCapturingMode.SPAN_AND_EVENT,
    ):
        return
    if input_messages:
        span.set_attribute(
            GenAI.GEN_AI_INPUT_MESSAGES,
            gen_ai_json_dumps([asdict(message) for message in input_messages]),
        )
    if output_messages:
        span.set_attribute(
            GenAI.GEN_AI_OUTPUT_MESSAGES,
            gen_ai_json_dumps(
                [asdict(message) for message in output_messages]
            ),
        )


def _apply_finish_attributes(span: Span, invocation: LLMInvocation) -> None:
    """Apply attributes/messages common to finish() paths."""
    _apply_common_span_attributes(span, invocation)
    _maybe_set_span_messages(
        span, invocation.input_messages, invocation.output_messages
    )
    _apply_request_attributes(span, invocation)
    _apply_response_attributes(span, invocation)
    span.set_attributes(invocation.attributes)


def _apply_error_attributes(span: Span, error: Error) -> None:
    """Apply status and error attributes common to error() paths."""
    span.set_status(Status(StatusCode.ERROR, error.message))
    if span.is_recording():
        span.set_attribute(ErrorAttributes.ERROR_TYPE, error.type.__qualname__)


def _apply_request_attributes(span: Span, invocation: LLMInvocation) -> None:
    """Attach GenAI request semantic convention attributes to the span."""
    attributes: dict[str, Any] = {}
    if invocation.temperature is not None:
        attributes[GenAI.GEN_AI_REQUEST_TEMPERATURE] = invocation.temperature
    if invocation.top_p is not None:
        attributes[GenAI.GEN_AI_REQUEST_TOP_P] = invocation.top_p
    if invocation.frequency_penalty is not None:
        attributes[GenAI.GEN_AI_REQUEST_FREQUENCY_PENALTY] = (
            invocation.frequency_penalty
        )
    if invocation.presence_penalty is not None:
        attributes[GenAI.GEN_AI_REQUEST_PRESENCE_PENALTY] = (
            invocation.presence_penalty
        )
    if invocation.max_tokens is not None:
        attributes[GenAI.GEN_AI_REQUEST_MAX_TOKENS] = invocation.max_tokens
    if invocation.stop_sequences is not None:
        attributes[GenAI.GEN_AI_REQUEST_STOP_SEQUENCES] = (
            invocation.stop_sequences
        )
    if invocation.seed is not None:
        attributes[GenAI.GEN_AI_REQUEST_SEED] = invocation.seed
    if attributes:
        span.set_attributes(attributes)


def _apply_response_attributes(span: Span, invocation: LLMInvocation) -> None:
    """Attach GenAI response semantic convention attributes to the span."""
    attributes: dict[str, Any] = {}

    finish_reasons: list[str] | None
    if invocation.finish_reasons is not None:
        finish_reasons = invocation.finish_reasons
    elif invocation.output_messages:
        finish_reasons = [
            message.finish_reason
            for message in invocation.output_messages
            if message.finish_reason
        ]
    else:
        finish_reasons = None

    if finish_reasons:
        # De-duplicate finish reasons
        unique_finish_reasons = sorted(set(finish_reasons))
        if unique_finish_reasons:
            attributes[GenAI.GEN_AI_RESPONSE_FINISH_REASONS] = (
                unique_finish_reasons
            )

    if invocation.response_model_name is not None:
        attributes[GenAI.GEN_AI_RESPONSE_MODEL] = (
            invocation.response_model_name
        )
    if invocation.response_id is not None:
        attributes[GenAI.GEN_AI_RESPONSE_ID] = invocation.response_id
    if invocation.input_tokens is not None:
        attributes[GenAI.GEN_AI_USAGE_INPUT_TOKENS] = invocation.input_tokens
    if invocation.output_tokens is not None:
        attributes[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] = invocation.output_tokens

    if attributes:
        span.set_attributes(attributes)


__all__ = [
    "_apply_finish_attributes",
    "_apply_error_attributes",
    "_apply_request_attributes",
    "_apply_response_attributes",
]
