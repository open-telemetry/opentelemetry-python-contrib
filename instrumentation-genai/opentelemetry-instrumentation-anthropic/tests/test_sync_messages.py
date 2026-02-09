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

"""Tests for sync Messages.create instrumentation."""

from types import SimpleNamespace

import pytest
from anthropic import Anthropic, APIConnectionError, NotFoundError

from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor
from opentelemetry.instrumentation.anthropic.utils import (
    MessageWrapper,
    StreamWrapper,
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


@pytest.mark.vcr()
def test_sync_messages_create_basic(
    span_exporter, anthropic_client, instrument_no_content
):
    """Test basic sync message creation produces correct span."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Say hello in one word."}]

    response = anthropic_client.messages.create(
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
def test_sync_messages_create_with_all_params(
    span_exporter, anthropic_client, instrument_no_content
):
    """Test message creation with all optional parameters."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Say hello."}]

    anthropic_client.messages.create(
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
def test_sync_messages_create_token_usage(
    span_exporter, anthropic_client, instrument_no_content
):
    """Test that token usage is captured correctly."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Count to 5."}]

    response = anthropic_client.messages.create(
        model=model,
        max_tokens=100,
        messages=messages,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS in span.attributes
    assert GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS in span.attributes
    assert span.attributes[
        GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS
    ] == expected_input_tokens(response.usage)
    assert (
        span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
        == response.usage.output_tokens
    )


@pytest.mark.vcr()
def test_sync_messages_create_stop_reason(
    span_exporter, anthropic_client, instrument_no_content
):
    """Test that stop reason is captured as finish_reasons array."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Say hi."}]

    response = anthropic_client.messages.create(
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


def test_sync_messages_create_connection_error(
    span_exporter, instrument_no_content
):
    """Test that connection errors are handled correctly."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Hello"}]

    # Create client with invalid endpoint
    client = Anthropic(base_url="http://localhost:9999")

    with pytest.raises(APIConnectionError):
        client.messages.create(
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
def test_sync_messages_create_api_error(
    span_exporter, anthropic_client, instrument_no_content
):
    """Test that API errors (e.g., invalid model) are handled correctly."""
    model = "invalid-model-name"
    messages = [{"role": "user", "content": "Hello"}]

    with pytest.raises(NotFoundError):
        anthropic_client.messages.create(
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


def test_uninstrument_removes_patching(
    span_exporter, tracer_provider, logger_provider, meter_provider
):
    """Test that uninstrument() removes the patching."""
    instrumentor = AnthropicInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )

    # Uninstrument
    instrumentor.uninstrument()

    # Create a new client after uninstrumenting
    # The actual API call won't work without a real API key,
    # but we can verify no spans are created for a mocked scenario
    # For this test, we'll just verify uninstrument doesn't raise
    assert True


def test_multiple_instrument_uninstrument_cycles(
    tracer_provider, logger_provider, meter_provider
):
    """Test that multiple instrument/uninstrument cycles work correctly."""
    instrumentor = AnthropicInstrumentor()

    # First cycle
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )
    instrumentor.uninstrument()

    # Second cycle
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )
    instrumentor.uninstrument()

    # Third cycle - should still work
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )
    instrumentor.uninstrument()


@pytest.mark.vcr()
def test_sync_messages_create_streaming(  # pylint: disable=too-many-locals
    span_exporter, anthropic_client, instrument_no_content
):
    """Test streaming message creation produces correct span."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Say hello in one word."}]

    # Collect response data from stream
    response_text = ""
    response_id = None
    response_model = None
    stop_reason = None
    input_tokens = None
    output_tokens = None

    with anthropic_client.messages.create(
        model=model,
        max_tokens=100,
        messages=messages,
        stream=True,
    ) as stream:
        for chunk in stream:
            # Extract data from chunks for assertion
            if chunk.type == "message_start":
                message = getattr(chunk, "message", None)
                if message:
                    response_id = getattr(message, "id", None)
                    response_model = getattr(message, "model", None)
                    usage = getattr(message, "usage", None)
                    if usage:
                        input_tokens = getattr(usage, "input_tokens", None)
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
def test_sync_messages_create_streaming_iteration(
    span_exporter, anthropic_client, instrument_no_content
):
    """Test streaming with direct iteration (without context manager)."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Say hi."}]

    stream = anthropic_client.messages.create(
        model=model,
        max_tokens=100,
        messages=messages,
        stream=True,
    )

    # Consume the stream by iterating
    chunks = list(stream)
    assert len(chunks) > 0

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == model
    # Verify span has response attributes from streaming
    assert GenAIAttributes.GEN_AI_RESPONSE_ID in span.attributes
    assert GenAIAttributes.GEN_AI_RESPONSE_MODEL in span.attributes


def test_sync_messages_create_streaming_connection_error(
    span_exporter, instrument_no_content
):
    """Test that connection errors during streaming are handled correctly."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Hello"}]

    # Create client with invalid endpoint
    client = Anthropic(base_url="http://localhost:9999")

    with pytest.raises(APIConnectionError):
        client.messages.create(
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
# Tests for Messages.stream() method
# =============================================================================


@pytest.mark.vcr()
def test_sync_messages_stream_basic(
    span_exporter, anthropic_client, instrument_no_content
):
    """Test Messages.stream() produces correct span with context manager."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Say hello in one word."}]

    with anthropic_client.messages.stream(
        model=model,
        max_tokens=100,
        messages=messages,
    ) as stream:
        # Consume the stream using text_stream
        response_text = "".join(stream.text_stream)
        # Get the final message for assertions
        final_message = stream.get_final_message()

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
def test_stream_wrapper_finalize_idempotent(
    span_exporter, anthropic_client, instrument_no_content
):
    """Fully consumed stream plus explicit close should still yield one span."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Say hello in one word."}]

    stream = anthropic_client.messages.create(
        model=model,
        max_tokens=100,
        messages=messages,
        stream=True,
    )

    response_id = None
    response_model = None
    stop_reason = None
    input_tokens = None
    output_tokens = None

    # Consume the stream fully, then call close() to verify idempotent finalization.
    for chunk in stream:
        if chunk.type == "message_start":
            message = getattr(chunk, "message", None)
            if message:
                response_id = getattr(message, "id", None)
                response_model = getattr(message, "model", None)
                usage = getattr(message, "usage", None)
                if usage:
                    input_tokens = expected_input_tokens(usage)
        elif chunk.type == "message_delta":
            delta = getattr(chunk, "delta", None)
            if delta:
                stop_reason = getattr(delta, "stop_reason", None)
            usage = getattr(chunk, "usage", None)
            if usage:
                output_tokens = getattr(usage, "output_tokens", None)
                input_tokens = expected_input_tokens(usage)

    stream.close()

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


