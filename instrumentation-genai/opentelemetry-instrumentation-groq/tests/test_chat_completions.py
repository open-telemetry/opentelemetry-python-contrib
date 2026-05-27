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

"""Tests for Groq chat.completions.create instrumentation."""

import pytest
from groq import APIConnectionError, AuthenticationError, Groq

from opentelemetry.instrumentation.groq import GroqInstrumentor
from opentelemetry.semconv._incubating.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics

DEFAULT_MODEL = "llama-3.3-70b-versatile"
USER_ONLY_PROMPT = [{"role": "user", "content": "Say hello in one word."}]


def assert_span_attributes(
    span,
    request_model,
    response_id=None,
    response_model=None,
    input_tokens=None,
    output_tokens=None,
    finish_reasons=None,
    operation_name="chat",
    server_address="api.groq.com",
):
    assert span.name == f"{operation_name} {request_model}"
    assert (
        operation_name
        == span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
    )
    assert (
        GenAIAttributes.GenAiSystemValues.GROQ.value
        == span.attributes[GenAIAttributes.GEN_AI_SYSTEM]
    )
    assert (
        request_model == span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
    )
    assert server_address == span.attributes[ServerAttributes.SERVER_ADDRESS]

    if response_id is not None:
        assert (
            response_id == span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID]
        )
    if response_model is not None:
        assert (
            response_model
            == span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL]
        )
    if input_tokens is not None:
        assert (
            input_tokens
            == span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
        )
    if output_tokens is not None:
        assert (
            output_tokens
            == span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
        )
    if finish_reasons is not None:
        assert finish_reasons == tuple(
            span.attributes[GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS]
        )


# ---------------------------------------------------------------------------
# Span tests
# ---------------------------------------------------------------------------


@pytest.mark.vcr()
def test_chat_completion_basic(
    span_exporter, groq_client, instrument_no_content
):
    """Span created with correct provider and model attributes."""
    response = groq_client.chat.completions.create(
        model=DEFAULT_MODEL,
        max_tokens=100,
        messages=USER_ONLY_PROMPT,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    assert_span_attributes(
        spans[0],
        request_model=DEFAULT_MODEL,
        response_id=response.id,
        response_model=response.model,
    )


@pytest.mark.vcr()
def test_chat_completion_token_usage(
    span_exporter, groq_client, instrument_no_content
):
    """Token counts appear as span attributes."""
    response = groq_client.chat.completions.create(
        model=DEFAULT_MODEL,
        max_tokens=100,
        messages=[{"role": "user", "content": "Count to 5."}],
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS in span.attributes
    assert GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS in span.attributes
    assert (
        span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
        == response.usage.prompt_tokens
    )
    assert (
        span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
        == response.usage.completion_tokens
    )


@pytest.mark.vcr()
def test_chat_completion_stop_reason(
    span_exporter, groq_client, instrument_no_content
):
    """Finish reason captured on span."""
    response = groq_client.chat.completions.create(
        model=DEFAULT_MODEL,
        max_tokens=100,
        messages=[{"role": "user", "content": "Say hi."}],
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS] == (
        response.choices[0].finish_reason,
    )


@pytest.mark.vcr()
def test_chat_completion_with_all_params(
    span_exporter, groq_client, instrument_no_content
):
    """All request parameters appear as span attributes."""
    groq_client.chat.completions.create(
        model=DEFAULT_MODEL,
        max_tokens=50,
        messages=USER_ONLY_PROMPT,
        temperature=0.7,
        top_p=0.9,
        stop=["STOP"],
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS] == 50
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE] == 0.7
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_TOP_P] == 0.9
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_STOP_SEQUENCES] == (
        "STOP",
    )


def test_chat_completion_connection_error(
    span_exporter, instrument_no_content
):
    """Connection errors are recorded on the span with error.type."""
    client = Groq(base_url="http://localhost:9999")

    with pytest.raises(APIConnectionError):
        client.chat.completions.create(
            model=DEFAULT_MODEL,
            max_tokens=100,
            messages=USER_ONLY_PROMPT,
            timeout=0.1,
        )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert (
        span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == DEFAULT_MODEL
    )
    assert ErrorAttributes.ERROR_TYPE in span.attributes
    assert "APIConnectionError" in span.attributes[ErrorAttributes.ERROR_TYPE]


