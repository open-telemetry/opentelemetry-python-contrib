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

"""Tests for async Cohere chat completions instrumentation."""

import asyncio

import httpx
import pytest

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)


def _chat_response_json(
    response_id="async-response-id",
    finish_reason="COMPLETE",
    content_text="Hello from async!",
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


def _make_async_client(response_json=None, handler=None):
    """Create a Cohere AsyncClientV2 with a mock HTTP transport."""
    if handler is None:
        body = response_json or _chat_response_json()

        async def default_handler(request):
            return httpx.Response(200, json=body)

        handler = default_handler

    transport = httpx.MockTransport(handler)
    httpx_client = httpx.AsyncClient(transport=transport)

    from cohere import AsyncClientV2

    return AsyncClientV2(api_key="test-key", httpx_client=httpx_client)


class TestAsyncChatCompletions:
    """Test async chat completions."""

    @pytest.mark.usefixtures("instrument_no_content")
    def test_async_chat_basic(self, span_exporter):
        async def run():
            client = _make_async_client()
            response = await client.chat(
                model="command-r-plus",
                messages=[{"role": "user", "content": "Hello async"}],
            )
            return response

        response = asyncio.run(run())
        assert response.id == "async-response-id"

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

    @pytest.mark.usefixtures("instrument_no_content")
    def test_async_chat_error(self, span_exporter):
        async def error_handler(request):
            raise httpx.ConnectError("Async connection refused")

        async def run():
            client = _make_async_client(handler=error_handler)
            await client.chat(
                model="command-r-plus",
                messages=[{"role": "user", "content": "Hello"}],
            )

        with pytest.raises(Exception):
            asyncio.run(run())

        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].status.status_code.name == "ERROR"

    @pytest.mark.usefixtures("instrument_with_content")
    def test_async_chat_with_content(self, span_exporter):
        async def run():
            client = _make_async_client(
                response_json=_chat_response_json(
                    content_text="Async content capture test"
                )
            )
            await client.chat(
                model="command-r-plus",
                messages=[{"role": "user", "content": "Test content"}],
            )

        asyncio.run(run())

        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        attrs = dict(spans[0].attributes)
        assert GenAIAttributes.GEN_AI_INPUT_MESSAGES in attrs
        assert GenAIAttributes.GEN_AI_OUTPUT_MESSAGES in attrs
        assert "Test content" in attrs[GenAIAttributes.GEN_AI_INPUT_MESSAGES]
        assert "Async content capture test" in attrs[GenAIAttributes.GEN_AI_OUTPUT_MESSAGES]
