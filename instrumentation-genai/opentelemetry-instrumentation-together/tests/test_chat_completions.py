# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Offline tests for the Together AI chat completion instrumentation.

These tests never touch the network. They use ``respx`` to mock the httpx
transport that the ``together`` SDK uses, returning canned Together
chat-completion JSON. The real ``together`` SDK parses that JSON into real
response objects, so the instrumentation wrapper runs end-to-end against
real SDK types.

The tests exercise the latest-experimental semantic-convention path
(``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental``), which is what
the ``instrument`` fixtures enable.
"""

import json

import httpx
import pytest
import respx
from together import Together

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

TEST_MODEL = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
TEST_RESPONSE_MODEL = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
CHAT_COMPLETIONS_URL = "https://api.together.ai/v1/chat/completions"
GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"

USER_PROMPT = [{"role": "user", "content": "Say this is a test"}]


def _chat_completion_body():
    return {
        "id": "chatcmpl-test-123",
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


def _sse_stream_bytes(chunks):
    lines = []
    for chunk in chunks:
        lines.append(f"data: {json.dumps(chunk)}\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode("utf-8")


def _stream_chunks():
    base = {
        "id": "chatcmpl-test-stream-123",
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


def _assert_common_request_attributes(span):
    assert span.name == f"chat {TEST_MODEL}"
    assert (
        span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    assert isinstance(
        span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME], str
    )
    # experimental path uses gen_ai.provider.name (not gen_ai.system)
    assert span.attributes[GEN_AI_PROVIDER_NAME] == "together"
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == TEST_MODEL
    assert isinstance(
        span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL], str
    )
    assert (
        span.attributes[ServerAttributes.SERVER_ADDRESS] == "api.together.ai"
    )


def _get_metric(metric_reader, name):
    metrics_data = metric_reader.get_metrics_data()
    for resource_metric in metrics_data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                if metric.name == name:
                    return metric
    return None


@respx.mock
def test_chat_completion_non_streaming(
    span_exporter, metric_reader, instrument
):
    respx.post(CHAT_COMPLETIONS_URL).mock(
        return_value=httpx.Response(200, json=_chat_completion_body())
    )

    client = Together(api_key="test_together_api_key")
    response = client.chat.completions.create(
        model=TEST_MODEL,
        messages=USER_PROMPT,
        stream=False,
    )

    span = _get_span(span_exporter)
    _assert_common_request_attributes(span)

    # response attributes with exact value types
    assert (
        span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL]
        == TEST_RESPONSE_MODEL
    )
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID] == response.id
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID] == (
        "chatcmpl-test-123"
    )
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

    # metrics: token usage + operation duration recorded
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
        assert (
            point.attributes[GEN_AI_PROVIDER_NAME] == "together"
        )
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
def test_chat_completion_with_content(
    span_exporter, instrument_with_content
):
    respx.post(CHAT_COMPLETIONS_URL).mock(
        return_value=httpx.Response(200, json=_chat_completion_body())
    )

    client = Together(api_key="test_together_api_key")
    client.chat.completions.create(
        model=TEST_MODEL,
        messages=USER_PROMPT,
        stream=False,
    )

    span = _get_span(span_exporter)
    _assert_common_request_attributes(span)

    # content capture writes messages as JSON strings on the span
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
def test_chat_completion_streaming(span_exporter, metric_reader, instrument):
    respx.post(CHAT_COMPLETIONS_URL).mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse_stream_bytes(_stream_chunks()),
        )
    )

    client = Together(api_key="test_together_api_key")
    stream = client.chat.completions.create(
        model=TEST_MODEL,
        messages=USER_PROMPT,
        stream=True,
    )

    collected = "".join(
        chunk.choices[0].delta.content or ""
        for chunk in stream
        if chunk.choices
    )
    assert collected == "This is a test"

    span = _get_span(span_exporter)
    _assert_common_request_attributes(span)

    assert (
        span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL]
        == TEST_RESPONSE_MODEL
    )
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID] == (
        "chatcmpl-test-stream-123"
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

    token_metric = _get_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE
    )
    assert token_metric is not None
    duration_metric = _get_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
    )
    assert duration_metric is not None


@respx.mock
def test_chat_completion_error(span_exporter, metric_reader, instrument):
    respx.post(CHAT_COMPLETIONS_URL).mock(
        return_value=httpx.Response(
            500,
            json={"error": {"message": "internal error", "type": "server"}},
        )
    )

    client = Together(api_key="test_together_api_key")

    with pytest.raises(Exception) as exc_info:
        client.chat.completions.create(
            model=TEST_MODEL,
            messages=USER_PROMPT,
            stream=False,
        )

    span = _get_span(span_exporter)
    _assert_common_request_attributes(span)

    # error.type recorded on span, with the original error re-raised
    error_type = span.attributes[ErrorAttributes.ERROR_TYPE]
    assert isinstance(error_type, str)
    assert error_type == type(exc_info.value).__qualname__

    # error.type also present on the duration metric
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
