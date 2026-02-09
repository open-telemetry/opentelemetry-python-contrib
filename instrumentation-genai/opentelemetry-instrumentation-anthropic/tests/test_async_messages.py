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

"""Tests for async AsyncMessages.create and AsyncMessages.stream instrumentation."""

from types import SimpleNamespace

import pytest
from anthropic import APIConnectionError, AsyncAnthropic, NotFoundError

from opentelemetry.instrumentation.anthropic.utils import (
    AsyncStreamWrapper,
    MessageWrapper,
)
from opentelemetry.semconv._incubating.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.util.genai.types import LLMInvocation


def normalize_stop_reason(stop_reason):
    """Map Anthropic stop reasons to GenAI semconv values."""
    return {
        "end_turn": "stop",
        "stop_sequence": "stop",
        "max_tokens": "length",
        "tool_use": "tool_calls",
    }.get(stop_reason, stop_reason)


def expected_input_tokens(usage):
    """Compute semconv input tokens from Anthropic usage."""
    base = getattr(usage, "input_tokens", 0) or 0
    cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    return base + cache_creation + cache_read


def assert_span_attributes(  # pylint: disable=too-many-arguments
    span,
    request_model,
    response_id=None,
    response_model=None,
    input_tokens=None,
    output_tokens=None,
    finish_reasons=None,
    operation_name="chat",
    server_address="api.anthropic.com",
):
    """Assert that a span has the expected attributes."""
    assert span.name == f"{operation_name} {request_model}"
    assert (
        operation_name
        == span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
    )
    assert (
        GenAIAttributes.GenAiSystemValues.ANTHROPIC.value
        == span.attributes[GenAIAttributes.GEN_AI_SYSTEM]
    )
    assert (
        request_model == span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
    )
    assert server_address == span.attributes[ServerAttributes.SERVER_ADDRESS]

    if response_id is not None:
        assert (
            response_id == span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID]
        )

    if response_model is not None:
        assert (
            response_model
            == span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL]
        )

    if input_tokens is not None:
        assert (
            input_tokens
            == span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
        )

    if output_tokens is not None:
        assert (
            output_tokens
            == span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
        )

    if finish_reasons is not None:
        # OpenTelemetry converts lists to tuples when storing as attributes
        assert (
            tuple(finish_reasons)
            == span.attributes[GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS]
        )


# =============================================================================
# Tests for AsyncMessages.create() method
# =============================================================================


@pytest.mark.vcr()
@pytest.mark.asyncio
async def test_async_messages_create_basic(
    span_exporter, async_anthropic_client, instrument_no_content
):
    """Test basic async message creation produces correct span."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Say hello in one word."}]

    response = await async_anthropic_client.messages.create(
        model=model,
        max_tokens=100,
        messages=messages,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    assert_span_attributes(
        spans[0],
        request_model=model,
        response_id=response.id,
        response_model=response.model,
        input_tokens=expected_input_tokens(response.usage),
        output_tokens=response.usage.output_tokens,
        finish_reasons=[normalize_stop_reason(response.stop_reason)],
    )


@pytest.mark.vcr()
@pytest.mark.asyncio
async def test_async_messages_create_with_all_params(
    span_exporter, async_anthropic_client, instrument_no_content
):
    """Test async message creation with all optional parameters."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Say hello."}]

    await async_anthropic_client.messages.create(
        model=model,
        max_tokens=50,
        messages=messages,
        temperature=0.7,
        top_p=0.9,
        top_k=40,
        stop_sequences=["STOP"],
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS] == 50
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE] == 0.7
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_TOP_P] == 0.9
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_TOP_K] == 40
    # OpenTelemetry converts lists to tuples when storing as attributes
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_STOP_SEQUENCES] == (
        "STOP",
    )


