# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=too-many-locals

"""Offline tests for the Aleph Alpha completion instrumentation.

These tests never hit the network and never require a real API token. The
Aleph Alpha SDK talks to the API through ``requests`` (sync ``Client``) and
``aiohttp`` (async ``AsyncClient``), not ``httpx``, so ``respx`` cannot be used
here. Instead we patch the SDK's ``_post_request`` boundary to return a canned
JSON body (or raise a real error). The real ``aleph_alpha_client`` SDK still
parses that body into a genuine ``CompletionResponse`` via
``CompletionResponse.from_json``, so the instrumentation wrapper runs against
real SDK response objects.

Client construction itself does not touch the network (the API version check is
a separate, explicit ``validate_version()`` call), so a plain ``Client(...)`` /
``AsyncClient(...)`` can be built offline.
"""

from __future__ import annotations

import json

import pytest
from aleph_alpha_client import (
    AsyncClient,
    Client,
    CompletionRequest,
    Prompt,
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

from .conftest import TEST_HOST, TEST_TOKEN

TEST_MODEL = "luminous-base"
TEST_RESPONSE_MODEL = "luminous-base-2023"
INPUT_TOKENS = 12
OUTPUT_TOKENS = 5
COMPLETION_TEXT = "This is a test"
PROMPT_TEXT = "Say this is a test"

GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"
ALEPH_ALPHA = "aleph_alpha"


class AlephAlphaBoom(RuntimeError):
    """Stand-in provider error raised from the mocked HTTP boundary."""


def _completion_body() -> dict:
    return {
        "model_version": TEST_RESPONSE_MODEL,
        "completions": [
            {
                "completion": COMPLETION_TEXT,
                "finish_reason": "maximum_tokens",
            }
        ],
        "num_tokens_prompt_total": INPUT_TOKENS,
        "num_tokens_generated": OUTPUT_TOKENS,
    }


def _make_request() -> CompletionRequest:
    return CompletionRequest(
        prompt=Prompt.from_text(PROMPT_TEXT),
        maximum_tokens=64,
    )


def _sync_client() -> Client:
    return Client(token=TEST_TOKEN, host=TEST_HOST)


def _async_client() -> AsyncClient:
    return AsyncClient(token=TEST_TOKEN, host=TEST_HOST)


def _get_span(span_exporter):
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    return spans[0]


def _get_metric(metric_reader, name):
    metrics_data = metric_reader.get_metrics_data()
    if metrics_data is None:
        return None
    for resource_metric in metrics_data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                if metric.name == name:
                    return metric
    return None


def _assert_common_request_attributes(span):
    assert span.name == f"chat {TEST_MODEL}"

    operation_name = span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
    assert (
        operation_name == GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    assert isinstance(operation_name, str)

    # experimental path uses gen_ai.provider.name (literal, no enum member)
    assert span.attributes[GEN_AI_PROVIDER_NAME] == ALEPH_ALPHA
    assert isinstance(span.attributes[GEN_AI_PROVIDER_NAME], str)

    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == TEST_MODEL
    assert isinstance(
        span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL], str
    )

    assert (
        span.attributes[ServerAttributes.SERVER_ADDRESS]
        == "api.aleph-alpha.com"
    )
    assert isinstance(span.attributes[ServerAttributes.SERVER_ADDRESS], str)


def _assert_response_attributes(span):
    assert (
        span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL]
        == TEST_RESPONSE_MODEL
    )
    assert isinstance(
        span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL], str
    )

    input_tokens = span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
    output_tokens = span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
    assert input_tokens == INPUT_TOKENS
    assert output_tokens == OUTPUT_TOKENS
    assert isinstance(input_tokens, int)
    assert isinstance(output_tokens, int)

    # Aleph Alpha finish reasons are not part of the semconv value set, so no
    # finish-reason attribute is emitted.
    assert (
        GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS not in span.attributes
    )


def _assert_token_and_duration_metrics(metric_reader):
    token_metric = _get_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE
    )
    assert token_metric is not None
    token_types = {
        point.attributes[GenAIAttributes.GEN_AI_TOKEN_TYPE]
        for point in token_metric.data.data_points
    }
    assert GenAIAttributes.GenAiTokenTypeValues.INPUT.value in token_types
    assert GenAIAttributes.GenAiTokenTypeValues.OUTPUT.value in token_types
    for point in token_metric.data.data_points:
        assert point.attributes[GEN_AI_PROVIDER_NAME] == ALEPH_ALPHA
        assert (
            point.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
            == TEST_MODEL
        )
        assert isinstance(point.sum, int)

    duration_metric = _get_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
    )
    assert duration_metric is not None
    duration_points = list(duration_metric.data.data_points)
    assert len(duration_points) == 1
    assert duration_points[0].sum >= 0


