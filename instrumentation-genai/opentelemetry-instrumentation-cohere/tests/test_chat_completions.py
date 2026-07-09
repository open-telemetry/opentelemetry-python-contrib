# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=too-many-locals

"""Offline tests for the Cohere instrumentation.

These tests never hit the network and never require a real API key: an
``httpx`` mock transport (via ``respx``) returns canned Cohere responses so the
real ``cohere`` SDK parses real response objects and the instrumentation
wrapper runs against them.
"""

from __future__ import annotations

import json

import cohere
import httpx
import pytest
import respx
from cohere.core.api_error import ApiError

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

COHERE_V2_CHAT_URL = "https://api.cohere.com/v2/chat"
COHERE_V1_CHAT_URL = "https://api.cohere.com/v1/chat"
COHERE_V2_EMBED_URL = "https://api.cohere.com/v2/embed"
COHERE_V1_EMBED_URL = "https://api.cohere.com/v1/embed"

LLM_MODEL = "command-r"
EMBED_MODEL = "embed-english-v3.0"
V2_RESPONSE_ID = "chat-v2-0001"
V1_RESPONSE_ID = "chat-v1-0001"
EMBED_RESPONSE_ID = "embed-v2-0001"

USER_MESSAGES = [{"role": "user", "content": "Say this is a test."}]

_COHERE_PROVIDER = "cohere"


def _v2_chat_body() -> dict:
    return {
        "id": V2_RESPONSE_ID,
        "finish_reason": "COMPLETE",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "This is a test."}],
        },
        "usage": {
            "billed_units": {"input_tokens": 12, "output_tokens": 5},
            "tokens": {"input_tokens": 20, "output_tokens": 5},
        },
    }


def _v1_chat_body() -> dict:
    return {
        "text": "This is a test.",
        "response_id": V1_RESPONSE_ID,
        "generation_id": "gen-0001",
        "finish_reason": "COMPLETE",
        "meta": {
            "api_version": {"version": "1"},
            "billed_units": {"input_tokens": 10, "output_tokens": 4},
        },
    }


def _v2_embed_body() -> dict:
    return {
        "response_type": "embeddings_by_type",
        "id": EMBED_RESPONSE_ID,
        "embeddings": {"float": [[0.1, 0.2, 0.3, 0.4]]},
        "texts": ["Say this is a test."],
        "meta": {
            "api_version": {"version": "2"},
            "billed_units": {"input_tokens": 3},
        },
    }


def _v1_embed_body() -> dict:
    return {
        "response_type": "embeddings_floats",
        "id": "embed-v1-0001",
        "embeddings": [[0.1, 0.2, 0.3, 0.4]],
        "texts": ["Say this is a test."],
        "meta": {
            "api_version": {"version": "1"},
            "billed_units": {"input_tokens": 3},
        },
    }


def _v2_chat_stream_body() -> str:
    events = [
        {
            "type": "message-start",
            "id": V2_RESPONSE_ID,
            "delta": {"message": {"role": "assistant"}},
        },
        {
            "type": "content-start",
            "index": 0,
            "delta": {"message": {"content": {"type": "text", "text": ""}}},
        },
        {
            "type": "content-delta",
            "index": 0,
            "delta": {"message": {"content": {"text": "This is a test."}}},
        },
        {"type": "content-end", "index": 0},
        {
            "type": "message-end",
            "delta": {
                "finish_reason": "COMPLETE",
                "usage": {
                    "billed_units": {
                        "input_tokens": 12,
                        "output_tokens": 5,
                    },
                    "tokens": {"input_tokens": 20, "output_tokens": 5},
                },
            },
        },
    ]
    lines = [f"data: {json.dumps(event)}\n\n" for event in events]
    return "".join(lines)


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


def _assert_duration_metric(metric_reader, operation_name):
    duration_metric = _find_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
    )
    assert duration_metric is not None
    point = duration_metric.data.data_points[0]
    assert point.sum >= 0
    assert (
        point.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == operation_name
    )
    assert (
        point.attributes[GenAIAttributes.GEN_AI_PROVIDER_NAME]
        == _COHERE_PROVIDER
    )


def _assert_token_metric(metric_reader):
    token_metric = _find_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE
    )
    assert token_metric is not None
    token_types = {
        point.attributes[GenAIAttributes.GEN_AI_TOKEN_TYPE]
        for point in token_metric.data.data_points
    }
    assert GenAIAttributes.GenAiTokenTypeValues.INPUT.value in token_types
    for point in token_metric.data.data_points:
        assert isinstance(point.sum, int)


