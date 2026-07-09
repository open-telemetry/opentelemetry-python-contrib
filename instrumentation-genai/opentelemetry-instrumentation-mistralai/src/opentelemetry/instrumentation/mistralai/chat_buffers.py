# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any


class ToolCallBuffer:
    """Accumulates a single tool call across streamed chunks.

    Unlike OpenAI/Groq, mistralai typically emits a tool call's name and
    arguments within a single delta, but the fields are appended defensively to
    tolerate fragmented deltas.
    """

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

    def append_arguments(self, arguments: Any) -> None:
        if arguments is None:
            return
        if not isinstance(arguments, str):
            arguments = str(arguments)
        self.arguments.append(arguments)


class ChoiceBuffer:
    def __init__(self, index: int) -> None:
        self.index: int = index
        self.finish_reason: str | None = None
        self.text_content: list[str] = []
        self.tool_calls_buffers: list[ToolCallBuffer | None] = []

    def append_text_content(self, content: str) -> None:
        self.text_content.append(content)

    def append_tool_call(self, tool_call: Any) -> None:
        idx = getattr(tool_call, "index", None)
        if idx is None:
            idx = len(self.tool_calls_buffers)
        for _ in range(len(self.tool_calls_buffers), idx + 1):
            self.tool_calls_buffers.append(None)

        function = getattr(tool_call, "function", None)
        buffer = self.tool_calls_buffers[idx]
        if buffer is None:
            buffer = ToolCallBuffer(
                idx,
                getattr(tool_call, "id", None),
                getattr(function, "name", None) if function else None,
            )
            self.tool_calls_buffers[idx] = buffer

        if function is not None:
            buffer.append_arguments(getattr(function, "arguments", None))
