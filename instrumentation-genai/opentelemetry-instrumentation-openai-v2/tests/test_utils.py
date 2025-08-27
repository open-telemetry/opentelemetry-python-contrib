import json
from typing import Optional
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
    server_attributes as ServerAttributes,
)

from openai.resources.chat.completions import ChatCompletion

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
):
    assert span.name == f"{operation_name} {request_model}"
    assert (
        operation_name
        == span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
    )
    provider_name_attr_name = "gen_ai.provider.name" if latest_experimental_enabled else GenAIAttributes.GEN_AI_SYSTEM    
    assert (
        GenAIAttributes.GenAiSystemValues.OPENAI.value
        == span.attributes[provider_name_attr_name]
    )
    assert (
        request_model == span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
    )
    if response_model:
        assert (
            response_model
            == span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL]
        )
    else:
        assert GenAIAttributes.GEN_AI_RESPONSE_MODEL not in span.attributes

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
    result = {}
    for key, value in body.items():
        if value is None:
            continue
        if isinstance(value, dict):
            result[key] = remove_none_values(value)
        elif isinstance(value, list):
            result[key] = [remove_none_values(i) for i in value]
        else:
            result[key] = value
    return result


def assert_completion_attributes(
    span: ReadableSpan,
    request_model: str,
    response: ChatCompletion,
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