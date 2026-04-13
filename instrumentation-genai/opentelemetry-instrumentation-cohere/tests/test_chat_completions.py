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

"""Tests for Cohere chat completions instrumentation."""

import json

import httpx
import pytest

from opentelemetry.instrumentation.cohere import CohereInstrumentor
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv.attributes import (
    server_attributes as ServerAttributes,
)


def _chat_response_json(
    response_id="test-response-id",
    finish_reason="COMPLETE",
    content_text="Hello! How can I help you?",
    input_tokens=10,
    output_tokens=20,
):
    return {
        "id": response_id,
        "finish_reason": finish_reason,
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": content_text}],
        },
        "usage": {
            "tokens": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
        },
    }


def _make_client(response_json=None, handler=None):
    """Create a Cohere ClientV2 with a mock HTTP transport."""
    if handler is None:
        body = response_json or _chat_response_json()

        def handler(request):
            return httpx.Response(200, json=body)

    transport = httpx.MockTransport(handler)
    httpx_client = httpx.Client(transport=transport)

    from cohere import ClientV2

    return ClientV2(api_key="test-key", httpx_client=httpx_client)




def _make_stream_handler(events):
    """Create an httpx handler that returns SSE-formatted stream events."""

    def handler(request):
        lines = []
        for event in events:
            lines.append(f"data: {json.dumps(event)}")
            lines.append("")  # blank line = SSE event separator
        body = "\n".join(lines) + "\n"
        return httpx.Response(
            200,
            content=body.encode(),
            headers={"content-type": "text/event-stream"},
        )

    return handler


def _stream_events(
    content_parts=None,
    finish_reason="COMPLETE",
    input_tokens=5,
    output_tokens=15,
    stream_id="stream-id-123",
):
    """Generate a list of SSE events for a streaming chat response."""
    if content_parts is None:
        content_parts = ["Hello ", "world!"]

    events = [
        {
            "type": "message-start",
            "id": stream_id,
            "delta": {"message": {"role": "assistant"}},
        },
    ]
    for text in content_parts:
        events.append(
            {
                "type": "content-delta",
                "index": 0,
                "delta": {"message": {"content": {"text": text}}},
            }
        )
    events.append(
        {
            "type": "message-end",
            "id": stream_id,
            "delta": {
                "finish_reason": finish_reason,
                "usage": {
                    "tokens": {
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                    },
                },
            },
        }
    )
    return events

