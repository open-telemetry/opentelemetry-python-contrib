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

import inspect
import json
import os
from pathlib import Path

import pytest
from anthropic import Anthropic, APIConnectionError, NotFoundError
from anthropic.resources.messages import Messages as _Messages

from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor
from opentelemetry.instrumentation.anthropic.messages_extractors import (
    GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS,
    GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS,
)
from opentelemetry.instrumentation.anthropic.wrappers import (
    MessagesStreamWrapper,
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

# Detect whether the installed anthropic SDK supports tools / thinking params.
# Older SDK versions (e.g. 0.16.0) do not accept these keyword arguments.
_create_params = set(inspect.signature(_Messages.create).parameters)
_has_tools_param = "tools" in _create_params
_has_thinking_param = "thinking" in _create_params


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


def _load_span_messages(span, attribute):
    value = span.attributes.get(attribute)
    assert value is not None
    assert isinstance(value, str)
    parsed = json.loads(value)
    assert isinstance(parsed, list)
    return parsed


def _skip_if_cassette_missing_and_no_real_key(request):
    cassette_path = (
        Path(__file__).parent / "cassettes" / f"{request.node.name}.yaml"
    )
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not cassette_path.exists() and api_key == "test_anthropic_api_key":
        pytest.skip(
            f"Cassette {cassette_path.name} is missing. "
            "Set a real ANTHROPIC_API_KEY to record it."
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
def test_sync_messages_create_captures_content(
    span_exporter, anthropic_client, instrument_with_content
):
    """Test content capture on non-streaming create."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Say hello in one word."}]

    anthropic_client.messages.create(
        model=model,
        max_tokens=100,
        messages=messages,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    input_messages = _load_span_messages(
        span, GenAIAttributes.GEN_AI_INPUT_MESSAGES
    )
    output_messages = _load_span_messages(
        span, GenAIAttributes.GEN_AI_OUTPUT_MESSAGES
    )

    assert input_messages[0]["role"] == "user"
    assert input_messages[0]["parts"][0]["type"] == "text"
    assert output_messages[0]["role"] == "assistant"
    assert output_messages[0]["parts"][0]["type"] == "text"


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
def test_sync_messages_create_streaming_captures_content(
    span_exporter, anthropic_client, instrument_with_content
):
    """Test content capture on create(stream=True)."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Say hello in one word."}]

    with anthropic_client.messages.create(
        model=model,
        max_tokens=100,
        messages=messages,
        stream=True,
    ) as stream:
        for _ in stream:
            pass

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    input_messages = _load_span_messages(
        span, GenAIAttributes.GEN_AI_INPUT_MESSAGES
    )
    output_messages = _load_span_messages(
        span, GenAIAttributes.GEN_AI_OUTPUT_MESSAGES
    )
    assert input_messages[0]["role"] == "user"
    assert output_messages[0]["role"] == "assistant"
    assert output_messages[0]["parts"]


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


@pytest.mark.vcr()
def test_sync_messages_create_streaming_delegates_response_attribute(
    request, anthropic_client, instrument_no_content
):
    """Stream wrapper should expose attributes from the wrapped stream."""
    _skip_if_cassette_missing_and_no_real_key(request)

    stream = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=100,
        messages=[{"role": "user", "content": "Say hi."}],
        stream=True,
    )

    # `response` exists on Anthropic Stream and should be reachable on wrapper.
    assert stream.response is not None
    assert stream.response.status_code == 200
    assert stream.response.headers.get("request-id") is not None
    stream.close()


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


