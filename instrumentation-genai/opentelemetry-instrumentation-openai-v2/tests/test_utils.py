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

"""Shared test utilities for OpenAI instrumentation tests."""

import json
from typing import Any, Optional

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
    openai_attributes as OpenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)

DEFAULT_MODEL = "gpt-4o-mini"
USER_ONLY_PROMPT = [{"role": "user", "content": "Say this is a test"}]
USER_ONLY_EXPECTED_INPUT_MESSAGES = [
    {
        "role": "user",
        "parts": [
            {
                "type": "text",
                "content": USER_ONLY_PROMPT[0]["content"],
            }
        ],
    }
]
WEATHER_TOOL_PROMPT = [
    {"role": "system", "content": "You're a helpful assistant."},
    {
        "role": "user",
        "content": "What's the weather in Seattle and San Francisco today?",
    },
]
WEATHER_TOOL_EXPECTED_INPUT_MESSAGES = [
    {
        "role": "system",
        "parts": [
            {
                "type": "text",
                "content": WEATHER_TOOL_PROMPT[0]["content"],
            }
        ],
    },
    {
        "role": "user",
        "parts": [
            {
                "type": "text",
                "content": WEATHER_TOOL_PROMPT[1]["content"],
            }
        ],
    },
]

def _assert_optional_attribute(span, attribute_name, expected_value):
    """Helper to assert optional span attributes."""
    if expected_value is not None:
        assert expected_value == span.attributes[attribute_name]
    else:
        assert attribute_name not in span.attributes

def assert_all_attributes(
    span: ReadableSpan,
    request_model: str,
    latest_experimental_enabled: bool,
    response_id: str = None,
    response_model: str = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    operation_name: str = "chat",
    server_address: str = "api.openai.com",
    server_port: int = 443,
    request_service_tier: Optional[str] = None,
    response_service_tier: Optional[str] = None,
):
    assert span.name == f"{operation_name} {request_model}"
    assert (
        operation_name
        == span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
    )

    provider_name_attr_name = (
        "gen_ai.provider.name"
        if latest_experimental_enabled
        else GenAIAttributes.GEN_AI_SYSTEM
    )

    assert (
        GenAIAttributes.GenAiProviderNameValues.OPENAI.value
        == span.attributes[provider_name_attr_name]
    )
    assert (
        request_model
        == span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
    )

    _assert_optional_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, response_model)
    _assert_optional_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_ID, response_id)
    _assert_optional_attribute(span, GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS, input_tokens)
    _assert_optional_attribute(span, GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS, output_tokens)

    assert server_address == span.attributes[ServerAttributes.SERVER_ADDRESS]
    if server_port != 443 and server_port > 0:
        assert server_port == span.attributes[ServerAttributes.SERVER_PORT]

    request_service_tier_attr_name = (
        OpenAIAttributes.OPENAI_REQUEST_SERVICE_TIER
        if latest_experimental_enabled
        else GenAIAttributes.GEN_AI_OPENAI_REQUEST_SERVICE_TIER
    )
    _assert_optional_attribute(
        span,
        request_service_tier_attr_name,
        request_service_tier,
    )

    response_service_tier_attr_name = (
        OpenAIAttributes.OPENAI_RESPONSE_SERVICE_TIER
        if latest_experimental_enabled
        else GenAIAttributes.GEN_AI_OPENAI_RESPONSE_SERVICE_TIER
    )
    _assert_optional_attribute(
        span,
        response_service_tier_attr_name,
        response_service_tier,
    )


def assert_log_parent(log, span):
    if span:
        assert log.log_record.trace_id == span.get_span_context().trace_id
        assert log.log_record.span_id == span.get_span_context().span_id
        assert (
            log.log_record.trace_flags == span.get_span_context().trace_flags
        )


def get_current_weather_tool_definition():
    return {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "Get the current weather in a given location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. Boston, MA",
                    },
                },
                "required": ["location"],
                "additionalProperties": False,
            },
        },
    }


def remove_none_values(body):
    """Remove None values from a dictionary recursively"""
    result = {}
    for key, value in body.items():
        if value is None:
            continue
        if isinstance(value, dict):
            result[key] = remove_none_values(value)
        elif isinstance(value, list):
            result[key] = [
                remove_none_values(i) if isinstance(i, dict) else i
                for i in value
            ]
        else:
            result[key] = value
    return result


def assert_completion_attributes(
    span: ReadableSpan,
    request_model: str,
    response: Any,
    latest_experimental_enabled: bool,
    operation_name: str = "chat",
    server_address: str = "api.openai.com",
):
    return assert_all_attributes(
        span,
        request_model,
        latest_experimental_enabled,
        response.id,
        response.model,
        response.usage.prompt_tokens,
        response.usage.completion_tokens,
        operation_name,
        server_address,
    )


def assert_messages_attribute(actual, expected):
    assert json.loads(actual) == expected


def format_simple_expected_output_message(
    content: str, finish_reason: str = "stop"
):
    return [
        {
            "role": "assistant",
            "parts": [
                {
                    "type": "text",
                    "content": content,
                }
            ],
            "finish_reason": finish_reason,
        }
    ]


def assert_message_in_logs(log, event_name, expected_content, parent_span):
    assert log.log_record.event_name == event_name
    assert (
        log.log_record.attributes[GenAIAttributes.GEN_AI_SYSTEM]
        == GenAIAttributes.GenAiSystemValues.OPENAI.value
    )

    if not expected_content:
        assert not log.log_record.body
    else:
        assert log.log_record.body
        assert dict(log.log_record.body) == remove_none_values(
            expected_content
        )
    assert_log_parent(log, parent_span)


def assert_embedding_attributes(
    span: ReadableSpan,
    request_model: str,
    latest_experimental_enabled: bool,
    response,
):
    """Assert that the span contains all required attributes for embeddings operation"""
    # Use the common assertion function
    assert_all_attributes(
        span,
        request_model,
        latest_experimental_enabled,
        response_id=None,  # Embeddings don't have a response ID
        response_model=response.model,
        input_tokens=response.usage.prompt_tokens,
        operation_name="embeddings",
        server_address="api.openai.com",
    )

    # Assert embeddings-specific attributes
    if (
        hasattr(span, "attributes")
        and "gen_ai.embeddings.dimension.count" in span.attributes
    ):
        # If dimensions were specified, verify that they match the actual dimensions
        assert span.attributes["gen_ai.embeddings.dimension.count"] == len(
            response.data[0].embedding
        )
