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

import pytest
from openai import OpenAI

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
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
    assert span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME] == "chat"
    assert span.attributes[GenAIAttributes.GEN_AI_SYSTEM] == "openai"
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == llm_model_value
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL] == response.model
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID] == response.id

    # Check usage tokens if available
    if response.usage:
        assert GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS in span.attributes
        assert GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS in span.attributes

    logs = log_exporter.get_finished_logs()
    # At least input message should be logged
    assert len(logs) >= 1


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
    assert span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME] == "chat"
    assert span.attributes[GenAIAttributes.GEN_AI_SYSTEM] == "openai"
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == llm_model_value

    # No content should be captured in logs when capture_content is False
    logs = log_exporter.get_finished_logs()
    for log in logs:
        if log.body and isinstance(log.body, dict):
            assert "content" not in log.body or not log.body.get("content")
