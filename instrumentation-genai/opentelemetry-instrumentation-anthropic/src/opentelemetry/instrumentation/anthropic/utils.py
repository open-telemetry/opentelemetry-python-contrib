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
from dataclasses import dataclass
from typing import TYPE_CHECKING

from anthropic.types import (
    InputJSONDelta,
    RedactedThinkingBlock,
    ServerToolUseBlock,
    TextBlock,
    TextDelta,
    ThinkingBlock,
    ThinkingDelta,
    ToolUseBlock,
    WebSearchToolResultBlock,
)

from opentelemetry.util.genai.types import (
    Blob,
    MessagePart,
    Reasoning,
    Text,
    ToolCall,
    ToolCallResponse,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from anthropic.types import (
        ContentBlock,
        ContentBlockParam,
        RawContentBlockDelta,
    )


@dataclass
class StreamBlockState:
    type: str
    text: str = ""
    tool_id: str | None = None
    tool_name: str = ""
    tool_input: dict[str, object] | None = None
    input_json: str = ""
    thinking: str = ""


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


def _decode_base64(data: str) -> bytes | None:
    try:
        return base64.b64decode(data)
    except Exception:  # pylint: disable=broad-exception-caught
        return None


def _extract_base64_blob(source: object, modality: str) -> Blob | None:
    """Extract a Blob from a base64-encoded source dict."""
    if not isinstance(source, dict):
        return None
    # source is a TypedDict (e.g. Base64ImageSourceParam) narrowed to dict;
    # pyright cannot infer value types from isinstance-narrowed dicts.
    data: object = source.get("data")  # type: ignore[reportUnknownMemberType]
    if not isinstance(data, str):
        return None
    decoded = _decode_base64(data)
    if decoded is None:
        return None
    media_type: object = source.get("media_type")  # type: ignore[reportUnknownMemberType]
    return Blob(
        mime_type=media_type if isinstance(media_type, str) else None,
        modality=modality,
        content=decoded,
    )


def _convert_dict_block_to_part(
    block: Mapping[str, object],
) -> MessagePart | None:
    """Convert a request-param content block (TypedDict/dict) to a MessagePart."""
    block_type = block.get("type")

    if block_type == "text":
        text = block.get("text")
        return Text(content=str(text) if text is not None else "")

    if block_type == "tool_use":
        inp = block.get("input")
        return ToolCall(
            arguments=inp if isinstance(inp, dict) else None,
            name=str(block.get("name", "")),
            id=str(block.get("id", "")),
        )

    if block_type == "tool_result":
        return ToolCallResponse(
            response=block.get("content"),
            id=str(block.get("tool_use_id", "")),
        )

    if block_type in ("thinking", "redacted_thinking"):
        thinking = block.get("thinking") or block.get("data")
        return Reasoning(content=str(thinking) if thinking is not None else "")

    if block_type in ("image", "audio", "video", "document", "file"):
        return _extract_base64_blob(block.get("source"), str(block_type))

    return None


def _convert_content_block_to_part(
    block: ContentBlock | ContentBlockParam,
) -> MessagePart | None:
    """Convert an Anthropic content block to a MessagePart."""
    if isinstance(block, TextBlock):
        return Text(content=block.text)

    if isinstance(block, (ToolUseBlock, ServerToolUseBlock)):
        return ToolCall(arguments=block.input, name=block.name, id=block.id)

    if isinstance(block, (ThinkingBlock, RedactedThinkingBlock)):
        content = (
            block.thinking if isinstance(block, ThinkingBlock) else block.data
        )
        return Reasoning(content=content)

    if isinstance(block, WebSearchToolResultBlock):
        return ToolCallResponse(
            response=block.model_dump().get("content"),
            id=block.tool_use_id,
        )

    # ContentBlockParam variants are TypedDicts (dicts at runtime);
    # newer SDK versions may add Pydantic block types not handled above.
    if isinstance(block, dict):
        return _convert_dict_block_to_part(block)

    return None


def convert_content_to_parts(
    content: str | Iterable[ContentBlock | ContentBlockParam] | None,
) -> list[MessagePart]:
    if content is None:
        return []
    if isinstance(content, str):
        return [Text(content=content)]
    parts: list[MessagePart] = []
    for item in content:
        part = _convert_content_block_to_part(item)
        if part is not None:
            parts.append(part)
    return parts


def create_stream_block_state(content_block: ContentBlock) -> StreamBlockState:
    if isinstance(content_block, TextBlock):
        return StreamBlockState(type="text", text=content_block.text)

    if isinstance(content_block, (ToolUseBlock, ServerToolUseBlock)):
        return StreamBlockState(
            type="tool_use",
            tool_id=content_block.id,
            tool_name=content_block.name,
            tool_input=content_block.input,
        )

    if isinstance(content_block, ThinkingBlock):
        return StreamBlockState(
            type="thinking", thinking=content_block.thinking
        )

    if isinstance(content_block, RedactedThinkingBlock):
        return StreamBlockState(type="redacted_thinking")

    return StreamBlockState(type=content_block.type)


def update_stream_block_state(
    state: StreamBlockState, delta: RawContentBlockDelta
) -> None:
    if isinstance(delta, TextDelta):
        state.type = "text"
        state.text += delta.text
    elif isinstance(delta, InputJSONDelta):
        state.type = "tool_use"
        state.input_json += delta.partial_json
    elif isinstance(delta, ThinkingDelta):
        state.type = "thinking"
        state.thinking += delta.thinking


def stream_block_state_to_part(state: StreamBlockState) -> MessagePart | None:
    if state.type == "text":
        return Text(content=state.text)

    if state.type == "tool_use":
        arguments: str | dict[str, object] | None = state.tool_input
        if state.input_json:
            try:
                arguments = json.loads(state.input_json)
            except ValueError:
                arguments = state.input_json
        return ToolCall(
            arguments=arguments,
            name=state.tool_name,
            id=state.tool_id,
        )

    if state.type in ("thinking", "redacted_thinking"):
        return Reasoning(content=state.thinking)

    return None
