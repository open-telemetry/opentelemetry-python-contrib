# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, List, Optional, TypeVar, Union

from pydantic import BaseModel, Field, StrictInt, StrictStr, ValidationError

from opentelemetry.semconv._incubating.attributes import (
    openai_attributes as OpenAIAttributes,
)

_PYDANTIC_V2 = hasattr(BaseModel, "model_validate")

if _PYDANTIC_V2:
    from pydantic import ConfigDict
else:
    ConfigDict = None

if TYPE_CHECKING:
    from opentelemetry.util.genai.types import (
        InputMessage,
        LLMInvocation,
        OutputMessage,
        Text,
    )

try:
    from opentelemetry.util.genai.types import (
        InputMessage,
        OutputMessage,
        Text,
    )
except ImportError:
    InputMessage = None
    OutputMessage = None
    Text = None

GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS = "gen_ai.usage.cache_read.input_tokens"
GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS = (
    "gen_ai.usage.cache_creation.input_tokens"
)

_logger = logging.getLogger(__name__)
ModelT = TypeVar("ModelT", bound=BaseModel)


class _ExtractorModel(BaseModel):
    if _PYDANTIC_V2:
        model_config = ConfigDict(extra="ignore", from_attributes=True)
    else:

        class Config:
            extra = "ignore"
            orm_mode = True


class _ResponseTextFormatModel(_ExtractorModel):
    type: Optional[StrictStr] = None


class _ResponseTextConfigModel(_ExtractorModel):
    format: Optional[_ResponseTextFormatModel] = None


class _ResponseInputContentModel(_ExtractorModel):
    text: Optional[StrictStr] = None


class _ResponseInputItemModel(_ExtractorModel):
    role: Optional[StrictStr] = None
    content: Optional[Union[StrictStr, List[_ResponseInputContentModel]]] = (
        None
    )


class _ResponsesRequestModel(_ExtractorModel):
    instructions: Optional[StrictStr] = None
    input: Optional[Union[StrictStr, List[_ResponseInputItemModel]]] = None
    text: Optional[_ResponseTextConfigModel] = None


class _ResponseOutputContentModel(_ExtractorModel):
    type: Optional[StrictStr] = None
    text: Optional[StrictStr] = None
    refusal: Optional[StrictStr] = None


class _ResponseOutputItemModel(_ExtractorModel):
    type: Optional[StrictStr] = None
    role: Optional[StrictStr] = None
    status: Optional[StrictStr] = None
    content: List[_ResponseOutputContentModel] = Field(default_factory=list)


class _UsageDetailsModel(_ExtractorModel):
    cached_tokens: Optional[StrictInt] = None
    cache_creation_input_tokens: Optional[StrictInt] = None


class _UsageModel(_ExtractorModel):
    input_tokens: Optional[StrictInt] = None
    output_tokens: Optional[StrictInt] = None
    prompt_tokens: Optional[StrictInt] = None
    completion_tokens: Optional[StrictInt] = None
    input_tokens_details: Optional[_UsageDetailsModel] = None
    prompt_tokens_details: Optional[_UsageDetailsModel] = None


class _ResponsesResultModel(_ExtractorModel):
    # Responses can be partial or otherwise omit `output`. Treat that as "no
    # terminal message items available yet" so downstream extraction helpers
    # naturally return empty lists instead of raising.
    output: List[_ResponseOutputItemModel] = Field(default_factory=list)
    model: Optional[StrictStr] = None
    id: Optional[StrictStr] = None
    service_tier: Optional[StrictStr] = None
    usage: Optional[_UsageModel] = None


def _rebuild_model(model_type: type[BaseModel]) -> None:
    if _PYDANTIC_V2:
        model_type.model_rebuild(_types_namespace=globals())
    else:
        model_type.update_forward_refs(**globals())


for _model_type in (
    _ResponseTextFormatModel,
    _ResponseTextConfigModel,
    _ResponseInputContentModel,
    _ResponseInputItemModel,
    _ResponsesRequestModel,
    _ResponseOutputContentModel,
    _ResponseOutputItemModel,
    _UsageDetailsModel,
    _UsageModel,
    _ResponsesResultModel,
):
    _rebuild_model(_model_type)


def _validate_model(
    model_type: type[ModelT], value: object, context: str
) -> ModelT | None:
    try:
        if _PYDANTIC_V2:
            return model_type.model_validate(value)
        if isinstance(value, Mapping):
            return model_type.parse_obj(value)
        return model_type.from_orm(value)
    except ValidationError:
        _logger.debug(
            "OpenAI responses extractor validation failed for %s",
            context,
            exc_info=True,
        )
        return None


def _validate_request_kwargs(
    kwargs: Mapping[str, object],
) -> _ResponsesRequestModel | None:
    return _validate_model(
        _ResponsesRequestModel, kwargs, "request parameters"
    )


def _validate_response_result(result: object) -> _ResponsesResultModel | None:
    return _validate_model(_ResponsesResultModel, result, "response payload")


def _coerce_response_result(
    result: object | _ResponsesResultModel | None,
) -> _ResponsesResultModel | None:
    if result is None:
        return None

    if isinstance(result, _ResponsesResultModel):
        return result

    return _validate_response_result(result)


def _extract_system_instruction(kwargs: Mapping[str, object]) -> list["Text"]:
    """Extract system instruction from the ``instructions`` parameter."""
    if Text is None:
        return []

    request = _validate_request_kwargs(kwargs)
    if request is None or request.instructions is None:
        return []

    return [Text(content=request.instructions)]


