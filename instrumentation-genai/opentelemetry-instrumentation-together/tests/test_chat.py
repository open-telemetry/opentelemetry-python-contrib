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

"""Tests for Together AI chat instrumentation."""

from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)

pytest.importorskip("together", reason="together not installed")


@pytest.fixture
def mock_together_response():
    """Create mock Together response."""
    response = MagicMock()
    response.id = "chatcmpl-test123"
    response.model = "meta-llama/Llama-2-7b-chat-hf"
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


@pytest.fixture
def mock_together_completion_response():
    """Create mock Together completion response."""
    response = MagicMock()
    response.id = "cmpl-test123"
    response.model = "meta-llama/Llama-2-7b-hf"
    response.object = "text_completion"

    choice = MagicMock()
    choice.text = "a language model"
    choice.finish_reason = "length"
    response.choices = [choice]

    response.usage = MagicMock()
    response.usage.prompt_tokens = 5
    response.usage.completion_tokens = 20
    response.usage.total_tokens = 25

    return response


def test_together_chat(
    span_exporter, instrument_with_content, mock_together_response
):
    """Test Together AI chat instrumentation."""
    with patch("together.Together") as mock_client_class:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_together_response
        mock_client_class.return_value = mock_client

        from together import Together

        client = Together(api_key="test-key")
        client.chat.completions.create(
            model="meta-llama/Llama-2-7b-chat-hf",
            messages=[{"role": "user", "content": "Say hello in one word"}],
        )

        spans = span_exporter.get_finished_spans()
        chat_spans = [s for s in spans if "chat" in s.name.lower()]

        if chat_spans:
            span = chat_spans[0]
            assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "together"
            assert (
                span.attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL)
                == "meta-llama/Llama-2-7b-chat-hf"
            )


def test_together_chat_no_content(
    span_exporter, instrument_no_content, mock_together_response
):
    """Test Together AI chat instrumentation without content capture."""
    with patch("together.Together") as mock_client_class:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_together_response
        mock_client_class.return_value = mock_client

        from together import Together

        client = Together(api_key="test-key")
        client.chat.completions.create(
            model="meta-llama/Llama-2-7b-chat-hf",
            messages=[{"role": "user", "content": "Say hello in one word"}],
        )

        spans = span_exporter.get_finished_spans()
        chat_spans = [s for s in spans if "chat" in s.name.lower()]

        if chat_spans:
            span = chat_spans[0]
            assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "together"


def test_together_completion(
    span_exporter, instrument_with_content, mock_together_completion_response
):
    """Test Together AI completion instrumentation."""
    with patch("together.Together") as mock_client_class:
        mock_client = MagicMock()
        mock_client.completions.create.return_value = mock_together_completion_response
        mock_client_class.return_value = mock_client

        from together import Together

        client = Together(api_key="test-key")
        client.completions.create(
            model="meta-llama/Llama-2-7b-hf",
            prompt="Hello, I am",
            max_tokens=20,
        )

        spans = span_exporter.get_finished_spans()
        completion_spans = [s for s in spans if "completion" in s.name.lower()]

        if completion_spans:
            span = completion_spans[0]
            assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "together"
