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

"""Tests for Replicate instrumentation."""

import sys
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)


@pytest.fixture
def mock_replicate_client():
    """Create a mock Replicate client."""
    with patch("replicate.Client") as mock_client_class:
        mock_client = MagicMock()

        # Mock run response
        mock_client.run.return_value = [
            "Why did the observability tool go to therapy? ",
            "Because it had too many traces of anxiety!",
        ]

        # Mock stream response
        def mock_stream(*args, **kwargs):
            yield "Why did the "
            yield "telemetry "
            yield "cross the road? "
            yield "To get to the other span!"

        mock_client.stream = mock_stream

        mock_client_class.return_value = mock_client
        yield mock_client


@pytest.mark.skipif(sys.version_info < (3, 9), reason="requires python3.9")
def test_replicate_run(span_exporter, log_exporter, instrument_with_content, mock_replicate_client):
    """Test replicate.run operation instrumentation."""
    model_version = "meta/llama-2-70b-chat"

    mock_replicate_client.run(
        model_version,
        input={
            "prompt": "Tell me a joke about OpenTelemetry",
        },
    )

    spans = span_exporter.get_finished_spans()
    run_spans = [s for s in spans if "run" in s.name.lower() or "replicate" in s.name.lower()]

    if run_spans:
        span = run_spans[0]
        assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "replicate"


@pytest.mark.skipif(sys.version_info < (3, 9), reason="requires python3.9")
def test_replicate_stream(span_exporter, log_exporter, instrument_with_content, mock_replicate_client):
    """Test replicate.stream operation instrumentation."""
    model_version = "meta/llama-2-70b-chat"

    response = ""
    for event in mock_replicate_client.stream(
        model_version,
        input={
            "prompt": "Tell me a joke about OpenTelemetry",
        },
    ):
        response += str(event)

    spans = span_exporter.get_finished_spans()
    stream_spans = [s for s in spans if "stream" in s.name.lower() or "replicate" in s.name.lower()]

    if stream_spans:
        span = stream_spans[0]
        assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "replicate"


@pytest.mark.skipif(sys.version_info < (3, 9), reason="requires python3.9")
def test_replicate_no_content_capture(span_exporter, log_exporter, instrument_no_content, mock_replicate_client):
    """Test replicate with content capture disabled."""
    model_version = "meta/llama-2-70b-chat"

    mock_replicate_client.run(
        model_version,
        input={
            "prompt": "Tell me a joke about OpenTelemetry",
        },
    )

    spans = span_exporter.get_finished_spans()
    run_spans = [s for s in spans if "run" in s.name.lower() or "replicate" in s.name.lower()]

    if run_spans:
        span = run_spans[0]
        assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "replicate"
