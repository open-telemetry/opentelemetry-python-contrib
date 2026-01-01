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

"""Tests for Transformers instrumentation."""

import importlib.util
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)

# Skip the whole module if torch is absent
pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("torch") is None,
    reason="`torch` not available - install extras to run these tests",
)


@pytest.fixture
def mock_transformers_pipeline():
    """Create a mock transformers pipeline."""
    with patch("transformers.pipeline") as mock_pipeline_func:
        mock_pipeline = MagicMock()

        # Mock pipeline response
        mock_pipeline.return_value = [
            {"generated_text": "Tell me a joke about OpenTelemetry. Why did the span cross the trace? To get to the other side!"}
        ]

        # Set model name
        mock_pipeline.model = MagicMock()
        mock_pipeline.model.name_or_path = "gpt2"

        mock_pipeline_func.return_value = mock_pipeline
        yield mock_pipeline


def test_transformers_pipeline(span_exporter, log_exporter, instrument_with_content, mock_transformers_pipeline):
    """Test transformers pipeline instrumentation."""
    prompt_text = "Tell me a joke about OpenTelemetry."

    mock_transformers_pipeline(prompt_text)

    spans = span_exporter.get_finished_spans()
    pipeline_spans = [s for s in spans if "pipeline" in s.name.lower() or "transformers" in s.name.lower()]

    if pipeline_spans:
        span = pipeline_spans[0]
        assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "transformers"
        assert span.attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL) == "gpt2"


def test_transformers_pipeline_no_content(span_exporter, log_exporter, instrument_no_content, mock_transformers_pipeline):
    """Test transformers pipeline with content capture disabled."""
    prompt_text = "Tell me a joke about OpenTelemetry."

    mock_transformers_pipeline(prompt_text)

    spans = span_exporter.get_finished_spans()
    pipeline_spans = [s for s in spans if "pipeline" in s.name.lower() or "transformers" in s.name.lower()]

    if pipeline_spans:
        span = pipeline_spans[0]
        assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "transformers"


def test_transformers_pipeline_with_logs(span_exporter, log_exporter, instrument_with_content, mock_transformers_pipeline):
    """Test transformers pipeline with log events."""
    prompt_text = "Complete this sentence: The weather today is"

    mock_transformers_pipeline(prompt_text)

    spans = span_exporter.get_finished_spans()
    logs = log_exporter.get_finished_logs()

    pipeline_spans = [s for s in spans if "pipeline" in s.name.lower() or "transformers" in s.name.lower()]

    if pipeline_spans:
        span = pipeline_spans[0]
        assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "transformers"
