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

"""
Stream wrappers for OpenAI Chat Completions streaming responses.

This module provides type-safe wrappers that intercept OpenAI streaming
responses to extract telemetry (spans, logs, metrics) while preserving
the original iteration protocol.
"""

import asyncio
import inspect
import warnings
from typing import Any, AsyncIterator, Iterator, Optional

from opentelemetry._logs import Logger, LogRecord
from opentelemetry.context import get_current
from opentelemetry.semconv._incubating.attributes import gen_ai_attributes as GenAIAttributes
from opentelemetry.trace import Span, set_span_in_context

from opentelemetry.instrumentation.openai_v2.utils import (
    ChoiceBuffer,
    handle_span_exception,
    set_span_attribute,
)


class _StreamWrapperBase:
    """
    Base class with shared stream processing logic for Chat Completions.

    Subclasses provide the sync or async iteration protocol.
    """

    span: Span
    response_id: Optional[str] = None
    response_model: Optional[str] = None
    service_tier: Optional[str] = None
    finish_reasons: list = []
    prompt_tokens: Optional[int] = 0
    completion_tokens: Optional[int] = 0

    def __init__(
        self,
        span: Span,
        logger: Logger,
        capture_content: bool,
    ):
        self.span = span
        self.choice_buffers: list[ChoiceBuffer] = []
        self._span_started = False
        self.capture_content = capture_content
        self.logger = logger
        self._setup()

    def _setup(self):
        if not self._span_started:
            self._span_started = True

    def _cleanup(self):
        if not self._span_started:
            return

        if self.span.is_recording():
            if self.response_model:
                set_span_attribute(
                    self.span,
                    GenAIAttributes.GEN_AI_RESPONSE_MODEL,
                    self.response_model,
                )
            if self.response_id:
                set_span_attribute(
                    self.span,
                    GenAIAttributes.GEN_AI_RESPONSE_ID,
                    self.response_id,
                )
            set_span_attribute(
                self.span,
                GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
                self.prompt_tokens,
            )
            set_span_attribute(
                self.span,
                GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS,
                self.completion_tokens,
            )
            set_span_attribute(
                self.span,
                GenAIAttributes.GEN_AI_OPENAI_RESPONSE_SERVICE_TIER,
                self.service_tier,
            )
            set_span_attribute(
                self.span,
                GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS,
                self.finish_reasons,
            )

        for idx, choice in enumerate(self.choice_buffers):
            message: dict[str, Any] = {"role": "assistant"}
            if self.capture_content and choice.text_content:
                message["content"] = "".join(choice.text_content)
            if choice.tool_calls_buffers:
                tool_calls = []
                for tool_call in choice.tool_calls_buffers:
                    function = {"name": tool_call.function_name}
                    if self.capture_content:
                        function["arguments"] = "".join(tool_call.arguments)
                    tool_calls.append({
                        "id": tool_call.tool_call_id,
                        "type": "function",
                        "function": function,
                    })
                message["tool_calls"] = tool_calls

            body = {
                "index": idx,
                "finish_reason": choice.finish_reason or "error",
                "message": message,
            }
            event_attributes = {
                GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value
            }
            context = set_span_in_context(self.span, get_current())
            self.logger.emit(
                LogRecord(
                    event_name="gen_ai.choice",
                    attributes=event_attributes,
                    body=body,
                    context=context,
                )
            )

        self.span.end()
        self._span_started = False

    def _process_chunk(self, chunk):
        """Extract telemetry data from a streaming chunk."""
        if not self.response_id and getattr(chunk, "id", None):
            self.response_id = chunk.id
        if not self.response_model and getattr(chunk, "model", None):
            self.response_model = chunk.model
        if not self.service_tier and getattr(chunk, "service_tier", None):
            self.service_tier = chunk.service_tier
        if getattr(chunk, "usage", None):
            self.completion_tokens = chunk.usage.completion_tokens
            self.prompt_tokens = chunk.usage.prompt_tokens
        self._build_streaming_response(chunk)

    def _build_streaming_response(self, chunk):
        """Accumulate choice content from streaming chunks."""
        if getattr(chunk, "choices", None) is None:
            return

        for choice in chunk.choices:
            if not choice.delta:
                continue

            # Ensure we have enough choice buffers
            for idx in range(len(self.choice_buffers), choice.index + 1):
                self.choice_buffers.append(ChoiceBuffer(idx))

            if choice.finish_reason:
                self.choice_buffers[choice.index].finish_reason = choice.finish_reason

            if choice.delta.content is not None:
                self.choice_buffers[choice.index].append_text_content(
                    choice.delta.content
                )

            if choice.delta.tool_calls is not None:
                for tool_call in choice.delta.tool_calls:
                    self.choice_buffers[choice.index].append_tool_call(tool_call)


