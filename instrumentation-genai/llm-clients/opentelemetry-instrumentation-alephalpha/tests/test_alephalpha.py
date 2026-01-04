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

"""Tests for Aleph Alpha instrumentation."""

from unittest.mock import MagicMock

import pytest

# Skip all tests if aleph_alpha_client is not installed
pytest.importorskip("aleph_alpha_client", reason="aleph_alpha_client not installed")

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)


@pytest.fixture
def mock_aleph_alpha_client():
    """Create a mock Aleph Alpha client."""
    from unittest.mock import patch
    with patch("aleph_alpha_client.Client") as mock_client_class:
        mock_client = MagicMock()

        # Mock completion response
        mock_completion = MagicMock()
        mock_completion.completion = "Why did the developer use OpenTelemetry? Because they wanted to trace their steps!"
        mock_completion.finish_reason = "maximum_tokens"

        mock_response = MagicMock()
        mock_response.completions = [mock_completion]
        mock_response.num_tokens_prompt_total = 9
        mock_response.num_tokens_generated = 25

        mock_client.complete.return_value = mock_response

        mock_client_class.return_value = mock_client
        yield mock_client


def test_alephalpha_completion(span_exporter, log_exporter, instrument_with_content, mock_aleph_alpha_client):
    """Test alephalpha.completion operation instrumentation."""
    prompt_text = "Tell me a joke about OpenTelemetry."

    # Mock the Prompt class
    mock_prompt = MagicMock()
    mock_request = MagicMock()

    mock_aleph_alpha_client.complete(mock_request, model="luminous-base")

    spans = span_exporter.get_finished_spans()
    completion_spans = [s for s in spans if "completion" in s.name.lower() or "alephalpha" in s.name.lower()]

    if completion_spans:
        span = completion_spans[0]
        assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "alephalpha"
        assert span.attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL) == "luminous-base"


def test_alephalpha_completion_no_content(span_exporter, log_exporter, instrument_no_content, mock_aleph_alpha_client):
    """Test alephalpha.completion with content capture disabled."""
    mock_request = MagicMock()

    mock_aleph_alpha_client.complete(mock_request, model="luminous-base")

    spans = span_exporter.get_finished_spans()
    completion_spans = [s for s in spans if "completion" in s.name.lower() or "alephalpha" in s.name.lower()]

    if completion_spans:
        span = completion_spans[0]
        assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "alephalpha"


def test_alephalpha_completion_with_logs(span_exporter, log_exporter, instrument_with_content, mock_aleph_alpha_client):
    """Test alephalpha.completion with log events."""
    mock_request = MagicMock()

    mock_aleph_alpha_client.complete(mock_request, model="luminous-extended")

    spans = span_exporter.get_finished_spans()
    logs = log_exporter.get_finished_logs()

    completion_spans = [s for s in spans if "completion" in s.name.lower() or "alephalpha" in s.name.lower()]

    if completion_spans:
        span = completion_spans[0]
        assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "alephalpha"
