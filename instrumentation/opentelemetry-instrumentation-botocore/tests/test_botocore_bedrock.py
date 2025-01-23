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

import boto3
import pytest

from opentelemetry.semconv._incubating.attributes.error_attributes import (
    ERROR_TYPE,
)
from opentelemetry.trace.status import StatusCode

from .bedrock_utils import (
    assert_completion_attributes_from_streaming_body,
    assert_converse_completion_attributes,
    assert_converse_stream_completion_attributes,
)

BOTO3_VERSION = tuple(int(x) for x in boto3.__version__.split("."))


@pytest.mark.skipif(
    BOTO3_VERSION < (1, 35, 56), reason="Converse API not available"
)
@pytest.mark.vcr()
def test_converse_with_content(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_with_content,
):
    messages = [{"role": "user", "content": [{"text": "Say this is a test"}]}]

    llm_model_value = "amazon.titan-text-lite-v1"
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
    assert_converse_completion_attributes(
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


@pytest.mark.skipif(
    BOTO3_VERSION < (1, 35, 56), reason="Converse API not available"
)
@pytest.mark.vcr()
def test_converse_with_invalid_model(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_with_content,
):
    messages = [{"role": "user", "content": [{"text": "Say this is a test"}]}]

    llm_model_value = "does-not-exist"
    with pytest.raises(bedrock_runtime_client.exceptions.ValidationException):
        bedrock_runtime_client.converse(
            messages=messages,
            modelId=llm_model_value,
        )

    (span,) = span_exporter.get_finished_spans()
    assert_converse_completion_attributes(
        span,
        llm_model_value,
        None,
        "chat",
    )

    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes[ERROR_TYPE] == "ValidationException"

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 0


@pytest.mark.skipif(
    BOTO3_VERSION < (1, 35, 56), reason="ConverseStream API not available"
)
@pytest.mark.vcr()
def test_converse_stream_with_content(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_with_content,
):
    messages = [{"role": "user", "content": [{"text": "Say this is a test"}]}]

    llm_model_value = "amazon.titan-text-lite-v1"
    max_tokens, temperature, top_p, stop_sequences = 10, 0.8, 1, ["|"]
    response = bedrock_runtime_client.converse_stream(
        messages=messages,
        modelId=llm_model_value,
        inferenceConfig={
            "maxTokens": max_tokens,
            "temperature": temperature,
            "topP": top_p,
            "stopSequences": stop_sequences,
        },
    )

    # consume the stream in order to have it traced
    finish_reason = None
    input_tokens, output_tokens = None, None
    text = ""
    for event in response["stream"]:
        if "contentBlockDelta" in event:
            text += event["contentBlockDelta"]["delta"]["text"]
        if "messageStop" in event:
            finish_reason = (event["messageStop"]["stopReason"],)
        if "metadata" in event:
            usage = event["metadata"]["usage"]
            input_tokens = usage["inputTokens"]
            output_tokens = usage["outputTokens"]

    assert text

    (span,) = span_exporter.get_finished_spans()
    assert_converse_stream_completion_attributes(
        span,
        llm_model_value,
        input_tokens,
        output_tokens,
        finish_reason,
        "chat",
        top_p,
        temperature,
        max_tokens,
        stop_sequences,
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 0


@pytest.mark.skipif(
    BOTO3_VERSION < (1, 35, 56), reason="ConverseStream API not available"
)
@pytest.mark.vcr()
def test_converse_stream_with_invalid_model(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_with_content,
):
    messages = [{"role": "user", "content": [{"text": "Say this is a test"}]}]

    llm_model_value = "does-not-exist"
    with pytest.raises(bedrock_runtime_client.exceptions.ValidationException):
        bedrock_runtime_client.converse_stream(
            messages=messages,
            modelId=llm_model_value,
        )

    (span,) = span_exporter.get_finished_spans()
    assert_converse_stream_completion_attributes(
        span,
        llm_model_value,
        None,
        "chat",
    )

    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes[ERROR_TYPE] == "ValidationException"

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 0


def get_invoke_model_body(
    llm_model,
    max_tokens=None,
    temperature=None,
    top_p=None,
    stop_sequences=None,
):
    def set_if_not_none(config, key, value):
        if value is not None:
            config[key] = value

    prompt = "Say this is a test"
    if llm_model == "amazon.nova-micro-v1:0":
        config = {}
        set_if_not_none(config, "max_new_tokens", max_tokens)
        set_if_not_none(config, "temperature", temperature)
        set_if_not_none(config, "topP", top_p)
        set_if_not_none(config, "stopSequences", stop_sequences)
        body = {
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": config,
            "schemaVersion": "messages-v1",
        }
    elif llm_model == "amazon.titan-text-lite-v1":
        config = {}
        set_if_not_none(config, "maxTokenCount", max_tokens)
        set_if_not_none(config, "temperature", temperature)
        set_if_not_none(config, "topP", top_p)
        set_if_not_none(config, "stopSequences", stop_sequences)
        body = {"inputText": prompt, "textGenerationConfig": config}
    elif llm_model == "anthropic.claude-v2":
        body = {
            "messages": [
                {"role": "user", "content": [{"text": prompt, "type": "text"}]}
            ],
            "anthropic_version": "bedrock-2023-05-31",
        }
        set_if_not_none(body, "max_tokens", max_tokens)
        set_if_not_none(body, "temperature", temperature)
        set_if_not_none(body, "top_p", top_p)
        set_if_not_none(body, "stop_sequences", stop_sequences)
    else:
        raise ValueError(f"No config for {llm_model}")

    return json.dumps(body)


def get_model_name_from_family(llm_model):
    llm_model_name = {
        "amazon.titan": "amazon.titan-text-lite-v1",
        "amazon.nova": "amazon.nova-micro-v1:0",
        "anthropic.claude": "anthropic.claude-v2",
    }
    return llm_model_name[llm_model]


@pytest.mark.parametrize(
    "model_family",
    ["amazon.nova", "amazon.titan", "anthropic.claude"],
)
@pytest.mark.vcr()
def test_invoke_model_with_content(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_with_content,
    model_family,
):
    llm_model_value = get_model_name_from_family(model_family)
    max_tokens, temperature, top_p, stop_sequences = 10, 0.8, 1, ["|"]
    body = get_invoke_model_body(
        llm_model_value, max_tokens, temperature, top_p, stop_sequences
    )
    response = bedrock_runtime_client.invoke_model(
        body=body,
        modelId=llm_model_value,
    )

    (span,) = span_exporter.get_finished_spans()
    assert_completion_attributes_from_streaming_body(
        span,
        llm_model_value,
        response,
        "text_completion" if model_family == "amazon.titan" else "chat",
        top_p,
        temperature,
        max_tokens,
        stop_sequences,
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 0


@pytest.mark.vcr()
def test_invoke_model_with_invalid_model(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_with_content,
):
    llm_model_value = "does-not-exist"
    with pytest.raises(bedrock_runtime_client.exceptions.ClientError):
        bedrock_runtime_client.invoke_model(
            body=b"",
            modelId=llm_model_value,
        )

    (span,) = span_exporter.get_finished_spans()
    assert_completion_attributes_from_streaming_body(
        span,
        llm_model_value,
        None,
        "chat",
    )

    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes[ERROR_TYPE] == "ValidationException"

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 0
