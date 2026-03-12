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
from types import TracebackType
from typing import TYPE_CHECKING, Callable, Iterator, Optional

from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import (
    Error,
    LLMInvocation,
    MessagePart,
    OutputMessage,
)

from .messages_extractors import (
    GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS,
    GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS,
    extract_usage_tokens,
    get_output_messages_from_message,
)
from .utils import (
    StreamBlockState,
    create_stream_block_state,
    normalize_finish_reason,
    stream_block_state_to_part,
    update_stream_block_state,
)

if TYPE_CHECKING:
    from anthropic._streaming import Stream
    from anthropic.types import (
        Message,
        MessageDeltaUsage,
        RawMessageStreamEvent,
        Usage,
    )


_logger = logging.getLogger(__name__)


class MessageWrapper:
    """Wrapper for non-streaming Message response that handles telemetry."""

    def __init__(self, message: Message, capture_content: bool):
        self._message = message
        self._capture_content = capture_content

    def extract_into(self, invocation: LLMInvocation) -> None:
        """Extract response data into the invocation."""
        if self._message.model:
            invocation.response_model_name = self._message.model

        if self._message.id:
            invocation.response_id = self._message.id

        finish_reason = normalize_finish_reason(self._message.stop_reason)
        if finish_reason:
            invocation.finish_reasons = [finish_reason]

        if self._message.usage:
            tokens = extract_usage_tokens(self._message.usage)
            invocation.input_tokens = tokens.input_tokens
            invocation.output_tokens = tokens.output_tokens
            if tokens.cache_creation_input_tokens is not None:
                invocation.attributes[
                    GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS
                ] = tokens.cache_creation_input_tokens
            if tokens.cache_read_input_tokens is not None:
                invocation.attributes[GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS] = (
                    tokens.cache_read_input_tokens
                )

        if self._capture_content:
            invocation.output_messages = get_output_messages_from_message(
                self._message
            )

    @property
    def message(self) -> Message:
        """Return the wrapped Message object."""
        return self._message


class MessagesStreamWrapper(Iterator["RawMessageStreamEvent"]):
    """Wrapper for Anthropic Stream that handles telemetry."""

    def __init__(
        self,
        stream: Stream[RawMessageStreamEvent],
        handler: TelemetryHandler,
        invocation: LLMInvocation,
        capture_content: bool,
    ):
        self._stream = stream
        self._handler = handler
        self._invocation = invocation
        self._response_id: Optional[str] = None
        self._response_model: Optional[str] = None
        self._stop_reason: Optional[str] = None
        self._input_tokens: Optional[int] = None
        self._output_tokens: Optional[int] = None
        self._cache_creation_input_tokens: Optional[int] = None
        self._cache_read_input_tokens: Optional[int] = None
        self._capture_content = capture_content
        self._content_blocks: dict[int, StreamBlockState] = {}
        self._finalized = False

    def _update_usage(self, usage: Usage | MessageDeltaUsage | None) -> None:
        tokens = extract_usage_tokens(usage)
        if tokens.input_tokens is not None:
            self._input_tokens = tokens.input_tokens
        if tokens.output_tokens is not None:
            self._output_tokens = tokens.output_tokens
        if tokens.cache_creation_input_tokens is not None:
            self._cache_creation_input_tokens = (
                tokens.cache_creation_input_tokens
            )
        if tokens.cache_read_input_tokens is not None:
            self._cache_read_input_tokens = tokens.cache_read_input_tokens

    def _process_chunk(self, chunk: RawMessageStreamEvent) -> None:
        """Extract telemetry data from a streaming chunk."""
        if chunk.type == "message_start":
            message = chunk.message
            if message.id:
                self._response_id = message.id
            if message.model:
                self._response_model = message.model
            self._update_usage(message.usage)
        elif chunk.type == "message_delta":
            if chunk.delta.stop_reason:
                self._stop_reason = normalize_finish_reason(
                    chunk.delta.stop_reason
                )
            self._update_usage(chunk.usage)
        elif self._capture_content and chunk.type == "content_block_start":
            self._content_blocks[chunk.index] = create_stream_block_state(
                chunk.content_block
            )
        elif self._capture_content and chunk.type == "content_block_delta":
            block = self._content_blocks.get(chunk.index)
            if block is not None:
                update_stream_block_state(block, chunk.delta)

    @staticmethod
    def _safe_instrumentation(
        callback: Callable[[], object], context: str
    ) -> None:
        try:
            callback()
        except Exception:  # pylint: disable=broad-exception-caught
            _logger.debug(
                "Anthropic MessagesStreamWrapper instrumentation error in %s",
                context,
                exc_info=True,
            )

    def _set_invocation_response_attributes(self) -> None:
        """Extract accumulated stream state into the invocation."""
        if self._response_model:
            self._invocation.response_model_name = self._response_model
        if self._response_id:
            self._invocation.response_id = self._response_id
        if self._stop_reason:
            self._invocation.finish_reasons = [self._stop_reason]
        if self._input_tokens is not None:
            self._invocation.input_tokens = self._input_tokens
        if self._output_tokens is not None:
            self._invocation.output_tokens = self._output_tokens
        if self._cache_creation_input_tokens is not None:
            self._invocation.attributes[
                GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS
            ] = self._cache_creation_input_tokens
        if self._cache_read_input_tokens is not None:
            self._invocation.attributes[
                GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS
            ] = self._cache_read_input_tokens

        if self._capture_content and self._content_blocks:
            parts: list[MessagePart] = []
            for index in sorted(self._content_blocks):
                part = stream_block_state_to_part(self._content_blocks[index])
                if part is not None:
                    parts.append(part)
            self._invocation.output_messages = [
                OutputMessage(
                    role="assistant",
                    parts=parts,
                    finish_reason=self._stop_reason or "",
                )
            ]

    def _stop(self) -> None:
        if self._finalized:
            return
        self._safe_instrumentation(
            self._set_invocation_response_attributes,
            "response attribute extraction",
        )
        self._safe_instrumentation(
            lambda: self._handler.stop_llm(self._invocation),
            "stop_llm",
        )
        self._finalized = True

    def _fail(self, message: str, error_type: type[BaseException]) -> None:
        if self._finalized:
            return
        self._safe_instrumentation(
            lambda: self._handler.fail_llm(
                self._invocation, Error(message=message, type=error_type)
            ),
            "fail_llm",
        )
        self._finalized = True

    def __iter__(self) -> MessagesStreamWrapper:
        return self

    def __getattr__(self, name: str) -> object:
        return getattr(self._stream, name)

    def __next__(self) -> RawMessageStreamEvent:
        try:
            chunk = next(self._stream)
        except StopIteration:
            self._stop()
            raise
        except Exception as exc:
            self._fail(str(exc), type(exc))
            raise
        self._safe_instrumentation(
            lambda: self._process_chunk(chunk),
            "stream chunk processing",
        )
        return chunk

    def __enter__(self) -> MessagesStreamWrapper:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        try:
            if exc_type is not None:
                self._fail(
                    str(exc_val), type(exc_val) if exc_val else Exception
                )
        finally:
            self.close()
        return False

    def close(self) -> None:
        try:
            self._stream.close()
        finally:
            self._stop()
