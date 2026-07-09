# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, Optional

from opentelemetry.util.genai.invocation import InferenceInvocation
from opentelemetry.util.genai.stream import (
    AsyncStreamWrapper,
    SyncStreamWrapper,
)
from opentelemetry.util.genai.types import OutputMessage, Text


class _CompletionStreamMixin:
    """Stream hooks for the text ``completions.create`` API.

    writerai ``CompletionChunk`` objects only carry a ``value: str`` field --
    they have no ``choices``, ``model``, ``usage`` or per-chunk finish reason
    (unlike chat completion chunks). The streamed text is therefore accumulated
    into a single output message, mirroring the non-streaming completion
    handling, which likewise records only ``choices[].text`` with a ``"stop"``
    finish reason.
    """

    _self_invocation: InferenceInvocation
    _self_capture_content: bool
    _self_text_parts: list[str]

    def _process_chunk(self, chunk: Any) -> None:
        value = getattr(chunk, "value", None)
        if isinstance(value, str) and value:
            self._self_text_parts.append(value)

    def _on_stream_end(self) -> None:
        self._cleanup()

    def _on_stream_error(self, error: BaseException) -> None:
        self._cleanup(error)

    def _cleanup(self, error: Optional[BaseException] = None) -> None:
        if self._self_capture_content and self._self_text_parts:
            self._self_invocation.output_messages = [
                OutputMessage(
                    role="assistant",
                    finish_reason="stop",
                    parts=[Text(content="".join(self._self_text_parts))],
                )
            ]
        if error:
            self._self_invocation.fail(error)
        else:
            self._self_invocation.stop()


class CompletionStreamWrapper(
    _CompletionStreamMixin,
    SyncStreamWrapper[Any],
):
    def __init__(
        self,
        stream: Any,
        invocation: InferenceInvocation,
        capture_content: bool,
    ) -> None:
        super().__init__(stream)
        self._self_invocation = invocation
        self._self_capture_content = capture_content
        self._self_text_parts = []


class AsyncCompletionStreamWrapper(
    _CompletionStreamMixin,
    AsyncStreamWrapper[Any],
):
    def __init__(
        self,
        stream: Any,
        invocation: InferenceInvocation,
        capture_content: bool,
    ) -> None:
        super().__init__(stream)
        self._self_invocation = invocation
        self._self_capture_content = capture_content
        self._self_text_parts = []


__all__ = [
    "AsyncCompletionStreamWrapper",
    "CompletionStreamWrapper",
]
