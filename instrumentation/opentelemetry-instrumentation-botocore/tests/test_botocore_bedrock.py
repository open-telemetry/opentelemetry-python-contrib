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

from typing import Any

import boto3
import pytest

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)

BOTO3_VERSION = tuple(int(x) for x in boto3.__version__.split("."))


@pytest.mark.skipif(
    BOTO3_VERSION < (1, 35, 56), reason="Converse API not available"
)
@pytest.mark.vcr()
@pytest.mark.parametrize("llm_model", ["amazon.titan", "anthropic.claude"])
def test_converse_with_content(
    llm_model,
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_with_content,
):
    llm_model_id = {
        "amazon.titan": "amazon.titan-text-lite-v1",
        "anthropic.claude": "anthropic.claude-3-haiku-20240307-v1:0",
    }
    messages = [{"role": "user", "content": [{"text": "Say this is a test"}]}]

    llm_model_value = llm_model_id[llm_model]
    max_tokens, temperature, top_p, stop_sequences = 10, 0.8, 1, ["|"]
    response = bedrock_runtime_client.converse(
        messages=messages,
        modelId=llm_model_value,
        inferenceConfig={
            "maxTokens": max_tokens,
            "temperature": temperature,
            "topP": top_p,
            "stopSequences": stop_sequences,
        },
    )

    (span,) = span_exporter.get_finished_spans()
    assert_completion_attributes(
        span,
        llm_model_value,
        response,
        "chat",
        top_p,
        temperature,
        max_tokens,
        stop_sequences,
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 0


def assert_completion_attributes(
    span: ReadableSpan,
    request_model: str,
    response: dict[str, Any],
    operation_name: str = "chat",
    request_top_p: int | None = None,
    request_temperature: int | None = None,
    request_max_tokens: int | None = None,
    request_stop_sequences: list[str] | None = None,
):
    return assert_all_attributes(
        span,
        request_model,
        response["usage"]["inputTokens"],
        response["usage"]["outputTokens"],
        (response["stopReason"],),
        operation_name,
        request_top_p,
        request_temperature,
        request_max_tokens,
        tuple(request_stop_sequences),
    )


def assert_equal_or_not_present(value, attribute_name, span):
    if value:
        assert value == span.attributes[attribute_name]
    else:
        assert attribute_name not in span.attributes


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
