# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from openai.types.chat.chat_completion_chunk import ChoiceDeltaToolCall


class ToolCallBuffer:
    def __init__(
        self,
        index: int,
        tool_call_id: str | None,
        function_name: str | None,
    ) -> None:
        self.index: int = index
        self.function_name: str | None = function_name
        self.tool_call_id: str | None = tool_call_id
        self.arguments: list[str] = []

    def append_arguments(self, arguments: str | None) -> None:
        if arguments is not None:
            self.arguments.append(arguments)


class ChoiceBuffer:
    def __init__(self, index: int) -> None:
        self.index: int = index
        self.finish_reason: str | None = None
        self.text_content: list[str] = []
        self.tool_calls_buffers: list[ToolCallBuffer | None] = []

    def append_text_content(self, content: str) -> None:
        self.text_content.append(content)

    def append_tool_call(self, tool_call: ChoiceDeltaToolCall) -> None:
        idx = tool_call.index
        for _ in range(len(self.tool_calls_buffers), idx + 1):
            self.tool_calls_buffers.append(None)

        function = tool_call.function
        buffer = self.tool_calls_buffers[idx]
        if buffer is None:
            buffer = ToolCallBuffer(
                idx,
                tool_call.id,
                function.name if function else None,
            )
            self.tool_calls_buffers[idx] = buffer

        if function:
            buffer.append_arguments(function.arguments)
