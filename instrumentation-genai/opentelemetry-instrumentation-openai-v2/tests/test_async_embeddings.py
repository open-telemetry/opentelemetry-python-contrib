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

"""Unit tests for OpenAI Async Embeddings API instrumentation."""

import pytest
from openai import AsyncOpenAI, NotFoundError

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.semconv._incubating.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics

from .test_utils import assert_all_attributes


@pytest.mark.asyncio
@pytest.mark.vcr()
async def test_async_embeddings_no_content(
    span_exporter, log_exporter, async_openai_client, instrument_no_content
):
    """Test creating embeddings asynchronously with content capture disabled"""
    model_name = "text-embedding-3-small"
    input_text = "This is a test for async embeddings"

    response = await async_openai_client.embeddings.create(
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


@pytest.mark.asyncio
@pytest.mark.vcr()
async def test_async_embeddings_with_dimensions(
    span_exporter, metric_reader, async_openai_client, instrument_no_content
):
    """Test creating embeddings asynchronously with custom dimensions"""
    model_name = "text-embedding-3-small"
    input_text = "This is a test for async embeddings with dimensions"
    dimensions = 512  # Using a smaller dimension than default

    response = await async_openai_client.embeddings.create(
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


@pytest.mark.asyncio
@pytest.mark.vcr()
async def test_async_embeddings_with_batch_input(
    span_exporter, metric_reader, async_openai_client, instrument_with_content
):
    """Test creating embeddings asynchronously with batch input"""
    model_name = "text-embedding-3-small"
    input_texts = [
        "This is the first test string for async embeddings",
        "This is the second test string for async embeddings",
        "This is the third test string for async embeddings",
    ]

    response = await async_openai_client.embeddings.create(
        model=model_name,
        input=input_texts,
    )

    # Verify spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert_embedding_attributes(spans[0], model_name, response)

    # Verify results contain the same number of embeddings as input texts
    assert len(response.data) == len(input_texts)


@pytest.mark.asyncio
@pytest.mark.vcr()
async def test_async_embeddings_error_handling(
    span_exporter, metric_reader, instrument_no_content
):
    """Test async embeddings error handling"""
    model_name = "non-existent-embedding-model"
    input_text = "This is a test for async embeddings with error"

    client = AsyncOpenAI()

    with pytest.raises(NotFoundError):
        await client.embeddings.create(
            model=model_name,
            input=input_text,
        )

    # Verify spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert_all_attributes(spans[0], model_name, operation_name="embeddings")
    assert "NotFoundError" == spans[0].attributes[ErrorAttributes.ERROR_TYPE]


@pytest.mark.asyncio
@pytest.mark.vcr()
async def test_async_embeddings_token_metrics(
    span_exporter, metric_reader, async_openai_client, instrument_no_content
):
    """Test that token usage metrics are correctly recorded for async embeddings"""
    model_name = "text-embedding-3-small"
    input_text = "This is a test for async embeddings token metrics"

    response = await async_openai_client.embeddings.create(
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


@pytest.mark.asyncio
@pytest.mark.vcr()
async def test_async_embeddings_with_encoding_format(
    span_exporter, metric_reader, async_openai_client, instrument_no_content
):
    """Test creating embeddings with different encoding format"""
    model_name = "text-embedding-3-small"
    input_text = "This is a test for embeddings with encoding format"
    encoding_format = "base64"

    response = await async_openai_client.embeddings.create(
        model=model_name,
        input=input_text,
        encoding_format=encoding_format,
    )

    # Verify spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert_embedding_attributes(spans[0], model_name, response)

    # Verify encoding_format attribute is set correctly
    assert spans[0].attributes["gen_ai.request.encoding_formats"] == (
        encoding_format,
    )


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

    return
