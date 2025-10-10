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

from dataclasses import asdict
from typing import Any, Dict, List

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

    if invocation.output_messages:
        span.set_attribute(
            GenAI.GEN_AI_RESPONSE_FINISH_REASONS,
            [gen.finish_reason for gen in invocation.output_messages],
        )

    if invocation.response_model_name is not None:
        span.set_attribute(
            GenAI.GEN_AI_RESPONSE_MODEL, invocation.response_model_name
        )
    if invocation.response_id is not None:
        span.set_attribute(GenAI.GEN_AI_RESPONSE_ID, invocation.response_id)
    if invocation.input_tokens is not None:
        span.set_attribute(
            GenAI.GEN_AI_USAGE_INPUT_TOKENS, invocation.input_tokens
        )
    if invocation.output_tokens is not None:
        span.set_attribute(
            GenAI.GEN_AI_USAGE_OUTPUT_TOKENS, invocation.output_tokens
        )


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
    span.set_attributes(invocation.attributes)


def _apply_error_attributes(span: Span, error: Error) -> None:
    """Apply status and error attributes common to error() paths."""
    span.set_status(Status(StatusCode.ERROR, error.message))
    if span.is_recording():
        span.set_attribute(ErrorAttributes.ERROR_TYPE, error.type.__qualname__)


def _apply_request_attributes(span: Span, invocation: LLMInvocation) -> None:
    """Attach GenAI request semantic convention attributes to the span."""
    attributes: Dict[str, Any] = {}
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


__all__ = [
    "_apply_finish_attributes",
    "_apply_error_attributes",
    "_apply_request_attributes",
]
