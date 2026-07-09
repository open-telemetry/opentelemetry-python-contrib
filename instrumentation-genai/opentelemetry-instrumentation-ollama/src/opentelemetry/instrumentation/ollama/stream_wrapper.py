# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Streaming wrappers for ollama chat/generate responses.

ollama returns a plain (async) generator when ``stream=True``. The sync
generator exposes ``close()``; the async generator exposes ``aclose()`` instead
of ``close()``, so the async wrapper adapts the stream to the ``close()`` contract
expected by :class:`opentelemetry.util.genai.stream.AsyncStreamWrapper`.

The wrappers reuse the shared ``SyncStreamWrapper``/``AsyncStreamWrapper`` base
classes for iteration, close/context-manager, and finalization behavior. Only
ollama-specific chunk accumulation and invocation finalization live here.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Iterator, Literal

from opentelemetry.util.genai.invocation import InferenceInvocation
from opentelemetry.util.genai.stream import (
    AsyncStreamWrapper,
    SyncStreamWrapper,
)
from opentelemetry.util.genai.types import OutputMessage, Text

from .utils import _get, _as_int

# Operation kinds handled by the streaming wrappers.
_CHAT: Literal["chat"] = "chat"
_GENERATE: Literal["generate"] = "generate"


class _OllamaStreamMixin:
    """ollama-specific chunk accumulation shared by sync and async wrappers."""

    _self_invocation: InferenceInvocation
    _self_capture_content: bool
    _self_kind: str
    _self_content: list[str]
    _self_role: str | None
    _self_finish_reason: str | None
    _self_model: str | None
    _self_input_tokens: int | None
    _self_output_tokens: int | None

    def _process_chunk(self, chunk: Any) -> None:
        model = _get(chunk, "model")
        if model and not self._self_model:
            self._self_model = str(model)

        done_reason = _get(chunk, "done_reason")
        if done_reason:
            self._self_finish_reason = str(done_reason)

        input_tokens = _as_int(_get(chunk, "prompt_eval_count"))
        if input_tokens is not None:
            self._self_input_tokens = input_tokens

        output_tokens = _as_int(_get(chunk, "eval_count"))
        if output_tokens is not None:
            self._self_output_tokens = output_tokens

        if self._self_kind == _CHAT:
            message = _get(chunk, "message")
            if message is not None:
                role = _get(message, "role")
                if role:
                    self._self_role = str(role)
                content = _get(message, "content")
                if isinstance(content, str) and content:
                    self._self_content.append(content)
        else:
            content = _get(chunk, "response")
            if isinstance(content, str) and content:
                self._self_content.append(content)

    def _on_stream_end(self) -> None:
        self._finalize()

    def _on_stream_error(self, error: BaseException) -> None:
        self._finalize(error)

    def _finalize(self, error: BaseException | None = None) -> None:
        invocation = self._self_invocation
        invocation.response_model_name = self._self_model
        if self._self_input_tokens is not None:
            invocation.input_tokens = self._self_input_tokens
        if self._self_output_tokens is not None:
            invocation.output_tokens = self._self_output_tokens
        finish_reason = self._self_finish_reason or "stop"
        invocation.finish_reasons = [finish_reason]

        if self._self_capture_content and self._self_content:
            invocation.output_messages = [
                OutputMessage(
                    role=self._self_role or "assistant",
                    parts=[Text(content="".join(self._self_content))],
                    finish_reason=finish_reason,
                )
            ]

        if error is not None:
            invocation.fail(error)
        else:
            invocation.stop()

    def _init_state(
        self,
        invocation: InferenceInvocation,
        capture_content: bool,
        kind: str,
    ) -> None:
        self._self_invocation = invocation
        self._self_capture_content = capture_content
        self._self_kind = kind
        self._self_content = []
        self._self_role = None
        self._self_finish_reason = None
        self._self_model = None
        self._self_input_tokens = None
        self._self_output_tokens = None


class OllamaSyncStreamWrapper(
    _OllamaStreamMixin,
    SyncStreamWrapper[Any],
):
    def __init__(
        self,
        stream: Iterator[Any],
        invocation: InferenceInvocation,
        capture_content: bool,
        kind: str,
    ) -> None:
        super().__init__(stream)
        self._init_state(invocation, capture_content, kind)


class _AsyncCloseAdapter:
    """Adapt an ollama async generator to expose async ``close()``.

    ollama's streaming return is an async generator, which provides ``aclose()``
    but not ``close()``. :class:`AsyncStreamWrapper` calls ``close()`` on the
    wrapped stream, so this adapter forwards it to ``aclose()`` while preserving
    async iteration.
    """

    def __init__(self, stream: AsyncIterator[Any]) -> None:
        self._stream = stream

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._stream.__aiter__()

    async def close(self) -> None:
        aclose = getattr(self._stream, "aclose", None)
        if aclose is not None:
            await aclose()


class OllamaAsyncStreamWrapper(
    _OllamaStreamMixin,
    AsyncStreamWrapper[Any],
):
    def __init__(
        self,
        stream: AsyncIterator[Any],
        invocation: InferenceInvocation,
        capture_content: bool,
        kind: str,
    ) -> None:
        super().__init__(_AsyncCloseAdapter(stream))
        self._init_state(invocation, capture_content, kind)


__all__ = [
    "OllamaAsyncStreamWrapper",
    "OllamaSyncStreamWrapper",
]
