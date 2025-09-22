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

import logging

from google.genai import types as genai_types
from opentelemetry.util.genai.types import (
    InputMessage,
    OutputMessage,
    MessagePart,
    FinishReason,
    Text,
    ToolCall,
    ToolCallResponse,
)

from .message_models import (
    # BlobPart,
    # FileDataPart,
    Role,
)

_logger = logging.getLogger(__name__)

def to_input_messages(
    *,
    contents: list[genai_types.Content],
) -> list[InputMessage]:
    return [_to_input_message(content) for content in contents])

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

def to_system_instruction(
    *,
    content: genai_types.Content,
) -> InputMessage:
    return _to_input_message(content)

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

    # if data := part.inline_data:  # TODO ???
    #     return BlobPart(mime_type=data.mime_type or "", data=data.data or b"")

    # if data := part.file_data: # TODO ???
    #     return FileDataPart(
    #         mime_type=data.mime_type or "", file_uri=data.file_uri or ""
    #     )

    if call := part.function_call:
        return ToolCall(
            id=call.id or tool_call_id(call.name), # TODO ???
            name=call.name or "",
            arguments=call.args,
        )

    if response := part.function_response:
        return ToolCallResponse(
            id=response.id or tool_call_id(response.name), # TODO ???
            response=response.response,
        )

    _logger.info("Unknown part dropped from telemetry %s", part)
    return None

def _to_role(role: str | None) -> Role | str:
    if role == "user":
        return Role.USER
    if role == "model":
        return Role.ASSISTANT
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
