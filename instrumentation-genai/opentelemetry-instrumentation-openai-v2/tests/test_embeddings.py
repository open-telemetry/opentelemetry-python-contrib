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

"""Unit tests for OpenAI Embeddings API instrumentation."""

from typing import Optional

import pytest
from openai import APIConnectionError, NotFoundError, OpenAI

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.semconv._incubating.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    event_attributes as EventAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics


@pytest.mark.vcr()
def test_embeddings_no_content(
    span_exporter, log_exporter, openai_client, instrument_no_content
):
    """Test creating embeddings with content capture disabled"""
    model_name = "text-embedding-3-small"
    input_text = "This is a test for embeddings"

    response = openai_client.embeddings.create(
        model=model_name,
        input=input_text,
    )

    # Verify spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert_embedding_attributes(spans[0], model_name, response)

    # No logs should be emitted when content capture is disabled
    logs = log_exporter.get_finished_logs()
    assert len(logs) == 0


@pytest.mark.vcr()
def test_embeddings_with_dimensions(
    span_exporter, metric_reader, openai_client, instrument_no_content
):
    """Test creating embeddings with custom dimensions parameter"""
    model_name = "text-embedding-3-small"
    input_text = "This is a test for embeddings with dimensions"
    dimensions = 512  # Using a smaller dimension than default

    response = openai_client.embeddings.create(
        model=model_name,
        input=input_text,
        dimensions=dimensions,
    )

    # Verify spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert_embedding_attributes(spans[0], model_name, response)

    # Verify dimensions attribute is set correctly
    assert (
        spans[0].attributes["gen_ai.embeddings.dimension.count"] == dimensions
    )

    # Verify actual embedding dimensions match the requested dimensions
    assert len(response.data[0].embedding) == dimensions

    # Verify metrics
    metrics = metric_reader.get_metrics_data().resource_metrics
    assert len(metrics) == 1

    metric_data = metrics[0].scope_metrics[0].metrics
    duration_metric = next(
        (
            m
            for m in metric_data
            if m.name == gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
        ),
        None,
    )
    assert duration_metric is not None

    # Verify the dimensions attribute is present in metrics
    for point in duration_metric.data.data_points:
        if "gen_ai.embeddings.dimension.count" in point.attributes:
            assert (
                point.attributes["gen_ai.embeddings.dimension.count"]
                == dimensions
            )
            break
    else:
        assert False, "Dimensions attribute not found in metrics"


@pytest.mark.vcr()
def test_embeddings_with_batch_input(
    span_exporter, metric_reader, openai_client, instrument_with_content
):
    """Test creating embeddings with batch input (list of strings)"""
    model_name = "text-embedding-3-small"
    input_texts = [
        "This is the first test string for embeddings",
        "This is the second test string for embeddings",
        "This is the third test string for embeddings",
    ]

    response = openai_client.embeddings.create(
        model=model_name,
        input=input_texts,
    )

    # Verify spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert_embedding_attributes(spans[0], model_name, response)

    # Verify results contain the same number of embeddings as input texts
    assert len(response.data) == len(input_texts)


@pytest.mark.vcr()
def test_embeddings_with_encoding_format(
    span_exporter, metric_reader, openai_client, instrument_no_content
):
    """Test creating embeddings with different encoding format"""
    model_name = "text-embedding-3-small"
    input_text = "This is a test for embeddings with encoding format"
    encoding_format = "base64"

    response = openai_client.embeddings.create(
        model=model_name,
        input=input_text,
        encoding_format=encoding_format,
    )

    # Verify spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert_embedding_attributes(spans[0], model_name, response)

    # Verify encoding_format attribute is set correctly
    assert (
        spans[0].attributes["gen_ai.request.encoding_formats"]
        == encoding_format
    )


@pytest.mark.vcr()
def test_embeddings_bad_endpoint(
    span_exporter, metric_reader, instrument_no_content
):
    """Test error handling for bad endpoint"""
    model_name = "text-embedding-3-small"
    input_text = "This is a test for embeddings with bad endpoint"

    client = OpenAI(base_url="http://localhost:4242")

    with pytest.raises(APIConnectionError):
        client.embeddings.create(
            model=model_name,
            input=input_text,
            timeout=0.1,
        )

    # Verify spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert_all_attributes(
        spans[0],
        model_name,
        operation_name="embeddings",
        server_address="localhost",
    )
    assert 4242 == spans[0].attributes[ServerAttributes.SERVER_PORT]
    assert (
        "APIConnectionError" == spans[0].attributes[ErrorAttributes.ERROR_TYPE]
    )

    # Verify metrics
    metrics = metric_reader.get_metrics_data().resource_metrics
    assert len(metrics) == 1

    metric_data = metrics[0].scope_metrics[0].metrics
    duration_metric = next(
        (
            m
            for m in metric_data
            if m.name == gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
        ),
        None,
    )
    assert duration_metric is not None
    assert duration_metric.data.data_points[0].sum > 0
    assert (
        duration_metric.data.data_points[0].attributes[
            ErrorAttributes.ERROR_TYPE
        ]
        == "APIConnectionError"
    )