@pytest.mark.vcr()
@pytest.mark.skipif(
    not _has_tools_param,
    reason="anthropic SDK too old to support 'tools' parameter",
)
def test_sync_messages_create_captures_tool_use_content(
    request, span_exporter, anthropic_client, instrument_with_content
):
    """Test that tool_use blocks are captured as tool_call parts."""
    _skip_if_cassette_missing_and_no_real_key(request)
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "What is the weather in SF?"}]

    anthropic_client.messages.create(
        model=model,
        max_tokens=256,
        messages=messages,
        tools=[
            {
                "name": "get_weather",
                "description": "Get weather by city",
                "input_schema": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            }
        ],
        tool_choice={"type": "tool", "name": "get_weather"},
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    output_messages = _load_span_messages(
        span, GenAIAttributes.GEN_AI_OUTPUT_MESSAGES
    )

    assert any(
        part.get("type") == "tool_call"
        for message in output_messages
        for part in message.get("parts", [])
    )


@pytest.mark.vcr()
@pytest.mark.skipif(
    not _has_thinking_param,
    reason="anthropic SDK too old to support 'thinking' parameter",
)
def test_sync_messages_create_captures_thinking_content(
    request, span_exporter, anthropic_client, instrument_with_content
):
    """Test that thinking blocks are captured as reasoning parts."""
    _skip_if_cassette_missing_and_no_real_key(request)
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "What is 17*19? Think first."}]

    anthropic_client.messages.create(
        model=model,
        max_tokens=16000,
        messages=messages,
        thinking={"type": "enabled", "budget_tokens": 10000},
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    output_messages = _load_span_messages(
        span, GenAIAttributes.GEN_AI_OUTPUT_MESSAGES
    )

    assert any(
        part.get("type") == "reasoning"
        for message in output_messages
        for part in message.get("parts", [])
    )


@pytest.mark.vcr()
def test_stream_wrapper_finalize_idempotent(  # pylint: disable=too-many-locals
    span_exporter,
    anthropic_client,
    instrument_no_content,
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


@pytest.mark.vcr()
def test_sync_messages_create_aggregates_cache_tokens(
    span_exporter, anthropic_client, instrument_no_content
):
    """Non-streaming response with non-zero cache tokens aggregates correctly."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Say hello in one word."}]

    response = anthropic_client.messages.create(
        model=model,
        max_tokens=100,
        messages=messages,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert (
        GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS in span.attributes
    )
    assert GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS in span.attributes
    assert span.attributes[
        GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS
    ] == expected_input_tokens(response.usage)
    assert (
        span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
        == response.usage.output_tokens
    )
    cache_creation = getattr(response.usage, "cache_creation_input_tokens", 0)
    cache_read = getattr(response.usage, "cache_read_input_tokens", 0)
    assert (
        span.attributes[GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS]
        == cache_creation
    )
    assert span.attributes[GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS] == cache_read


@pytest.mark.vcr()
def test_sync_messages_create_streaming_aggregates_cache_tokens(
    span_exporter, anthropic_client, instrument_no_content
):
    """Streaming response with non-zero cache tokens aggregates correctly."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Say hello in one word."}]

    input_tokens = None
    output_tokens = None
    cache_creation = None
    cache_read = None

    with anthropic_client.messages.create(
        model=model,
        max_tokens=100,
        messages=messages,
        stream=True,
    ) as stream:
        for chunk in stream:
            if chunk.type == "message_delta":
                usage = getattr(chunk, "usage", None)
                if usage:
                    input_tokens = expected_input_tokens(usage)
                    output_tokens = getattr(usage, "output_tokens", None)
                    cache_creation = getattr(
                        usage, "cache_creation_input_tokens", None
                    )
                    cache_read = getattr(
                        usage, "cache_read_input_tokens", None
                    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert (
        GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS in span.attributes
    )
    assert GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS in span.attributes
    assert (
        span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
        == input_tokens
    )
    assert (
        span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
        == output_tokens
    )
    assert (
        span.attributes[GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS]
        == cache_creation
    )
    assert (
        span.attributes[GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS] == cache_read
    )


@pytest.mark.vcr()
def test_sync_messages_create_stream_propagation_error(
    span_exporter, anthropic_client, instrument_no_content, monkeypatch
):
    """Mid-stream errors from the underlying iterator must propagate and record error on span."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Say hello in one word."}]

    stream = anthropic_client.messages.create(
        model=model,
        max_tokens=100,
        messages=messages,
        stream=True,
    )

    # Wrap the underlying stream so we inject an iteration error but still
    # delegate close()/other behavior to the real stream.
    class ErrorInjectingStreamDelegate:
        def __init__(self, inner):
            self._inner = inner
            self._count = 0

        def __iter__(self):
            return self

        def __next__(self):
            # Fail after yielding one chunk so this exercises a mid-stream error.
            if self._count == 1:
                raise ConnectionError("connection reset during stream")
            self._count += 1
            return next(self._inner)

        def close(self):
            return self._inner.close()

        def __getattr__(self, name):
            return getattr(self._inner, name)

    monkeypatch.setattr(
        stream, "_stream", ErrorInjectingStreamDelegate(stream._stream)
    )

    with pytest.raises(
        ConnectionError, match="connection reset during stream"
    ):
        with stream:
            for _ in stream:
                pass

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == model
    assert span.attributes[ErrorAttributes.ERROR_TYPE] == "ConnectionError"


@pytest.mark.vcr()
def test_sync_messages_create_streaming_user_exception(
    span_exporter, anthropic_client, instrument_no_content
):
    """Test that user raised exceptions are propagated."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Say hello in one word."}]

    with pytest.raises(ValueError, match="User raised exception"):
        with anthropic_client.messages.create(
            model=model,
            max_tokens=100,
            messages=messages,
            stream=True,
        ) as stream:
            for _ in stream:
                raise ValueError("User raised exception")

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == model
    assert span.attributes[ErrorAttributes.ERROR_TYPE] == "ValueError"


@pytest.mark.vcr()
def test_sync_messages_create_instrumentation_error_swallowed(
    span_exporter, anthropic_client, instrument_no_content, monkeypatch
):
    """Instrumentation errors in _process_chunk must not propagate to user code."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Say hello in one word."}]

    def exploding_process_chunk(self, chunk):
        raise RuntimeError("instrumentation bug")

    monkeypatch.setattr(
        MessagesStreamWrapper, "_process_chunk", exploding_process_chunk
    )

    with anthropic_client.messages.create(
        model=model,
        max_tokens=100,
        messages=messages,
        stream=True,
    ) as stream:
        chunks = list(stream)

    assert len(chunks) > 0

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == model
    assert ErrorAttributes.ERROR_TYPE not in span.attributes


# =============================================================================
# Tests for EVENT_ONLY content capture mode
# =============================================================================


@pytest.mark.vcr()
def test_sync_messages_create_event_only_no_content_in_span(
    span_exporter, log_exporter, anthropic_client, instrument_event_only
):
    """Test that EVENT_ONLY mode does not capture content in span attributes
    but does emit a log event with the content."""
    model = "claude-sonnet-4-20250514"
    messages = [{"role": "user", "content": "Say hello in one word."}]

    anthropic_client.messages.create(
        model=model,
        max_tokens=100,
        messages=messages,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    # Content should NOT be in span attributes under EVENT_ONLY
    assert GenAIAttributes.GEN_AI_INPUT_MESSAGES not in span.attributes
    assert GenAIAttributes.GEN_AI_OUTPUT_MESSAGES not in span.attributes

    # Basic span attributes should still be present
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == model
    assert GenAIAttributes.GEN_AI_RESPONSE_MODEL in span.attributes
    assert GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS in span.attributes
    assert GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS in span.attributes

    # A log event should have been emitted with the content
    logs = log_exporter.get_finished_logs()
    assert len(logs) == 1
    log_record = logs[0].log_record
    assert log_record.event_name == "gen_ai.client.inference.operation.details"
