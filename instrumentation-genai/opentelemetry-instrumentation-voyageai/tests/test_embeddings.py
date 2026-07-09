# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=too-many-locals

"""Offline tests for the Voyage AI embeddings instrumentation.

These tests never hit the network and never require a real API key. The Voyage
AI SDK talks to the API through ``requests`` (sync) and ``aiohttp`` (async),
not ``httpx``, so ``respx`` cannot be used here. Instead we patch the SDK's
``APIRequestor.request`` / ``APIRequestor.arequest`` boundary to return canned
``VoyageHttpResponse`` objects (or raise the real Voyage AI errors). The real
``voyageai`` SDK still parses these into real ``EmbeddingsObject`` instances, so
the instrumentation wrapper runs against genuine response objects.
"""

from __future__ import annotations

import pytest
import voyageai
from voyageai.api_resources.api_requestor import (
    APIRequestor,
    VoyageHttpResponse,
)

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.util.genai.utils import is_experimental_mode

LLM_MODEL = "voyage-3-lite"
DIMENSION = 8
INPUT_TOKENS = 17
TEXTS = [
    "The capital of France is Paris.",
    "London is the capital of England.",
    "Berlin is the capital of Germany.",
]

_VOYAGEAI_PROVIDER = "voyageai"


def _embedding_vector() -> list[float]:
    return [float(i) / 10.0 for i in range(DIMENSION)]


def _embeddings_body() -> dict:
    return {
        "object": "list",
        "data": [
            {
                "object": "embedding",
                "embedding": _embedding_vector(),
                "index": idx,
            }
            for idx in range(len(TEXTS))
        ],
        "model": LLM_MODEL,
        "usage": {"total_tokens": INPUT_TOKENS},
    }


def _mock_response() -> VoyageHttpResponse:
    return VoyageHttpResponse(
        _embeddings_body(), {"request-id": "voyage-req-1"}
    )


@pytest.fixture
def mock_sync_transport(monkeypatch):
    """Patch the sync HTTP boundary to return a canned embeddings response."""

    def fake_request(self, method, url, **kwargs):  # noqa: ARG001
        return _mock_response()

    monkeypatch.setattr(APIRequestor, "request", fake_request)


@pytest.fixture
def mock_async_transport(monkeypatch):
    """Patch the async HTTP boundary to return a canned embeddings response."""

    async def fake_arequest(self, method, url, **kwargs):  # noqa: ARG001
        return _mock_response()

    monkeypatch.setattr(APIRequestor, "arequest", fake_arequest)


def _find_metric(metric_reader, name):
    metrics_data = metric_reader.get_metrics_data()
    if metrics_data is None:
        return None
    for resource_metric in metrics_data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                if metric.name == name:
                    return metric
    return None


def _provider_attr_name(latest_experimental_enabled: bool) -> str:
    if latest_experimental_enabled:
        return GenAIAttributes.GEN_AI_PROVIDER_NAME
    return GenAIAttributes.GEN_AI_SYSTEM


def _assert_common_success_attributes(span, latest_experimental_enabled):
    attributes = span.attributes

    assert span.name == f"embeddings {LLM_MODEL}"

    operation_name = attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
    assert (
        operation_name
        == GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value
    )
    assert operation_name == "embeddings"
    assert isinstance(operation_name, str)

    assert (
        attributes[_provider_attr_name(latest_experimental_enabled)]
        == _VOYAGEAI_PROVIDER
    )

    assert attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == LLM_MODEL
    assert isinstance(attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL], str)

    input_tokens = attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
    assert isinstance(input_tokens, int)
    assert input_tokens == INPUT_TOKENS

    dimension = attributes[GenAIAttributes.GEN_AI_EMBEDDINGS_DIMENSION_COUNT]
    assert isinstance(dimension, int)
    assert dimension == DIMENSION

    # Embeddings tokens are all input tokens; output token attribute must be absent.
    assert GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS not in attributes


