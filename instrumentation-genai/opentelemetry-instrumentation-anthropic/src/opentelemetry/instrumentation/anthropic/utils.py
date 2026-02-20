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

"""Shared helper utilities for Anthropic instrumentation."""

from __future__ import annotations

import base64
import json
from typing import Any, cast

from opentelemetry.util.genai.types import (
    Blob,
    MessagePart,
    Reasoning,
    Text,
    ToolCall,
    ToolCallResponse,
)


def normalize_finish_reason(stop_reason: str | None) -> str | None:
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


def as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


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


def convert_content_to_parts(content: Any) -> list[MessagePart]:
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
