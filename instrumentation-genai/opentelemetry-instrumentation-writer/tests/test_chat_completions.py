# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=too-many-locals

"""Offline tests for the Writer AI instrumentation.

These tests never touch the network and never require a real API key. They use
``respx`` to mock the httpx transport that the ``writerai`` SDK uses, returning
canned Writer JSON. The real ``writerai`` SDK parses that JSON into real
response objects, so the instrumentation wrapper runs end-to-end against real
SDK types.

The tests exercise the latest-experimental semantic-convention path
(``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental``), which is what
the ``instrument`` fixtures enable.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from writerai import APIConnectionError, Writer

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

BASE_URL = "https://api.writer.com"
CHAT_URL = f"{BASE_URL}/v1/chat"
COMPLETIONS_URL = f"{BASE_URL}/v1/completions"

LLM_MODEL = "palmyra-x-004"
RESPONSE_MODEL = "palmyra-x-004"
RESPONSE_ID = "chatcmpl-writer-0001"
USER_PROMPT = [{"role": "user", "content": "Say this is a test."}]

_WRITER_PROVIDER = "writer"
GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"


def _chat_body() -> dict:
    return {
        "id": RESPONSE_ID,
        "object": "chat.completion",
        "created": 1731368630,
        "model": RESPONSE_MODEL,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "This is a test.",
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


def _completion_body() -> dict:
    # The Writer text-completion endpoint returns only ``model`` and
    # ``choices[].text`` -- no ``id`` or ``usage``.
    return {
        "model": RESPONSE_MODEL,
        "choices": [{"text": "This is a test.", "log_probs": None}],
    }


def _completion_stream_body() -> str:
    # The Writer text-completion stream yields ``CompletionChunk`` objects that
    # carry only a ``value`` field -- no ``choices``, ``model`` or ``usage``.
    chunks = [
        {"value": "This is "},
        {"value": "a test."},
    ]
    return _sse(chunks)


def _sse(chunks: list[dict]) -> str:
    lines = [f"data: {json.dumps(chunk)}\n\n" for chunk in chunks]
    lines.append("data: [DONE]\n\n")
    return "".join(lines)


def _chat_stream_body() -> str:
    chunks = [
        {
            "id": RESPONSE_ID,
            "object": "chat.completion.chunk",
            "created": 1731368639,
            "model": RESPONSE_MODEL,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": ""},
                    "finish_reason": None,
                }
            ],
        },
        {
            "id": RESPONSE_ID,
            "object": "chat.completion.chunk",
            "created": 1731368639,
            "model": RESPONSE_MODEL,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": "This is a test."},
                    "finish_reason": None,
                }
            ],
        },
        {
            "id": RESPONSE_ID,
            "object": "chat.completion.chunk",
            "created": 1731368639,
            "model": RESPONSE_MODEL,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
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
    return _sse(chunks)


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


def _get_span(span_exporter):
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    return spans[0]


def _assert_common_chat_attributes(span):
    attributes = span.attributes

    assert span.name == f"chat {LLM_MODEL}"

    assert (
        attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    assert isinstance(attributes[GenAIAttributes.GEN_AI_OPERATION_NAME], str)

    # No GenAiProviderNameValues member exists for Writer, so the raw literal
    # "writer" is used for gen_ai.provider.name on the experimental path.
    assert attributes[GEN_AI_PROVIDER_NAME] == _WRITER_PROVIDER
    assert isinstance(attributes[GEN_AI_PROVIDER_NAME], str)

    assert attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == LLM_MODEL
    assert isinstance(attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL], str)


def _assert_chat_response_attributes(span):
    attributes = span.attributes

    assert attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL] == RESPONSE_MODEL
    assert isinstance(attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL], str)

    assert attributes[GenAIAttributes.GEN_AI_RESPONSE_ID] == RESPONSE_ID
    assert isinstance(attributes[GenAIAttributes.GEN_AI_RESPONSE_ID], str)

    finish_reasons = attributes[GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS]
    assert isinstance(finish_reasons, (tuple, list))
    assert list(finish_reasons) == ["stop"]

    input_tokens = attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
    output_tokens = attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
    assert isinstance(input_tokens, int)
    assert isinstance(output_tokens, int)
    assert input_tokens == 12
    assert output_tokens == 5


def _assert_token_and_duration_metrics(metric_reader):
    token_metric = _find_metric(
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
        assert isinstance(point.sum, int)
        assert point.attributes[GEN_AI_PROVIDER_NAME] == _WRITER_PROVIDER
        assert (
            point.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == LLM_MODEL
        )

    duration_metric = _find_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
    )
    assert duration_metric is not None
    duration_points = list(duration_metric.data.data_points)
    assert len(duration_points) == 1
    assert duration_points[0].sum >= 0
    assert (
        duration_points[0].attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )


@respx.mock
def test_chat_non_streaming(
    span_exporter, metric_reader, writer_client, instrument
):
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_chat_body())
    )

    response = writer_client.chat.chat(
        model=LLM_MODEL,
        messages=USER_PROMPT,
        stream=False,
    )

    assert response.id == RESPONSE_ID
    assert response.model == RESPONSE_MODEL

    span = _get_span(span_exporter)
    _assert_common_chat_attributes(span)
    _assert_chat_response_attributes(span)

    if ServerAttributes.SERVER_ADDRESS in span.attributes:
        assert (
            span.attributes[ServerAttributes.SERVER_ADDRESS]
            == "api.writer.com"
        )
        assert isinstance(
            span.attributes[ServerAttributes.SERVER_ADDRESS], str
        )

    _assert_token_and_duration_metrics(metric_reader)


@pytest.mark.asyncio
@respx.mock
async def test_chat_non_streaming_async(
    span_exporter, metric_reader, async_writer_client, instrument
):
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_chat_body())
    )

    response = await async_writer_client.chat.chat(
        model=LLM_MODEL,
        messages=USER_PROMPT,
        stream=False,
    )

    assert response.id == RESPONSE_ID

    span = _get_span(span_exporter)
    _assert_common_chat_attributes(span)
    _assert_chat_response_attributes(span)
    _assert_token_and_duration_metrics(metric_reader)


@respx.mock
def test_chat_with_content(
    span_exporter, writer_client, instrument_with_content
):
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_chat_body())
    )

    writer_client.chat.chat(
        model=LLM_MODEL,
        messages=USER_PROMPT,
    )

    span = _get_span(span_exporter)
    _assert_common_chat_attributes(span)

    input_messages = json.loads(
        span.attributes[GenAIAttributes.GEN_AI_INPUT_MESSAGES]
    )
    assert input_messages[0]["role"] == "user"
    assert input_messages[0]["parts"][0]["content"] == "Say this is a test."

    output_messages = json.loads(
        span.attributes[GenAIAttributes.GEN_AI_OUTPUT_MESSAGES]
    )
    assert output_messages[0]["role"] == "assistant"
    assert output_messages[0]["finish_reason"] == "stop"
    assert output_messages[0]["parts"][0]["content"] == "This is a test."


@respx.mock
def test_chat_streaming(
    span_exporter, metric_reader, writer_client, instrument
):
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            text=_chat_stream_body(),
            headers={"content-type": "text/event-stream"},
        )
    )

    stream = writer_client.chat.chat(
        model=LLM_MODEL,
        messages=USER_PROMPT,
        stream=True,
    )

    collected = "".join(
        chunk.choices[0].delta.content or ""
        for chunk in stream
        if chunk.choices
    )
    assert collected == "This is a test."

    span = _get_span(span_exporter)
    _assert_common_chat_attributes(span)

    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID] == RESPONSE_ID
    assert (
        span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL]
        == RESPONSE_MODEL
    )

    finish_reasons = span.attributes[
        GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS
    ]
    assert isinstance(finish_reasons, (tuple, list))
    assert list(finish_reasons) == ["stop"]

    input_tokens = span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
    output_tokens = span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
    assert isinstance(input_tokens, int)
    assert isinstance(output_tokens, int)
    assert input_tokens == 12
    assert output_tokens == 5

    _assert_token_and_duration_metrics(metric_reader)


@pytest.mark.asyncio
@respx.mock
async def test_chat_streaming_async(
    span_exporter, metric_reader, async_writer_client, instrument
):
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            text=_chat_stream_body(),
            headers={"content-type": "text/event-stream"},
        )
    )

    stream = await async_writer_client.chat.chat(
        model=LLM_MODEL,
        messages=USER_PROMPT,
        stream=True,
    )

    collected = ""
    async for chunk in stream:
        if chunk.choices:
            collected += chunk.choices[0].delta.content or ""
    assert collected == "This is a test."

    span = _get_span(span_exporter)
    _assert_common_chat_attributes(span)
    assert (
        span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL]
        == RESPONSE_MODEL
    )
    assert span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS] == 12
    assert span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS] == 5

    finish_reasons = span.attributes[
        GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS
    ]
    assert list(finish_reasons) == ["stop"]

    _assert_token_and_duration_metrics(metric_reader)


@respx.mock
def test_completions_create(
    span_exporter, metric_reader, writer_client, instrument
):
    respx.post(COMPLETIONS_URL).mock(
        return_value=httpx.Response(200, json=_completion_body())
    )

    response = writer_client.completions.create(
        model=LLM_MODEL,
        prompt="Say this is a test.",
    )

    assert response.model == RESPONSE_MODEL
    assert response.choices[0].text == "This is a test."

    span = _get_span(span_exporter)
    assert span.name == f"text_completion {LLM_MODEL}"
    assert (
        span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.TEXT_COMPLETION.value
    )
    assert span.attributes[GEN_AI_PROVIDER_NAME] == _WRITER_PROVIDER
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == LLM_MODEL
    assert (
        span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL]
        == RESPONSE_MODEL
    )

    # The text-completion endpoint returns no usage, so the token metric is not
    # emitted, but the operation-duration metric always is.
    duration_metric = _find_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
    )
    assert duration_metric is not None


@respx.mock
def test_completions_create_streaming(
    span_exporter, writer_client, instrument_with_content
):
    respx.post(COMPLETIONS_URL).mock(
        return_value=httpx.Response(
            200,
            text=_completion_stream_body(),
            headers={"content-type": "text/event-stream"},
        )
    )

    stream = writer_client.completions.create(
        model=LLM_MODEL,
        prompt="Say this is a test.",
        stream=True,
    )
    collected = "".join(chunk.value for chunk in stream)
    assert collected == "This is a test."

    # The streamed text must still be captured on the span even though
    # ``CompletionChunk`` has no ``choices`` (regression: it was previously
    # routed through the chat stream wrapper and dropped entirely).
    span = _get_span(span_exporter)
    output_messages = json.loads(
        span.attributes[GenAIAttributes.GEN_AI_OUTPUT_MESSAGES]
    )
    assert output_messages[0]["role"] == "assistant"
    assert output_messages[0]["finish_reason"] == "stop"
    assert output_messages[0]["parts"][0]["content"] == "This is a test."


@respx.mock
def test_chat_error_is_reraised(span_exporter, metric_reader, instrument):
    # Disable client retries so a single mocked 5xx response deterministically
    # surfaces as an error without retry backoff.
    client = Writer(max_retries=0)

    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            500,
            json={"error": {"message": "boom", "type": "server_error"}},
        )
    )

    with pytest.raises(Exception) as exc_info:
        client.chat.chat(
            model=LLM_MODEL,
            messages=USER_PROMPT,
            stream=False,
        )

    span = _get_span(span_exporter)
    _assert_common_chat_attributes(span)

    error_type = span.attributes[ErrorAttributes.ERROR_TYPE]
    assert isinstance(error_type, str)
    assert error_type == type(exc_info.value).__qualname__

    duration_metric = _find_metric(
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


@respx.mock
def test_chat_connection_error_propagates(span_exporter, instrument):
    """A transport failure raised inside the SDK call must propagate unmodified.

    The instrumentation records ``error.type`` and re-raises the original
    exception without wrapping or swallowing it.
    """
    client = Writer(max_retries=0)

    respx.post(CHAT_URL).mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    with pytest.raises(APIConnectionError):
        client.chat.chat(
            model=LLM_MODEL,
            messages=USER_PROMPT,
            stream=False,
        )

    span = _get_span(span_exporter)
    error_type = span.attributes[ErrorAttributes.ERROR_TYPE]
    assert error_type == "APIConnectionError"
    assert isinstance(error_type, str)