def _extract_input_messages(
    kwargs: Mapping[str, object],
) -> list["InputMessage"]:
    """Extract input messages from Responses API kwargs."""
    if InputMessage is None or Text is None:
        return []

    request = _validate_request_kwargs(kwargs)
    if request is None or request.input is None:
        return []

    if isinstance(request.input, str):
        return [InputMessage(role="user", parts=[Text(content=request.input)])]

    messages: list[InputMessage] = []
    for item in request.input:
        if item.role is None:
            continue

        if isinstance(item.content, str):
            messages.append(
                InputMessage(
                    role=item.role, parts=[Text(content=item.content)]
                )
            )
            continue

        if item.content is None:
            continue

        parts = [
            Text(content=part.text)
            for part in item.content
            if part.text is not None
        ]
        if parts:
            messages.append(InputMessage(role=item.role, parts=parts))

    return messages


def _extract_output_parts(
    content_blocks: Sequence[_ResponseOutputContentModel],
) -> list["Text"]:
    if Text is None:
        return []

    parts: list[Text] = []
    for block in content_blocks:
        if block.type == "output_text" and block.text is not None:
            parts.append(Text(content=block.text))
        elif block.type == "refusal" and block.refusal is not None:
            parts.append(Text(content=block.refusal))
    return parts


def _finish_reason_from_status(status: str | None) -> str | None:
    # Responses API output items expose lifecycle statuses rather than finish
    # reasons. We map the normal terminal state to the GenAI "stop" reason,
    # preserve the other terminal statuses verbatim, and drop non-terminal or
    # unknown states from the finish_reasons attribute.
    if status == "completed":
        return "stop"
    if status in {"failed", "cancelled", "incomplete"}:
        return status
    return None


def _extract_output_messages_from_model(
    result: _ResponsesResultModel,
) -> list["OutputMessage"]:
    if OutputMessage is None or Text is None:
        return []

    messages: list[OutputMessage] = []
    for item in result.output:
        if item.type != "message":
            continue
        finish_reason = _finish_reason_from_status(item.status)
        if finish_reason is None:
            continue

        messages.append(
            OutputMessage(
                role=item.role if item.role is not None else "assistant",
                parts=_extract_output_parts(item.content),
                finish_reason=finish_reason,
            )
        )

    return messages


def _extract_output_messages(
    result: object | _ResponsesResultModel | None,
) -> list["OutputMessage"]:
    """Extract output messages from a Responses API result."""
    validated_result = _coerce_response_result(result)
    if validated_result is None:
        return []

    return _extract_output_messages_from_model(validated_result)


def _extract_finish_reasons_from_model(
    result: _ResponsesResultModel,
) -> list[str]:
    finish_reasons: list[str] = []
    for item in result.output:
        if item.type != "message":
            continue
        finish_reason = _finish_reason_from_status(item.status)
        if finish_reason is not None:
            finish_reasons.append(finish_reason)
    return finish_reasons


def _extract_finish_reasons(
    result: object | _ResponsesResultModel | None,
) -> list[str]:
    """Extract finish reasons from Responses API output items."""
    validated_result = _coerce_response_result(result)
    if validated_result is None:
        return []

    return _extract_finish_reasons_from_model(validated_result)


def _extract_output_type(kwargs: Mapping[str, object]) -> str | None:
    """Extract output type from Responses API request text.format."""
    request = _validate_request_kwargs(kwargs)
    if request is None or request.text is None or request.text.format is None:
        return None

    if request.text.format.type == "json_schema":
        return "json"
    return request.text.format.type


def _set_invocation_usage_attributes(
    invocation: "LLMInvocation", usage: _UsageModel
) -> None:
    if usage.input_tokens is not None:
        invocation.input_tokens = usage.input_tokens
    else:
        invocation.input_tokens = usage.prompt_tokens

    if usage.output_tokens is not None:
        invocation.output_tokens = usage.output_tokens
    else:
        invocation.output_tokens = usage.completion_tokens

    details = (
        usage.input_tokens_details
        if usage.input_tokens_details is not None
        else usage.prompt_tokens_details
    )
    if details is None:
        return

    if details.cached_tokens is not None:
        invocation.attributes[GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS] = (
            details.cached_tokens
        )

    if details.cache_creation_input_tokens is not None:
        invocation.attributes[GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS] = (
            details.cache_creation_input_tokens
        )


def _set_invocation_response_attributes(
    invocation: "LLMInvocation",
    result: object | None,
    capture_content: bool,
) -> None:
    # This helper sits at the raw response boundary for instrumentation. Unlike
    # the extractor helpers above, it intentionally validates exactly once and
    # then fans out to the `_from_model` helpers rather than accepting an
    # already-coerced `_ResponsesResultModel`.
    if result is None:
        return

    validated_result = _validate_response_result(result)
    if validated_result is None:
        return

    if validated_result.model is not None:
        invocation.response_model_name = validated_result.model

    if validated_result.id is not None:
        invocation.response_id = validated_result.id

    if validated_result.service_tier is not None:
        invocation.attributes[
            OpenAIAttributes.OPENAI_RESPONSE_SERVICE_TIER
        ] = validated_result.service_tier

    if validated_result.usage is not None:
        _set_invocation_usage_attributes(invocation, validated_result.usage)

    finish_reasons = _extract_finish_reasons_from_model(validated_result)
    if finish_reasons:
        invocation.finish_reasons = finish_reasons

    if capture_content:
        output_messages = _extract_output_messages_from_model(validated_result)
        if output_messages:
            invocation.output_messages = output_messages