def test_complete(span_exporter, metric_reader, instrument, monkeypatch):
    monkeypatch.setattr(
        Client,
        "_post_request",
        lambda self, endpoint, request, model=None: _completion_body(),
    )

    client = _sync_client()
    response = client.complete(_make_request(), model=TEST_MODEL)

    assert response.model_version == TEST_RESPONSE_MODEL
    assert response.completions[0].completion == COMPLETION_TEXT

    span = _get_span(span_exporter)
    _assert_common_request_attributes(span)
    _assert_response_attributes(span)
    _assert_token_and_duration_metrics(metric_reader)


def test_complete_model_positional(
    span_exporter, metric_reader, instrument, monkeypatch
):
    """``model`` passed positionally must still populate the request model."""
    monkeypatch.setattr(
        Client,
        "_post_request",
        lambda self, endpoint, request, model=None: _completion_body(),
    )

    client = _sync_client()
    client.complete(_make_request(), TEST_MODEL)

    span = _get_span(span_exporter)
    _assert_common_request_attributes(span)


@pytest.mark.asyncio
async def test_complete_async(
    span_exporter, metric_reader, instrument, monkeypatch
):
    async def fake_post(self, endpoint, request, model=None):  # noqa: ARG001
        return _completion_body()

    monkeypatch.setattr(AsyncClient, "_post_request", fake_post)

    client = _async_client()
    try:
        response = await client.complete(_make_request(), model=TEST_MODEL)
    finally:
        await client.close()

    assert response.model_version == TEST_RESPONSE_MODEL
    assert response.completions[0].completion == COMPLETION_TEXT

    span = _get_span(span_exporter)
    _assert_common_request_attributes(span)
    _assert_response_attributes(span)
    _assert_token_and_duration_metrics(metric_reader)


def test_complete_with_content(
    span_exporter, instrument_with_content, monkeypatch
):
    monkeypatch.setattr(
        Client,
        "_post_request",
        lambda self, endpoint, request, model=None: _completion_body(),
    )

    client = _sync_client()
    client.complete(_make_request(), model=TEST_MODEL)

    span = _get_span(span_exporter)
    _assert_common_request_attributes(span)

    input_messages = json.loads(
        span.attributes[GenAIAttributes.GEN_AI_INPUT_MESSAGES]
    )
    assert input_messages[0]["role"] == "user"
    assert input_messages[0]["parts"][0]["content"] == PROMPT_TEXT

    output_messages = json.loads(
        span.attributes[GenAIAttributes.GEN_AI_OUTPUT_MESSAGES]
    )
    assert output_messages[0]["role"] == "assistant"
    assert output_messages[0]["parts"][0]["content"] == COMPLETION_TEXT


def test_complete_error_is_reraised(
    span_exporter, metric_reader, instrument, monkeypatch
):
    """A provider error must propagate unmodified while telemetry is recorded."""

    def fake_post(self, endpoint, request, model=None):  # noqa: ARG001
        raise AlephAlphaBoom("boom")

    monkeypatch.setattr(Client, "_post_request", fake_post)

    client = _sync_client()
    with pytest.raises(AlephAlphaBoom) as exc_info:
        client.complete(_make_request(), model=TEST_MODEL)

    span = _get_span(span_exporter)
    _assert_common_request_attributes(span)

    error_type = span.attributes[ErrorAttributes.ERROR_TYPE]
    assert isinstance(error_type, str)
    assert error_type == type(exc_info.value).__qualname__
    assert error_type == "AlephAlphaBoom"
    assert span.status.status_code.name == "ERROR"

    duration_metric = _get_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
    )
    assert duration_metric is not None
    error_points = [
        point
        for point in duration_metric.data.data_points
        if ErrorAttributes.ERROR_TYPE in point.attributes
    ]
    assert error_points
    assert error_points[0].attributes[ErrorAttributes.ERROR_TYPE] == error_type

    # No token-usage metric on the error path (no usage available).
    token_metric = _get_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE
    )
    if token_metric is not None:
        assert len(token_metric.data.data_points) == 0