def _assert_chat_common(span):
    attributes = span.attributes
    assert span.name == f"chat {LLM_MODEL}"
    assert (
        attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    assert attributes[GenAIAttributes.GEN_AI_PROVIDER_NAME] == _COHERE_PROVIDER
    assert attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == LLM_MODEL
    assert isinstance(attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL], str)

    finish_reasons = attributes[GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS]
    assert isinstance(finish_reasons, (tuple, list))
    assert list(finish_reasons) == ["COMPLETE"]

    input_tokens = attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
    output_tokens = attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
    assert isinstance(input_tokens, int)
    assert isinstance(output_tokens, int)


# --- V2 chat (non-streaming) ------------------------------------------------


@respx.mock
def test_v2_chat_non_streaming(
    span_exporter, metric_reader, instrument_with_content
):
    respx.post(COHERE_V2_CHAT_URL).mock(
        return_value=httpx.Response(200, json=_v2_chat_body())
    )

    client = cohere.ClientV2()
    response = client.chat(model=LLM_MODEL, messages=USER_MESSAGES)

    assert response.id == V2_RESPONSE_ID

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    _assert_chat_common(span)
    assert (
        span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID] == V2_RESPONSE_ID
    )
    assert isinstance(span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID], str)
    assert span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS] == 12
    assert span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS] == 5

    if ServerAttributes.SERVER_ADDRESS in span.attributes:
        assert (
            span.attributes[ServerAttributes.SERVER_ADDRESS]
            == "api.cohere.com"
        )
        assert isinstance(
            span.attributes[ServerAttributes.SERVER_ADDRESS], str
        )

    _assert_duration_metric(
        metric_reader, GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    _assert_token_metric(metric_reader)


@pytest.mark.asyncio
@respx.mock
async def test_v2_chat_non_streaming_async(
    span_exporter, metric_reader, instrument_with_content
):
    respx.post(COHERE_V2_CHAT_URL).mock(
        return_value=httpx.Response(200, json=_v2_chat_body())
    )

    client = cohere.AsyncClientV2()
    response = await client.chat(model=LLM_MODEL, messages=USER_MESSAGES)

    assert response.id == V2_RESPONSE_ID

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    _assert_chat_common(spans[0])
    assert spans[0].attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS] == 12
    assert spans[0].attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS] == 5
    _assert_duration_metric(
        metric_reader, GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    _assert_token_metric(metric_reader)


# --- V2 chat (streaming) ----------------------------------------------------


@respx.mock
def test_v2_chat_streaming(
    span_exporter, metric_reader, instrument_with_content
):
    respx.post(COHERE_V2_CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            text=_v2_chat_stream_body(),
            headers={"content-type": "text/event-stream"},
        )
    )

    client = cohere.ClientV2()
    stream = client.chat_stream(model=LLM_MODEL, messages=USER_MESSAGES)

    collected = ""
    for event in stream:
        if event.type == "content-delta":
            collected += event.delta.message.content.text or ""
    assert collected == "This is a test."

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    _assert_chat_common(span)
    assert (
        span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID] == V2_RESPONSE_ID
    )
    assert span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS] == 12
    assert span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS] == 5

    _assert_duration_metric(
        metric_reader, GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    _assert_token_metric(metric_reader)


@pytest.mark.asyncio
@respx.mock
async def test_v2_chat_streaming_async(
    span_exporter, metric_reader, instrument_with_content
):
    respx.post(COHERE_V2_CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            text=_v2_chat_stream_body(),
            headers={"content-type": "text/event-stream"},
        )
    )

    client = cohere.AsyncClientV2()
    stream = client.chat_stream(model=LLM_MODEL, messages=USER_MESSAGES)

    collected = ""
    async for event in stream:
        if event.type == "content-delta":
            collected += event.delta.message.content.text or ""
    assert collected == "This is a test."

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    _assert_chat_common(span)
    assert span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS] == 12
    assert span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS] == 5

    _assert_duration_metric(
        metric_reader, GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    _assert_token_metric(metric_reader)


@pytest.mark.asyncio
@respx.mock
async def test_v2_chat_streaming_async_close_does_not_raise(
    span_exporter, instrument_with_content
):
    # Cohere's async chat_stream is a native async generator, which exposes
    # ``aclose`` but not ``close``. Closing the wrapped stream (as an
    # ``async with`` block does on exit) must not raise and must not mark the
    # span as failed.
    respx.post(COHERE_V2_CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            text=_v2_chat_stream_body(),
            headers={"content-type": "text/event-stream"},
        )
    )

    client = cohere.AsyncClientV2()
    stream = client.chat_stream(model=LLM_MODEL, messages=USER_MESSAGES)
    # Close before consuming the stream: this drives the wrapper's close path.
    await stream.close()

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert ErrorAttributes.ERROR_TYPE not in spans[0].attributes


# --- V1 chat (non-streaming) ------------------------------------------------


