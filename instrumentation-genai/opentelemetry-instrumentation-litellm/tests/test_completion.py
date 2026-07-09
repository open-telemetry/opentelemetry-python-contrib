# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=too-many-locals

"""Offline tests for the LiteLLM chat/embedding instrumentation.

These tests never hit the network and never require a real API key.

Non-streaming cases use an ``httpx`` mock transport (via ``respx``) that returns
canned OpenAI-style responses, so the real ``litellm`` SDK parses a real
``ModelResponse`` and the instrumentation wrapper runs against it.

Streaming cases use litellm's built-in ``mock_response`` short-circuit: litellm
still produces a real ``CustomStreamWrapper`` yielding real chunk objects, which
the instrumentation wraps and accumulates. (respx cannot intercept litellm's
async streaming transport, so ``mock_response`` is used uniformly for streaming
to keep sync/async coverage symmetric and fully offline.)
"""

from __future__ import annotations

import json

import httpx
import litellm
import pytest
import respx

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)

OPENAI_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"
LLM_MODEL = "gpt-3.5-turbo"
RESPONSE_MODEL = "gpt-3.5-turbo-0125"
RESPONSE_ID = "chatcmpl-litellm-0001"
USER_PROMPT = [{"role": "user", "content": "Say this is a test."}]

_OPENAI_PROVIDER = "openai"


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
        "system_fingerprint": "fp_litellm_test",
    }


def _embedding_body() -> dict:
    return {
        "object": "list",
        "data": [
            {
                "object": "embedding",
                "index": 0,
                "embedding": [0.1, 0.2, 0.3],
            }
        ],
        "model": "text-embedding-3-small",
        "usage": {"prompt_tokens": 4, "total_tokens": 4},
    }


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


def _assert_common_chat_attributes(span):
    attributes = span.attributes

    assert span.name == f"chat {LLM_MODEL}"

    assert (
        attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    assert attributes[GenAIAttributes.GEN_AI_PROVIDER_NAME] == _OPENAI_PROVIDER

    assert attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == LLM_MODEL
    assert isinstance(attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL], str)

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


def _assert_metrics_recorded(metric_reader, *, expect_token_metric=True):
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
        duration_point.attributes[GenAIAttributes.GEN_AI_PROVIDER_NAME]
        == _OPENAI_PROVIDER
    )

    token_metric = _find_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE
    )
    if not expect_token_metric:
        assert token_metric is None
        return
    assert token_metric is not None
    token_types = {
        point.attributes[GenAIAttributes.GEN_AI_TOKEN_TYPE]
        for point in token_metric.data.data_points
    }
    assert GenAIAttributes.GenAiTokenTypeValues.INPUT.value in token_types
    assert GenAIAttributes.GenAiTokenTypeValues.OUTPUT.value in token_types
    for point in token_metric.data.data_points:
        assert isinstance(point.sum, int)


# -- non-streaming chat ------------------------------------------------------


@respx.mock
def test_chat_completion_non_streaming(
    span_exporter, metric_reader, instrument_with_content
):
    respx.post(OPENAI_COMPLETIONS_URL).mock(
        return_value=httpx.Response(200, json=_non_streaming_body())
    )

    response = litellm.completion(
        model=LLM_MODEL,
        messages=USER_PROMPT,
        temperature=0.5,
    )

    assert response.id == RESPONSE_ID
    assert response.model == RESPONSE_MODEL

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    _assert_common_chat_attributes(span)

    # Request parameter captured on the span.
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE] == 0.5
    assert isinstance(
        span.attributes[GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE], float
    )

    # Content captured on the span as gen_ai.input.messages / output.messages.
    input_messages = json.loads(
        span.attributes[GenAIAttributes.GEN_AI_INPUT_MESSAGES]
    )
    assert input_messages[0]["role"] == "user"
    assert input_messages[0]["parts"][0]["content"] == "Say this is a test."

    output_messages = json.loads(
        span.attributes[GenAIAttributes.GEN_AI_OUTPUT_MESSAGES]
    )
    assert output_messages[0]["finish_reason"] == "stop"
    assert output_messages[0]["parts"][0]["content"] == "This is a test."

    _assert_metrics_recorded(metric_reader)