@pytest.mark.vcr()
@pytest.mark.asyncio
async def test_async_messages_create_token_usage(
    span_exporter, async_anthropic_client, instrument_no_content
):
    """Test that token usage is captured correctly for async create."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Count to 5."}]

    response = await async_anthropic_client.messages.create(
        model=model,
        max_tokens=100,
        messages=messages,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS in span.attributes
    assert GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS in span.attributes
    assert (
        span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
        == expected_input_tokens(response.usage)
    )
    assert (
        span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
        == response.usage.output_tokens
    )


@pytest.mark.vcr()
@pytest.mark.asyncio
async def test_async_messages_create_stop_reason(
    span_exporter, async_anthropic_client, instrument_no_content
):
    """Test that stop reason is captured as finish_reasons array for async create."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Say hi."}]

    response = await async_anthropic_client.messages.create(
        model=model,
        max_tokens=100,
        messages=messages,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    # Anthropic's stop_reason should be wrapped in a tuple (OTel converts lists)
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS] == (
        normalize_stop_reason(response.stop_reason),
    )


@pytest.mark.asyncio
async def test_async_messages_create_connection_error(
    span_exporter, instrument_no_content
):
    """Test that connection errors are handled correctly for async create."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Hello"}]

    # Create client with invalid endpoint
    client = AsyncAnthropic(base_url="http://localhost:9999")

    with pytest.raises(APIConnectionError):
        await client.messages.create(
            model=model,
            max_tokens=100,
            messages=messages,
            timeout=0.1,
        )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == model
    assert ErrorAttributes.ERROR_TYPE in span.attributes
    assert "APIConnectionError" in span.attributes[ErrorAttributes.ERROR_TYPE]


@pytest.mark.vcr()
@pytest.mark.asyncio
async def test_async_messages_create_api_error(
    span_exporter, async_anthropic_client, instrument_no_content
):
    """Test that API errors (e.g., invalid model) are handled correctly for async."""
    model = "invalid-model-name"
    messages = [{"role": "user", "content": "Hello"}]

    with pytest.raises(NotFoundError):
        await async_anthropic_client.messages.create(
            model=model,
            max_tokens=100,
            messages=messages,
        )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == model
    assert ErrorAttributes.ERROR_TYPE in span.attributes
    assert "NotFoundError" in span.attributes[ErrorAttributes.ERROR_TYPE]


@pytest.mark.vcr()
@pytest.mark.asyncio
async def test_async_messages_create_streaming(  # pylint: disable=too-many-locals
    span_exporter, async_anthropic_client, instrument_no_content
):
    """Test async streaming message creation produces correct span."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Say hello in one word."}]

    # Collect response data from stream
    response_text = ""
    response_id = None
    response_model = None
    stop_reason = None
    input_tokens = None
    output_tokens = None

    # Note: AsyncMessages.create() is a coroutine that must be awaited first,
    # then you can use async with on the result (unlike sync which returns directly)
    stream = await async_anthropic_client.messages.create(
        model=model,
        max_tokens=100,
        messages=messages,
        stream=True,
    )
    async with stream:
        async for chunk in stream:
            # Extract data from chunks for assertion
            if chunk.type == "message_start":
                message = getattr(chunk, "message", None)
                if message:
                    response_id = getattr(message, "id", None)
                    response_model = getattr(message, "model", None)
                    usage = getattr(message, "usage", None)
                    if usage:
                        input_tokens = expected_input_tokens(usage)
            elif chunk.type == "content_block_delta":
                delta = getattr(chunk, "delta", None)
                if delta and hasattr(delta, "text"):
                    response_text += delta.text
            elif chunk.type == "message_delta":
                delta = getattr(chunk, "delta", None)
                if delta:
                    stop_reason = getattr(delta, "stop_reason", None)
                usage = getattr(chunk, "usage", None)
                if usage:
                    output_tokens = getattr(usage, "output_tokens", None)

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    assert_span_attributes(
        spans[0],
        request_model=model,
        response_id=response_id,
        response_model=response_model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        finish_reasons=[normalize_stop_reason(stop_reason)]
        if stop_reason
        else None,
    )


