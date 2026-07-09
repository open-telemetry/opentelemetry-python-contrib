# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=too-many-locals

"""Offline tests for the Groq chat completions instrumentation.

These tests never hit the network and never require a real API key: an
``httpx`` mock transport (via ``respx``) returns canned Groq responses so the
real ``groq`` SDK parses real response objects and the instrumentation wrapper
runs against them.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics
from opentelemetry.semconv.attributes import error_attributes as ErrorAttributes
from opentelemetry.util.genai.utils import is_experimental_mode

GROQ_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
LLM_MODEL = "llama-3.3-70b-versatile"
RESPONSE_MODEL = "llama-3.3-70b-versatile"
RESPONSE_ID = "chatcmpl-groq-0001"
USER_PROMPT = [{"role": "user", "content": "Say this is a test."}]

_GROQ_PROVIDER = "groq"


def _non_streaming_body() -> dict:
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
                "logprobs": None,
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 5,
            "total_tokens": 17,
        },
        "system_fingerprint": "fp_groq_test",
    }


def _streaming_body() -> str:
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
            "x_groq": {
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 5,
                    "total_tokens": 17,
                }
            },
        },
    ]
    lines = [f"data: {json.dumps(chunk)}\n\n" for chunk in chunks]
    lines.append("data: [DONE]\n\n")
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


def _provider_attr_name(latest_experimental_enabled: bool) -> str:
    if latest_experimental_enabled:
        return GenAIAttributes.GEN_AI_PROVIDER_NAME
    return GenAIAttributes.GEN_AI_SYSTEM


def _assert_common_success_attributes(span, latest_experimental_enabled):
    attributes = span.attributes

    assert span.name == f"chat {LLM_MODEL}"

    assert (
        attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    # Groq identity: gen_ai.system on the legacy path, gen_ai.provider.name on
    # the experimental path. Both carry the well-known value "groq".
    assert (
        attributes[_provider_attr_name(latest_experimental_enabled)]
        == _GROQ_PROVIDER
    )

    assert attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == LLM_MODEL
    assert isinstance(attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL], str)

    assert attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL] == RESPONSE_MODEL
    assert isinstance(attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL], str)

    assert attributes[GenAIAttributes.GEN_AI_RESPONSE_ID] == RESPONSE_ID
    assert isinstance(attributes[GenAIAttributes.GEN_AI_RESPONSE_ID], str)

    finish_reasons = attributes[
        GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS
    ]
    assert isinstance(finish_reasons, (tuple, list))
    assert list(finish_reasons) == ["stop"]

    input_tokens = attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
    output_tokens = attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
    assert isinstance(input_tokens, int)
    assert isinstance(output_tokens, int)
    assert input_tokens == 12
    assert output_tokens == 5


def _assert_metrics_recorded(
    metric_reader, latest_experimental_enabled, *, expect_token_metric=True
):
    duration_metric = _find_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
    )
    assert duration_metric is not None
    duration_point = duration_metric.data.data_points[0]
    assert duration_point.sum >= 0
    assert (
        duration_point.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    assert (
        duration_point.attributes[
            _provider_attr_name(latest_experimental_enabled)
        ]
        == _GROQ_PROVIDER
    )

    token_metric = _find_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE
    )
    if not expect_token_metric:
        # On the legacy semconv path, token-usage metrics are recorded from the
        # raw result in the ``finally`` block. For streaming responses that raw
        # result is an unconsumed ``Stream`` with no ``.usage`` yet, so no token
        # metric is emitted -- matching the OpenAI-v2 reference instrumentation.
        assert token_metric is None
        return
    assert token_metric is not None
    token_types = {
        point.attributes[GenAIAttributes.GEN_AI_TOKEN_TYPE]
        for point in token_metric.data.data_points
    }
    assert GenAIAttributes.GenAiTokenTypeValues.INPUT.value in token_types
    assert GenAIAttributes.GenAiTokenTypeValues.COMPLETION.value in token_types
    for point in token_metric.data.data_points:
        assert isinstance(point.sum, int)


@respx.mock
def test_chat_completion_non_streaming(
    span_exporter, metric_reader, groq_client, instrument_with_content
):
    latest_experimental_enabled = is_experimental_mode()

    respx.post(GROQ_COMPLETIONS_URL).mock(
        return_value=httpx.Response(200, json=_non_streaming_body())
    )

    response = groq_client.chat.completions.create(
        model=LLM_MODEL,
        messages=USER_PROMPT,
        stream=False,
    )

    assert response.id == RESPONSE_ID
    assert response.model == RESPONSE_MODEL

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    _assert_common_success_attributes(span, latest_experimental_enabled)

    # Server address is derived from the Groq client base URL when the SDK
    # exposes it on the resource instance.
    if ServerAttributes.SERVER_ADDRESS in span.attributes:
        assert (
            span.attributes[ServerAttributes.SERVER_ADDRESS] == "api.groq.com"
        )
        assert isinstance(
            span.attributes[ServerAttributes.SERVER_ADDRESS], str
        )

    _assert_metrics_recorded(metric_reader, latest_experimental_enabled)


@pytest.mark.asyncio
@respx.mock
async def test_async_chat_completion_non_streaming(
    span_exporter, metric_reader, async_groq_client, instrument_with_content
):
    latest_experimental_enabled = is_experimental_mode()

    respx.post(GROQ_COMPLETIONS_URL).mock(
        return_value=httpx.Response(200, json=_non_streaming_body())
    )

    response = await async_groq_client.chat.completions.create(
        model=LLM_MODEL,
        messages=USER_PROMPT,
        stream=False,
    )

    assert response.id == RESPONSE_ID

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    _assert_common_success_attributes(spans[0], latest_experimental_enabled)
    _assert_metrics_recorded(metric_reader, latest_experimental_enabled)


@respx.mock
def test_chat_completion_streaming(
    span_exporter, metric_reader, groq_client, instrument_with_content
):
    latest_experimental_enabled = is_experimental_mode()

    respx.post(GROQ_COMPLETIONS_URL).mock(
        return_value=httpx.Response(
            200,
            text=_streaming_body(),
            headers={"content-type": "text/event-stream"},
        )
    )

    stream = groq_client.chat.completions.create(
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

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.name == f"chat {LLM_MODEL}"
    assert (
        span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    assert (
        span.attributes[_provider_attr_name(latest_experimental_enabled)]
        == _GROQ_PROVIDER
    )
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
    output_tokens = span.attributes[
        GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS
    ]
    assert isinstance(input_tokens, int)
    assert isinstance(output_tokens, int)
    assert input_tokens == 12
    assert output_tokens == 5

    _assert_metrics_recorded(
        metric_reader,
        latest_experimental_enabled,
        expect_token_metric=latest_experimental_enabled,
    )


@pytest.mark.asyncio
@respx.mock
async def test_async_chat_completion_streaming(
    span_exporter, metric_reader, async_groq_client, instrument_with_content
):
    latest_experimental_enabled = is_experimental_mode()

    respx.post(GROQ_COMPLETIONS_URL).mock(
        return_value=httpx.Response(
            200,
            text=_streaming_body(),
            headers={"content-type": "text/event-stream"},
        )
    )

    stream = await async_groq_client.chat.completions.create(
        model=LLM_MODEL,
        messages=USER_PROMPT,
        stream=True,
    )

    collected = ""
    async for chunk in stream:
        if chunk.choices:
            collected += chunk.choices[0].delta.content or ""
    assert collected == "This is a test."

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == f"chat {LLM_MODEL}"
    assert (
        span.attributes[_provider_attr_name(latest_experimental_enabled)]
        == _GROQ_PROVIDER
    )
    assert span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS] == 12
    assert span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS] == 5

    _assert_metrics_recorded(
        metric_reader,
        latest_experimental_enabled,
        expect_token_metric=latest_experimental_enabled,
    )


@respx.mock
def test_chat_completion_error_is_reraised(
    span_exporter, metric_reader, instrument_no_content
):
    from groq import Groq, InternalServerError

    # Disable client retries so a single mocked 5xx response deterministically
    # surfaces as an error without retry backoff.
    client = Groq(max_retries=0)

    respx.post(GROQ_COMPLETIONS_URL).mock(
        return_value=httpx.Response(
            500, json={"error": {"message": "boom", "type": "server_error"}}
        )
    )

    with pytest.raises(InternalServerError):
        client.chat.completions.create(
            model=LLM_MODEL,
            messages=USER_PROMPT,
            stream=False,
        )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    error_type = span.attributes[ErrorAttributes.ERROR_TYPE]
    assert error_type == "InternalServerError"
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
        == "InternalServerError"
    )


@respx.mock
def test_chat_completion_connection_error_propagates(
    span_exporter, instrument_no_content
):
    """A transport failure raised inside the SDK call must propagate unmodified.

    The instrumentation must record ``error.type`` and re-raise the original
    exception without wrapping or swallowing it.
    """
    from groq import APIConnectionError, Groq

    # Disable retries so the connection failure surfaces immediately.
    client = Groq(max_retries=0)

    respx.post(GROQ_COMPLETIONS_URL).mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    with pytest.raises(APIConnectionError):
        client.chat.completions.create(
            model=LLM_MODEL,
            messages=USER_PROMPT,
            stream=False,
        )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    error_type = spans[0].attributes[ErrorAttributes.ERROR_TYPE]
    assert error_type == "APIConnectionError"
    assert isinstance(error_type, str)


def test_assistant_message_event_keeps_content_with_tool_calls():
    # An assistant message carrying both text and tool calls must retain its
    # content in the emitted event; the tool calls must not overwrite it.
    from opentelemetry.instrumentation.groq.utils import message_to_event

    message = {
        "role": "assistant",
        "content": "the answer",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "f", "arguments": "{}"},
            }
        ],
    }

    event = message_to_event(message, capture_content=True)

    assert event.body is not None
    assert event.body["content"] == "the answer"
    assert event.body["tool_calls"]