def _assert_metrics_recorded(metric_reader, latest_experimental_enabled):
    duration_metric = _find_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
    )
    assert duration_metric is not None
    duration_point = duration_metric.data.data_points[0]
    assert duration_point.sum >= 0
    assert (
        duration_point.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value
    )
    assert (
        duration_point.attributes[
            _provider_attr_name(latest_experimental_enabled)
        ]
        == _VOYAGEAI_PROVIDER
    )

    token_metric = _find_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE
    )
    assert token_metric is not None
    token_types = {
        point.attributes[GenAIAttributes.GEN_AI_TOKEN_TYPE]
        for point in token_metric.data.data_points
    }
    # Only input tokens are recorded for embeddings; no completion/output tokens.
    assert GenAIAttributes.GenAiTokenTypeValues.INPUT.value in token_types
    assert (
        GenAIAttributes.GenAiTokenTypeValues.COMPLETION.value
        not in token_types
    )
    for point in token_metric.data.data_points:
        assert isinstance(point.sum, int)
        assert point.sum == INPUT_TOKENS


def test_embed(
    span_exporter,
    metric_reader,
    voyageai_client,
    instrument_with_content,
    mock_sync_transport,
):
    latest_experimental_enabled = is_experimental_mode()

    result = voyageai_client.embed(
        texts=TEXTS,
        model=LLM_MODEL,
        input_type="document",
    )

    assert len(result.embeddings) == len(TEXTS)
    assert result.total_tokens == INPUT_TOKENS

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    _assert_common_success_attributes(span, latest_experimental_enabled)

    # Server address / port are derived from the client base URL.
    if ServerAttributes.SERVER_ADDRESS in span.attributes:
        assert (
            span.attributes[ServerAttributes.SERVER_ADDRESS]
            == "api.voyageai.com"
        )
        assert isinstance(
            span.attributes[ServerAttributes.SERVER_ADDRESS], str
        )

    _assert_metrics_recorded(metric_reader, latest_experimental_enabled)


@pytest.mark.asyncio
async def test_async_embed(
    span_exporter,
    metric_reader,
    async_voyageai_client,
    instrument_with_content,
    mock_async_transport,
):
    latest_experimental_enabled = is_experimental_mode()

    result = await async_voyageai_client.embed(
        texts=TEXTS,
        model=LLM_MODEL,
        input_type="document",
    )

    assert len(result.embeddings) == len(TEXTS)
    assert result.total_tokens == INPUT_TOKENS

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    _assert_common_success_attributes(spans[0], latest_experimental_enabled)
    _assert_metrics_recorded(metric_reader, latest_experimental_enabled)


def test_embed_error_is_reraised(
    span_exporter,
    metric_reader,
    voyageai_client,
    instrument_no_content,
    monkeypatch,
):
    """A provider error must propagate unmodified while telemetry is recorded."""

    def fake_request(self, method, url, **kwargs):  # noqa: ARG001
        raise voyageai.error.InvalidRequestError("boom")

    monkeypatch.setattr(APIRequestor, "request", fake_request)

    with pytest.raises(voyageai.error.InvalidRequestError):
        voyageai_client.embed(
            texts=TEXTS,
            model=LLM_MODEL,
            input_type="document",
        )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    error_type = span.attributes[ErrorAttributes.ERROR_TYPE]
    assert error_type == "InvalidRequestError"
    assert isinstance(error_type, str)

    # The operation duration metric is still recorded, tagged with error.type.
    duration_metric = _find_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
    )
    assert duration_metric is not None
    assert (
        duration_metric.data.data_points[0].attributes[
            ErrorAttributes.ERROR_TYPE
        ]
        == "InvalidRequestError"
    )

    # No token-usage metric on the error path (no usage available).
    token_metric = _find_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE
    )
    if token_metric is not None:
        assert len(token_metric.data.data_points) == 0
