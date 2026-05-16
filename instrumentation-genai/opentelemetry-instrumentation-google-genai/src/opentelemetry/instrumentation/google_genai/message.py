# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from enum import Enum

from google.genai import types as genai_types

from opentelemetry.util.genai.types import (
    Blob,
    FinishReason,
    InputMessage,
    MessagePart,
    OutputMessage,
    Text,
    ToolCallRequest,
    ToolCallResponse,
    Uri,
)


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


_logger = logging.getLogger(__name__)


def to_input_messages(
    *,
    contents: list[genai_types.Content],
) -> list[InputMessage]:
    return [_to_input_message(content) for content in contents]


def to_output_messages(
    *,
    candidates: list[genai_types.Candidate],
) -> list[OutputMessage]:
    def content_to_output_message(
        candidate: genai_types.Candidate,
    ) -> OutputMessage | None:
        if not candidate.content:
            return None

        message = _to_input_message(candidate.content)
        return OutputMessage(
            finish_reason=_to_finish_reason(candidate.finish_reason),
            role=message.role,
            parts=message.parts,
        )

    messages = (
        content_to_output_message(candidate) for candidate in candidates
    )
    return [message for message in messages if message is not None]


def to_system_instructions(
    *,
    content: genai_types.Content,
) -> list[MessagePart]:
    parts = (
        _to_part(part, idx) for idx, part in enumerate(content.parts or [])
    )
    return [part for part in parts if part is not None]


def _to_input_message(
    content: genai_types.Content,
) -> InputMessage:
    parts = (
        _to_part(part, idx) for idx, part in enumerate(content.parts or [])
    )
    return InputMessage(
        role=_to_role(content.role),
        # filter Nones
        parts=[part for part in parts if part is not None],
    )


def _to_part(part: genai_types.Part, idx: int) -> MessagePart | None:
    def tool_call_id(name: str | None) -> str:
        if name:
            return f"{name}_{idx}"
        return f"{idx}"

    if (text := part.text) is not None:
        return Text(content=text)

    if inline_data := part.inline_data:
        mime_type = inline_data.mime_type or ""
        modality = mime_type.split("/")[0] if mime_type else ""
        return Blob(
            mime_type=mime_type,
            modality=modality,
            content=inline_data.data or b"",
        )

    if file_data := part.file_data:
        mime_type = file_data.mime_type or ""
        modality = mime_type.split("/")[0] if mime_type else ""
        return Uri(
            mime_type=mime_type,
            modality=modality,
            uri=file_data.file_uri or "",
        )

    if call := part.function_call:
        return ToolCallRequest(
            id=call.id or tool_call_id(call.name),
            name=call.name or "",
            arguments=call.args,
        )

    if response := part.function_response:
        return ToolCallResponse(
            id=response.id or tool_call_id(response.name),
            response=response.response,
        )

    _logger.info("Unknown part dropped from telemetry %s", part)
    return None


def _to_role(role: str | None) -> str:
    if role == "user":
        return Role.USER.value
    if role == "model":
        return Role.ASSISTANT.value
    return ""


def _to_finish_reason(
    finish_reason: genai_types.FinishReason | None,
) -> FinishReason | str:
    if finish_reason is None:
        return ""
    if (
        finish_reason is genai_types.FinishReason.FINISH_REASON_UNSPECIFIED
        or finish_reason is genai_types.FinishReason.OTHER
    ):
        return "error"
    if finish_reason is genai_types.FinishReason.STOP:
        return "stop"
    if finish_reason is genai_types.FinishReason.MAX_TOKENS:
        return "length"

    # If there is no 1:1 mapping to an OTel preferred enum value, use the exact vertex reason
    return finish_reason.name
