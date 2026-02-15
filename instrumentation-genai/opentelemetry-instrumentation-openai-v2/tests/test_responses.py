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

import json

import openai
import pytest
from packaging.version import Version

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)

from .test_utils import assert_all_attributes


def _load_span_messages(span, attribute):
    """Load and parse JSON message content from a span attribute."""
    value = span.attributes.get(attribute)
    assert value is not None, f"Expected attribute {attribute} to be present"
    assert isinstance(value, str), f"Expected {attribute} to be a JSON string"
    parsed = json.loads(value)
    assert isinstance(parsed, list), f"Expected {attribute} to be a JSON list"
    return parsed

# The Responses API was introduced in openai>=1.66.0
# https://github.com/openai/openai-python/blob/main/CHANGELOG.md#1660-2025-03-11
OPENAI_VERSION = Version(openai.__version__)
RESPONSES_API_MIN_VERSION = Version("1.66.0")
skip_if_no_responses_api = pytest.mark.skipif(
    OPENAI_VERSION < RESPONSES_API_MIN_VERSION,
    reason=f"Responses API requires openai >= {RESPONSES_API_MIN_VERSION}, got {OPENAI_VERSION}",
)


@skip_if_no_responses_api
@pytest.mark.vcr()
def test_responses_create(
    span_exporter, openai_client, instrument_with_content
):
    response = openai_client.responses.create(
        model="gpt-4o-mini",
        input="Say this is a test",
        stream=False,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    input_tokens = response.usage.input_tokens if response.usage else None
    output_tokens = response.usage.output_tokens if response.usage else None

    assert_all_attributes(
        spans[0],
        "gpt-4o-mini",
        response.id,
        response.model,
        input_tokens,
        output_tokens,
        operation_name=GenAIAttributes.GenAiOperationNameValues.CHAT.value,
        response_service_tier=response.service_tier,
    )


@skip_if_no_responses_api
@pytest.mark.vcr()
def test_responses_stream_new_response(
    span_exporter, openai_client, instrument_with_content
):
    with openai_client.responses.stream(
        model="gpt-4o-mini",
        input="Say this is a test",
    ) as stream:
        final_response = None
        for event in stream:
            if event.type == "response.completed":
                final_response = event.response
                break

    assert final_response is not None

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    input_tokens = (
        final_response.usage.input_tokens if final_response.usage else None
    )
    output_tokens = (
        final_response.usage.output_tokens if final_response.usage else None
    )

    assert_all_attributes(
        spans[0],
        "gpt-4o-mini",
        final_response.id,
        final_response.model,
        input_tokens,
        output_tokens,
        operation_name=GenAIAttributes.GenAiOperationNameValues.CHAT.value,
        response_service_tier=final_response.service_tier,
    )


@skip_if_no_responses_api
@pytest.mark.vcr()
def test_responses_stream_existing_response(
    span_exporter, openai_client, instrument_with_content
):
    response_id = None
    starting_after = None

    with openai_client.responses.stream(
        model="gpt-4o-mini",
        input="Say this is a test",
        background=True,
    ) as stream:
        for event in stream:
            if event.type == "response.created":
                response_id = event.response.id
            starting_after = event.sequence_number
            if response_id is not None and starting_after is not None:
                break

    assert response_id is not None
    assert starting_after is not None
    span_count = len(span_exporter.get_finished_spans())

    with openai_client.responses.stream(
        response_id=response_id,
        starting_after=starting_after,
    ) as stream:
        final_response = None
        for event in stream:
            if event.type == "response.completed":
                final_response = event.response
                break

    assert final_response is not None

    spans = span_exporter.get_finished_spans()
    assert len(spans) == span_count + 1

    retrieve_spans = spans[span_count:]
    retrieval_operation = getattr(
        GenAIAttributes.GenAiOperationNameValues, "RETRIEVAL", None
    )
    retrieval_operation_name = (
        retrieval_operation.value
        if retrieval_operation is not None
        else "retrieval"
    )
    assert {
        span.attributes.get(GenAIAttributes.GEN_AI_OPERATION_NAME)
        for span in retrieve_spans
    } == {
        retrieval_operation_name,
    }
    retrieve_span = retrieve_spans[0]

    assert_all_attributes(
        retrieve_span,
        final_response.model,
        final_response.id,
        final_response.model,
        final_response.usage.input_tokens if final_response.usage else None,
        final_response.usage.output_tokens if final_response.usage else None,
        operation_name=retrieval_operation_name,
        response_service_tier=final_response.service_tier,
    )


@skip_if_no_responses_api
@pytest.mark.vcr()
def test_responses_retrieve(
    span_exporter, openai_client, instrument_with_content
):
    create_response = openai_client.responses.create(
        model="gpt-4o-mini",
        input="Say this is a test",
        stream=False,
    )

    span_count = len(span_exporter.get_finished_spans())

    response = openai_client.responses.retrieve(create_response.id)
    spans = span_exporter.get_finished_spans()
    assert len(spans) == span_count + 1

    input_tokens = response.usage.input_tokens if response.usage else None
    output_tokens = response.usage.output_tokens if response.usage else None
    retrieval_operation = getattr(
        GenAIAttributes.GenAiOperationNameValues, "RETRIEVAL", None
    )
    operation_name = (
        retrieval_operation.value
        if retrieval_operation is not None
        else "retrieval"
    )

    assert_all_attributes(
        spans[-1],
        response.model,
        response.id,
        response.model,
        input_tokens,
        output_tokens,
        operation_name=operation_name,
        response_service_tier=response.service_tier,
    )


@skip_if_no_responses_api
@pytest.mark.vcr()
def test_responses_retrieve_stream_existing_response(
    span_exporter, openai_client, instrument_with_content
):
    response_id = None
    starting_after = None

    with openai_client.responses.stream(
        model="gpt-4o-mini",
        input="Say this is a test",
        background=True,
    ) as stream:
        for event in stream:
            if event.type == "response.created":
                response_id = event.response.id
            starting_after = event.sequence_number
            if response_id is not None and starting_after is not None:
                break

    assert response_id is not None
    assert starting_after is not None
    span_count = len(span_exporter.get_finished_spans())

    with openai_client.responses.retrieve(
        response_id=response_id,
        starting_after=starting_after,
        stream=True,
    ) as stream:
        final_response = None
        for event in stream:
            if event.type == "response.completed":
                final_response = event.response
                break

    assert final_response is not None

    spans = span_exporter.get_finished_spans()
    assert len(spans) == span_count + 1

    input_tokens = (
        final_response.usage.input_tokens if final_response.usage else None
    )
    output_tokens = (
        final_response.usage.output_tokens if final_response.usage else None
    )
    retrieval_operation = getattr(
        GenAIAttributes.GenAiOperationNameValues, "RETRIEVAL", None
    )
    operation_name = (
        retrieval_operation.value
        if retrieval_operation is not None
        else "retrieval"
    )

    assert_all_attributes(
        spans[-1],
        final_response.model,
        final_response.id,
        final_response.model,
        input_tokens,
        output_tokens,
        operation_name=operation_name,
        response_service_tier=final_response.service_tier,
    )


# =============================================================================
# Content capture tests (experimental mode)
# =============================================================================


@skip_if_no_responses_api
@pytest.mark.vcr("test_responses_create_captures_content.yaml")
def test_responses_create_captures_content(
    span_exporter, openai_client, instrument_with_experimental_content
):
    """Test that input and output content is captured in span attributes."""
    openai_client.responses.create(
        model="gpt-4o-mini",
        input="Say this is a test",
        stream=False,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    input_messages = _load_span_messages(
        span, GenAIAttributes.GEN_AI_INPUT_MESSAGES
    )
    output_messages = _load_span_messages(
        span, GenAIAttributes.GEN_AI_OUTPUT_MESSAGES
    )

    # Input: string input should become a user message with text part
    assert len(input_messages) == 1
    assert input_messages[0]["role"] == "user"
    assert input_messages[0]["parts"][0]["type"] == "text"
    assert "test" in input_messages[0]["parts"][0]["content"]

    # Output: should have an assistant message with text part
    assert len(output_messages) >= 1
    assert output_messages[0]["role"] == "assistant"
    assert output_messages[0]["parts"][0]["type"] == "text"
    assert len(output_messages[0]["parts"][0]["content"]) > 0


@skip_if_no_responses_api
@pytest.mark.vcr("test_responses_stream_captures_content.yaml")
def test_responses_stream_captures_content(
    span_exporter, openai_client, instrument_with_experimental_content
):
    """Test that streaming responses capture content in span attributes."""
    with openai_client.responses.stream(
        model="gpt-4o-mini",
        input="Say this is a test",
    ) as stream:
        for event in stream:
            if event.type == "response.completed":
                break

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    input_messages = _load_span_messages(
        span, GenAIAttributes.GEN_AI_INPUT_MESSAGES
    )
    output_messages = _load_span_messages(
        span, GenAIAttributes.GEN_AI_OUTPUT_MESSAGES
    )

    assert input_messages[0]["role"] == "user"
    assert output_messages[0]["role"] == "assistant"
    assert output_messages[0]["parts"]
    assert output_messages[0]["parts"][0]["type"] == "text"


@skip_if_no_responses_api
@pytest.mark.vcr("test_responses_create_no_content_in_experimental_mode.yaml")
def test_responses_create_no_content_in_experimental_mode(
    span_exporter, openai_client, instrument_with_experimental_no_content
):
    """Test that NO_CONTENT mode does not capture messages in span attributes."""
    openai_client.responses.create(
        model="gpt-4o-mini",
        input="Say this is a test",
        stream=False,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    # Content should NOT be in span attributes under NO_CONTENT
    assert GenAIAttributes.GEN_AI_INPUT_MESSAGES not in span.attributes
    assert GenAIAttributes.GEN_AI_OUTPUT_MESSAGES not in span.attributes

    # Basic span attributes should still be present
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == "gpt-4o-mini"
    assert GenAIAttributes.GEN_AI_RESPONSE_MODEL in span.attributes
    assert GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS in span.attributes
    assert GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS in span.attributes


@skip_if_no_responses_api
@pytest.mark.vcr("test_responses_create_captures_system_instruction.yaml")
def test_responses_create_captures_system_instruction(
    span_exporter, openai_client, instrument_with_experimental_content
):
    """Test that system instructions are captured in span attributes."""
    openai_client.responses.create(
        model="gpt-4o-mini",
        input="Say this is a test",
        instructions="You are a helpful assistant.",
        stream=False,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    system_instructions = span.attributes.get(
        GenAIAttributes.GEN_AI_SYSTEM_INSTRUCTIONS
    )
    assert system_instructions is not None
    parsed = json.loads(system_instructions)
    assert isinstance(parsed, list)
    assert len(parsed) >= 1
    assert parsed[0]["type"] == "text"
    assert "helpful assistant" in parsed[0]["content"]


@skip_if_no_responses_api
@pytest.mark.vcr("test_responses_stream_no_content_in_experimental_mode.yaml")
def test_responses_stream_no_content_in_experimental_mode(
    span_exporter, openai_client, instrument_with_experimental_no_content
):
    """Test that streaming with NO_CONTENT mode does not capture messages."""
    with openai_client.responses.stream(
        model="gpt-4o-mini",
        input="Say this is a test",
    ) as stream:
        for event in stream:
            if event.type == "response.completed":
                break

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    # Content should NOT be in span attributes
    assert GenAIAttributes.GEN_AI_INPUT_MESSAGES not in span.attributes
    assert GenAIAttributes.GEN_AI_OUTPUT_MESSAGES not in span.attributes

    # Basic span attributes should still be present
    assert GenAIAttributes.GEN_AI_RESPONSE_MODEL in span.attributes
    assert GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS in span.attributes
