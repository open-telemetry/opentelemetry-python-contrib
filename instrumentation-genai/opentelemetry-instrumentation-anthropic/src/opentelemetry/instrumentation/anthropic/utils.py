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

"""Utility functions for Anthropic instrumentation."""

from __future__ import annotations

import base64
import json
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
    Blob,
    InputMessage,
    MessagePart,
    OutputMessage,
    Reasoning,
    Text,
    ToolCall,
    ToolCallResponse,
)
from opentelemetry.util.types import AttributeValue

if TYPE_CHECKING:
    from anthropic.resources.messages import Messages


@dataclass
class MessageRequestParams:
    """Parameters extracted from Anthropic Messages API calls."""

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


def _normalize_finish_reason(stop_reason: str | None) -> str | None:
    """Map Anthropic stop reasons to GenAI semantic convention values."""
    if stop_reason is None:
        return None

    normalized = {
        "end_turn": "stop",
        "stop_sequence": "stop",
        "max_tokens": "length",
        "tool_use": "tool_calls",
    }.get(stop_reason)
    return normalized or stop_reason


def _get_field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return cast(dict[str, Any], obj).get(name, default)
    return getattr(obj, name, default)


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def extract_usage_tokens(
    usage: Any | None,
) -> tuple[int | None, int | None, int | None, int | None]:
    """Extract Anthropic usage fields and compute semconv input tokens."""
    if usage is None:
        return None, None, None, None

    input_tokens = _as_int(getattr(usage, "input_tokens", None))
    cache_creation_input_tokens = _as_int(
        getattr(usage, "cache_creation_input_tokens", None)
    )
    cache_read_input_tokens = _as_int(
        getattr(usage, "cache_read_input_tokens", None)
    )
    output_tokens = _as_int(getattr(usage, "output_tokens", None))

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


def _to_dict_if_possible(value: Any) -> Any:
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    if hasattr(value, "to_dict"):
        to_dict = getattr(value, "to_dict")
        if callable(to_dict):
            try:
                return to_dict()
            except Exception:  # pylint: disable=broad-exception-caught
                return value
    if hasattr(value, "__dict__"):
        return cast(dict[str, Any], dict(value.__dict__))
    return value


def _decode_base64(data: str | None) -> bytes | None:
    if not data:
        return None
    try:
        return base64.b64decode(data)
    except Exception:  # pylint: disable=broad-exception-caught
        return None


def _convert_content_block_to_part(content_block: Any) -> MessagePart | None:
    block_type = _as_str(_get_field(content_block, "type"))
    if block_type is None:
        return None

    result: MessagePart | None = None
    if block_type == "text":
        text = _as_str(_get_field(content_block, "text"))
        result = Text(content=text or "")
    elif block_type == "tool_use":
        result = ToolCall(
            arguments=_to_dict_if_possible(_get_field(content_block, "input")),
            name=_as_str(_get_field(content_block, "name")) or "",
            id=_as_str(_get_field(content_block, "id")),
        )
    elif block_type == "tool_result":
        result = ToolCallResponse(
            response=_to_dict_if_possible(
                _get_field(content_block, "content")
            ),
            id=_as_str(_get_field(content_block, "tool_use_id")),
        )
    elif block_type in ("thinking", "redacted_thinking"):
        content = _as_str(_get_field(content_block, "thinking"))
        if content is None:
            content = _as_str(_get_field(content_block, "data"))
        result = Reasoning(content=content or "")
    elif block_type in ("image", "audio", "video", "document", "file"):
        source = _get_field(content_block, "source")
        mime_type = _as_str(_get_field(source, "media_type"))
        raw_data = _as_str(_get_field(source, "data"))
        data = _decode_base64(raw_data)
        if data is not None:
            modality = _as_str(_get_field(content_block, "type")) or "file"
            result = Blob(mime_type=mime_type, modality=modality, content=data)
    else:
        result = _to_dict_if_possible(content_block)

    return result


def _convert_content_to_parts(content: Any) -> list[MessagePart]:
    if content is None:
        return []
    if isinstance(content, str):
        return [Text(content=content)]
    if isinstance(content, list):
        parts: list[MessagePart] = []
        for item in cast(list[Any], content):
            part = _convert_content_block_to_part(item)
            if part is not None:
                parts.append(part)
        return parts
    part = _convert_content_block_to_part(content)
    return [part] if part is not None else []


def get_input_messages(messages: Any) -> list[InputMessage]:
    if not isinstance(messages, list):
        return []

    result: list[InputMessage] = []
    for message in cast(list[Any], messages):
        role = _as_str(_get_field(message, "role")) or "user"
        parts = _convert_content_to_parts(_get_field(message, "content"))
        result.append(InputMessage(role=role, parts=parts))
    return result


def get_system_instruction(system: Any) -> list[MessagePart]:
    return _convert_content_to_parts(system)