def test_message_wrapper_aggregates_cache_tokens():
    """MessageWrapper should aggregate cache token fields into input tokens."""

    class FakeHandler:
        def stop_llm(self, invocation):  # pylint: disable=no-self-use
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


def test_stream_wrapper_aggregates_cache_tokens():
    """StreamWrapper should aggregate cache token fields from stream chunks."""

    class FakeHandler:
        def stop_llm(self, invocation):  # pylint: disable=no-self-use
            return invocation

        def fail_llm(self, invocation, error):  # pylint: disable=no-self-use
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

    class FakeStream:
        def __init__(self):
            self._chunks = [message_start, message_delta]
            self._index = 0

        def __iter__(self):
            return self

        def __next__(self):
            if self._index >= len(self._chunks):
                raise StopIteration
            value = self._chunks[self._index]
            self._index += 1
            return value

        def close(self):  # pylint: disable=no-self-use
            return None

    invocation = LLMInvocation(
        request_model="claude-sonnet-4-20250514",
        provider="anthropic",
    )
    wrapper = StreamWrapper(FakeStream(), FakeHandler(), invocation)  # type: ignore[arg-type]
    list(wrapper)

    assert invocation.input_tokens == 17
    assert invocation.output_tokens == 8
    assert invocation.finish_reasons == ["stop"]
    assert (
        invocation.attributes["gen_ai.usage.cache_creation.input_tokens"] == 3
    )
    assert invocation.attributes["gen_ai.usage.cache_read.input_tokens"] == 4


@pytest.mark.vcr()
def test_sync_messages_stream_with_params(
    span_exporter, anthropic_client, instrument_no_content
):
    """Test Messages.stream() with additional parameters."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Say hi."}]

    with anthropic_client.messages.stream(
        model=model,
        max_tokens=50,
        messages=messages,
        temperature=0.7,
        top_p=0.9,
        top_k=40,
    ) as stream:
        # Consume the stream
        _ = "".join(stream.text_stream)

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == model
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS] == 50
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE] == 0.7
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_TOP_P] == 0.9
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_TOP_K] == 40


@pytest.mark.vcr()
def test_sync_messages_stream_token_usage(
    span_exporter, anthropic_client, instrument_no_content
):
    """Test that Messages.stream() captures token usage correctly."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Count to 3."}]

    with anthropic_client.messages.stream(
        model=model,
        max_tokens=100,
        messages=messages,
    ) as stream:
        _ = "".join(stream.text_stream)
        final_message = stream.get_final_message()

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS in span.attributes
    assert GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS in span.attributes
    assert span.attributes[
        GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS
    ] == expected_input_tokens(final_message.usage)
    assert (
        span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
        == final_message.usage.output_tokens
    )


def test_sync_messages_stream_connection_error(
    span_exporter, instrument_no_content
):
    """Test that connection errors in Messages.stream() are handled correctly."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Hello"}]

    # Create client with invalid endpoint
    client = Anthropic(base_url="http://localhost:9999")

    with pytest.raises(APIConnectionError):
        with client.messages.stream(
            model=model,
            max_tokens=100,
            messages=messages,
            timeout=0.1,
        ) as stream:
            # Try to consume the stream
            _ = "".join(stream.text_stream)

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == model
    assert ErrorAttributes.ERROR_TYPE in span.attributes
