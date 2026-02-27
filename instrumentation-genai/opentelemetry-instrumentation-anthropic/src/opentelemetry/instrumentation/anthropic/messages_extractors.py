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

from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

from anthropic.types import MessageDeltaUsage

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.util.genai.types import (
    InputMessage,
    MessagePart,
    OutputMessage,
)
from opentelemetry.util.types import AttributeValue

from .utils import (
    convert_content_to_parts,
    normalize_finish_reason,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

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


@dataclass
class MessageRequestParams:
    model: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    top_k: int | None = None
    top_p: float | None = None
    stop_sequences: Sequence[str] | None = None
    stream: bool | None = None
    messages: Iterable[MessageParam] | None = None
    system: str | Iterable[TextBlockParam] | None = None


GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS = (
    "gen_ai.usage.cache_creation.input_tokens"
)
GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS = "gen_ai.usage.cache_read.input_tokens"


@dataclass
class UsageTokens:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None


def extract_usage_tokens(
    usage: Usage | MessageDeltaUsage | None,
) -> UsageTokens:
    if usage is None:
        return UsageTokens()

    input_tokens = usage.input_tokens
    output_tokens = usage.output_tokens
    cache_creation_input_tokens = usage.cache_creation_input_tokens
    cache_read_input_tokens = usage.cache_read_input_tokens

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
    messages: Iterable[MessageParam] | None,
) -> list[InputMessage]:
    if messages is None:
        return []
    result: list[InputMessage] = []
    for message in messages:
        role = message["role"]
        parts = convert_content_to_parts(message["content"])
        result.append(InputMessage(role=role, parts=parts))
    return result


def get_system_instruction(
    system: str | Iterable[TextBlockParam] | None,
) -> list[MessagePart]:
    if system is None:
        return []
    return convert_content_to_parts(system)


def get_output_messages_from_message(
    message: Message | None,
) -> list[OutputMessage]:
    if message is None:
        return []

    parts = convert_content_to_parts(message.content)
    finish_reason = normalize_finish_reason(message.stop_reason)
    return [
        OutputMessage(
            role=message.role,
            parts=parts,
            finish_reason=finish_reason or "",
        )
    ]


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
    return MessageRequestParams(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        stop_sequences=stop_sequences,
        stream=stream,
        messages=messages,
        system=system,
    )


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
