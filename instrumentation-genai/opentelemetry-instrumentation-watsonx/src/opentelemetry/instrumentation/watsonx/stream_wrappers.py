# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, Mapping, Optional

from opentelemetry.util.genai.invocation import InferenceInvocation
from opentelemetry.util.genai.stream import SyncStreamWrapper
from opentelemetry.util.genai.types import OutputMessage, Text


def _get(obj: Any, key: str) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key)
    return getattr(obj, key, None)


class TextGenerationStreamWrapper(SyncStreamWrapper[Any]):
    """Accumulate a watsonx ``generate_text_stream`` generator.

    The generator yields either plain strings (default) or dicts (when
    ``raw_response=True``) shaped like the ``generate`` result payload. Text is
    accumulated across chunks, and token counts / stop reasons are read from the
    final raw chunk when available.
    """

    def __init__(
        self,
        stream: Any,
        invocation: InferenceInvocation,
        capture_content: bool,
    ) -> None:
        super().__init__(stream)
        self._self_invocation = invocation
        self._self_capture_content = capture_content
        self._self_text_parts: list[str] = []
        self._self_finish_reason: Optional[str] = None
        self._self_response_model: Optional[str] = None
        self._self_input_tokens: Optional[int] = None
        self._self_output_tokens: Optional[int] = None

    def _process_chunk(self, chunk: Any) -> None:
        if isinstance(chunk, str):
            if chunk:
                self._self_text_parts.append(chunk)
            return
        if not isinstance(chunk, Mapping):
            return

        model_id = _get(chunk, "model_id")
        if model_id and self._self_response_model is None:
            self._self_response_model = str(model_id)

        results = _get(chunk, "results")
        if not results:
            return
        for result in results:
            generated_text = _get(result, "generated_text")
            if isinstance(generated_text, str) and generated_text:
                self._self_text_parts.append(generated_text)

            stop_reason = _get(result, "stop_reason")
            if stop_reason is not None:
                self._self_finish_reason = str(stop_reason)

            input_token_count = _get(result, "input_token_count")
            # watsonx reports the prompt token count only on the first chunk
            # (0 afterwards), so only capture a non-zero value and never let a
            # later chunk clobber it back to 0.
            if isinstance(input_token_count, int) and input_token_count:
                self._self_input_tokens = input_token_count

            output_token_count = _get(result, "generated_token_count")
            if isinstance(output_token_count, int):
                self._self_output_tokens = (
                    self._self_output_tokens or 0
                ) + output_token_count

    def _on_stream_end(self) -> None:
        self._cleanup()

    def _on_stream_error(self, error: BaseException) -> None:
        self._cleanup(error)

    def _cleanup(self, error: Optional[BaseException] = None) -> None:
        if self._self_response_model is not None:
            self._self_invocation.response_model_name = (
                self._self_response_model
            )
        if self._self_input_tokens is not None:
            self._self_invocation.input_tokens = self._self_input_tokens
        if self._self_output_tokens is not None:
            self._self_invocation.output_tokens = self._self_output_tokens

        finish_reason = self._self_finish_reason or "stop"
        self._self_invocation.finish_reasons = [finish_reason]

        if self._self_capture_content:  # optimization
            parts: list[Any] = []
            if self._self_text_parts:
                parts.append(Text(content="".join(self._self_text_parts)))
            self._self_invocation.output_messages = [
                OutputMessage(
                    role="assistant",
                    finish_reason=finish_reason,
                    parts=parts,
                )
            ]

        if error is not None:
            self._self_invocation.fail(error)
        else:
            self._self_invocation.stop()


__all__ = ["TextGenerationStreamWrapper"]
