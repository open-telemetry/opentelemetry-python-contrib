# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, AsyncIterator, Optional

from opentelemetry.util.genai.invocation import InferenceInvocation
from opentelemetry.util.genai.stream import (
    AsyncStreamWrapper,
    SyncStreamWrapper,
)
from opentelemetry.util.genai.types import OutputMessage, Text


def _event_text(chunk: Any) -> str:
    """Return the text payload for a Replicate ``output`` SSE event.

    Replicate ``ServerSentEvent`` objects stringify to their ``data`` for
    ``output`` events and to an empty string for other event types
    (``logs``/``error``/``done``), so ``str(chunk)`` yields only generated text.
    """
    return str(chunk)


class _ReplicateStreamMixin:
    """Replicate-specific hooks shared by sync and async stream wrappers."""

    _self_invocation: InferenceInvocation
    _self_capture_content: bool
    _self_text_chunks: list[str]

    def _process_chunk(self, chunk: Any) -> None:
        text = _event_text(chunk)
        if text:
            self._self_text_chunks.append(text)

    def _set_output_messages(self) -> None:
        if not self._self_capture_content:  # optimization
            return
        content = "".join(self._self_text_chunks)
        if not content:
            return
        self._self_invocation.output_messages = [
            OutputMessage(
                role="assistant",
                parts=[Text(content=content)],
                finish_reason="stop",
            )
        ]

    def _on_stream_end(self) -> None:
        self._cleanup()

    def _on_stream_error(self, error: BaseException) -> None:
        self._cleanup(error)

    def _cleanup(self, error: Optional[BaseException] = None) -> None:
        # Replicate streaming responses carry no token usage or response id.
        self._self_invocation.finish_reasons = ["stop"]
        self._set_output_messages()

        if error:
            self._self_invocation.fail(error)
        else:
            self._self_invocation.stop()


class ReplicateStreamWrapper(
    _ReplicateStreamMixin,
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
        self._self_text_chunks = []


class _AsyncGeneratorCloseAdapter:
    """Adapt an async generator (``aclose``) to the ``close`` API.

    ``AsyncStreamWrapper`` expects the wrapped stream to expose an awaitable
    ``close()``. Replicate's ``async_stream`` returns a native async generator,
    which exposes ``aclose()`` instead, so this thin adapter bridges the two
    without reimplementing iteration.
    """

    def __init__(self, agen: AsyncIterator[Any]) -> None:
        self._agen = agen

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._agen.__aiter__()

    async def close(self) -> None:
        aclose = getattr(self._agen, "aclose", None)
        if aclose is not None:
            await aclose()


class ReplicateAsyncStreamWrapper(
    _ReplicateStreamMixin,
    AsyncStreamWrapper[Any],
):
    def __init__(
        self,
        stream: AsyncIterator[Any],
        invocation: InferenceInvocation,
        capture_content: bool,
    ) -> None:
        super().__init__(_AsyncGeneratorCloseAdapter(stream))
        self._self_invocation = invocation
        self._self_capture_content = capture_content
        self._self_text_chunks = []


__all__ = [
    "ReplicateAsyncStreamWrapper",
    "ReplicateStreamWrapper",
]