class TestChatCompletionsNoContent:
    """Test sync chat completions without content capture."""

    @pytest.mark.usefixtures("instrument_no_content")
    def test_chat_basic(self, span_exporter):
        client = _make_client()
        response = client.chat(
            model="command-r-plus",
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert response.id == "test-response-id"

        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1

        span = spans[0]
        assert span.name == "chat command-r-plus"
        attrs = dict(span.attributes)
        assert attrs[GenAIAttributes.GEN_AI_OPERATION_NAME] == "chat"
        assert attrs[GenAIAttributes.GEN_AI_REQUEST_MODEL] == "command-r-plus"
        assert attrs[GenAIAttributes.GEN_AI_PROVIDER_NAME] == "cohere"
        assert attrs[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS] == 10
        assert attrs[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS] == 20
        assert attrs[GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS] == ("stop",)
        assert attrs[GenAIAttributes.GEN_AI_RESPONSE_ID] == "test-response-id"
        assert attrs[ServerAttributes.SERVER_ADDRESS] == "api.cohere.com"

        # No content should be captured
        assert GenAIAttributes.GEN_AI_INPUT_MESSAGES not in attrs
        assert GenAIAttributes.GEN_AI_OUTPUT_MESSAGES not in attrs

    @pytest.mark.usefixtures("instrument_no_content")
    def test_chat_with_optional_params(self, span_exporter):
        client = _make_client()
        client.chat(
            model="command-r-plus",
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.7,
            max_tokens=100,
            p=0.9,
            frequency_penalty=0.5,
            presence_penalty=0.3,
            seed=42,
            stop_sequences=["END"],
        )

        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        attrs = dict(spans[0].attributes)
        assert attrs[GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE] == 0.7
        assert attrs[GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS] == 100
        assert attrs[GenAIAttributes.GEN_AI_REQUEST_TOP_P] == 0.9
        assert attrs[GenAIAttributes.GEN_AI_REQUEST_FREQUENCY_PENALTY] == 0.5
        assert attrs[GenAIAttributes.GEN_AI_REQUEST_PRESENCE_PENALTY] == 0.3
        assert attrs[GenAIAttributes.GEN_AI_REQUEST_SEED] == 42
        assert attrs[GenAIAttributes.GEN_AI_REQUEST_STOP_SEQUENCES] == ("END",)

    @pytest.mark.usefixtures("instrument_no_content")
    def test_chat_max_tokens_finish(self, span_exporter):
        client = _make_client(
            response_json=_chat_response_json(finish_reason="MAX_TOKENS")
        )
        client.chat(
            model="command-r-plus",
            messages=[{"role": "user", "content": "Hello"}],
        )

        spans = span_exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert attrs[GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS] == ("length",)

    @pytest.mark.usefixtures("instrument_no_content")
    def test_chat_error(self, span_exporter):
        def error_handler(request):
            raise httpx.ConnectError("Connection refused")

        client = _make_client(handler=error_handler)
        with pytest.raises(Exception):
            client.chat(
                model="command-r-plus",
                messages=[{"role": "user", "content": "Hello"}],
            )

        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.status.status_code.name == "ERROR"


class TestChatCompletionsWithContent:
    """Test sync chat completions with content capture enabled."""

    @pytest.mark.usefixtures("instrument_with_content")
    def test_chat_captures_content(self, span_exporter):
        client = _make_client(
            response_json=_chat_response_json(
                content_text="I'm doing great, thanks!"
            )
        )
        client.chat(
            model="command-r-plus",
            messages=[{"role": "user", "content": "How are you?"}],
        )

        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        attrs = dict(spans[0].attributes)

        assert GenAIAttributes.GEN_AI_INPUT_MESSAGES in attrs
        assert GenAIAttributes.GEN_AI_OUTPUT_MESSAGES in attrs

        input_msgs = attrs[GenAIAttributes.GEN_AI_INPUT_MESSAGES]
        assert "How are you?" in input_msgs

        output_msgs = attrs[GenAIAttributes.GEN_AI_OUTPUT_MESSAGES]
        assert "I'm doing great, thanks!" in output_msgs

    @pytest.mark.usefixtures("instrument_with_content")
    def test_chat_multi_message(self, span_exporter):
        client = _make_client(
            response_json=_chat_response_json(
                content_text="The capital of France is Paris."
            )
        )
        client.chat(
            model="command-r-plus",
            messages=[
                {"role": "system", "content": "You are a geography expert."},
                {"role": "user", "content": "What is the capital of France?"},
            ],
        )

        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        attrs = dict(spans[0].attributes)
        input_msgs = attrs[GenAIAttributes.GEN_AI_INPUT_MESSAGES]
        assert "geography expert" in input_msgs
        assert "capital of France" in input_msgs




class TestChatStreamNoContent:
    """Test streaming chat completions without content capture."""

    @pytest.mark.usefixtures("instrument_no_content")
    def test_chat_stream_basic(self, span_exporter):
        events = _stream_events()
        client = _make_client(handler=_make_stream_handler(events))

        chunks = list(
            client.chat_stream(
                model="command-r-plus",
                messages=[{"role": "user", "content": "Hello"}],
            )
        )

        # message-start + 2 content-delta + message-end
        assert len(chunks) >= 3

        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1

        span = spans[0]
        assert span.name == "chat command-r-plus"
        attrs = dict(span.attributes)
        assert attrs[GenAIAttributes.GEN_AI_OPERATION_NAME] == "chat"
        assert attrs[GenAIAttributes.GEN_AI_REQUEST_MODEL] == "command-r-plus"
        assert attrs[GenAIAttributes.GEN_AI_PROVIDER_NAME] == "cohere"
        assert attrs[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS] == 5
        assert attrs[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS] == 15
        assert attrs[GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS] == ("stop",)
        assert attrs[GenAIAttributes.GEN_AI_RESPONSE_ID] == "stream-id-123"

        # No content captured
        assert GenAIAttributes.GEN_AI_OUTPUT_MESSAGES not in attrs


class TestChatStreamWithContent:
    """Test streaming chat completions with content capture enabled."""

    @pytest.mark.usefixtures("instrument_with_content")
    def test_chat_stream_captures_content(self, span_exporter):
        events = _stream_events(
            content_parts=["Streamed ", "response"],
            stream_id="stream-id-456",
            input_tokens=8,
            output_tokens=12,
        )
        client = _make_client(handler=_make_stream_handler(events))

        list(
            client.chat_stream(
                model="command-r-plus",
                messages=[{"role": "user", "content": "Stream test"}],
            )
        )

        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        attrs = dict(spans[0].attributes)

        assert GenAIAttributes.GEN_AI_OUTPUT_MESSAGES in attrs
        output_msgs = attrs[GenAIAttributes.GEN_AI_OUTPUT_MESSAGES]
        assert "Streamed response" in output_msgs

class TestUninstrument:
    """Test that uninstrumenting properly restores original methods."""

    def test_uninstrument(
        self, tracer_provider, logger_provider, meter_provider, span_exporter
    ):
        import os

        from opentelemetry.instrumentation._semconv import (
            OTEL_SEMCONV_STABILITY_OPT_IN,
            _OpenTelemetrySemanticConventionStability,
        )

        _OpenTelemetrySemanticConventionStability._initialized = False
        os.environ[OTEL_SEMCONV_STABILITY_OPT_IN] = "gen_ai_latest_experimental"

        instrumentor = CohereInstrumentor()
        instrumentor.instrument(
            tracer_provider=tracer_provider,
            logger_provider=logger_provider,
            meter_provider=meter_provider,
        )

        client = _make_client()
        client.chat(
            model="command-r-plus",
            messages=[{"role": "user", "content": "Hello"}],
        )
        assert len(span_exporter.get_finished_spans()) == 1

        instrumentor.uninstrument()
        span_exporter.clear()

        client2 = _make_client()
        client2.chat(
            model="command-r-plus",
            messages=[{"role": "user", "content": "Hello again"}],
        )
        # After uninstrument, no new spans should be created
        assert len(span_exporter.get_finished_spans()) == 0

        os.environ.pop(OTEL_SEMCONV_STABILITY_OPT_IN, None)
