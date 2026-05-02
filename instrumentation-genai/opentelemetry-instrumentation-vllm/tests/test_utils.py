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

"""Tests for utility functions."""

from unittest.mock import MagicMock

from opentelemetry.instrumentation.vllm.utils import (
    extract_finish_reasons,
    extract_sampling_params,
    extract_server_metrics,
    extract_token_counts,
    get_common_attributes,
    get_request_attributes,
    get_span_name,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)


def test_get_span_name_with_model():
    assert get_span_name("chat", "llama-7b") == "chat llama-7b"


def test_get_span_name_without_model():
    assert get_span_name("chat", None) == "chat"


def test_get_common_attributes():
    attrs = get_common_attributes("chat", "llama-7b")
    assert attrs[GenAIAttributes.GEN_AI_SYSTEM] == "vllm"
    assert attrs[GenAIAttributes.GEN_AI_OPERATION_NAME] == "chat"
    assert attrs[GenAIAttributes.GEN_AI_REQUEST_MODEL] == "llama-7b"


def test_get_common_attributes_no_model():
    attrs = get_common_attributes("generate")
    assert GenAIAttributes.GEN_AI_REQUEST_MODEL not in attrs


def test_get_request_attributes_full():
    attrs = get_request_attributes(
        operation_name="chat",
        model="llama-7b",
        temperature=0.5,
        max_tokens=100,
        top_p=0.9,
        top_k=40,
        frequency_penalty=0.1,
        presence_penalty=0.2,
    )
    assert attrs[GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE] == 0.5
    assert attrs[GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS] == 100
    assert attrs[GenAIAttributes.GEN_AI_REQUEST_TOP_P] == 0.9
    assert attrs[GenAIAttributes.GEN_AI_REQUEST_TOP_K] == 40
    assert attrs[GenAIAttributes.GEN_AI_REQUEST_FREQUENCY_PENALTY] == 0.1
    assert attrs[GenAIAttributes.GEN_AI_REQUEST_PRESENCE_PENALTY] == 0.2


def test_get_request_attributes_minimal():
    attrs = get_request_attributes(operation_name="chat")
    assert GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE not in attrs
    assert GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS not in attrs


def test_extract_sampling_params():
    sp = MagicMock()
    sp.temperature = 0.8
    sp.max_tokens = 512
    sp.top_p = 0.95
    sp.top_k = -1
    sp.frequency_penalty = 0.0
    sp.presence_penalty = 0.0

    params = extract_sampling_params(sp)
    assert params["temperature"] == 0.8
    assert params["max_tokens"] == 512
    assert params["top_p"] == 0.95


def test_extract_sampling_params_none():
    assert extract_sampling_params(None) == {}


def test_extract_token_counts():
    output = MagicMock()
    output.prompt_token_ids = [1, 2, 3, 4, 5]
    out1 = MagicMock()
    out1.token_ids = [10, 11, 12]
    output.outputs = [out1]

    prompt, completion = extract_token_counts(output)
    assert prompt == 5
    assert completion == 3


def test_extract_token_counts_multiple_outputs():
    output = MagicMock()
    output.prompt_token_ids = [1, 2]
    out1 = MagicMock()
    out1.token_ids = [10, 11]
    out2 = MagicMock()
    out2.token_ids = [20, 21, 22]
    output.outputs = [out1, out2]

    prompt, completion = extract_token_counts(output)
    assert prompt == 2
    assert completion == 5


def test_extract_finish_reasons():
    output = MagicMock()
    out1 = MagicMock()
    out1.finish_reason = "stop"
    out2 = MagicMock()
    out2.finish_reason = "length"
    output.outputs = [out1, out2]

    reasons = extract_finish_reasons(output)
    assert reasons == ["stop", "length"]


def test_extract_finish_reasons_none():
    output = MagicMock()
    output.outputs = None
    assert extract_finish_reasons(output) is None


def test_extract_server_metrics_from_object():
    output = MagicMock()
    output.metrics.first_token_latency = 0.05
    output.metrics.mean_time_per_output_token = 0.01

    ttft, tpot = extract_server_metrics(output)
    assert ttft == 0.05
    assert tpot == 0.01


def test_extract_server_metrics_no_metrics():
    output = MagicMock(spec=[])
    # spec=[] means no attributes at all
    ttft, tpot = extract_server_metrics(output)
    assert ttft is None
    assert tpot is None
