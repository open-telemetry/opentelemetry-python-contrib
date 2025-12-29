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

"""Streaming response wrappers for Anthropic instrumentation."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from opentelemetry._logs import Logger
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.trace import Span
from opentelemetry.trace.status import Status, StatusCode

from opentelemetry.instrumentation.anthropic.instruments import Instruments
from opentelemetry.instrumentation.anthropic.utils import (
    GEN_AI_SYSTEM_ANTHROPIC,
    LLM_USAGE_CACHE_CREATION_INPUT_TOKENS,
    LLM_USAGE_CACHE_READ_INPUT_TOKENS,
    LLM_USAGE_TOTAL_TOKENS,
    dont_throw,
    is_content_enabled,
    set_span_attribute,
)

logger = logging.getLogger(__name__)


@dont_throw
def _process_response_item(item: Any, complete_response: dict) -> None:
    """Process a streaming response item and update the complete response."""
    item_type = getattr(item, "type", None)

    if item_type == "message_start":
        message = getattr(item, "message", None)
        if message:
            complete_response["model"] = getattr(message, "model", "")
            complete_response["id"] = getattr(message, "id", "")
            usage = getattr(message, "usage", None)
            if usage:
                complete_response["usage"] = {
                    "input_tokens": getattr(usage, "input_tokens", 0),
                    "output_tokens": getattr(usage, "output_tokens", 0),
                    "cache_read_input_tokens": getattr(
                        usage, "cache_read_input_tokens", 0
                    ),
                    "cache_creation_input_tokens": getattr(
                        usage, "cache_creation_input_tokens", 0
                    ),
                }

    elif item_type == "content_block_start":
        index = getattr(item, "index", 0)
        content_block = getattr(item, "content_block", None)
        if content_block:
            block_type = getattr(content_block, "type", "text")
            block_data = {
                "index": index,
                "type": block_type,
                "text": "",
            }
            if block_type == "tool_use":
                block_data["id"] = getattr(content_block, "id", "")
                block_data["name"] = getattr(content_block, "name", "")
                block_data["input"] = ""

            # Ensure we have enough slots
            while len(complete_response.get("content_blocks", [])) <= index:
                complete_response.setdefault("content_blocks", []).append({})
            complete_response["content_blocks"][index] = block_data

    elif item_type == "content_block_delta":
        index = getattr(item, "index", 0)
        delta = getattr(item, "delta", None)
        if delta:
            delta_type = getattr(delta, "type", "")
            blocks = complete_response.get("content_blocks", [])
            if index < len(blocks):
                if delta_type == "text_delta":
                    text = getattr(delta, "text", "")
                    blocks[index]["text"] = blocks[index].get("text", "") + text
                elif delta_type == "thinking_delta":
                    thinking = getattr(delta, "thinking", "")
                    blocks[index]["text"] = (
                        blocks[index].get("text", "") + thinking
                    )
                elif delta_type == "input_json_delta":
                    partial_json = getattr(delta, "partial_json", "")
                    blocks[index]["input"] = (
                        blocks[index].get("input", "") + partial_json
                    )

    elif item_type == "message_delta":
        delta = getattr(item, "delta", None)
        if delta:
            complete_response["stop_reason"] = getattr(
                delta, "stop_reason", None
            )

        usage = getattr(item, "usage", None)
        if usage:
            existing_usage = complete_response.get("usage", {})
            output_tokens = getattr(usage, "output_tokens", 0)
            existing_usage["output_tokens"] = (
                existing_usage.get("output_tokens", 0) + output_tokens
            )
            complete_response["usage"] = existing_usage


def _set_streaming_response_attributes(
    span: Span,
    complete_response: dict,
    capture_content: bool,
) -> None:
    """Set span attributes from the completed streaming response."""
    if not span.is_recording():
        return

    set_span_attribute(
        span,
        GenAIAttributes.GEN_AI_RESPONSE_MODEL,
        complete_response.get("model"),
    )
    set_span_attribute(
        span,
        GenAIAttributes.GEN_AI_RESPONSE_ID,
        complete_response.get("id"),
    )

    stop_reason = complete_response.get("stop_reason")
    if stop_reason:
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS,
            [stop_reason],
        )

    # Set usage
    usage = complete_response.get("usage", {})
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0) or 0
    cache_creation = usage.get("cache_creation_input_tokens", 0) or 0

    total_input = input_tokens + cache_read + cache_creation

    set_span_attribute(
        span, GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS, total_input
    )
    set_span_attribute(
        span, GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS, output_tokens
    )
    set_span_attribute(span, LLM_USAGE_TOTAL_TOKENS, total_input + output_tokens)

    if cache_read > 0:
        set_span_attribute(span, LLM_USAGE_CACHE_READ_INPUT_TOKENS, cache_read)
    if cache_creation > 0:
        set_span_attribute(
            span, LLM_USAGE_CACHE_CREATION_INPUT_TOKENS, cache_creation
        )

    # Set response content if enabled
    if capture_content:
        content_blocks = complete_response.get("content_blocks", [])
        if content_blocks:
            response_parts = []
            for block in content_blocks:
                block_type = block.get("type", "text")
                if block_type == "text":
                    text = block.get("text", "")
                    if text:
                        response_parts.append(text)
                elif block_type == "tool_use":
                    name = block.get("name", "")
                    input_json = block.get("input", "")
                    response_parts.append(f"[Tool: {name}({input_json})]")
                elif block_type == "thinking":
                    text = block.get("text", "")
                    if text:
                        response_parts.append(f"[Thinking]: {text}")

            if response_parts:
                from opentelemetry.instrumentation.anthropic.utils import (
                    LLM_RESPONSE_CONTENT,
                )

                span.set_attribute(
                    LLM_RESPONSE_CONTENT, "\n---\n".join(response_parts)
                )


def _record_streaming_metrics(
    instruments: Instruments,
    complete_response: dict,
    start_time: float,
    first_token_time: Optional[float],
    end_time: float,
    request_attributes: dict,
) -> None:
    """Record metrics for a streaming response."""
    common_attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: (
            GenAIAttributes.GenAiOperationNameValues.CHAT.value
        ),
        GenAIAttributes.GEN_AI_SYSTEM: GEN_AI_SYSTEM_ANTHROPIC,
        GenAIAttributes.GEN_AI_REQUEST_MODEL: request_attributes.get(
            GenAIAttributes.GEN_AI_REQUEST_MODEL
        ),
        GenAIAttributes.GEN_AI_RESPONSE_MODEL: complete_response.get("model"),
    }

    # Record operation duration
    duration = end_time - start_time
    instruments.operation_duration_histogram.record(
        duration, attributes=common_attributes
    )

    # Record token usage
    usage = complete_response.get("usage", {})
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0) or 0
    cache_creation = usage.get("cache_creation_input_tokens", 0) or 0
    total_input = input_tokens + cache_read + cache_creation

    if total_input > 0:
        instruments.token_usage_histogram.record(
            total_input,
            attributes={
                **common_attributes,
                GenAIAttributes.GEN_AI_TOKEN_TYPE: "input",
            },
        )

    if output_tokens > 0:
        instruments.token_usage_histogram.record(
            output_tokens,
            attributes={
                **common_attributes,
                GenAIAttributes.GEN_AI_TOKEN_TYPE: "output",
            },
        )

    # Record streaming time metrics
    if first_token_time:
        ttft = first_token_time - start_time
        instruments.streaming_time_to_first_token.record(
            ttft, attributes=common_attributes
        )

        ttg = end_time - first_token_time
        instruments.streaming_time_to_generate.record(
            ttg, attributes=common_attributes
        )


class AnthropicStream:
    """Wrapper for Anthropic sync streaming responses."""

    def __init__(
        self,
        stream: Any,
        span: Span,
        instruments: Instruments,
        request_attributes: dict,
        capture_content: bool,
        event_logger: Optional[Logger] = None,
    ):
        self._stream = stream
        self._span = span
        self._instruments = instruments
        self._request_attributes = request_attributes
        self._capture_content = capture_content
        self._event_logger = event_logger

        self._complete_response: dict = {
            "model": "",
            "id": "",
            "usage": {},
            "content_blocks": [],
            "stop_reason": None,
        }
        self._start_time = time.time()
        self._first_token_time: Optional[float] = None
        self._finished = False

    def __iter__(self):
        return self

    def __next__(self):
        try:
            item = next(self._stream)
        except StopIteration:
            self._finish()
            raise

        # Track first token time
        if self._first_token_time is None:
            self._first_token_time = time.time()

        _process_response_item(item, self._complete_response)
        return item

    def _finish(self) -> None:
        """Complete instrumentation when stream ends."""
        if self._finished:
            return
        self._finished = True

        end_time = time.time()

        _set_streaming_response_attributes(
            self._span, self._complete_response, self._capture_content
        )

        _record_streaming_metrics(
            self._instruments,
            self._complete_response,
            self._start_time,
            self._first_token_time,
            end_time,
            self._request_attributes,
        )

        self._span.set_status(Status(StatusCode.OK))
        self._span.end()

    # Preserve helper methods from the underlying stream
    def get_final_message(self):
        """Consume stream and return final message."""
        for _ in self:
            pass
        return self._stream.get_final_message()

    @property
    def text_stream(self):
        """Generator yielding only text content."""

        def text_generator():
            for event in self:
                if (
                    hasattr(event, "delta")
                    and hasattr(event.delta, "type")
                    and event.delta.type == "text_delta"
                    and hasattr(event.delta, "text")
                ):
                    yield event.delta.text

        return text_generator()

    def until_done(self):
        """Consume stream without returning chunks."""
        for _ in self:
            pass

    def close(self):
        """Close the underlying stream."""
        if hasattr(self._stream, "close"):
            self._stream.close()


class AnthropicAsyncStream:
    """Wrapper for Anthropic async streaming responses."""

    def __init__(
        self,
        stream: Any,
        span: Span,
        instruments: Instruments,
        request_attributes: dict,
        capture_content: bool,
        event_logger: Optional[Logger] = None,
    ):
        self._stream = stream
        self._span = span
        self._instruments = instruments
        self._request_attributes = request_attributes
        self._capture_content = capture_content
        self._event_logger = event_logger

        self._complete_response: dict = {
            "model": "",
            "id": "",
            "usage": {},
            "content_blocks": [],
            "stop_reason": None,
        }
        self._start_time = time.time()
        self._first_token_time: Optional[float] = None
        self._finished = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            item = await self._stream.__anext__()
        except StopAsyncIteration:
            self._finish()
            raise

        # Track first token time
        if self._first_token_time is None:
            self._first_token_time = time.time()

        _process_response_item(item, self._complete_response)
        return item

    def _finish(self) -> None:
        """Complete instrumentation when stream ends."""
        if self._finished:
            return
        self._finished = True

        end_time = time.time()

        _set_streaming_response_attributes(
            self._span, self._complete_response, self._capture_content
        )

        _record_streaming_metrics(
            self._instruments,
            self._complete_response,
            self._start_time,
            self._first_token_time,
            end_time,
            self._request_attributes,
        )

        self._span.set_status(Status(StatusCode.OK))
        self._span.end()

    # Preserve helper methods from the underlying stream
    async def get_final_message(self):
        """Consume stream and return final message."""
        async for _ in self:
            pass
        return await self._stream.get_final_message()

    @property
    def text_stream(self):
        """Async generator yielding only text content."""

        async def text_generator():
            async for event in self:
                if (
                    hasattr(event, "delta")
                    and hasattr(event.delta, "type")
                    and event.delta.type == "text_delta"
                    and hasattr(event.delta, "text")
                ):
                    yield event.delta.text

        return text_generator()

    async def until_done(self):
        """Consume stream without returning chunks."""
        async for _ in self:
            pass

    async def close(self):
        """Close the underlying stream."""
        if hasattr(self._stream, "close"):
            await self._stream.close()


class WrappedMessageStreamManager:
    """Wrapper for MessageStreamManager context manager."""

    def __init__(
        self,
        stream_manager: Any,
        span: Span,
        instruments: Instruments,
        request_attributes: dict,
        capture_content: bool,
        event_logger: Optional[Logger] = None,
    ):
        self._stream_manager = stream_manager
        self._span = span
        self._instruments = instruments
        self._request_attributes = request_attributes
        self._capture_content = capture_content
        self._event_logger = event_logger

    def __enter__(self):
        stream = self._stream_manager.__enter__()
        return AnthropicStream(
            stream,
            self._span,
            self._instruments,
            self._request_attributes,
            self._capture_content,
            self._event_logger,
        )

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._stream_manager.__exit__(exc_type, exc_val, exc_tb)


class WrappedAsyncMessageStreamManager:
    """Wrapper for AsyncMessageStreamManager context manager."""

    def __init__(
        self,
        stream_manager: Any,
        span: Span,
        instruments: Instruments,
        request_attributes: dict,
        capture_content: bool,
        event_logger: Optional[Logger] = None,
    ):
        self._stream_manager = stream_manager
        self._span = span
        self._instruments = instruments
        self._request_attributes = request_attributes
        self._capture_content = capture_content
        self._event_logger = event_logger

    async def __aenter__(self):
        stream = await self._stream_manager.__aenter__()
        return AnthropicAsyncStream(
            stream,
            self._span,
            self._instruments,
            self._request_attributes,
            self._capture_content,
            self._event_logger,
        )

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self._stream_manager.__aexit__(exc_type, exc_val, exc_tb)
