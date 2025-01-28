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

from __future__ import annotations

import json
from typing import Any

from botocore.response import StreamingBody

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)


# pylint: disable=too-many-branches, too-many-locals
def assert_completion_attributes_from_streaming_body(
    span: ReadableSpan,
    request_model: str,
    response: StreamingBody | None,
    operation_name: str = "chat",
    request_top_p: int | None = None,
    request_temperature: int | None = None,
    request_max_tokens: int | None = None,
    request_stop_sequences: list[str] | None = None,
):
    input_tokens = None
    output_tokens = None
    finish_reason = None
    if response is not None:
        original_body = response["body"]
        body_content = original_body.read()
        response = json.loads(body_content.decode("utf-8"))
        assert response

        if "amazon.titan" in request_model:
            input_tokens = response.get("inputTextTokenCount")
            results = response.get("results")
            if results:
                first_result = results[0]
                output_tokens = first_result.get("tokenCount")
                finish_reason = (first_result["completionReason"],)
        elif "amazon.nova" in request_model:
            if usage := response.get("usage"):
                input_tokens = usage["inputTokens"]
                output_tokens = usage["outputTokens"]
            else:
                input_tokens, output_tokens = None, None

            if "stopReason" in response:
                finish_reason = (response["stopReason"],)
            else:
                finish_reason = None
        elif "anthropic.claude" in request_model:
            if usage := response.get("usage"):
                input_tokens = usage["input_tokens"]
                output_tokens = usage["output_tokens"]
            else:
                input_tokens, output_tokens = None, None

            if "stop_reason" in response:
                finish_reason = (response["stop_reason"],)
            else:
                finish_reason = None

    return assert_all_attributes(
        span,
        request_model,
        input_tokens,
        output_tokens,
        finish_reason,
        operation_name,
        request_top_p,
        request_temperature,
        request_max_tokens,
        tuple(request_stop_sequences)
        if request_stop_sequences is not None
        else request_stop_sequences,
    )


def assert_converse_completion_attributes(
    span: ReadableSpan,
    request_model: str,
    response: dict[str, Any] | None,
    operation_name: str = "chat",
    request_top_p: int | None = None,
    request_temperature: int | None = None,
    request_max_tokens: int | None = None,
    request_stop_sequences: list[str] | None = None,
):
    if usage := (response and response.get("usage")):
        input_tokens = usage["inputTokens"]
        output_tokens = usage["outputTokens"]
    else:
        input_tokens, output_tokens = None, None

    if response and "stopReason" in response:
        finish_reason = (response["stopReason"],)
    else:
        finish_reason = None

    return assert_all_attributes(
        span,
        request_model,
        input_tokens,
        output_tokens,
        finish_reason,
        operation_name,
        request_top_p,
        request_temperature,
        request_max_tokens,
        tuple(request_stop_sequences)
        if request_stop_sequences is not None
        else request_stop_sequences,
    )


def assert_stream_completion_attributes(
    span: ReadableSpan,
    request_model: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    finish_reason: tuple[str] | None = None,
    operation_name: str = "chat",
    request_top_p: int | None = None,
    request_temperature: int | None = None,
    request_max_tokens: int | None = None,
    request_stop_sequences: list[str] | None = None,
):
    return assert_all_attributes(
        span,
        request_model,
        input_tokens,
        output_tokens,
        finish_reason,
        operation_name,
        request_top_p,
        request_temperature,
        request_max_tokens,
        tuple(request_stop_sequences)
        if request_stop_sequences is not None
        else request_stop_sequences,
    )


def assert_equal_or_not_present(value, attribute_name, span):
    if value is not None:
        assert value == span.attributes[attribute_name]
    else:
        assert attribute_name not in span.attributes, attribute_name


def assert_all_attributes(
    span: ReadableSpan,
    request_model: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    finish_reason: tuple[str] | None = None,
    operation_name: str = "chat",
    request_top_p: int | None = None,
    request_temperature: int | None = None,
    request_max_tokens: int | None = None,
    request_stop_sequences: tuple[str] | None = None,
):
    assert span.name == f"{operation_name} {request_model}"
    assert (
        operation_name
        == span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
    )
    assert (
        GenAIAttributes.GenAiSystemValues.AWS_BEDROCK.value
        == span.attributes[GenAIAttributes.GEN_AI_SYSTEM]
    )
    assert (
        request_model == span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
    )

    assert_equal_or_not_present(
        input_tokens, GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS, span
    )
    assert_equal_or_not_present(
        output_tokens, GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS, span
    )
    assert_equal_or_not_present(
        finish_reason, GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS, span
    )
    assert_equal_or_not_present(
        request_top_p, GenAIAttributes.GEN_AI_REQUEST_TOP_P, span
    )
    assert_equal_or_not_present(
        request_temperature, GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE, span
    )
    assert_equal_or_not_present(
        request_max_tokens, GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS, span
    )
    assert_equal_or_not_present(
        request_stop_sequences,
        GenAIAttributes.GEN_AI_REQUEST_STOP_SEQUENCES,
        span,
    )
