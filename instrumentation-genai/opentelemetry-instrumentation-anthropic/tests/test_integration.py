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

"""Integration tests that make real API calls to Anthropic.

These tests require a valid ANTHROPIC_API_KEY environment variable.
Run with: pytest tests/test_integration.py -m integration

To skip integration tests: pytest -m "not integration"
"""

import os

import pytest
from anthropic import Anthropic

from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)


@pytest.fixture(scope="function")
def anthropic_client():
    """Create Anthropic client with real API key."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY environment variable not set")
    return Anthropic(api_key=api_key)


@pytest.mark.integration
def test_integration_basic_message_create(
    span_exporter, anthropic_client, instrument_anthropic
):
    """Test basic message creation with real API call."""
    model = "claude-sonnet-4-5-20250929"
    messages = [{"role": "user", "content": "Say hello in one word."}]

    response = anthropic_client.messages.create(
        model=model,
        max_tokens=100,
        messages=messages,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.name == f"chat {model}"
    assert (
        GenAIAttributes.GEN_AI_OPERATION_NAME
        in span.attributes
    )
    assert (
        span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME] == "chat"
    )
    assert (
        GenAIAttributes.GenAiSystemValues.ANTHROPIC.value
        == span.attributes[GenAIAttributes.GEN_AI_SYSTEM]
    )
    assert (
        model == span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
    )
    assert (
        ServerAttributes.SERVER_ADDRESS in span.attributes
    )
    assert span.attributes[ServerAttributes.SERVER_ADDRESS] == "api.anthropic.com"
    assert (
        response.id == span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID]
    )
    assert (
        response.model == span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL]
    )
    assert GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS in span.attributes
    assert GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS in span.attributes
    assert (
        span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
        == response.usage.input_tokens
    )
    assert (
        span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
        == response.usage.output_tokens
    )
    assert GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS in span.attributes
    # OpenTelemetry converts lists to tuples when storing as attributes
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS] == (
        response.stop_reason,
    )


# Note: top_p and temperature are mutually exclusive parameters in Anthropic's API.
# They should not be used together. Use temperature OR top_p, but not both.


@pytest.mark.integration
def test_integration_message_with_parameters(
    span_exporter, anthropic_client, instrument_anthropic
):
    """Test message creation with temperature parameter (without top_p)."""
    model = "claude-sonnet-4-5-20250929"
    messages = [{"role": "user", "content": "Count to 3."}]

    response = anthropic_client.messages.create(
        model=model,
        max_tokens=50,
        messages=messages,
        temperature=0.7,
        top_k=40,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS] == 50
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE] == 0.7
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_TOP_K] == 40
    assert response.id == span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID]


@pytest.mark.integration
def test_integration_message_with_top_p(
    span_exporter, anthropic_client, instrument_anthropic
):
    """Test message creation with top_p parameter (without temperature)."""
    model = "claude-sonnet-4-5-20250929"
    messages = [{"role": "user", "content": "Say hello."}]

    response = anthropic_client.messages.create(
        model=model,
        max_tokens=50,
        messages=messages,
        top_p=0.9,
        top_k=40,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS] == 50
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_TOP_P] == 0.9
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_TOP_K] == 40
    assert response.id == span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID]


@pytest.mark.integration
def test_integration_multiple_messages(
    span_exporter, anthropic_client, instrument_anthropic
):
    """Test multiple sequential API calls."""
    model = "claude-sonnet-4-5-20250929"

    # First call
    response1 = anthropic_client.messages.create(
        model=model,
        max_tokens=50,
        messages=[{"role": "user", "content": "Say 'first'."}],
    )

    # Second call
    response2 = anthropic_client.messages.create(
        model=model,
        max_tokens=50,
        messages=[{"role": "user", "content": "Say 'second'."}],
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 2

    # Verify both spans are correct
    span1 = spans[0]
    span2 = spans[1]

    assert span1.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID] == response1.id
    assert span2.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID] == response2.id
    assert span1.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == model
    assert span2.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == model

