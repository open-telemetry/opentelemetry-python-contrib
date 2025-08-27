import json
from typing import Optional

from openai.resources.chat.completions import ChatCompletion

from opentelemetry.sdk._logs import LogRecord
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
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


def assert_all_attributes(
    span: ReadableSpan,
    details_event: LogRecord,
    request_model: str,
    latest_experimental_enabled: bool,
    response_id: str = None,
    response_model: str = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    operation_name: str = "chat",
    server_address: str = "api.openai.com",
):
    if span:
        assert span.name == f"{operation_name} {request_model}"
    if details_event:
        assert (
            "gen_ai.client.inference.operation.details"
            == details_event.attributes["event.name"]
        )

    if span:
        assert (
            operation_name
            == span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        )
    if details_event:
        assert (
            operation_name
            == details_event.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        )

    provider_name_attr_name = (
        "gen_ai.provider.name"
        if latest_experimental_enabled
        else GenAIAttributes.GEN_AI_SYSTEM
    )
    if span:
        assert (
            GenAIAttributes.GenAiSystemValues.OPENAI.value
            == span.attributes[provider_name_attr_name]
        )
    if details_event:
        assert (
            GenAIAttributes.GenAiSystemValues.OPENAI.value
            == details_event.attributes[provider_name_attr_name]
        )

    if span:
        assert (
            request_model
            == span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
        )
    if details_event:
        assert (
            request_model
            == details_event.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
        )

    if response_model:
        if span:
            assert (
                response_model
                == span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL]
            )
        if details_event:
            assert (
                response_model
                == details_event.attributes[
                    GenAIAttributes.GEN_AI_RESPONSE_MODEL
                ]
            )
    else:
        if span:
            assert GenAIAttributes.GEN_AI_RESPONSE_MODEL not in span.attributes
        if details_event:
            assert (
                GenAIAttributes.GEN_AI_RESPONSE_MODEL
                not in details_event.attributes
            )

    if response_id:
        if span:
            assert (
                response_id
                == span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID]
            )
        if details_event:
            assert (
                response_id
                == details_event.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID]
            )
    else:
        if span:
            assert GenAIAttributes.GEN_AI_RESPONSE_ID not in span.attributes
        if details_event:
            assert (
                GenAIAttributes.GEN_AI_RESPONSE_MODEL
                not in details_event.attributes
            )

    if input_tokens:
        if span:
            assert (
                input_tokens
                == span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
            )
        if details_event:
            assert (
                input_tokens
                == details_event.attributes[
                    GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS
                ]
            )
    else:
        if span:
            assert (
                GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS
                not in span.attributes
            )
        if details_event:
            assert (
                GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS
                not in details_event.attributes
            )

    if output_tokens:
        if span:
            assert (
                output_tokens
                == span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
            )
        if details_event:
            assert (
                output_tokens
                == details_event.attributes[
                    GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS
                ]
            )
    else:
        if span:
            assert (
                GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS
                not in span.attributes
            )
        if details_event:
            assert (
                GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS
                not in details_event.attributes
            )

    if span:
        assert (
            server_address == span.attributes[ServerAttributes.SERVER_ADDRESS]
        )
    if details_event:
        assert (
            server_address
            == details_event.attributes[ServerAttributes.SERVER_ADDRESS]
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
    details_event: LogRecord,
    request_model: str,
    response: ChatCompletion,
    latest_experimental_enabled: bool,
    operation_name: str = "chat",
    server_address: str = "api.openai.com",
):
    return assert_all_attributes(
        span,
        details_event,
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