@pytest.mark.asyncio
async def test_async_chat_completion_non_streaming(
    span_exporter, metric_reader, instrument_with_content
):
    # litellm's async OpenAI transport is not interceptable by respx, so the
    # async non-streaming path uses litellm's built-in ``mock_response``
    # short-circuit. litellm still returns a real ``ModelResponse`` that the
    # instrumentation parses; the response id/tokens are litellm-generated.
    response = await litellm.acompletion(
        model=LLM_MODEL,
        messages=USER_PROMPT,
        mock_response="This is a test.",
    )

    assert response.choices[0].message.content == "This is a test."

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.name == f"chat {LLM_MODEL}"
    assert (
        span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    assert (
        span.attributes[GenAIAttributes.GEN_AI_PROVIDER_NAME]
        == _OPENAI_PROVIDER
    )
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == LLM_MODEL
    assert isinstance(
        span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL], str
    )
    assert isinstance(span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID], str)
    finish_reasons = span.attributes[
        GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS
    ]
    assert list(finish_reasons) == ["stop"]
    assert isinstance(
        span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS], int
    )
    assert isinstance(
        span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS], int
    )

    _assert_metrics_recorded(metric_reader)


# -- streaming chat ----------------------------------------------------------


def test_chat_completion_streaming(
    span_exporter, metric_reader, instrument_with_content
):
    stream = litellm.completion(
        model=LLM_MODEL,
        messages=USER_PROMPT,
        stream=True,
        mock_response="This is a test.",
    )

    assert isinstance(stream, litellm.CustomStreamWrapper)
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
        span.attributes[GenAIAttributes.GEN_AI_PROVIDER_NAME]
        == _OPENAI_PROVIDER
    )

    finish_reasons = span.attributes[
        GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS
    ]
    assert isinstance(finish_reasons, (tuple, list))
    assert list(finish_reasons) == ["stop"]

    output_messages = json.loads(
        span.attributes[GenAIAttributes.GEN_AI_OUTPUT_MESSAGES]
    )
    assert output_messages[0]["parts"][0]["content"] == "This is a test."

    # Duration metric is always recorded for streaming.
    duration_metric = _find_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
    )
    assert duration_metric is not None


@pytest.mark.asyncio
async def test_async_chat_completion_streaming(
    span_exporter, metric_reader, instrument_with_content
):
    stream = await litellm.acompletion(
        model=LLM_MODEL,
        messages=USER_PROMPT,
        stream=True,
        mock_response="This is a test.",
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
        span.attributes[GenAIAttributes.GEN_AI_PROVIDER_NAME]
        == _OPENAI_PROVIDER
    )
    finish_reasons = span.attributes[
        GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS
    ]
    assert list(finish_reasons) == ["stop"]


# -- error handling ----------------------------------------------------------


@respx.mock
def test_chat_completion_error_is_reraised(
    span_exporter, metric_reader, instrument_no_content
):
    respx.post(OPENAI_COMPLETIONS_URL).mock(
        return_value=httpx.Response(
            500, json={"error": {"message": "boom", "type": "server_error"}}
        )
    )

    with pytest.raises(litellm.InternalServerError):
        litellm.completion(
            model=LLM_MODEL,
            messages=USER_PROMPT,
            num_retries=0,
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


def test_chat_completion_mock_error_is_reraised(
    span_exporter, instrument_no_content
):
    """A provider error surfaced by litellm must propagate unmodified and the
    span must record ``error.type``."""
    with pytest.raises(litellm.InternalServerError):
        litellm.completion(
            model=LLM_MODEL,
            messages=USER_PROMPT,
            mock_response=Exception("boom"),
        )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    error_type = spans[0].attributes[ErrorAttributes.ERROR_TYPE]
    assert error_type == "InternalServerError"
    assert isinstance(error_type, str)


# -- embeddings --------------------------------------------------------------


@respx.mock
def test_embedding(span_exporter, metric_reader, instrument_no_content):
    respx.post(OPENAI_EMBEDDINGS_URL).mock(
        return_value=httpx.Response(200, json=_embedding_body())
    )

    response = litellm.embedding(
        model="text-embedding-3-small",
        input="hello world",
    )
    assert response.model == "text-embedding-3-small"

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.name == "embeddings text-embedding-3-small"
    assert (
        span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value
    )
    assert (
        span.attributes[GenAIAttributes.GEN_AI_PROVIDER_NAME]
        == _OPENAI_PROVIDER
    )
    assert (
        span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
        == "text-embedding-3-small"
    )
    input_tokens = span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
    assert isinstance(input_tokens, int)
    assert input_tokens == 4

    duration_metric = _find_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
    )
    assert duration_metric is not None
    assert (
        duration_metric.data.data_points[0].attributes[
            GenAIAttributes.GEN_AI_OPERATION_NAME
        ]
        == GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value
    )
