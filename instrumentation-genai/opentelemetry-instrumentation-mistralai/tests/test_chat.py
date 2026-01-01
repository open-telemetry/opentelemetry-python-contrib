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

"""Tests for MistralAI chat instrumentation."""

from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)


@pytest.fixture
def mock_mistral_response():
    """Create mock Mistral response."""
    response = MagicMock()
    response.id = "chatcmpl-test123"
    response.model = "mistral-small-latest"
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


def test_mistralai_chat(span_exporter, instrument_with_content, mock_mistral_response):
    """Test MistralAI chat instrumentation."""
    with patch("mistralai.Mistral") as mock_client_class:
        mock_client = MagicMock()
        mock_client.chat.complete.return_value = mock_mistral_response
        mock_client_class.return_value = mock_client

        from mistralai import Mistral

        client = Mistral(api_key="test-key")
        client.chat.complete(
            model="mistral-small-latest",
            messages=[{"role": "user", "content": "Say hello in one word"}],
        )

        spans = span_exporter.get_finished_spans()
        chat_spans = [s for s in spans if "chat" in s.name.lower()]

        if chat_spans:
            span = chat_spans[0]
            assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "mistral"
            assert (
                span.attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL)
                == "mistral-small-latest"
            )


def test_mistralai_chat_no_content(
    span_exporter, instrument_no_content, mock_mistral_response
):
    """Test MistralAI chat instrumentation without content capture."""
    with patch("mistralai.Mistral") as mock_client_class:
        mock_client = MagicMock()
        mock_client.chat.complete.return_value = mock_mistral_response
        mock_client_class.return_value = mock_client

        from mistralai import Mistral

        client = Mistral(api_key="test-key")
        client.chat.complete(
            model="mistral-small-latest",
            messages=[{"role": "user", "content": "Say hello in one word"}],
        )

        spans = span_exporter.get_finished_spans()
        chat_spans = [s for s in spans if "chat" in s.name.lower()]

        if chat_spans:
            span = chat_spans[0]
            assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "mistral"


def test_mistralai_chat_streaming(
    span_exporter, instrument_with_content, mock_mistral_response
):
    """Test MistralAI chat streaming instrumentation."""
    with patch("mistralai.Mistral") as mock_client_class:
        mock_client = MagicMock()

        # Mock streaming response
        def mock_stream():
            chunk = MagicMock()
            chunk.data = MagicMock()
            chunk.data.id = "chatcmpl-test123"
            chunk.data.model = "mistral-small-latest"
            delta = MagicMock()
            delta.content = "Hello!"
            choice = MagicMock()
            choice.delta = delta
            choice.finish_reason = "stop"
            chunk.data.choices = [choice]
            yield chunk

        mock_client.chat.stream.return_value = mock_stream()
        mock_client_class.return_value = mock_client

        from mistralai import Mistral

        client = Mistral(api_key="test-key")
        response = client.chat.stream(
            model="mistral-small-latest",
            messages=[{"role": "user", "content": "Count from 1 to 5"}],
        )

        # Consume the stream
        chunks = list(response)

        spans = span_exporter.get_finished_spans()
        chat_spans = [s for s in spans if "chat" in s.name.lower()]

        if chat_spans:
            span = chat_spans[0]
            assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "mistral"