@pytest.mark.vcr()
def test_embeddings_model_not_found(
    span_exporter, metric_reader, openai_client, instrument_no_content
):
    """Test error handling for non-existent model"""
    model_name = "non-existent-embedding-model"
    input_text = "This is a test for embeddings with bad model"

    with pytest.raises(NotFoundError):
        openai_client.embeddings.create(
            model=model_name,
            input=input_text,
        )

    # Verify spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert_all_attributes(spans[0], model_name, operation_name="embeddings")
    assert "NotFoundError" == spans[0].attributes[ErrorAttributes.ERROR_TYPE]

    # Verify metrics
    metrics = metric_reader.get_metrics_data().resource_metrics
    assert len(metrics) == 1

    metric_data = metrics[0].scope_metrics[0].metrics
    duration_metric = next(
        (
            m
            for m in metric_data
            if m.name == gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
        ),
        None,
    )
    assert duration_metric is not None
    assert duration_metric.data.data_points[0].sum > 0
    assert (
        duration_metric.data.data_points[0].attributes[
            ErrorAttributes.ERROR_TYPE
        ]
        == "NotFoundError"
    )


@pytest.mark.vcr()
def test_embeddings_token_metrics(
    span_exporter, metric_reader, openai_client, instrument_no_content
):
    """Test that token usage metrics are correctly recorded"""
    model_name = "text-embedding-3-small"
    input_text = "This is a test for embeddings token metrics"

    response = openai_client.embeddings.create(
        model=model_name,
        input=input_text,
    )

    # Verify spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert_embedding_attributes(spans[0], model_name, response)

    # Verify metrics
    metrics = metric_reader.get_metrics_data().resource_metrics
    assert len(metrics) == 1

    metric_data = metrics[0].scope_metrics[0].metrics

    # Verify operation duration metric
    duration_metric = next(
        (
            m
            for m in metric_data
            if m.name == gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
        ),
        None,
    )
    assert duration_metric is not None

    # Verify token usage metric
    token_metric = next(
        (
            m
            for m in metric_data
            if m.name == gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE
        ),
        None,
    )
    assert token_metric is not None

    # Find the input token data point
    input_token_point = None
    for point in token_metric.data.data_points:
        if (
            point.attributes[GenAIAttributes.GEN_AI_TOKEN_TYPE]
            == GenAIAttributes.GenAiTokenTypeValues.INPUT.value
        ):
            input_token_point = point
            break

    assert input_token_point is not None, "Input token metric not found"

    # Verify the token counts match what was reported in the response
    assert input_token_point.sum == response.usage.prompt_tokens


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
        output_tokens=None,  # Embeddings don't have separate output tokens
        operation_name="embeddings",
        server_address="api.openai.com",
    )

    # Assert embeddings-specific attributes
    if (
        hasattr(span, "attributes")
        and "gen_ai.embeddings.dimension.count" in span.attributes
    ):
        # If dimensions were specified, verify that they match the actual dimensions
        assert span.attributes["gen_ai.embeddings.dimension.count"] == len(
            response.data[0].embedding
        )

    # Assert tokens are correctly recorded
    assert (
        span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
        == response.usage.prompt_tokens
    )


def assert_all_attributes(
    span: ReadableSpan,
    request_model: str,
    response_id: str = None,
    response_model: str = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    operation_name: str = "embeddings",
    server_address: str = "api.openai.com",
):
    """Assert common attributes on the span"""
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

    if response_model:
        assert (
            response_model
            == span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL]
        )
    else:
        assert GenAIAttributes.GEN_AI_RESPONSE_MODEL not in span.attributes

    if response_id:
        assert (
            response_id == span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID]
        )
    else:
        assert GenAIAttributes.GEN_AI_RESPONSE_ID not in span.attributes

    if input_tokens:
        assert (
            input_tokens
            == span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
        )
    else:
        assert GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS not in span.attributes

    if output_tokens:
        assert (
            output_tokens
            == span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
        )
    else:
        assert (
            GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS not in span.attributes
        )

    assert server_address == span.attributes[ServerAttributes.SERVER_ADDRESS]


def assert_log_parent(log, span):
    """Assert that the log record has the correct parent span context"""
    if span:
        assert log.log_record.trace_id == span.get_span_context().trace_id
        assert log.log_record.span_id == span.get_span_context().span_id
        assert (
            log.log_record.trace_flags == span.get_span_context().trace_flags
        )


def assert_message_in_logs(log, event_name, expected_content, parent_span):
    assert log.log_record.attributes[EventAttributes.EVENT_NAME] == event_name
    assert (
        log.log_record.attributes[GenAIAttributes.GEN_AI_SYSTEM]
        == GenAIAttributes.GenAiSystemValues.OPENAI.value
    )

    if not expected_content:
        assert not log.log_record.body
    else:
        assert log.log_record.body
        assert dict(log.log_record.body) == remove_none_values(
            expected_content
        )
    assert_log_parent(log, parent_span)


def remove_none_values(body):
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
