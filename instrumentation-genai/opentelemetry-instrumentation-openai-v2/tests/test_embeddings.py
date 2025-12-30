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

import pytest
from openai import (
    NOT_GIVEN,
    APIConnectionError,
    NotFoundError,
    OpenAI,
)

try:
    from openai import not_given  # pylint: disable=no-name-in-module
except ImportError:
    not_given = NOT_GIVEN

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
from opentelemetry.util.genai.utils import is_experimental_mode

from .test_utils import assert_all_attributes, assert_embedding_attributes


def test_embeddings_no_content(
    span_exporter, log_exporter, openai_client, instrument_no_content, vcr
):
    """Test creating embeddings with content capture disabled"""
    latest_experimental_enabled = is_experimental_mode()
    model_name = "text-embedding-3-small"
    input_text = "This is a test for embeddings"

    with vcr.use_cassette("test_embeddings_no_content.yaml"):
        response = openai_client.embeddings.create(
            model=model_name,
            input=input_text,
        )

    # Verify spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert_embedding_attributes(
        spans[0], model_name, latest_experimental_enabled, response
    )

    # No logs should be emitted when content capture is disabled
    logs = log_exporter.get_finished_logs()
    assert len(logs) == 0


def test_embeddings_with_dimensions(
    span_exporter, metric_reader, openai_client, instrument_no_content, vcr
):
    """Test creating embeddings with custom dimensions parameter"""
    latest_experimental_enabled = is_experimental_mode()
    model_name = "text-embedding-3-small"
    input_text = "This is a test for embeddings with dimensions"
    dimensions = 512  # Using a smaller dimension than default

    with vcr.use_cassette("test_embeddings_with_dimensions.yaml"):
        response = openai_client.embeddings.create(
            model=model_name,
            input=input_text,
            dimensions=dimensions,
        )

    # Verify spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert_embedding_attributes(
        spans[0], model_name, latest_experimental_enabled, response
    )

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


def test_embeddings_with_batch_input(
    span_exporter, metric_reader, openai_client, instrument_with_content, vcr
):
    """Test creating embeddings with batch input (list of strings)"""
    latest_experimental_enabled = is_experimental_mode()
    model_name = "text-embedding-3-small"
    input_texts = [
        "This is the first test string for embeddings",
        "This is the second test string for embeddings",
        "This is the third test string for embeddings",
    ]

    with vcr.use_cassette("test_embeddings_with_batch_input.yaml"):
        response = openai_client.embeddings.create(
            model=model_name,
            input=input_texts,
        )

    # Verify spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert_embedding_attributes(
        spans[0], model_name, latest_experimental_enabled, response
    )

    # Verify results contain the same number of embeddings as input texts
    assert len(response.data) == len(input_texts)


def test_embeddings_with_encoding_format(
    span_exporter, metric_reader, openai_client, instrument_no_content, vcr
):
    """Test creating embeddings with different encoding format"""
    latest_experimental_enabled = is_experimental_mode()
    model_name = "text-embedding-3-small"
    input_text = "This is a test for embeddings with encoding format"
    encoding_format = "base64"

    with vcr.use_cassette("test_embeddings_with_encoding_format.yaml"):
        response = openai_client.embeddings.create(
            model=model_name,
            input=input_text,
            encoding_format=encoding_format,
        )

    # Verify spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert_embedding_attributes(
        spans[0], model_name, latest_experimental_enabled, response
    )

    # Verify encoding_format attribute is set correctly
    assert spans[0].attributes["gen_ai.request.encoding_formats"] == (
        encoding_format,
    )


@pytest.mark.parametrize("not_given_value", [NOT_GIVEN, not_given])
def test_embeddings_with_not_given_values(
    span_exporter,
    metric_reader,
    openai_client,
    instrument_no_content,
    not_given_value,
    vcr,
):
    """Test creating embeddings with NOT_GIVEN and not_given values"""
    latest_experimental_enabled = is_experimental_mode()
    model_name = "text-embedding-3-small"
    input_text = "This is a test for embeddings with encoding format"

    with vcr.use_cassette("test_embeddings_with_not_given_values.yaml"):
        response = openai_client.embeddings.create(
            model=model_name,
            input=input_text,
            dimensions=not_given_value,
        )

    # Verify spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert_embedding_attributes(
        spans[0], model_name, latest_experimental_enabled, response
    )

    assert "gen_ai.request.dimensions" not in spans[0].attributes


def test_embeddings_bad_endpoint(
    span_exporter, metric_reader, instrument_no_content, vcr
):
    """Test error handling for bad endpoint"""
    latest_experimental_enabled = is_experimental_mode()
    model_name = "text-embedding-3-small"
    input_text = "This is a test for embeddings with bad endpoint"

    client = OpenAI(base_url="http://localhost:4242")

    with vcr.use_cassette("test_embeddings_bad_endpoint.yaml"):
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
        latest_experimental_enabled,
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


def test_embeddings_model_not_found(
    span_exporter, metric_reader, openai_client, instrument_no_content, vcr
):
    """Test error handling for non-existent model"""
    latest_experimental_enabled = is_experimental_mode()
    model_name = "non-existent-embedding-model"
    input_text = "This is a test for embeddings with bad model"

    with vcr.use_cassette("test_embeddings_model_not_found.yaml"):
        with pytest.raises(NotFoundError):
            openai_client.embeddings.create(
                model=model_name,
                input=input_text,
            )

    # Verify spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert_all_attributes(
        spans[0],
        model_name,
        latest_experimental_enabled,
        operation_name="embeddings",
    )
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


def test_embeddings_token_metrics(
    span_exporter, metric_reader, openai_client, instrument_no_content, vcr
):
    """Test that token usage metrics are correctly recorded"""
    latest_experimental_enabled = is_experimental_mode()
    model_name = "text-embedding-3-small"
    input_text = "This is a test for embeddings token metrics"

    with vcr.use_cassette("test_embeddings_token_metrics.yaml"):
        response = openai_client.embeddings.create(
            model=model_name,
            input=input_text,
        )

    # Verify spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert_embedding_attributes(
        spans[0], model_name, latest_experimental_enabled, response
    )

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