@pytest.mark.vcr()
def test_chat_completion_api_error(
    span_exporter, groq_client, instrument_no_content
):
    """API errors (4xx) are recorded with error.type on the span."""
    with pytest.raises(AuthenticationError):
        groq_client.chat.completions.create(
            model=DEFAULT_MODEL,
            max_tokens=100,
            messages=USER_ONLY_PROMPT,
        )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert ErrorAttributes.ERROR_TYPE in span.attributes


# ---------------------------------------------------------------------------
# Instrumentor lifecycle
# ---------------------------------------------------------------------------


def test_instrumentor_instrument_uninstrument(uninstrument_groq):
    """Instrumentor can be applied and removed cleanly."""
    instrumentor = GroqInstrumentor()
    assert not instrumentor.is_instrumented_by_opentelemetry
    instrumentor.instrument()
    assert instrumentor.is_instrumented_by_opentelemetry
    instrumentor.uninstrument()
    assert not instrumentor.is_instrumented_by_opentelemetry


# ---------------------------------------------------------------------------
# Metrics tests
# ---------------------------------------------------------------------------

_DURATION_BUCKETS = (
    0.01,
    0.02,
    0.04,
    0.08,
    0.16,
    0.32,
    0.64,
    1.28,
    2.56,
    5.12,
    10.24,
    20.48,
    40.96,
    81.92,
)
_TOKEN_USAGE_BUCKETS = (
    1,
    4,
    16,
    64,
    256,
    1024,
    4096,
    16384,
    65536,
    262144,
    1048576,
    4194304,
    16777216,
    67108864,
)


def assert_metric_attributes(data_point, request_model):
    assert (
        data_point.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    assert GenAIAttributes.GEN_AI_PROVIDER_NAME in data_point.attributes
    assert (
        data_point.attributes[GenAIAttributes.GEN_AI_PROVIDER_NAME]
        == GenAIAttributes.GenAiSystemValues.GROQ.value
    )
    assert (
        data_point.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
        == request_model
    )


@pytest.mark.vcr()
def test_chat_completion_metrics(
    metric_reader, groq_client, instrument_no_content
):
    """Operation duration and token usage histograms are recorded."""
    groq_client.chat.completions.create(
        model=DEFAULT_MODEL,
        max_tokens=100,
        messages=[{"role": "user", "content": "Count to 5."}],
    )

    metrics = metric_reader.get_metrics_data().resource_metrics
    assert len(metrics) == 1

    metric_data = metrics[0].scope_metrics[0].metrics
    assert len(metric_data) == 2

    duration_metric = next(
        (
            m
            for m in metric_data
            if m.name == gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
        ),
        None,
    )
    assert duration_metric is not None
    duration_point = duration_metric.data.data_points[0]
    assert duration_point.sum > 0
    assert duration_point.explicit_bounds == _DURATION_BUCKETS
    assert_metric_attributes(duration_point, DEFAULT_MODEL)

    token_usage_metric = next(
        (
            m
            for m in metric_data
            if m.name == gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE
        ),
        None,
    )
    assert token_usage_metric is not None

    input_token_point = next(
        (
            d
            for d in token_usage_metric.data.data_points
            if d.attributes[GenAIAttributes.GEN_AI_TOKEN_TYPE]
            == GenAIAttributes.GenAiTokenTypeValues.INPUT.value
        ),
        None,
    )
    assert input_token_point is not None
    assert input_token_point.sum == 12
    assert input_token_point.explicit_bounds == _TOKEN_USAGE_BUCKETS
    assert_metric_attributes(input_token_point, DEFAULT_MODEL)

    output_token_point = next(
        (
            d
            for d in token_usage_metric.data.data_points
            if d.attributes[GenAIAttributes.GEN_AI_TOKEN_TYPE]
            == GenAIAttributes.GenAiTokenTypeValues.OUTPUT.value
        ),
        None,
    )
    assert output_token_point is not None
    assert output_token_point.sum == 17
    assert_metric_attributes(output_token_point, DEFAULT_MODEL)
