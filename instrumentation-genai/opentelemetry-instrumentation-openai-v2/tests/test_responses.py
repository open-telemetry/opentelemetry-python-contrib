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

import openai
import pytest
from packaging.version import Version

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)

from .test_utils import assert_all_attributes

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
        operation_name=GenAIAttributes.GenAiOperationNameValues.GENERATE_CONTENT.value,
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
        operation_name=GenAIAttributes.GenAiOperationNameValues.GENERATE_CONTENT.value,
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

    input_tokens = (
        final_response.usage.input_tokens if final_response.usage else None
    )
    output_tokens = (
        final_response.usage.output_tokens if final_response.usage else None
    )

    assert_all_attributes(
        spans[-1],
        final_response.model,
        final_response.id,
        final_response.model,
        input_tokens,
        output_tokens,
        operation_name=GenAIAttributes.GenAiOperationNameValues.GENERATE_CONTENT.value,
        response_service_tier=final_response.service_tier,
    )
