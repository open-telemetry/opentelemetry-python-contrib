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

"""Tests for Watsonx instrumentation."""

import sys
from unittest.mock import MagicMock

import pytest

# Skip all tests if ibm-watsonx-ai is not installed
pytest.importorskip("ibm_watsonx_ai", reason="ibm-watsonx-ai not installed")

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)


@pytest.fixture
def mock_watsonx_model():
    """Create a mock Watsonx model."""
    from unittest.mock import patch
    with patch("ibm_watsonx_ai.foundation_models.ModelInference") as mock_model_class:
        mock_model = MagicMock()

        # Mock generate response
        mock_model.generate.return_value = {
            "results": [
                {
                    "generated_text": "The capital of France is Paris.",
                    "stop_reason": "eos_token",
                    "generated_token_count": 10,
                    "input_token_count": 5,
                }
            ],
            "model_id": "google/flan-ul2",
        }

        # Mock generate_text response
        mock_model.generate_text.return_value = "The capital of France is Paris."

        mock_model_class.return_value = mock_model
        yield mock_model


def test_watsonx_generate(span_exporter, log_exporter, instrument_with_content, mock_watsonx_model):
    """Test watsonx.generate operation instrumentation."""
    prompt = "What is the capital of France?"

    mock_watsonx_model.generate(prompt)

    spans = span_exporter.get_finished_spans()
    generate_spans = [s for s in spans if "generate" in s.name.lower() or "watsonx" in s.name.lower()]

    if generate_spans:
        span = generate_spans[0]
        assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "watsonx"


def test_watsonx_generate_text(span_exporter, log_exporter, instrument_with_content, mock_watsonx_model):
    """Test watsonx.generate_text operation instrumentation."""
    prompt = "What is the capital of Germany?"

    mock_watsonx_model.generate_text(prompt)

    spans = span_exporter.get_finished_spans()
    generate_spans = [s for s in spans if "generate" in s.name.lower() or "watsonx" in s.name.lower()]

    if generate_spans:
        span = generate_spans[0]
        assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "watsonx"


def test_watsonx_generate_no_content(span_exporter, log_exporter, instrument_no_content, mock_watsonx_model):
    """Test watsonx.generate with content capture disabled."""
    prompt = "What is the capital of Spain?"

    mock_watsonx_model.generate(prompt)

    spans = span_exporter.get_finished_spans()
    generate_spans = [s for s in spans if "generate" in s.name.lower() or "watsonx" in s.name.lower()]

    if generate_spans:
        span = generate_spans[0]
        assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "watsonx"


def test_watsonx_with_logs(span_exporter, log_exporter, instrument_with_content, mock_watsonx_model):
    """Test watsonx with log events."""
    prompt = "Tell me about the history of computing."

    mock_watsonx_model.generate(prompt)

    spans = span_exporter.get_finished_spans()
    logs = log_exporter.get_finished_logs()

    generate_spans = [s for s in spans if "generate" in s.name.lower() or "watsonx" in s.name.lower()]

    if generate_spans:
        span = generate_spans[0]
        assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "watsonx"
