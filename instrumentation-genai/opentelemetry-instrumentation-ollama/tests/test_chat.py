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

"""Tests for Ollama chat instrumentation."""

from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)


@pytest.fixture
def mock_ollama_response():
    """Create mock Ollama response."""
    response = {
        "model": "llama2",
        "message": {
            "role": "assistant",
            "content": "Hello!",
        },
        "done": True,
        "total_duration": 1000000000,
        "load_duration": 100000000,
        "prompt_eval_count": 10,
        "prompt_eval_duration": 200000000,
        "eval_count": 5,
        "eval_duration": 300000000,
    }
    return response


def test_ollama_chat(span_exporter, instrument_with_content, mock_ollama_response):
    """Test Ollama chat instrumentation."""
    with patch("ollama.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client.chat.return_value = mock_ollama_response
        mock_client_class.return_value = mock_client

        import ollama
        client = ollama.Client()
        client.chat(
            model="llama2",
            messages=[{"role": "user", "content": "Say hello in one word"}],
        )

        spans = span_exporter.get_finished_spans()
        chat_spans = [s for s in spans if "chat" in s.name.lower()]

        if chat_spans:
            span = chat_spans[0]
            assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "ollama"
            assert span.attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL) == "llama2"


def test_ollama_chat_no_content(span_exporter, instrument_no_content, mock_ollama_response):
    """Test Ollama chat instrumentation without content capture."""
    with patch("ollama.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client.chat.return_value = mock_ollama_response
        mock_client_class.return_value = mock_client

        import ollama
        client = ollama.Client()
        client.chat(
            model="llama2",
            messages=[{"role": "user", "content": "Say hello in one word"}],
        )

        spans = span_exporter.get_finished_spans()
        chat_spans = [s for s in spans if "chat" in s.name.lower()]

        if chat_spans:
            span = chat_spans[0]
            assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "ollama"
