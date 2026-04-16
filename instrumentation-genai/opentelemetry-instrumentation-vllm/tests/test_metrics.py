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

"""Tests for vLLM instrumentation — metrics (TTFT, TPOT, token usage, duration)."""

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics


def _get_metrics(metric_reader):
    """Collect metrics and return them as a dict keyed by metric name."""
    data = metric_reader.get_metrics_data()
    metrics = {}
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                metrics[m.name] = m
    return metrics


# ── TTFT metric ──────────────────────────────────────────────────────


def test_generate_records_ttft(metric_reader, instrument, mock_llm):
    """generate() should record gen_ai.server.time_to_first_token metric."""
    mock_llm.generate(["Hello"])

    metrics = _get_metrics(metric_reader)
    assert gen_ai_metrics.GEN_AI_SERVER_TIME_TO_FIRST_TOKEN in metrics

    ttft_metric = metrics[gen_ai_metrics.GEN_AI_SERVER_TIME_TO_FIRST_TOKEN]
    dp = ttft_metric.data.data_points[0]
    # MockLLM sets ttft=0.05 for generate
    assert dp.sum == 0.05
    assert dp.attributes[GenAIAttributes.GEN_AI_SYSTEM] == "vllm"


def test_chat_records_ttft(metric_reader, instrument, mock_llm):
    """chat() should record gen_ai.server.time_to_first_token metric."""
    mock_llm.chat([{"role": "user", "content": "Hi"}])

    metrics = _get_metrics(metric_reader)
    assert gen_ai_metrics.GEN_AI_SERVER_TIME_TO_FIRST_TOKEN in metrics

    ttft_metric = metrics[gen_ai_metrics.GEN_AI_SERVER_TIME_TO_FIRST_TOKEN]
    dp = ttft_metric.data.data_points[0]
    # MockLLM sets ttft=0.03 for chat
    assert dp.sum == 0.03


# ── TPOT metric ──────────────────────────────────────────────────────


def test_generate_records_tpot(metric_reader, instrument, mock_llm):
    """generate() should record gen_ai.server.time_per_output_token metric."""
    mock_llm.generate(["Hello"])

    metrics = _get_metrics(metric_reader)
    assert gen_ai_metrics.GEN_AI_SERVER_TIME_PER_OUTPUT_TOKEN in metrics

    tpot_metric = metrics[gen_ai_metrics.GEN_AI_SERVER_TIME_PER_OUTPUT_TOKEN]
    dp = tpot_metric.data.data_points[0]
    assert dp.sum == 0.01


def test_chat_records_tpot(metric_reader, instrument, mock_llm):
    """chat() should record gen_ai.server.time_per_output_token metric."""
    mock_llm.chat([{"role": "user", "content": "Hi"}])

    metrics = _get_metrics(metric_reader)
    tpot_metric = metrics[gen_ai_metrics.GEN_AI_SERVER_TIME_PER_OUTPUT_TOKEN]
    dp = tpot_metric.data.data_points[0]
    assert dp.sum == 0.008


# ── Token usage metric ───────────────────────────────────────────────


def test_generate_records_token_usage(metric_reader, instrument, mock_llm):
    """generate() should record input and output token usage."""
    mock_llm.generate(["Hello"])

    metrics = _get_metrics(metric_reader)
    assert gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE in metrics

    token_metric = metrics[gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE]
    data_points = token_metric.data.data_points

    input_dp = next(
        (
            d
            for d in data_points
            if d.attributes.get(GenAIAttributes.GEN_AI_TOKEN_TYPE)
            == GenAIAttributes.GenAiTokenTypeValues.INPUT.value
        ),
        None,
    )
    assert input_dp is not None
    assert input_dp.sum == 10  # 10 prompt tokens from mock

    output_dp = next(
        (
            d
            for d in data_points
            if d.attributes.get(GenAIAttributes.GEN_AI_TOKEN_TYPE)
            == GenAIAttributes.GenAiTokenTypeValues.COMPLETION.value
        ),
        None,
    )
    assert output_dp is not None
    assert output_dp.sum == 5  # 5 output tokens from mock


# ── Operation duration metric ─────────────────────────────────────────


def test_generate_records_operation_duration(
    metric_reader, instrument, mock_llm
):
    """generate() should record gen_ai.client.operation.duration metric."""
    mock_llm.generate(["Hello"])

    metrics = _get_metrics(metric_reader)
    assert gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION in metrics

    duration_metric = metrics[gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION]
    dp = duration_metric.data.data_points[0]
    assert dp.sum > 0
    assert dp.attributes[GenAIAttributes.GEN_AI_SYSTEM] == "vllm"
    assert (
        dp.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == "text_completion"
    )


def test_chat_records_operation_duration(metric_reader, instrument, mock_llm):
    """chat() should record gen_ai.client.operation.duration metric."""
    mock_llm.chat([{"role": "user", "content": "Hi"}])

    metrics = _get_metrics(metric_reader)
    assert gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION in metrics

    duration_metric = metrics[gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION]
    dp = duration_metric.data.data_points[0]
    assert dp.sum > 0
    assert dp.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME] == "chat"


# ── Metric attributes ────────────────────────────────────────────────


def test_metric_attributes_include_model(metric_reader, instrument, mock_llm):
    """All metrics should include the request model in attributes."""
    mock_llm.generate(["Hello"])

    metrics = _get_metrics(metric_reader)
    ttft = metrics[gen_ai_metrics.GEN_AI_SERVER_TIME_TO_FIRST_TOKEN]
    dp = ttft.data.data_points[0]
    assert (
        dp.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
        == "meta-llama/Llama-2-7b-hf"
    )


def test_metric_attributes_include_response_model(
    metric_reader, instrument, mock_llm
):
    """Metrics should include the response model when available."""
    mock_llm.generate(["Hello"])

    metrics = _get_metrics(metric_reader)
    ttft = metrics[gen_ai_metrics.GEN_AI_SERVER_TIME_TO_FIRST_TOKEN]
    dp = ttft.data.data_points[0]
    assert (
        dp.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL]
        == "meta-llama/Llama-2-7b-hf"
    )
