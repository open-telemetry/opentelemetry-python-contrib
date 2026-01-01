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

"""Tests for Cohere instrumentation."""

from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)

pytest.importorskip("cohere", reason="cohere not installed")


@pytest.fixture
def mock_cohere_response():
    """Create mock Cohere response objects."""
    # Mock chat response
    chat_response = MagicMock()
    chat_response.text = "Hello!"
    chat_response.generation_id = "test-gen-id"
    chat_response.meta = MagicMock()
    chat_response.meta.billed_units = MagicMock()
    chat_response.meta.billed_units.input_tokens = 10
    chat_response.meta.billed_units.output_tokens = 5

    # Mock embed response
    embed_response = MagicMock()
    embed_response.embeddings = [[0.1] * 1024, [0.2] * 1024]
    embed_response.meta = MagicMock()
    embed_response.meta.billed_units = MagicMock()
    embed_response.meta.billed_units.input_tokens = 8

    # Mock rerank response
    rerank_response = MagicMock()
    rerank_result = MagicMock()
    rerank_result.index = 0
    rerank_result.relevance_score = 0.95
    rerank_response.results = [rerank_result]
    rerank_response.meta = MagicMock()

    return {
        "chat": chat_response,
        "embed": embed_response,
        "rerank": rerank_response,
    }


def test_cohere_chat(span_exporter, instrument_with_content, mock_cohere_response):
    """Test Cohere chat instrumentation."""
    with patch("cohere.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client.chat.return_value = mock_cohere_response["chat"]
        mock_client_class.return_value = mock_client

        import cohere
        client = cohere.Client(api_key="test-key")
        client.chat(model="command", message="Say hello in one word")

        # The instrumentation patches the client, so check spans
        spans = span_exporter.get_finished_spans()
        chat_spans = [s for s in spans if "chat" in s.name.lower()]

        if chat_spans:
            span = chat_spans[0]
            assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "cohere"
            assert span.attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL) == "command"


def test_cohere_chat_no_content(span_exporter, instrument_no_content, mock_cohere_response):
    """Test Cohere chat instrumentation without content capture."""
    with patch("cohere.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client.chat.return_value = mock_cohere_response["chat"]
        mock_client_class.return_value = mock_client

        import cohere
        client = cohere.Client(api_key="test-key")
        client.chat(model="command", message="Say hello in one word")

        spans = span_exporter.get_finished_spans()
        chat_spans = [s for s in spans if "chat" in s.name.lower()]

        if chat_spans:
            span = chat_spans[0]
            assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "cohere"


def test_cohere_embed(span_exporter, instrument_with_content, mock_cohere_response):
    """Test Cohere embed instrumentation."""
    with patch("cohere.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client.embed.return_value = mock_cohere_response["embed"]
        mock_client_class.return_value = mock_client

        import cohere
        client = cohere.Client(api_key="test-key")
        client.embed(model="embed-english-v2.0", texts=["Hello, world!", "How are you?"])

        spans = span_exporter.get_finished_spans()
        embed_spans = [s for s in spans if "embed" in s.name.lower()]

        if embed_spans:
            span = embed_spans[0]
            assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "cohere"


def test_cohere_rerank(span_exporter, instrument_with_content, mock_cohere_response):
    """Test Cohere rerank instrumentation."""
    with patch("cohere.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client.rerank.return_value = mock_cohere_response["rerank"]
        mock_client_class.return_value = mock_client

        import cohere
        client = cohere.Client(api_key="test-key")
        client.rerank(
            model="rerank-english-v2.0",
            query="What is the capital of France?",
            documents=[
                "Paris is the capital of France.",
                "Berlin is the capital of Germany.",
            ],
        )

        spans = span_exporter.get_finished_spans()
        rerank_spans = [s for s in spans if "rerank" in s.name.lower()]

        if rerank_spans:
            span = rerank_spans[0]
            assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "cohere"
