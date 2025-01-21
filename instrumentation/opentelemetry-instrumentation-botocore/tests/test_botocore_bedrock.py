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

import boto3
import pytest

from opentelemetry.semconv._incubating.attributes.error_attributes import (
    ERROR_TYPE,
)
from opentelemetry.trace.status import StatusCode

from .bedrock_utils import assert_completion_attributes

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
    assert_completion_attributes(
        span,
        llm_model_value,
        None,
        "chat",
    )

    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes[ERROR_TYPE] == "ValidationException"

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 0
