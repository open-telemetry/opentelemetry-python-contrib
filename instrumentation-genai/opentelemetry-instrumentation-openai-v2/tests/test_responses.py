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
from packaging import version as package_version

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)

# Skip all tests in this file if OpenAI version doesn't support responses API
pytestmark = pytest.mark.skipif(
    package_version.parse(openai.__version__) < package_version.parse("1.66.0"),
    reason="Responses API requires OpenAI >= 1.66.0",
)


@pytest.mark.vcr()
def test_responses_create_with_content(
    span_exporter, log_exporter, openai_client, instrument_with_content
):
    llm_model_value = "gpt-4o-mini"
    input_value = "Say this is a test"

    response = openai_client.responses.create(
        input=input_value, model=llm_model_value
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    
    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME] == "responses"
    assert span.attributes[GenAIAttributes.GEN_AI_SYSTEM] == "openai"
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == llm_model_value
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL] == response.model
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID] == response.id

    # Check usage tokens if available
    if response.usage:
        assert GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS in span.attributes
        assert GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS in span.attributes

    events = span.events
    # At least input message event should be present
    assert len(events) >= 1
    
    # Check for user input event
    user_events = [event for event in events if event.name == "gen_ai.user.message"]
    assert len(user_events) >= 1


@pytest.mark.vcr()
def test_responses_create_no_content(
    span_exporter, log_exporter, openai_client, instrument_no_content
):
    llm_model_value = "gpt-4o-mini"
    input_value = "Say this is a test"

    response = openai_client.responses.create(
        input=input_value, model=llm_model_value
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    
    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME] == "responses"
    assert span.attributes[GenAIAttributes.GEN_AI_SYSTEM] == "openai"
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == llm_model_value

    # Check span events - no content should be captured when capture_content is False
    events = span.events
    for event in events:
        if hasattr(event, 'attributes') and event.attributes:
            assert "gen_ai.event.content" not in event.attributes or not event.attributes.get("gen_ai.event.content")
