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

from opentelemetry._logs import Logger, LogRecord
from opentelemetry.context import get_current
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.trace import (
    Span,
)
from opentelemetry.trace.propagation import set_span_in_context
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util.genai.types import (
    Error,
    InputMessage,
    LLMInvocation,
    MessagePart,
    OutputMessage,
)
from opentelemetry.util.genai.utils import (
    ContentCapturingMode,
    gen_ai_json_dumps,
    get_content_capturing_mode,
    is_experimental_mode,
    should_emit_event,
)


def _get_llm_common_attributes(
    invocation: LLMInvocation,
) -> dict[str, Any]:
    """Get common LLM attributes shared by finish() and error() paths.

    Returns a dictionary of attributes.
    """
    attributes: dict[str, Any] = {}
    attributes[GenAI.GEN_AI_OPERATION_NAME] = (
        GenAI.GenAiOperationNameValues.CHAT.value
    )
    if invocation.request_model:
        attributes[GenAI.GEN_AI_REQUEST_MODEL] = invocation.request_model
    if invocation.provider is not None:
        # TODO: clean provider name to match GenAiProviderNameValues?
        attributes[GenAI.GEN_AI_PROVIDER_NAME] = invocation.provider
    return attributes


def _get_llm_span_name(invocation: LLMInvocation) -> str:
    """Get the span name for an LLM invocation."""
    return f"{GenAI.GenAiOperationNameValues.CHAT.value} {invocation.request_model}".strip()


def _get_llm_messages_attributes_for_span(
    input_messages: list[InputMessage],
    output_messages: list[OutputMessage],
    system_instruction: list[MessagePart] | None = None,
) -> dict[str, Any]:
    """Get message attributes formatted for span (JSON string format).

    Returns empty dict if not in experimental mode or content capturing is disabled.
    """
    attributes: dict[str, Any] = {}
    if not is_experimental_mode() or get_content_capturing_mode() not in (
        ContentCapturingMode.SPAN_ONLY,
        ContentCapturingMode.SPAN_AND_EVENT,
    ):
        return attributes
    if input_messages:
        attributes[GenAI.GEN_AI_INPUT_MESSAGES] = gen_ai_json_dumps(
            [asdict(message) for message in input_messages]
        )
    if output_messages:
        attributes[GenAI.GEN_AI_OUTPUT_MESSAGES] = gen_ai_json_dumps(
            [asdict(message) for message in output_messages]
        )
    if system_instruction:
        attributes[GenAI.GEN_AI_SYSTEM_INSTRUCTIONS] = gen_ai_json_dumps(
            [asdict(part) for part in system_instruction]
        )
    return attributes


def _get_llm_messages_attributes_for_event(
    input_messages: list[InputMessage],
    output_messages: list[OutputMessage],
    system_instruction: list[MessagePart] | None = None,
) -> dict[str, Any]:
    """Get message attributes formatted for event (structured format).

    Returns empty dict if not in experimental mode or content capturing is disabled.
    """
    attributes: dict[str, Any] = {}
    if not is_experimental_mode() or get_content_capturing_mode() not in (
        ContentCapturingMode.EVENT_ONLY,
        ContentCapturingMode.SPAN_AND_EVENT,
    ):
        return attributes
    if input_messages:
        attributes[GenAI.GEN_AI_INPUT_MESSAGES] = [
            asdict(message) for message in input_messages
        ]
    if output_messages:
        attributes[GenAI.GEN_AI_OUTPUT_MESSAGES] = [
            asdict(message) for message in output_messages
        ]
    if system_instruction:
        attributes[GenAI.GEN_AI_SYSTEM_INSTRUCTIONS] = [
            asdict(part) for part in system_instruction
        ]
    return attributes


def _maybe_emit_llm_event(
    logger: Logger | None,
    span: Span,
    invocation: LLMInvocation,
    error: Error | None = None,
) -> None:
    """Emit a gen_ai.client.inference.operation.details event to the logger.

    This function creates a LogRecord event following the semantic convention
    for gen_ai.client.inference.operation.details as specified in the GenAI
    event semantic conventions.

    For more details, see the semantic convention documentation:
    https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-events.md#event-eventgen_aiclientinferenceoperationdetails
    """
    if not is_experimental_mode() or not should_emit_event() or logger is None:
        return

    # Build event attributes by reusing the attribute getter functions
    attributes: dict[str, Any] = {}
    attributes.update(_get_llm_common_attributes(invocation))
    attributes.update(_get_llm_request_attributes(invocation))
    attributes.update(_get_llm_response_attributes(invocation))
    attributes.update(
        _get_llm_messages_attributes_for_event(
            invocation.input_messages,
            invocation.output_messages,
            invocation.system_instruction,
        )
    )

    # Add error.type if operation ended in error
    if error is not None:
        attributes[ErrorAttributes.ERROR_TYPE] = error.type.__qualname__

    # Create and emit the event
    context = set_span_in_context(span, get_current())
    event = LogRecord(
        event_name="gen_ai.client.inference.operation.details",
        attributes=attributes,
        context=context,
    )
    logger.emit(event)


def _apply_llm_finish_attributes(
    span: Span, invocation: LLMInvocation
) -> None:
    """Apply attributes/messages common to finish() paths."""
    # Update span name
    span.update_name(_get_llm_span_name(invocation))

    # Build all attributes by reusing the attribute getter functions
    attributes: dict[str, Any] = {}
    attributes.update(_get_llm_common_attributes(invocation))
    attributes.update(_get_llm_request_attributes(invocation))
    attributes.update(_get_llm_response_attributes(invocation))
    attributes.update(
        _get_llm_messages_attributes_for_span(
            invocation.input_messages,
            invocation.output_messages,
            invocation.system_instruction,
        )
    )
    attributes.update(invocation.attributes)

    # Set all attributes on the span
    if attributes:
        span.set_attributes(attributes)


def _apply_error_attributes(span: Span, error: Error) -> None:
    """Apply status and error attributes common to error() paths."""
    span.set_status(Status(StatusCode.ERROR, error.message))
    if span.is_recording():
        span.set_attribute(ErrorAttributes.ERROR_TYPE, error.type.__qualname__)


def _get_llm_request_attributes(
    invocation: LLMInvocation,
) -> dict[str, Any]:
    """Get GenAI request semantic convention attributes."""
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
    return attributes


def _get_llm_response_attributes(
    invocation: LLMInvocation,
) -> dict[str, Any]:
    """Get GenAI response semantic convention attributes."""
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

    return attributes


__all__ = [
    "_apply_llm_finish_attributes",
    "_apply_error_attributes",
    "_get_llm_common_attributes",
    "_get_llm_request_attributes",
    "_get_llm_response_attributes",
    "_get_llm_span_name",
    "_maybe_emit_llm_event",
]
