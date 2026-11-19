# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Shared test utilities for OpenAI instrumentation tests."""

from __future__ import annotations

from openai.resources.chat.completions import AsyncCompletions, Completions
from openai.resources.embeddings import AsyncEmbeddings, Embeddings
from wrapt import FunctionWrapper

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
USER_ONLY_PROMPT = [{"role": "user", "content": "Say this is a test"}]
WEATHER_TOOL_PROMPT = [
    {"role": "system", "content": "You're a helpful assistant."},
    {
        "role": "user",
        "content": "What's the weather in Seattle and San Francisco today?",
    },
]

V2_SCOPE = "opentelemetry.instrumentation.openai_v2"
GENAI_OPENAI_SCOPE = "opentelemetry.instrumentation.genai.openai"
PATCHED_CLASSES = (Completions, AsyncCompletions, Embeddings, AsyncEmbeddings)


def _wrapper_module(cls: type) -> str | None:
    attr = cls.__dict__["create"]
    if not isinstance(attr, FunctionWrapper):
        return None
    return attr._self_wrapper.__module__


def wrapped_by_v2() -> bool:
    return all(_wrapper_module(cls) == f"{V2_SCOPE}.patch" for cls in PATCHED_CLASSES)


def wrapped_by_genai_openai() -> bool:
    return all((_wrapper_module(cls) or "").startswith(GENAI_OPENAI_SCOPE) for cls in PATCHED_CLASSES)


def not_wrapped() -> bool:
    return all(_wrapper_module(cls) is None for cls in PATCHED_CLASSES)


def _assert_optional_attribute(span, attribute_name, expected_value):
    """Helper to assert optional span attributes."""
    if expected_value is not None:
        assert expected_value == span.attributes[attribute_name]
    else:
        assert attribute_name not in span.attributes


def assert_all_attributes(
    span: ReadableSpan,
    request_model: str,
    response_id: str = None,
    response_model: str = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    operation_name: str = "chat",
    server_address: str = "api.openai.com",
    server_port: int = 443,
    request_service_tier: str | None = None,
    response_service_tier: str | None = None,
):
    assert span.name == f"{operation_name} {request_model}"
    assert operation_name == span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
    assert GenAIAttributes.GenAiSystemValues.OPENAI.value == span.attributes[GenAIAttributes.GEN_AI_SYSTEM]
    assert request_model == span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]

    _assert_optional_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, response_model)
    _assert_optional_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_ID, response_id)
    _assert_optional_attribute(span, GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS, input_tokens)
    _assert_optional_attribute(span, GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS, output_tokens)

    assert server_address == span.attributes[ServerAttributes.SERVER_ADDRESS]
    if server_port != 443 and server_port > 0:
        assert server_port == span.attributes[ServerAttributes.SERVER_PORT]

    _assert_optional_attribute(
        span,
        GenAIAttributes.GEN_AI_OPENAI_REQUEST_SERVICE_TIER,
        request_service_tier,
    )
    _assert_optional_attribute(
        span,
        GenAIAttributes.GEN_AI_OPENAI_RESPONSE_SERVICE_TIER,
        response_service_tier,
    )


def assert_log_parent(log, span):
    """Assert that the log record has the correct parent span context"""
    if span:
        assert log.log_record.trace_id == span.get_span_context().trace_id
        assert log.log_record.span_id == span.get_span_context().span_id
        assert log.log_record.trace_flags == span.get_span_context().trace_flags


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
            result[key] = [remove_none_values(i) if isinstance(i, dict) else i for i in value]
        else:
            result[key] = value
    return result


def assert_message_in_logs(log, event_name, expected_content, parent_span):
    assert log.log_record.event_name == event_name
    assert log.log_record.attributes[GenAIAttributes.GEN_AI_SYSTEM] == GenAIAttributes.GenAiSystemValues.OPENAI.value

    if not expected_content:
        assert not log.log_record.body
    else:
        assert log.log_record.body
        assert dict(log.log_record.body) == remove_none_values(expected_content)
    assert_log_parent(log, parent_span)


def assert_embedding_attributes(
    span: ReadableSpan,
    request_model: str,
    response,
):
    """Assert that the span contains all required attributes for embeddings operation"""
    # Use the common assertion function
    assert_all_attributes(
        span,
        request_model,
        response_id=None,  # Embeddings don't have a response ID
        response_model=response.model,
        input_tokens=response.usage.prompt_tokens,
        operation_name="embeddings",
        server_address="api.openai.com",
    )

    # Assert embeddings-specific attributes
    if hasattr(span, "attributes") and "gen_ai.embeddings.dimension.count" in span.attributes:
        # If dimensions were specified, verify that they match the actual dimensions
        assert span.attributes["gen_ai.embeddings.dimension.count"] == len(response.data[0].embedding)
