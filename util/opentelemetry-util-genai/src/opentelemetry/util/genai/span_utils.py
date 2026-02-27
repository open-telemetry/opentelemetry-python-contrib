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
    error_attributes,
    server_attributes,
)
from opentelemetry.trace import (
    Span,
)
from opentelemetry.trace.propagation import set_span_in_context
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util.genai.types import (
    EmbeddingInvocation,
    Error,
    GenAIInvocation,
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
    # TODO: clean provider name to match GenAiProviderNameValues?
    optional_attrs = (
        (GenAI.GEN_AI_REQUEST_MODEL, invocation.request_model),
        (GenAI.GEN_AI_PROVIDER_NAME, invocation.provider),
        (server_attributes.SERVER_ADDRESS, invocation.server_address),
        (server_attributes.SERVER_PORT, invocation.server_port),
    )

    return {
        GenAI.GEN_AI_OPERATION_NAME: invocation.operation_name,
        **{key: value for key, value in optional_attrs if value is not None},
    }


def _get_embedding_common_attributes(
    invocation: EmbeddingInvocation,
) -> dict[str, Any]:
    """Get common Embedding attributes shared by finish() and error() paths.

    Returns a dictionary of attributes.
    """
    optional_attrs = (
        (server_attributes.SERVER_ADDRESS, invocation.server_address),
        (server_attributes.SERVER_PORT, invocation.server_port),
    )

    return {
        GenAI.GEN_AI_OPERATION_NAME: invocation.operation_name,
        GenAI.GEN_AI_PROVIDER_NAME: invocation.provider,
        **{key: value for key, value in optional_attrs if value is not None},
    }


def _get_span_name(
    invocation: GenAIInvocation,
) -> str:
    """Get the span name for a GenAI invocation."""
    return f"{invocation.operation_name} {invocation.request_model}".strip()


def _get_llm_span_name(invocation: LLMInvocation) -> str:
    """Get the span name for an LLM invocation."""
    return _get_span_name(invocation)


def _get_embedding_span_name(invocation: EmbeddingInvocation) -> str:
    """Get the span name for an Embedding invocation."""
    return _get_span_name(invocation)


def _get_llm_messages_attributes_for_span(
    input_messages: list[InputMessage],
    output_messages: list[OutputMessage],
    system_instruction: list[MessagePart] | None = None,
) -> dict[str, Any]:
    """Get message attributes formatted for span (JSON string format).

    Returns empty dict if not in experimental mode or content capturing is disabled.
    """
    if not is_experimental_mode() or get_content_capturing_mode() not in (
        ContentCapturingMode.SPAN_ONLY,
        ContentCapturingMode.SPAN_AND_EVENT,
    ):
        return {}

    optional_attrs = (
        (
            GenAI.GEN_AI_INPUT_MESSAGES,
            gen_ai_json_dumps([asdict(m) for m in input_messages])
            if input_messages
            else None,
        ),
        (
            GenAI.GEN_AI_OUTPUT_MESSAGES,
            gen_ai_json_dumps([asdict(m) for m in output_messages])
            if output_messages
            else None,
        ),
        (
            GenAI.GEN_AI_SYSTEM_INSTRUCTIONS,
            gen_ai_json_dumps([asdict(p) for p in system_instruction])
            if system_instruction
            else None,
        ),
    )

    return {key: value for key, value in optional_attrs if value is not None}


def _get_llm_messages_attributes_for_event(
    input_messages: list[InputMessage],
    output_messages: list[OutputMessage],
    system_instruction: list[MessagePart] | None = None,
) -> dict[str, Any]:
    """Get message attributes formatted for event (structured format).

    Returns empty dict if not in experimental mode or content capturing is disabled.
    """
    if not is_experimental_mode() or get_content_capturing_mode() not in (
        ContentCapturingMode.EVENT_ONLY,
        ContentCapturingMode.SPAN_AND_EVENT,
    ):
        return {}

    optional_attrs = (
        (
            GenAI.GEN_AI_INPUT_MESSAGES,
            [asdict(m) for m in input_messages] if input_messages else None,
        ),
        (
            GenAI.GEN_AI_OUTPUT_MESSAGES,
            [asdict(m) for m in output_messages] if output_messages else None,
        ),
        (
            GenAI.GEN_AI_SYSTEM_INSTRUCTIONS,
            [asdict(p) for p in system_instruction]
            if system_instruction
            else None,
        ),
    )

    return {key: value for key, value in optional_attrs if value is not None}


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
        attributes[error_attributes.ERROR_TYPE] = error.type.__qualname__

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


def _apply_embedding_finish_attributes(
    span: Span, invocation: EmbeddingInvocation
) -> None:
    """Apply attributes common to embedding finish() paths."""
    # Update span name
    span.update_name(_get_embedding_span_name(invocation))

    # Build all attributes by reusing the attribute getter functions
    attributes: dict[str, Any] = {}
    attributes.update(_get_embedding_common_attributes(invocation))
    attributes.update(_get_embedding_request_attributes(invocation))
    attributes.update(_get_embedding_response_attributes(invocation))

    attributes.update(invocation.attributes)

    # Set all attributes on the span
    if attributes:
        span.set_attributes(attributes)


def _apply_error_attributes(span: Span, error: Error) -> None:
    """Apply status and error attributes common to error() paths."""
    span.set_status(Status(StatusCode.ERROR, error.message))
    if span.is_recording():
        span.set_attribute(
            error_attributes.ERROR_TYPE, error.type.__qualname__
        )


def _get_llm_request_attributes(
    invocation: LLMInvocation,
) -> dict[str, Any]:
    """Get GenAI request semantic convention attributes."""
    optional_attrs = (
        (GenAI.GEN_AI_REQUEST_TEMPERATURE, invocation.temperature),
        (GenAI.GEN_AI_REQUEST_TOP_P, invocation.top_p),
        (GenAI.GEN_AI_REQUEST_FREQUENCY_PENALTY, invocation.frequency_penalty),
        (GenAI.GEN_AI_REQUEST_PRESENCE_PENALTY, invocation.presence_penalty),
        (GenAI.GEN_AI_REQUEST_MAX_TOKENS, invocation.max_tokens),
        (GenAI.GEN_AI_REQUEST_STOP_SEQUENCES, invocation.stop_sequences),
        (GenAI.GEN_AI_REQUEST_SEED, invocation.seed),
    )

    return {key: value for key, value in optional_attrs if value is not None}


def _get_embedding_request_attributes(
    invocation: EmbeddingInvocation,
) -> dict[str, Any]:
    """Get GenAI request semantic convention attributes."""
    optional_attrs = (
        (GenAI.GEN_AI_REQUEST_MODEL, invocation.request_model),
        (GenAI.GEN_AI_EMBEDDINGS_DIMENSION_COUNT, invocation.dimension_count),
        (GenAI.GEN_AI_REQUEST_ENCODING_FORMATS, invocation.encoding_formats),
    )

    return {key: value for key, value in optional_attrs if value is not None}


def _get_llm_response_attributes(
    invocation: LLMInvocation,
) -> dict[str, Any]:
    """Get GenAI response semantic convention attributes."""
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

    # De-duplicate finish reasons
    unique_finish_reasons = (
        sorted(set(finish_reasons)) if finish_reasons else None
    )

    optional_attrs = (
        (
            GenAI.GEN_AI_RESPONSE_FINISH_REASONS,
            unique_finish_reasons if unique_finish_reasons else None,
        ),
        (GenAI.GEN_AI_RESPONSE_MODEL, invocation.response_model_name),
        (GenAI.GEN_AI_RESPONSE_ID, invocation.response_id),
        (GenAI.GEN_AI_USAGE_INPUT_TOKENS, invocation.input_tokens),
        (GenAI.GEN_AI_USAGE_OUTPUT_TOKENS, invocation.output_tokens),
    )

    return {key: value for key, value in optional_attrs if value is not None}


def _get_embedding_response_attributes(
    invocation: EmbeddingInvocation,
) -> dict[str, Any]:
    """Get GenAI response semantic convention attributes."""
    optional_attrs = (
        (GenAI.GEN_AI_USAGE_INPUT_TOKENS, invocation.input_tokens),
    )

    return {key: value for key, value in optional_attrs if value is not None}


__all__ = [
    "_apply_llm_finish_attributes",
    "_apply_error_attributes",
    "_get_llm_common_attributes",
    "_get_llm_request_attributes",
    "_get_llm_response_attributes",
    "_get_llm_span_name",
    "_maybe_emit_llm_event",
    "_apply_embedding_finish_attributes",
    "_get_embedding_common_attributes",
    "_get_embedding_request_attributes",
    "_get_embedding_response_attributes",
    "_get_embedding_span_name",
]