def get_output_messages_from_message(message: Any) -> list[OutputMessage]:
    if message is None:
        return []

    parts = _convert_content_to_parts(_get_field(message, "content"))
    finish_reason = _normalize_finish_reason(
        _get_field(message, "stop_reason")
    )
    return [
        OutputMessage(
            role=_as_str(_get_field(message, "role")) or "assistant",
            parts=parts,
            finish_reason=finish_reason or "",
        )
    ]


def create_stream_block_state(content_block: Any) -> dict[str, Any]:
    block_type = _as_str(_get_field(content_block, "type")) or "text"
    state: dict[str, Any] = {"type": block_type}
    if block_type == "text":
        state["text"] = _as_str(_get_field(content_block, "text")) or ""
    elif block_type == "tool_use":
        state["id"] = _as_str(_get_field(content_block, "id"))
        state["name"] = _as_str(_get_field(content_block, "name")) or ""
        state["input"] = _get_field(content_block, "input")
        state["input_json"] = ""
    elif block_type in ("thinking", "redacted_thinking"):
        state["thinking"] = (
            _as_str(_get_field(content_block, "thinking")) or ""
        )
    return state


def update_stream_block_state(state: dict[str, Any], delta: Any) -> None:
    delta_type = _as_str(_get_field(delta, "type"))
    if delta_type == "text_delta":
        state["type"] = "text"
        state["text"] = (
            f"{state.get('text', '')}"
            f"{_as_str(_get_field(delta, 'text')) or ''}"
        )
        return
    if delta_type == "input_json_delta":
        state["type"] = "tool_use"
        state["input_json"] = (
            f"{state.get('input_json', '')}"
            f"{_as_str(_get_field(delta, 'partial_json')) or ''}"
        )
        return
    if delta_type == "thinking_delta":
        state["type"] = "thinking"
        state["thinking"] = (
            f"{state.get('thinking', '')}"
            f"{_as_str(_get_field(delta, 'thinking')) or ''}"
        )


def stream_block_state_to_part(state: dict[str, Any]) -> MessagePart | None:
    block_type = _as_str(state.get("type"))
    if block_type == "text":
        return Text(content=_as_str(state.get("text")) or "")
    if block_type == "tool_use":
        arguments: Any = state.get("input")
        partial_json = _as_str(state.get("input_json"))
        if partial_json:
            try:
                arguments = json.loads(partial_json)
            except ValueError:
                arguments = partial_json
        return ToolCall(
            arguments=arguments,
            name=_as_str(state.get("name")) or "",
            id=_as_str(state.get("id")),
        )
    if block_type in ("thinking", "redacted_thinking"):
        return Reasoning(content=_as_str(state.get("thinking")) or "")
    return None


# Use parameter signature from
# https://github.com/anthropics/anthropic-sdk-python/blob/9b5ab24ba17bcd5e762e5a5fd69bb3c17b100aaa/src/anthropic/resources/messages/messages.py#L896
# https://github.com/anthropics/anthropic-sdk-python/blob/9b5ab24ba17bcd5e762e5a5fd69bb3c17b100aaa/src/anthropic/resources/messages/messages.py#L963
# to handle named vs positional args robustly
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
    """Extract relevant parameters from Anthropic Messages API arguments."""
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


def set_server_address_and_port(
    client_instance: "Messages", attributes: dict[str, Any]
) -> None:
    """Extract server address and port from the Anthropic client instance."""
    base_client = getattr(client_instance, "_client", None)
    base_url = getattr(base_client, "base_url", None)
    if not base_url:
        return

    port: Optional[int] = None
    if hasattr(base_url, "host"):
        # httpx.URL object
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
    """Extract LLM request attributes from MessageRequestParams.

    Returns a dictionary of OpenTelemetry semantic convention attributes for LLM requests.
    The attributes follow the GenAI semantic conventions (gen_ai.*) and server semantic
    conventions (server.*) as defined in the OpenTelemetry specification.

    GenAI attributes included:
    - gen_ai.operation.name: The operation name (e.g., "chat")
    - gen_ai.system: The GenAI system identifier (e.g., "anthropic")
    - gen_ai.request.model: The model identifier
    - gen_ai.request.max_tokens: Maximum tokens in the request
    - gen_ai.request.temperature: Sampling temperature
    - gen_ai.request.top_p: Top-p sampling parameter
    - gen_ai.request.top_k: Top-k sampling parameter
    - gen_ai.request.stop_sequences: Stop sequences for the request

    Server attributes included (if available):
    - server.address: The server hostname
    - server.port: The server port (if not default 443)

    Only non-None values are included in the returned dictionary.
    """
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

    set_server_address_and_port(client_instance, attributes)

    # Filter out None values
    return {k: v for k, v in attributes.items() if v is not None}