class SyncStreamWrapper(_StreamWrapperBase):
    """
    Wrapper for synchronous OpenAI Chat Completion streams.

    Implements the sync iterator and context manager protocols.
    """

    stream: Iterator[Any]

    def __init__(
        self,
        stream: Iterator[Any],
        span: Span,
        logger: Logger,
        capture_content: bool,
    ):
        super().__init__(span, logger, capture_content)
        self.stream = stream

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                handle_span_exception(self.span, exc_val)
        finally:
            self._cleanup()
        return False

    def close(self):
        try:
            close_fn = getattr(self.stream, "close", None)
            if callable(close_fn):
                close_fn()
        finally:
            self._cleanup()

    def __iter__(self):
        return self

    def __next__(self):
        try:
            chunk = next(self.stream)
            self._process_chunk(chunk)
            return chunk
        except StopIteration:
            self._cleanup()
            raise
        except Exception as error:
            handle_span_exception(self.span, error)
            self._cleanup()
            raise


class AsyncStreamWrapper(_StreamWrapperBase):
    """
    Wrapper for asynchronous OpenAI Chat Completion streams.

    Implements the async iterator and async context manager protocols.
    """

    stream: AsyncIterator[Any]

    def __init__(
        self,
        stream: AsyncIterator[Any],
        span: Span,
        logger: Logger,
        capture_content: bool,
    ):
        super().__init__(span, logger, capture_content)
        self.stream = stream

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                handle_span_exception(self.span, exc_val)
        finally:
            self._cleanup()
        return False

    def close(self):
        """Close the stream, handling the async close internally."""
        try:
            close_fn = getattr(self.stream, "close", None)
            if not callable(close_fn):
                return

            close_result = close_fn()
            if inspect.iscoroutine(close_result):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    asyncio.run(close_result)
                else:
                    loop.create_task(close_result)
        finally:
            self._cleanup()

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            chunk = await anext(self.stream)
            self._process_chunk(chunk)
            return chunk
        except StopAsyncIteration:
            self._cleanup()
            raise
        except Exception as error:
            handle_span_exception(self.span, error)
            self._cleanup()
            raise


class StreamWrapper(_StreamWrapperBase):
    """
    Backwards-compatible wrapper that handles both sync and async streams.

    .. deprecated::
        Use :class:`SyncStreamWrapper` for sync streams or
        :class:`AsyncStreamWrapper` for async streams instead.
        This class will be removed in a future release.
    """

    stream: Any

    def __init__(
        self,
        stream: Any,
        span: Span,
        logger: Logger,
        capture_content: bool,
    ):
        warnings.warn(
            "StreamWrapper is deprecated. Use SyncStreamWrapper for sync streams "
            "or AsyncStreamWrapper for async streams instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(span, logger, capture_content)
        self.stream = stream

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                handle_span_exception(self.span, exc_val)
        finally:
            self._cleanup()
        return False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                handle_span_exception(self.span, exc_val)
        finally:
            self._cleanup()
        return False

    def close(self):
        try:
            close_fn = getattr(self.stream, "close", None)
            if not callable(close_fn):
                return

            close_result = close_fn()
            if inspect.iscoroutine(close_result):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    asyncio.run(close_result)
                else:
                    loop.create_task(close_result)
        finally:
            self._cleanup()

    def __iter__(self):
        return self

    def __aiter__(self):
        return self

    def __next__(self):
        try:
            chunk = next(self.stream)
            self._process_chunk(chunk)
            return chunk
        except StopIteration:
            self._cleanup()
            raise
        except Exception as error:
            handle_span_exception(self.span, error)
            self._cleanup()
            raise

    async def __anext__(self):
        try:
            chunk = await anext(self.stream)
            self._process_chunk(chunk)
            return chunk
        except StopAsyncIteration:
            self._cleanup()
            raise
        except Exception as error:
            handle_span_exception(self.span, error)
            self._cleanup()
            raise
