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

"""Get/extract helpers for Anthropic Messages instrumentation."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, List, Optional, TypeVar, Union

from anthropic.types import MessageDeltaUsage
from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    ValidationError,
)

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.util.genai.types import (
    InputMessage,
    LLMInvocation,
    MessagePart,
    OutputMessage,
)
from opentelemetry.util.types import AttributeValue

from .utils import (
    convert_content_to_parts,
    normalize_finish_reason,
)

_PYDANTIC_V2 = hasattr(BaseModel, "model_validate")

if _PYDANTIC_V2:
    from pydantic import ConfigDict
else:
    ConfigDict = None

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    import httpx
    from anthropic.resources.messages import Messages
    from anthropic.types import (
        Message,
        MessageParam,
        MetadataParam,
        TextBlockParam,
        ThinkingConfigParam,
        ToolChoiceParam,
        ToolUnionParam,
        Usage,
    )


_logger = logging.getLogger(__name__)
ModelT = TypeVar("ModelT", bound=BaseModel)


class _ExtractorModel(BaseModel):
    if _PYDANTIC_V2:
        assert ConfigDict is not None
        model_config = ConfigDict(extra="ignore", from_attributes=True)
    else:

        class Config:
            extra = "ignore"
            orm_mode = True


class _InputMessageParamModel(_ExtractorModel):
    role: Optional[StrictStr] = None
    content: Any = None


class MessageRequestParams(_ExtractorModel):
    model: Optional[StrictStr] = None
    max_tokens: Optional[StrictInt] = None
    temperature: Optional[Union[StrictFloat, StrictInt]] = None
    top_k: Optional[StrictInt] = None
    top_p: Optional[Union[StrictFloat, StrictInt]] = None
    stop_sequences: Optional[List[StrictStr]] = None
    stream: Optional[StrictBool] = None
    messages: Optional[List[_InputMessageParamModel]] = None
    system: Optional[Union[StrictStr, List[Any]]] = None


GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS = (
    "gen_ai.usage.cache_creation.input_tokens"
)
GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS = "gen_ai.usage.cache_read.input_tokens"


class UsageTokens(_ExtractorModel):
    input_tokens: Optional[StrictInt] = None
    output_tokens: Optional[StrictInt] = None
    cache_creation_input_tokens: Optional[StrictInt] = None
    cache_read_input_tokens: Optional[StrictInt] = None


class _UsageModel(_ExtractorModel):
    input_tokens: Optional[StrictInt] = None
    output_tokens: Optional[StrictInt] = None
    cache_creation_input_tokens: Optional[StrictInt] = None
    cache_read_input_tokens: Optional[StrictInt] = None


class _MessageResultModel(_ExtractorModel):
    role: Optional[StrictStr] = None
    content: List[Any] = Field(default_factory=list)
    stop_reason: Optional[StrictStr] = None
    model: Optional[StrictStr] = None
    id: Optional[StrictStr] = None
    usage: Optional[_UsageModel] = None


def _rebuild_model(model_type: type[BaseModel]) -> None:
    if _PYDANTIC_V2:
        model_type.model_rebuild(_types_namespace=globals())
    else:
        update_forward_refs = getattr(model_type, "update_forward_refs")
        update_forward_refs(**globals())


for _model_type in (
    _InputMessageParamModel,
    MessageRequestParams,
    UsageTokens,
    _UsageModel,
    _MessageResultModel,
):
    _rebuild_model(_model_type)


def _validate_model(
    model_type: type[ModelT], value: object, context: str
) -> ModelT | None:
    try:
        if _PYDANTIC_V2:
            return model_type.model_validate(value)
        if isinstance(value, Mapping):
            parse_obj = getattr(model_type, "parse_obj")
            return parse_obj(value)
        from_orm = getattr(model_type, "from_orm")
        return from_orm(value)
    except ValidationError:
        _logger.debug(
            "Anthropic messages extractor validation failed for %s",
            context,
            exc_info=True,
        )
        return None


def _validate_usage(usage: object) -> _UsageModel | None:
    return _validate_model(_UsageModel, usage, "usage payload")


def _validate_message_result(result: object) -> _MessageResultModel | None:
    return _validate_model(_MessageResultModel, result, "message payload")


def extract_usage_tokens(
    usage: Usage | MessageDeltaUsage | _UsageModel | None,
) -> UsageTokens:
    if usage is None:
        return UsageTokens()

    validated_usage = _validate_usage(usage)
    if validated_usage is None:
        return UsageTokens()

    input_tokens = validated_usage.input_tokens
    output_tokens = validated_usage.output_tokens
    cache_creation_input_tokens = validated_usage.cache_creation_input_tokens
    cache_read_input_tokens = validated_usage.cache_read_input_tokens

    if (
        input_tokens is None
        and cache_creation_input_tokens is None
        and cache_read_input_tokens is None
    ):
        total_input_tokens = None
    else:
        total_input_tokens = (
            (input_tokens or 0)
            + (cache_creation_input_tokens or 0)
            + (cache_read_input_tokens or 0)
        )

    return UsageTokens(
        input_tokens=total_input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=cache_creation_input_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
    )


def get_input_messages(
    messages: Iterable[MessageParam] | list[_InputMessageParamModel] | None,
) -> list[InputMessage]:
    if messages is None:
        return []
    result: list[InputMessage] = []
    for message in messages:
        validated_message = (
            message
            if isinstance(message, _InputMessageParamModel)
            else _validate_model(
                _InputMessageParamModel, message, "input message"
            )
        )
        if validated_message is None or validated_message.role is None:
            continue
        role = validated_message.role
        parts = convert_content_to_parts(validated_message.content)
        result.append(InputMessage(role=role, parts=parts))
    return result


def get_system_instruction(
    system: str | Iterable[TextBlockParam] | list[Any] | None,
) -> list[MessagePart]:
    if system is None:
        return []
    return convert_content_to_parts(system)


def get_output_messages_from_message(
    message: Message | _MessageResultModel | None,
) -> list[OutputMessage]:
    if message is None:
        return []

    validated_message = (
        message
        if isinstance(message, _MessageResultModel)
        else _validate_message_result(message)
    )
    if validated_message is None:
        return []

    parts = convert_content_to_parts(validated_message.content)
    finish_reason = normalize_finish_reason(validated_message.stop_reason)
    return [
        OutputMessage(
            role=validated_message.role or "assistant",
            parts=parts,
            finish_reason=finish_reason or "",
        )
    ]


def set_invocation_response_attributes(
    invocation: LLMInvocation,
    message: Message | None,
    capture_content: bool,
) -> None:
    if message is None:
        return

    validated_message = _validate_message_result(message)
    if validated_message is None:
        return

    invocation.response_model_name = validated_message.model
    invocation.response_id = validated_message.id

    finish_reason = normalize_finish_reason(validated_message.stop_reason)
    if finish_reason:
        invocation.finish_reasons = [finish_reason]

    tokens = extract_usage_tokens(validated_message.usage)
    invocation.input_tokens = tokens.input_tokens
    invocation.output_tokens = tokens.output_tokens
    if tokens.cache_creation_input_tokens is not None:
        invocation.attributes[GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS] = (
            tokens.cache_creation_input_tokens
        )
    if tokens.cache_read_input_tokens is not None:
        invocation.attributes[GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS] = (
            tokens.cache_read_input_tokens
        )

    if capture_content:
        invocation.output_messages = get_output_messages_from_message(
            validated_message
        )


def extract_params(  # pylint: disable=too-many-locals
    *,
    max_tokens: int | None = None,
    messages: Iterable[MessageParam] | None = None,
    model: str | None = None,
    metadata: MetadataParam | None = None,
    service_tier: str | None = None,
    stop_sequences: Sequence[str] | None = None,
    stream: bool | None = None,
    system: str | Iterable[TextBlockParam] | None = None,
    temperature: float | None = None,
    thinking: ThinkingConfigParam | None = None,
    tool_choice: ToolChoiceParam | None = None,
    tools: Iterable[ToolUnionParam] | None = None,
    top_k: int | None = None,
    top_p: float | None = None,
    extra_headers: Mapping[str, str] | None = None,
    extra_query: Mapping[str, object] | None = None,
    extra_body: object | None = None,
    timeout: float | httpx.Timeout | None = None,
    **_kwargs: object,
) -> MessageRequestParams:
    params = _validate_model(
        MessageRequestParams,
        {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "stop_sequences": stop_sequences,
            "stream": stream,
            "messages": messages,
            "system": system,
        },
        "request parameters",
    )
    return params or MessageRequestParams()


def _set_server_address_and_port(
    client_instance: "Messages",
    attributes: dict[str, AttributeValue | None],
) -> None:
    base_url = client_instance._client.base_url
    host = base_url.host
    if host:
        attributes[ServerAttributes.SERVER_ADDRESS] = host

    port = base_url.port
    if port and port != 443 and port > 0:
        attributes[ServerAttributes.SERVER_PORT] = port


def get_llm_request_attributes(
    params: MessageRequestParams, client_instance: "Messages"
) -> dict[str, AttributeValue]:
    attributes: dict[str, AttributeValue | None] = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.CHAT.value,
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.ANTHROPIC.value,  # pyright: ignore[reportDeprecated]
        GenAIAttributes.GEN_AI_REQUEST_MODEL: params.model,
        GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS: params.max_tokens,
        GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE: params.temperature,
        GenAIAttributes.GEN_AI_REQUEST_TOP_P: params.top_p,
        GenAIAttributes.GEN_AI_REQUEST_TOP_K: params.top_k,
        GenAIAttributes.GEN_AI_REQUEST_STOP_SEQUENCES: params.stop_sequences,
    }
    _set_server_address_and_port(client_instance, attributes)
    return {k: v for k, v in attributes.items() if v is not None}
