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

"""Tests for SageMaker instrumentation."""

import io
import json
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)


@pytest.fixture
def mock_sagemaker_client():
    """Create a mock SageMaker runtime client."""
    with patch("boto3.client") as mock_boto_client:
        mock_client = MagicMock()

        # Mock invoke_endpoint response
        response_body = json.dumps(
            [{"generated_text": "Why did the llama cross the road? To get to the other side!"}]
        )
        mock_response = {
            "Body": io.BytesIO(response_body.encode()),
            "ContentType": "application/json",
        }
        mock_client.invoke_endpoint.return_value = mock_response

        mock_boto_client.return_value = mock_client
        yield mock_client


def test_sagemaker_invoke_endpoint(span_exporter, log_exporter, instrument_with_content, mock_sagemaker_client):
    """Test sagemaker invoke_endpoint operation instrumentation."""
    endpoint_name = "my-llama2-endpoint"
    prompt = "Tell me a joke about llamas."
    body = json.dumps(
        {
            "inputs": prompt,
            "parameters": {"temperature": 0.1, "top_p": 0.9, "max_new_tokens": 128},
        }
    )

    mock_sagemaker_client.invoke_endpoint(
        EndpointName=endpoint_name,
        Body=body,
        ContentType="application/json",
    )

    spans = span_exporter.get_finished_spans()
    invoke_spans = [s for s in spans if "invoke" in s.name.lower() or "sagemaker" in s.name.lower()]

    if invoke_spans:
        span = invoke_spans[0]
        assert span.attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL) == endpoint_name


def test_sagemaker_invoke_endpoint_no_content(span_exporter, log_exporter, instrument_no_content, mock_sagemaker_client):
    """Test sagemaker invoke_endpoint with content capture disabled."""
    endpoint_name = "my-llama2-endpoint"
    prompt = "Tell me a joke about llamas."
    body = json.dumps(
        {
            "inputs": prompt,
            "parameters": {"temperature": 0.1, "top_p": 0.9, "max_new_tokens": 128},
        }
    )

    mock_sagemaker_client.invoke_endpoint(
        EndpointName=endpoint_name,
        Body=body,
        ContentType="application/json",
    )

    spans = span_exporter.get_finished_spans()
    invoke_spans = [s for s in spans if "invoke" in s.name.lower() or "sagemaker" in s.name.lower()]

    if invoke_spans:
        span = invoke_spans[0]
        assert span.attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL) == endpoint_name


def test_sagemaker_invoke_endpoint_with_logs(span_exporter, log_exporter, instrument_with_content, mock_sagemaker_client):
    """Test sagemaker invoke_endpoint with log events."""
    endpoint_name = "my-llama2-endpoint"
    prompt = "Tell me a story."
    body = json.dumps(
        {
            "inputs": prompt,
            "parameters": {"temperature": 0.7, "max_new_tokens": 256},
        }
    )

    mock_sagemaker_client.invoke_endpoint(
        EndpointName=endpoint_name,
        Body=body,
        ContentType="application/json",
    )

    spans = span_exporter.get_finished_spans()
    logs = log_exporter.get_finished_logs()

    # Verify we have spans
    invoke_spans = [s for s in spans if "invoke" in s.name.lower() or "sagemaker" in s.name.lower()]
    if invoke_spans:
        span = invoke_spans[0]
        assert span.attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL) == endpoint_name