@pytest.mark.vcr()
@pytest.mark.asyncio
async def test_async_messages_create_streaming_iteration(
    span_exporter, async_anthropic_client, instrument_no_content
):
    """Test async streaming with direct iteration (without context manager)."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Say hi."}]

    stream = await async_anthropic_client.messages.create(
        model=model,
        max_tokens=100,
        messages=messages,
        stream=True,
    )

    # Consume the stream by iterating
    chunks = []
    async for chunk in stream:
        chunks.append(chunk)
    assert len(chunks) > 0

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == model
    # Verify span has response attributes from streaming
    assert GenAIAttributes.GEN_AI_RESPONSE_ID in span.attributes
    assert GenAIAttributes.GEN_AI_RESPONSE_MODEL in span.attributes


@pytest.mark.asyncio
async def test_async_messages_create_streaming_connection_error(
    span_exporter, instrument_no_content
):
    """Test that connection errors during async streaming are handled correctly."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Hello"}]

    # Create client with invalid endpoint
    client = AsyncAnthropic(base_url="http://localhost:9999")

    with pytest.raises(APIConnectionError):
        await client.messages.create(
            model=model,
            max_tokens=100,
            messages=messages,
            stream=True,
            timeout=0.1,
        )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == model
    assert ErrorAttributes.ERROR_TYPE in span.attributes
    assert "APIConnectionError" in span.attributes[ErrorAttributes.ERROR_TYPE]


# =============================================================================
# Tests for AsyncMessages.stream() method
# =============================================================================


@pytest.mark.vcr()
@pytest.mark.asyncio
async def test_async_messages_stream_basic(
    span_exporter, async_anthropic_client, instrument_no_content
):
    """Test AsyncMessages.stream() produces correct span with async context manager."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Say hello in one word."}]

    async with async_anthropic_client.messages.stream(
        model=model,
        max_tokens=100,
        messages=messages,
    ) as stream:
        # Consume the stream using text_stream
        text_parts = []
        async for text in stream.text_stream:
            text_parts.append(text)
        response_text = "".join(text_parts)
        # Get the final message for assertions
        final_message = await stream.get_final_message()

    assert response_text  # Should have some text

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    assert_span_attributes(
        spans[0],
        request_model=model,
        response_id=final_message.id,
        response_model=final_message.model,
        input_tokens=expected_input_tokens(final_message.usage),
        output_tokens=final_message.usage.output_tokens,
        finish_reasons=[normalize_stop_reason(final_message.stop_reason)],
    )


@pytest.mark.vcr()
@pytest.mark.asyncio
async def test_async_messages_stream_with_params(
    span_exporter, async_anthropic_client, instrument_no_content
):
    """Test AsyncMessages.stream() with additional parameters."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Say hi."}]

    async with async_anthropic_client.messages.stream(
        model=model,
        max_tokens=50,
        messages=messages,
        temperature=0.7,
        top_p=0.9,
        top_k=40,
    ) as stream:
        # Consume the stream
        async for _ in stream.text_stream:
            pass

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == model
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS] == 50
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE] == 0.7
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_TOP_P] == 0.9
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_TOP_K] == 40


@pytest.mark.vcr()
@pytest.mark.asyncio
async def test_async_messages_stream_token_usage(
    span_exporter, async_anthropic_client, instrument_no_content
):
    """Test that AsyncMessages.stream() captures token usage correctly."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Count to 3."}]

    async with async_anthropic_client.messages.stream(
        model=model,
        max_tokens=100,
        messages=messages,
    ) as stream:
        async for _ in stream.text_stream:
            pass
        final_message = await stream.get_final_message()

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS in span.attributes
    assert GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS in span.attributes
    assert (
        span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
        == expected_input_tokens(final_message.usage)
    )
    assert (
        span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
        == final_message.usage.output_tokens
    )


@pytest.mark.asyncio
async def test_async_messages_stream_connection_error(
    span_exporter, instrument_no_content
):
    """Test that connection errors in AsyncMessages.stream() are handled correctly."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Hello"}]

    # Create client with invalid endpoint
    client = AsyncAnthropic(base_url="http://localhost:9999")

    with pytest.raises(APIConnectionError):
        # pylint: disable=not-async-context-manager
        async with client.messages.stream(
            model=model,
            max_tokens=100,
            messages=messages,
            timeout=0.1,
        ) as stream:
            # Try to consume the stream
            async for _ in stream.text_stream:
                pass

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == model
    assert ErrorAttributes.ERROR_TYPE in span.attributes
    assert "APIConnectionError" in span.attributes[ErrorAttributes.ERROR_TYPE]


