# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, AsyncIterator

from opentelemetry.util.genai.invocation import InferenceInvocation
from opentelemetry.util.genai.stream import (
    AsyncStreamWrapper,
    SyncStreamWrapper,
)
from opentelemetry.util.genai.types import OutputMessage, Text

from .chat_buffers import StreamBuffer
from .utils import get_property_value


class _V2ChatStreamMixin:
    """Cohere V2 chat streaming hooks shared by sync and async wrappers.

    Cohere V2 streams a sequence of typed events: ``message-start`` carries the
    response id, ``content-delta`` carries incremental assistant text, and
    ``message-end`` carries the finish reason and token usage.
    """

    _self_invocation: InferenceInvocation
    _self_capture_content: bool
    _self_buffer: StreamBuffer

    def _process_chunk(self, chunk: Any) -> None:
        event_type = get_property_value(chunk, "type")
        if event_type == "message-start":
            response_id = get_property_value(chunk, "id")
            if response_id:
                self._self_buffer.response_id = response_id
        elif event_type == "content-delta":
            delta = get_property_value(chunk, "delta")
            message = get_property_value(delta, "message")
            content = get_property_value(message, "content")
            text = get_property_value(content, "text")
            if isinstance(text, str):
                self._self_buffer.append_text_content(text)
        elif event_type == "message-end":
            delta = get_property_value(chunk, "delta")
            finish_reason = get_property_value(delta, "finish_reason")
            if finish_reason:
                self._self_buffer.finish_reason = finish_reason
            usage = get_property_value(delta, "usage")
            billed_units = get_property_value(usage, "billed_units")
            input_tokens = get_property_value(billed_units, "input_tokens")
            output_tokens = get_property_value(billed_units, "output_tokens")
            if input_tokens is not None:
                self._self_buffer.input_tokens = int(input_tokens)
            if output_tokens is not None:
                self._self_buffer.output_tokens = int(output_tokens)

    def _set_output_messages(self) -> None:
        if not self._self_capture_content:  # optimization
            return
        parts: list[Any] = []
        if self._self_buffer.text_content:
            parts.append(Text(content="".join(self._self_buffer.text_content)))
        self._self_invocation.output_messages = [
            OutputMessage(
                role="assistant",
                finish_reason=self._self_buffer.finish_reason or "error",
                parts=parts,
            )
        ]

    def _on_stream_end(self) -> None:
        self._cleanup()

    def _on_stream_error(self, error: BaseException) -> None:
        self._cleanup(error)

    def _cleanup(self, error: BaseException | None = None) -> None:
        self._self_invocation.response_id = self._self_buffer.response_id
        self._self_invocation.input_tokens = self._self_buffer.input_tokens
        self._self_invocation.output_tokens = self._self_buffer.output_tokens
        if self._self_buffer.finish_reason:
            self._self_invocation.finish_reasons = [
                self._self_buffer.finish_reason
            ]
        self._set_output_messages()
        if error:
            self._self_invocation.fail(error)
        else:
            self._self_invocation.stop()


class V2ChatStreamWrapper(_V2ChatStreamMixin, SyncStreamWrapper[Any]):
    def __init__(
        self,
        stream: Any,
        invocation: InferenceInvocation,
        capture_content: bool,
    ) -> None:
        super().__init__(stream)
        self._self_invocation = invocation
        self._self_capture_content = capture_content
        self._self_buffer = StreamBuffer()


class _AsyncGeneratorCloseAdapter:
    """Adapt an async generator (``aclose``) to the ``close`` API.

    ``AsyncStreamWrapper`` expects the wrapped stream to expose an awaitable
    ``close()``. Cohere's async ``chat_stream`` returns a native async
    generator, which exposes ``aclose()`` instead, so this thin adapter bridges
    the two without reimplementing iteration.
    """

    def __init__(self, agen: AsyncIterator[Any]) -> None:
        self._agen = agen

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._agen.__aiter__()

    async def close(self) -> None:
        aclose = getattr(self._agen, "aclose", None)
        if aclose is not None:
            await aclose()


class AsyncV2ChatStreamWrapper(_V2ChatStreamMixin, AsyncStreamWrapper[Any]):
    def __init__(
        self,
        stream: Any,
        invocation: InferenceInvocation,
        capture_content: bool,
    ) -> None:
        super().__init__(_AsyncGeneratorCloseAdapter(stream))
        self._self_invocation = invocation
        self._self_capture_content = capture_content
        self._self_buffer = StreamBuffer()


__all__ = [
    "AsyncV2ChatStreamWrapper",
    "V2ChatStreamWrapper",
]
