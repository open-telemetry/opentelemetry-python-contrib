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
# pylint: disable=too-many-locals

from typing import Optional

import pytest
from cohere import ChatResponse

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.semconv._incubating.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    event_attributes as EventAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)


@pytest.mark.vcr()
def test_chat_with_content(
    span_exporter, log_exporter, instrument_with_content, cohere_client
):
    llm_model_value = "command-r-plus"
    messages_value = [{"role": "user", "content": "Say this is a test"}]

    response = cohere_client.chat(
        messages=messages_value, model=llm_model_value,
    )

    spans = span_exporter.get_finished_spans()
    assert_chat_attributes(spans[0], llm_model_value, response)

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 2

    user_message = {"content": messages_value[0]["content"]}
    assert_message_in_logs(
        logs[0], "gen_ai.user.message", user_message, spans[0]
    )

    response_event = {
        "id": response.id,
        "finish_reason": "COMPLETE",
        "message": {
            "content": response.message.content,
        },
    }
    assert_message_in_logs(logs[1], "gen_ai.choice", response_event, spans[0])


def assert_message_in_logs(log, event_name, expected_content, parent_span):
    assert log.log_record.attributes[EventAttributes.EVENT_NAME] == event_name
    assert (
        log.log_record.attributes[GenAIAttributes.GEN_AI_SYSTEM]
        == GenAIAttributes.GenAiSystemValues.COHERE.value
    )

    if not expected_content:
        assert not log.log_record.body
    else:
        assert log.log_record.body
        assert dict(log.log_record.body) == expected_content
    assert_log_parent(log, parent_span)


def assert_chat_attributes(
    span: ReadableSpan,
    request_model: str,
    response: ChatResponse,
    operation_name: str = "chat",
    server_address: str = "api.cohere.com",
):
    return assert_all_attributes(
        span,
        request_model,
        response.id,
        response.usage.tokens.input_tokens,
        response.usage.tokens.output_tokens,
        operation_name,
        server_address,
    )


def assert_all_attributes(
    span: ReadableSpan,
    request_model: str,
    response_id: str = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    operation_name: str = "chat",
    server_address: str = "api.cohere.com",
):
    assert span.name == f"{operation_name} {request_model}"
    assert (
        operation_name
        == span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
    )
    assert (
        GenAIAttributes.GenAiSystemValues.COHERE.value
        == span.attributes[GenAIAttributes.GEN_AI_SYSTEM]
    )
    assert (
        request_model == span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
    )

    if response_id:
        assert (
            response_id == span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID]
        )
    else:
        assert GenAIAttributes.GEN_AI_RESPONSE_ID not in span.attributes

    if input_tokens:
        assert (
            input_tokens
            == span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
        )
    else:
        assert GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS not in span.attributes

    if output_tokens:
        assert (
            output_tokens
            == span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
        )
    else:
        assert (
            GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS not in span.attributes
        )

    assert server_address == span.attributes[ServerAttributes.SERVER_ADDRESS]


def assert_log_parent(log, span):
    assert log.log_record.trace_id == span.get_span_context().trace_id
    assert log.log_record.span_id == span.get_span_context().span_id
    assert log.log_record.trace_flags == span.get_span_context().trace_flags