@pytest.mark.asyncio
async def test_message_wrapper_aggregates_cache_tokens():
    """MessageWrapper should aggregate cache token fields into input tokens."""

    class FakeHandler:
        def stop_llm(self, invocation):
            return invocation

    usage = SimpleNamespace(
        input_tokens=10,
        cache_creation_input_tokens=3,
        cache_read_input_tokens=7,
        output_tokens=5,
    )
    message = SimpleNamespace(
        model="claude-sonnet-4-20250514",
        id="msg_123",
        stop_reason="end_turn",
        usage=usage,
    )
    invocation = LLMInvocation(
        request_model="claude-sonnet-4-20250514",
        provider="anthropic",
    )

    MessageWrapper(message, FakeHandler(), invocation)  # type: ignore[arg-type]

    assert invocation.input_tokens == 20
    assert invocation.output_tokens == 5
    assert invocation.finish_reasons == ["stop"]
    assert (
        invocation.attributes["gen_ai.usage.cache_creation.input_tokens"] == 3
    )
    assert invocation.attributes["gen_ai.usage.cache_read.input_tokens"] == 7


@pytest.mark.asyncio
async def test_async_stream_wrapper_aggregates_cache_tokens():
    """AsyncStreamWrapper should aggregate cache token fields from chunks."""

    class FakeHandler:
        def __init__(self):
            self.stop_calls = 0
            self.fail_calls = 0

        def stop_llm(self, invocation):
            self.stop_calls += 1
            return invocation

        def fail_llm(self, invocation, error):
            self.fail_calls += 1
            return invocation

    message_start = SimpleNamespace(
        type="message_start",
        message=SimpleNamespace(
            id="msg_1",
            model="claude-sonnet-4-20250514",
            usage=SimpleNamespace(
                input_tokens=9,
                cache_creation_input_tokens=1,
                cache_read_input_tokens=2,
            ),
        ),
    )
    message_delta = SimpleNamespace(
        type="message_delta",
        delta=SimpleNamespace(stop_reason="end_turn"),
        usage=SimpleNamespace(
            input_tokens=10,
            cache_creation_input_tokens=3,
            cache_read_input_tokens=4,
            output_tokens=8,
        ),
    )

    class FakeAsyncStream:
        def __init__(self):
            self._chunks = [message_start, message_delta]
            self._index = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._index >= len(self._chunks):
                raise StopAsyncIteration
            value = self._chunks[self._index]
            self._index += 1
            return value

        async def close(self):
            return None

    invocation = LLMInvocation(
        request_model="claude-sonnet-4-20250514",
        provider="anthropic",
    )
    handler = FakeHandler()
    wrapper = AsyncStreamWrapper(
        FakeAsyncStream(), handler, invocation
    )  # type: ignore[arg-type]

    async for _ in wrapper:
        pass
    await wrapper.close()

    assert invocation.input_tokens == 17
    assert invocation.output_tokens == 8
    assert invocation.finish_reasons == ["stop"]
    assert (
        invocation.attributes["gen_ai.usage.cache_creation.input_tokens"] == 3
    )
    assert invocation.attributes["gen_ai.usage.cache_read.input_tokens"] == 4
    assert handler.stop_calls == 1
    assert handler.fail_calls == 0
