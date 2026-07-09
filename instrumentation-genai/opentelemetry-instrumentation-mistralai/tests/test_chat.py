# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Offline tests for the Mistral AI instrumentation.

These tests never touch the network. They use ``respx`` to mock the httpx
transport that the ``mistralai`` SDK uses, returning canned Mistral JSON. The
real ``mistralai`` SDK parses that JSON into real response objects, so the
instrumentation wrapper runs end-to-end against real SDK types.

The tests exercise the latest-experimental semantic-convention path
(``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental``), which is what
the ``instrument`` fixtures enable.
"""

import json

import httpx
import pytest
import respx
from mistralai import Mistral

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.semconv.attributes import (
    server_attributes as ServerAttributes,
)

TEST_MODEL = "mistral-small-latest"
TEST_RESPONSE_MODEL = "mistral-small-2409"
BASE_URL = "https://api.mistral.ai"
CHAT_URL = f"{BASE_URL}/v1/chat/completions"
EMBEDDINGS_URL = f"{BASE_URL}/v1/embeddings"
GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"
MISTRAL_AI = "mistral_ai"

USER_PROMPT = [{"role": "user", "content": "Say this is a test"}]


def _chat_completion_body():
    return {
        "id": "cmpl-test-123",
        "object": "chat.completion",
        "created": 1727795200,
        "model": TEST_RESPONSE_MODEL,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "This is a test",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 5,
            "total_tokens": 17,
        },
    }


def _embeddings_body():
    return {
        "id": "emb-test-123",
        "object": "list",
        "model": TEST_RESPONSE_MODEL,
        "data": [
            {
                "object": "embedding",
                "embedding": [0.1, 0.2, 0.3, 0.4],
                "index": 0,
            }
        ],
        "usage": {
            "prompt_tokens": 8,
            "completion_tokens": 0,
            "total_tokens": 8,
        },
    }


def _sse_stream_bytes(events):
    lines = []
    for event in events:
        lines.append(f"data: {json.dumps(event)}\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode("utf-8")


def _stream_events():
    """Each SSE ``data:`` line carries a ``CompletionChunk`` payload directly.

    The mistralai SSE decoder parses that JSON and assigns it to the ``data``
    field of the ``CompletionEvent`` it yields, so the payload on the wire must
    be the bare ``CompletionChunk`` (``id``/``model``/``choices`` at the top
    level) and must not be pre-wrapped under a ``data`` key.
    """
    base = {
        "id": "cmpl-test-stream-123",
        "object": "chat.completion.chunk",
        "created": 1727795201,
        "model": TEST_RESPONSE_MODEL,
    }
    return [
        {
            **base,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": "This "},
                    "finish_reason": None,
                }
            ],
        },
        {
            **base,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": "is a test"},
                    "finish_reason": None,
                }
            ],
        },
        {
            **base,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": ""},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 5,
                "total_tokens": 17,
            },
        },
    ]


def _get_span(span_exporter):
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    return spans[0]


def _get_metric(metric_reader, name):
    metrics_data = metric_reader.get_metrics_data()
    for resource_metric in metrics_data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                if metric.name == name:
                    return metric
    return None


def _assert_common_chat_request_attributes(span):
    assert span.name == f"chat {TEST_MODEL}"
    assert (
        span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    assert isinstance(
        span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME], str
    )
    # experimental path uses gen_ai.provider.name (not gen_ai.system)
    assert span.attributes[GEN_AI_PROVIDER_NAME] == MISTRAL_AI
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == TEST_MODEL
    assert isinstance(
        span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL], str
    )
    assert (
        span.attributes[ServerAttributes.SERVER_ADDRESS] == "api.mistral.ai"
    )


def _assert_chat_response_attributes(span, response_id):
    assert (
        span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL]
        == TEST_RESPONSE_MODEL
    )
    assert isinstance(
        span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL], str
    )
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID] == response_id
    assert isinstance(
        span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID], str
    )

    finish_reasons = span.attributes[
        GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS
    ]
    assert isinstance(finish_reasons, (list, tuple))
    assert list(finish_reasons) == ["stop"]

    input_tokens = span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
    output_tokens = span.attributes[
        GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS
    ]
    assert input_tokens == 12
    assert output_tokens == 5
    assert isinstance(input_tokens, int)
    assert isinstance(output_tokens, int)


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
        assert point.attributes[GEN_AI_PROVIDER_NAME] == MISTRAL_AI
        assert (
            point.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
            == TEST_MODEL
        )

    duration_metric = _get_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
    )
    assert duration_metric is not None
    duration_points = list(duration_metric.data.data_points)
    assert len(duration_points) == 1
    assert duration_points[0].sum >= 0


@respx.mock
def test_chat_non_streaming(span_exporter, metric_reader, instrument):
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_chat_completion_body())
    )

    client = Mistral(api_key="test_mistral_api_key")
    response = client.chat.complete(
        model=TEST_MODEL,
        messages=USER_PROMPT,
    )

    span = _get_span(span_exporter)
    _assert_common_chat_request_attributes(span)
    _assert_chat_response_attributes(span, response.id)
    assert response.id == "cmpl-test-123"
    _assert_token_and_duration_metrics(metric_reader)


@pytest.mark.asyncio
@respx.mock
async def test_chat_non_streaming_async(
    span_exporter, metric_reader, instrument
):
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_chat_completion_body())
    )

    client = Mistral(api_key="test_mistral_api_key")
    response = await client.chat.complete_async(
        model=TEST_MODEL,
        messages=USER_PROMPT,
    )

    span = _get_span(span_exporter)
    _assert_common_chat_request_attributes(span)
    _assert_chat_response_attributes(span, response.id)
    _assert_token_and_duration_metrics(metric_reader)


@respx.mock
def test_chat_with_content(span_exporter, instrument_with_content):
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_chat_completion_body())
    )

    client = Mistral(api_key="test_mistral_api_key")
    client.chat.complete(
        model=TEST_MODEL,
        messages=USER_PROMPT,
    )

    span = _get_span(span_exporter)
    _assert_common_chat_request_attributes(span)

    input_messages = json.loads(
        span.attributes[GenAIAttributes.GEN_AI_INPUT_MESSAGES]
    )
    assert input_messages[0]["role"] == "user"
    assert input_messages[0]["parts"][0]["content"] == "Say this is a test"

    output_messages = json.loads(
        span.attributes[GenAIAttributes.GEN_AI_OUTPUT_MESSAGES]
    )
    assert output_messages[0]["role"] == "assistant"
    assert output_messages[0]["finish_reason"] == "stop"
    assert output_messages[0]["parts"][0]["content"] == "This is a test"


@respx.mock
def test_chat_streaming(span_exporter, metric_reader, instrument):
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse_stream_bytes(_stream_events()),
        )
    )

    client = Mistral(api_key="test_mistral_api_key")
    stream = client.chat.stream(
        model=TEST_MODEL,
        messages=USER_PROMPT,
    )

    collected = "".join(
        event.data.choices[0].delta.content or ""
        for event in stream
        if event.data.choices
    )
    assert collected == "This is a test"

    span = _get_span(span_exporter)
    _assert_common_chat_request_attributes(span)

    assert (
        span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL]
        == TEST_RESPONSE_MODEL
    )
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID] == (
        "cmpl-test-stream-123"
    )

    finish_reasons = span.attributes[
        GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS
    ]
    assert isinstance(finish_reasons, (list, tuple))
    assert list(finish_reasons) == ["stop"]

    input_tokens = span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
    output_tokens = span.attributes[
        GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS
    ]
    assert input_tokens == 12
    assert output_tokens == 5
    assert isinstance(input_tokens, int)
    assert isinstance(output_tokens, int)

    assert (
        _get_metric(metric_reader, gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE)
        is not None
    )
    assert (
        _get_metric(
            metric_reader, gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
        )
        is not None
    )


@pytest.mark.asyncio
@respx.mock
async def test_chat_streaming_async(span_exporter, instrument):
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse_stream_bytes(_stream_events()),
        )
    )

    client = Mistral(api_key="test_mistral_api_key")
    stream = await client.chat.stream_async(
        model=TEST_MODEL,
        messages=USER_PROMPT,
    )

    collected = ""
    async for event in stream:
        if event.data.choices:
            collected += event.data.choices[0].delta.content or ""
    assert collected == "This is a test"

    span = _get_span(span_exporter)
    _assert_common_chat_request_attributes(span)
    assert (
        span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL]
        == TEST_RESPONSE_MODEL
    )
    finish_reasons = span.attributes[
        GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS
    ]
    assert list(finish_reasons) == ["stop"]


@respx.mock
def test_chat_error(span_exporter, metric_reader, instrument):
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            500,
            json={"message": "internal error"},
        )
    )

    client = Mistral(api_key="test_mistral_api_key")

    with pytest.raises(Exception) as exc_info:
        client.chat.complete(
            model=TEST_MODEL,
            messages=USER_PROMPT,
        )

    span = _get_span(span_exporter)
    _assert_common_chat_request_attributes(span)

    error_type = span.attributes[ErrorAttributes.ERROR_TYPE]
    assert isinstance(error_type, str)
    assert error_type == type(exc_info.value).__qualname__

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
    assert (
        error_points[0].attributes[ErrorAttributes.ERROR_TYPE] == error_type
    )


@respx.mock
def test_embeddings(span_exporter, metric_reader, instrument):
    respx.post(EMBEDDINGS_URL).mock(
        return_value=httpx.Response(200, json=_embeddings_body())
    )

    client = Mistral(api_key="test_mistral_api_key")
    client.embeddings.create(
        model=TEST_MODEL,
        inputs=["hello world"],
    )

    span = _get_span(span_exporter)
    assert span.name == f"embeddings {TEST_MODEL}"
    assert (
        span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value
    )
    assert span.attributes[GEN_AI_PROVIDER_NAME] == MISTRAL_AI
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == TEST_MODEL
    assert (
        span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL]
        == TEST_RESPONSE_MODEL
    )

    input_tokens = span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
    assert input_tokens == 8
    assert isinstance(input_tokens, int)

    dimension_count = span.attributes[
        GenAIAttributes.GEN_AI_EMBEDDINGS_DIMENSION_COUNT
    ]
    assert dimension_count == 4
    assert isinstance(dimension_count, int)

    duration_metric = _get_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
    )
    assert duration_metric is not None
    for point in duration_metric.data.data_points:
        assert (
            point.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
            == GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value
        )
