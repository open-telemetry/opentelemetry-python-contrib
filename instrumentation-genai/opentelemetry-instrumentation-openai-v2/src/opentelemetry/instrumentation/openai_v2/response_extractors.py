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

import json
import logging
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, List, Optional, TypeVar, Union

from pydantic import (
    BaseModel,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    ValidationError,
)

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    openai_attributes as OpenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)

from .utils import get_server_address_and_port, value_is_set

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
        LLMInvocation,
        OutputMessage,
        Reasoning,
        Text,
    )
    from opentelemetry.util.genai.types import (
        ToolCallRequest as ToolCall,
    )
except ImportError:
    InputMessage = None
    LLMInvocation = None
    OutputMessage = None
    Reasoning = None
    Text = None
    ToolCall = None

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
    max_output_tokens: Optional[StrictInt] = None
    model: Optional[StrictStr] = None
    service_tier: Optional[StrictStr] = None
    temperature: Optional[StrictFloat] = None
    text: Optional[_ResponseTextConfigModel] = None
    top_p: Optional[StrictFloat] = None


class _ResponseOutputContentModel(_ExtractorModel):
    type: Optional[StrictStr] = None
    text: Optional[StrictStr] = None
    refusal: Optional[StrictStr] = None


class _ResponseOutputItemModel(_ExtractorModel):
    type: Optional[StrictStr] = None
    role: Optional[StrictStr] = None
    status: Optional[StrictStr] = None
    id: Optional[StrictStr] = None
    call_id: Optional[StrictStr] = None
    name: Optional[StrictStr] = None
    arguments: Optional[StrictStr] = None
    content: List[_ResponseOutputContentModel] = Field(default_factory=list)
    summary: List[_ResponseOutputContentModel] = Field(default_factory=list)


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


def _parse_tool_call_arguments(arguments: str | None) -> object:
    if arguments is None:
        return None

    try:
        return json.loads(arguments)
    except (TypeError, ValueError):
        return arguments


def _extract_reasoning_parts(
    item: _ResponseOutputItemModel,
) -> list["Reasoning"]:
    if Reasoning is None:
        return []

    parts: list[Reasoning] = []
    for block in item.summary:
        if block.text is not None:
            parts.append(Reasoning(content=block.text))
    for block in item.content:
        if block.type == "reasoning_text" and block.text is not None:
            parts.append(Reasoning(content=block.text))
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
        if item.type == "message":
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
            continue

        if item.type == "function_call":
            if ToolCall is None or item.name is None:
                continue
            if item.status not in {"completed", "incomplete"}:
                continue

            messages.append(
                OutputMessage(
                    role="assistant",
                    parts=[
                        ToolCall(
                            id=item.call_id if item.call_id else item.id,
                            name=item.name,
                            arguments=_parse_tool_call_arguments(
                                item.arguments
                            ),
                        )
                    ],
                    finish_reason="tool_calls",
                )
            )
            continue

        if item.type == "reasoning":
            finish_reason = _finish_reason_from_status(item.status)
            if finish_reason is None:
                continue

            parts = _extract_reasoning_parts(item)
            if parts:
                messages.append(
                    OutputMessage(
                        role="assistant",
                        parts=parts,
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
        if item.type == "function_call" and item.status in {
            "completed",
            "incomplete",
        }:
            finish_reasons.append("tool_calls")
            continue

        if item.type != "message":
            continue
        finish_reason = _finish_reason_from_status(item.status)
        if finish_reason is not None:
            finish_reasons.append(finish_reason)
    return list(dict.fromkeys(finish_reasons))


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


def _extract_request_service_tier(
    kwargs: Mapping[str, object],
) -> str | None:
    request = _validate_request_kwargs(kwargs)
    if request is None:
        return None

    service_tier = request.service_tier
    if service_tier in (None, "auto"):
        return None

    return service_tier


def _get_request_attributes(
    kwargs: Mapping[str, object],
    client_instance: object,
    latest_experimental_enabled: bool,
) -> dict[str, object]:
    request = _validate_request_kwargs(kwargs)
    request_model = request.model if request is not None else None
    attributes: dict[str, object] = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: (
            GenAIAttributes.GenAiOperationNameValues.CHAT.value
        ),
        GenAIAttributes.GEN_AI_REQUEST_MODEL: request_model,
    }

    if latest_experimental_enabled:
        attributes[GenAIAttributes.GEN_AI_PROVIDER_NAME] = (
            GenAIAttributes.GenAiProviderNameValues.OPENAI.value
        )
    else:
        attributes[GenAIAttributes.GEN_AI_SYSTEM] = (
            GenAIAttributes.GenAiSystemValues.OPENAI.value
        )

    output_type = _extract_output_type(kwargs)
    if output_type is not None:
        output_type_key = (
            GenAIAttributes.GEN_AI_OUTPUT_TYPE
            if latest_experimental_enabled
            else GenAIAttributes.GEN_AI_OPENAI_REQUEST_RESPONSE_FORMAT
        )
        attributes[output_type_key] = output_type

    service_tier = _extract_request_service_tier(kwargs)
    if service_tier is not None:
        service_tier_key = (
            OpenAIAttributes.OPENAI_REQUEST_SERVICE_TIER
            if latest_experimental_enabled
            else GenAIAttributes.GEN_AI_OPENAI_REQUEST_SERVICE_TIER
        )
        attributes[service_tier_key] = service_tier

    address, port = get_server_address_and_port(client_instance)
    if address is not None:
        attributes[ServerAttributes.SERVER_ADDRESS] = address
    if port is not None:
        attributes[ServerAttributes.SERVER_PORT] = port

    return {
        key: value for key, value in attributes.items() if value_is_set(value)
    }


def _get_inference_creation_kwargs(
    kwargs: Mapping[str, object],
    client_instance: object,
) -> dict[str, object]:
    request = _validate_request_kwargs(kwargs)
    request_model = request.model if request is not None else None
    address, port = get_server_address_and_port(client_instance)

    creation_kwargs: dict[str, object] = {
        "provider": GenAIAttributes.GenAiProviderNameValues.OPENAI.value,
    }
    if request_model is not None:
        creation_kwargs["request_model"] = request_model
    if address is not None:
        creation_kwargs["server_address"] = address
    if port is not None:
        creation_kwargs["server_port"] = port
    return creation_kwargs


def _apply_request_attributes(
    invocation,
    kwargs: Mapping[str, object],
    capture_content: bool,
) -> None:
    request = _validate_request_kwargs(kwargs)

    if request is not None:
        invocation.temperature = request.temperature
        invocation.top_p = request.top_p
        invocation.max_tokens = request.max_output_tokens

    request_service_tier = _extract_request_service_tier(kwargs)
    if request_service_tier is not None:
        invocation.attributes[OpenAIAttributes.OPENAI_REQUEST_SERVICE_TIER] = (
            request_service_tier
        )

    output_type = _extract_output_type(kwargs)
    if output_type is not None:
        invocation.attributes[GenAIAttributes.GEN_AI_OUTPUT_TYPE] = output_type

    if capture_content:
        invocation.system_instruction = _extract_system_instruction(kwargs)
        invocation.input_messages = _extract_input_messages(kwargs)


def _set_invocation_usage_attributes(invocation, usage: _UsageModel) -> None:
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
    invocation,
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
