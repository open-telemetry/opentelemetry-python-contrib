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
from typing import TYPE_CHECKING, Any, Optional, Sequence, cast
from urllib.parse import urlparse

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
    _as_str,
    _get_field,
    as_int,
    convert_content_to_parts,
    normalize_finish_reason,
)

if TYPE_CHECKING:
    from anthropic.resources.messages import Messages


@dataclass
class MessageRequestParams:
    model: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    top_k: int | None = None
    top_p: float | None = None
    stop_sequences: Sequence[str] | None = None
    messages: Any | None = None
    system: Any | None = None


GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS = (
    "gen_ai.usage.cache_creation.input_tokens"
)
GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS = "gen_ai.usage.cache_read.input_tokens"


def extract_usage_tokens(
    usage: Any | None,
) -> tuple[int | None, int | None, int | None, int | None]:
    if usage is None:
        return None, None, None, None

    input_tokens = as_int(getattr(usage, "input_tokens", None))
    cache_creation_input_tokens = as_int(
        getattr(usage, "cache_creation_input_tokens", None)
    )
    cache_read_input_tokens = as_int(
        getattr(usage, "cache_read_input_tokens", None)
    )
    output_tokens = as_int(getattr(usage, "output_tokens", None))

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

    return (
        total_input_tokens,
        output_tokens,
        cache_creation_input_tokens,
        cache_read_input_tokens,
    )


def get_input_messages(messages: Any) -> list[InputMessage]:
    if not isinstance(messages, list):
        return []

    result: list[InputMessage] = []
    for message in cast(list[Any], messages):
        role = _as_str(_get_field(message, "role")) or "user"
        parts = convert_content_to_parts(_get_field(message, "content"))
        result.append(InputMessage(role=role, parts=parts))
    return result


def get_system_instruction(system: Any) -> list[MessagePart]:
    return convert_content_to_parts(system)


def get_output_messages_from_message(message: Any) -> list[OutputMessage]:
    if message is None:
        return []

    parts = convert_content_to_parts(_get_field(message, "content"))
    finish_reason = normalize_finish_reason(_get_field(message, "stop_reason"))
    return [
        OutputMessage(
            role=_as_str(_get_field(message, "role")) or "assistant",
            parts=parts,
            finish_reason=finish_reason or "",
        )
    ]


def extract_params(  # pylint: disable=too-many-locals
    *,
    max_tokens: int | None = None,
    messages: Any | None = None,
    model: str | None = None,
    metadata: Any | None = None,
    service_tier: Any | None = None,
    stop_sequences: Sequence[str] | None = None,
    stream: Any | None = None,
    system: Any | None = None,
    temperature: float | None = None,
    thinking: Any | None = None,
    tool_choice: Any | None = None,
    tools: Any | None = None,
    top_k: int | None = None,
    top_p: float | None = None,
    extra_headers: Any | None = None,
    extra_query: Any | None = None,
    extra_body: Any | None = None,
    timeout: Any | None = None,
    **_kwargs: Any,
) -> MessageRequestParams:
    return MessageRequestParams(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        stop_sequences=stop_sequences,
        messages=messages,
        system=system,
    )


def _set_server_address_and_port(
    client_instance: "Messages", attributes: dict[str, Any]
) -> None:
    base_client = getattr(client_instance, "_client", None)
    base_url = getattr(base_client, "base_url", None)
    if not base_url:
        return

    port: Optional[int] = None
    if hasattr(base_url, "host"):
        attributes[ServerAttributes.SERVER_ADDRESS] = base_url.host
        port = getattr(base_url, "port", None)
    elif isinstance(base_url, str):
        url = urlparse(base_url)
        attributes[ServerAttributes.SERVER_ADDRESS] = url.hostname
        port = url.port

    if port and port != 443 and port > 0:
        attributes[ServerAttributes.SERVER_PORT] = port


def get_llm_request_attributes(
    params: MessageRequestParams, client_instance: "Messages"
) -> dict[str, AttributeValue]:
    attributes = {
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