@respx.mock
def test_v1_chat_non_streaming(
    span_exporter, metric_reader, instrument_with_content
):
    respx.post(COHERE_V1_CHAT_URL).mock(
        return_value=httpx.Response(200, json=_v1_chat_body())
    )

    client = cohere.Client()
    response = client.chat(model=LLM_MODEL, message="Say this is a test.")

    assert response.response_id == V1_RESPONSE_ID

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.name == f"chat {LLM_MODEL}"
    assert (
        span.attributes[GenAIAttributes.GEN_AI_PROVIDER_NAME]
        == _COHERE_PROVIDER
    )
    assert (
        span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID] == V1_RESPONSE_ID
    )
    finish_reasons = span.attributes[
        GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS
    ]
    assert list(finish_reasons) == ["COMPLETE"]
    assert span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS] == 10
    assert span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS] == 4

    _assert_duration_metric(
        metric_reader, GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    _assert_token_metric(metric_reader)


# --- Embeddings -------------------------------------------------------------


@respx.mock
def test_v2_embed(span_exporter, metric_reader, instrument_no_content):
    respx.post(COHERE_V2_EMBED_URL).mock(
        return_value=httpx.Response(200, json=_v2_embed_body())
    )

    client = cohere.ClientV2()
    response = client.embed(
        model=EMBED_MODEL,
        texts=["Say this is a test."],
        input_type="search_document",
        embedding_types=["float"],
    )

    assert response.id == EMBED_RESPONSE_ID

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.name == f"embeddings {EMBED_MODEL}"
    assert (
        span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value
    )
    assert (
        span.attributes[GenAIAttributes.GEN_AI_PROVIDER_NAME]
        == _COHERE_PROVIDER
    )
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == EMBED_MODEL
    input_tokens = span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
    assert isinstance(input_tokens, int)
    assert input_tokens == 3
    assert (
        span.attributes[GenAIAttributes.GEN_AI_EMBEDDINGS_DIMENSION_COUNT]
        == 4
    )

    encoding_formats = span.attributes[
        GenAIAttributes.GEN_AI_REQUEST_ENCODING_FORMATS
    ]
    assert isinstance(encoding_formats, (tuple, list))
    assert list(encoding_formats) == ["float"]

    _assert_duration_metric(
        metric_reader,
        GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value,
    )
    _assert_token_metric(metric_reader)


@pytest.mark.asyncio
@respx.mock
async def test_v1_embed_async(
    span_exporter, metric_reader, instrument_no_content
):
    respx.post(COHERE_V1_EMBED_URL).mock(
        return_value=httpx.Response(200, json=_v1_embed_body())
    )

    client = cohere.AsyncClient()
    await client.embed(
        model=EMBED_MODEL,
        texts=["Say this is a test."],
        input_type="search_document",
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.name == f"embeddings {EMBED_MODEL}"
    assert (
        span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value
    )
    assert span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS] == 3
    # V1 returns embeddings as a plain list, so the dimension count must still
    # be derived from the list-shaped response.
    assert (
        span.attributes[GenAIAttributes.GEN_AI_EMBEDDINGS_DIMENSION_COUNT]
        == 4
    )

    _assert_duration_metric(
        metric_reader,
        GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value,
    )


# --- Error handling ---------------------------------------------------------


@respx.mock
def test_v2_chat_error_is_reraised(
    span_exporter, metric_reader, instrument_no_content
):
    respx.post(COHERE_V2_CHAT_URL).mock(
        return_value=httpx.Response(
            500, json={"message": "internal server error"}
        )
    )

    client = cohere.ClientV2()
    with pytest.raises(ApiError):
        client.chat(model=LLM_MODEL, messages=USER_MESSAGES)

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    error_type = span.attributes[ErrorAttributes.ERROR_TYPE]
    assert isinstance(error_type, str)
    assert "Error" in error_type

    duration_metric = _find_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
    )
    assert duration_metric is not None
    assert (
        duration_metric.data.data_points[0].attributes[
            ErrorAttributes.ERROR_TYPE
        ]
        == error_type
    )


@respx.mock
def test_v2_chat_connection_error_propagates(
    span_exporter, instrument_no_content
):
    """A transport failure raised inside the SDK call must propagate unmodified.

    The instrumentation must record ``error.type`` and re-raise the original
    exception without wrapping or swallowing it.
    """
    respx.post(COHERE_V2_CHAT_URL).mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    client = cohere.ClientV2()
    with pytest.raises(httpx.ConnectError):
        client.chat(model=LLM_MODEL, messages=USER_MESSAGES)

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    error_type = spans[0].attributes[ErrorAttributes.ERROR_TYPE]
    assert error_type == "ConnectError"
    assert isinstance(error_type, str)
