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

from typing import Optional

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    openai_attributes as OpenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)


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
    assert (
        GenAIAttributes.GenAiSystemValues.OPENAI.value
        == span.attributes[GenAIAttributes.GEN_AI_SYSTEM]
    )
    assert (
        request_model == span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
    )

    _assert_optional_attribute(
        span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, response_model
    )
    _assert_optional_attribute(
        span, GenAIAttributes.GEN_AI_RESPONSE_ID, response_id
    )
    _assert_optional_attribute(
        span, GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS, input_tokens
    )
    _assert_optional_attribute(
        span, GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS, output_tokens
    )

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
        OpenAIAttributes.OPENAI_RESPONSE_SERVICE_TIER,
        response_service_tier,
    )


def assert_log_parent(log, span):
    """Assert that the log record has the correct parent span context"""
    if span:
        assert log.log_record.trace_id == span.get_span_context().trace_id
        assert log.log_record.span_id == span.get_span_context().span_id
        assert (
            log.log_record.trace_flags == span.get_span_context().trace_flags
        )


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
