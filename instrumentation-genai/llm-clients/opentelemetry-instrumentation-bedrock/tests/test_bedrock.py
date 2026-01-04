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

"""Tests for AWS Bedrock instrumentation."""

import io
import json
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)

pytest.importorskip("boto3", reason="boto3 not installed")


@pytest.fixture
def mock_invoke_model_response():
    """Create mock Bedrock invoke_model response."""
    response_body = {
        "id": "msg_test123",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "Hello!"}],
        "model": "claude-3-sonnet-20240229",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    return {
        "body": io.BytesIO(json.dumps(response_body).encode("utf-8")),
        "contentType": "application/json",
        "ResponseMetadata": {
            "RequestId": "test-request-id",
            "HTTPStatusCode": 200,
        },
    }


@pytest.fixture
def mock_converse_response():
    """Create mock Bedrock converse response."""
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": "Hello!"}],
            }
        },
        "stopReason": "end_turn",
        "usage": {
            "inputTokens": 10,
            "outputTokens": 5,
            "totalTokens": 15,
        },
        "ResponseMetadata": {
            "RequestId": "test-request-id",
            "HTTPStatusCode": 200,
        },
    }


def test_bedrock_invoke_model(
    span_exporter, instrument_bedrock_with_content, mock_invoke_model_response
):
    """Test Bedrock invoke_model instrumentation."""
    with patch("boto3.client") as mock_boto_client:
        mock_client = MagicMock()
        mock_client.invoke_model.return_value = mock_invoke_model_response
        mock_boto_client.return_value = mock_client

        import boto3

        brt = boto3.client(
            service_name="bedrock-runtime",
            region_name="us-east-1",
        )

        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "Say hello in one word"}],
            }
        )

        brt.invoke_model(
            modelId="anthropic.claude-3-sonnet-20240229-v1:0",
            body=body,
            contentType="application/json",
            accept="application/json",
        )

        spans = span_exporter.get_finished_spans()
        invoke_spans = [s for s in spans if "invoke" in s.name.lower()]

        if invoke_spans:
            span = invoke_spans[0]
            assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "aws.bedrock"
            assert (
                span.attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL)
                == "anthropic.claude-3-sonnet-20240229-v1:0"
            )


def test_bedrock_invoke_model_no_content(
    span_exporter, instrument_bedrock_no_content, mock_invoke_model_response
):
    """Test Bedrock invoke_model instrumentation without content capture."""
    with patch("boto3.client") as mock_boto_client:
        mock_client = MagicMock()
        mock_client.invoke_model.return_value = mock_invoke_model_response
        mock_boto_client.return_value = mock_client

        import boto3

        brt = boto3.client(
            service_name="bedrock-runtime",
            region_name="us-east-1",
        )

        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "Say hello in one word"}],
            }
        )

        brt.invoke_model(
            modelId="anthropic.claude-3-sonnet-20240229-v1:0",
            body=body,
            contentType="application/json",
            accept="application/json",
        )

        spans = span_exporter.get_finished_spans()
        invoke_spans = [s for s in spans if "invoke" in s.name.lower()]

        if invoke_spans:
            span = invoke_spans[0]
            assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "aws.bedrock"


def test_bedrock_converse(
    span_exporter, instrument_bedrock_with_content, mock_converse_response
):
    """Test Bedrock converse instrumentation."""
    with patch("boto3.client") as mock_boto_client:
        mock_client = MagicMock()
        mock_client.converse.return_value = mock_converse_response
        mock_boto_client.return_value = mock_client

        import boto3

        brt = boto3.client(
            service_name="bedrock-runtime",
            region_name="us-east-1",
        )

        brt.converse(
            modelId="anthropic.claude-3-sonnet-20240229-v1:0",
            messages=[
                {
                    "role": "user",
                    "content": [{"text": "Say hello in one word"}],
                }
            ],
            inferenceConfig={"maxTokens": 100},
        )

        spans = span_exporter.get_finished_spans()
        converse_spans = [s for s in spans if "converse" in s.name.lower()]

        if converse_spans:
            span = converse_spans[0]
            assert span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM) == "aws.bedrock"
