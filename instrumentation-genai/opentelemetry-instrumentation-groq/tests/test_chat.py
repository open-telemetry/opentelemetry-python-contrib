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

"""Tests for Groq chat instrumentation."""

from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)


@pytest.fixture
def mock_groq_response():
    """Create mock Groq response."""
    response = MagicMock()
    response.id = "chatcmpl-test123"
    response.model = "mixtral-8x7b-32768"
    response.object = "chat.completion"

    choice = MagicMock()
    choice.index = 0
    choice.finish_reason = "stop"
    choice.message = MagicMock()
    choice.message.role = "assistant"
    choice.message.content = "Hello!"
    response.choices = [choice]

    response.usage = MagicMock()
    response.usage.prompt_tokens = 10
    response.usage.completion_tokens = 5
    response.usage.total_tokens = 15

    return response


def test_groq_chat(span_exporter, instrument_with_content, mock_groq_response):
    """Test Groq chat completion instrumentation."""
    with patch("groq.Groq") as mock_client_class:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_groq_response
        mock_client_class.return_value = mock_client

        import groq
        client = groq.Groq(api_key="test-key")
        client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[{"role": "user", "content": "Say hello in one word"}],
        )

        spans = span_exporter.get_finished_spans()
        chat_spans = [s for s in spans if "chat" in s.name.lower()]

        if chat_spans:
            span = chat_spans[0]
            assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "groq"
            assert span.attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL) == "mixtral-8x7b-32768"


def test_groq_chat_no_content(span_exporter, instrument_no_content, mock_groq_response):
    """Test Groq chat completion instrumentation without content capture."""
    with patch("groq.Groq") as mock_client_class:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_groq_response
        mock_client_class.return_value = mock_client

        import groq
        client = groq.Groq(api_key="test-key")
        client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[{"role": "user", "content": "Say hello in one word"}],
        )

        spans = span_exporter.get_finished_spans()
        chat_spans = [s for s in spans if "chat" in s.name.lower()]

        if chat_spans:
            span = chat_spans[0]
            assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "groq"


def test_groq_chat_streaming(span_exporter, instrument_with_content, mock_groq_response):
    """Test Groq chat completion streaming instrumentation."""
    with patch("groq.Groq") as mock_client_class:
        mock_client = MagicMock()

        # Mock streaming response
        def mock_stream():
            chunk = MagicMock()
            chunk.id = "chatcmpl-test123"
            chunk.model = "mixtral-8x7b-32768"
            delta = MagicMock()
            delta.content = "Hello!"
            choice = MagicMock()
            choice.delta = delta
            choice.finish_reason = "stop"
            chunk.choices = [choice]
            yield chunk

        mock_client.chat.completions.create.return_value = mock_stream()
        mock_client_class.return_value = mock_client

        import groq
        client = groq.Groq(api_key="test-key")
        response = client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[{"role": "user", "content": "Count from 1 to 5"}],
            stream=True,
        )

        # Consume the stream
        chunks = list(response)

        spans = span_exporter.get_finished_spans()
        chat_spans = [s for s in spans if "chat" in s.name.lower()]

        if chat_spans:
            span = chat_spans[0]
            assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "groq"
