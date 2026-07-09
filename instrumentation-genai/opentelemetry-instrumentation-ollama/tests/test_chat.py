# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json

import pytest
from ollama import AsyncClient, Client, ResponseError

from opentelemetry.sdk.metrics.export import Histogram
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics
from opentelemetry.semconv.attributes import (
    error_attributes,
    server_attributes,
)
from opentelemetry.trace import SpanKind

from .conftest import json_body, ndjson_body

_MODEL = "llama3.2"
_MESSAGES = [{"role": "user", "content": "Tell me a joke about OpenTelemetry"}]

_CHAT_RESPONSE = {
    "model": _MODEL,
    "created_at": "2024-01-01T00:00:00Z",
    "message": {"role": "assistant", "content": "Why did the span cross the trace?"},
    "done": True,
    "done_reason": "stop",
    "total_duration": 5000000,
    "prompt_eval_count": 17,
    "eval_count": 24,
}

_CHAT_STREAM_CHUNKS = [
    {
        "model": _MODEL,
        "created_at": "2024-01-01T00:00:00Z",
        "message": {"role": "assistant", "content": "Why did "},
        "done": False,
    },
    {
        "model": _MODEL,
        "created_at": "2024-01-01T00:00:01Z",
        "message": {"role": "assistant", "content": "the span cross?"},
        "done": False,
    },
    {
        "model": _MODEL,
        "created_at": "2024-01-01T00:00:02Z",
        "message": {"role": "assistant", "content": ""},
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": 17,
        "eval_count": 24,
    },
]


def _chat_responder(_request):
    return 200, json_body(_CHAT_RESPONSE)


def _chat_stream_responder(_request):
    return 200, ndjson_body(_CHAT_STREAM_CHUNKS)


def _error_responder(_request):
    return 404, json_body({"error": "model 'llama3.2' not found"})


def _get_span(span_exporter):
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    return spans[0]


def test_chat_non_streaming(
    instrument_with_content, span_exporter, metric_reader, mock_ollama
):
    mock_ollama(_chat_responder)

    response = Client().chat(model=_MODEL, messages=_MESSAGES)

    assert response["message"]["content"] == "Why did the span cross the trace?"

    span = _get_span(span_exporter)
    assert span.name == f"chat {_MODEL}"
    assert span.kind == SpanKind.CLIENT

    attrs = span.attributes
    # Exact attribute names and value types.
    assert attrs[GenAI.GEN_AI_OPERATION_NAME] == "chat"
    assert isinstance(attrs[GenAI.GEN_AI_OPERATION_NAME], str)
    assert attrs[GenAI.GEN_AI_PROVIDER_NAME] == "ollama"
    assert attrs[GenAI.GEN_AI_REQUEST_MODEL] == _MODEL
    assert attrs[GenAI.GEN_AI_RESPONSE_MODEL] == _MODEL
    assert attrs[GenAI.GEN_AI_USAGE_INPUT_TOKENS] == 17
    assert isinstance(attrs[GenAI.GEN_AI_USAGE_INPUT_TOKENS], int)
    assert attrs[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] == 24
    assert isinstance(attrs[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS], int)
    finish_reasons = attrs[GenAI.GEN_AI_RESPONSE_FINISH_REASONS]
    assert tuple(finish_reasons) == ("stop",)
    assert all(isinstance(reason, str) for reason in finish_reasons)
    # Default local ollama server address is recorded, default port dropped.
    assert attrs[server_attributes.SERVER_ADDRESS] == "127.0.0.1"
    assert server_attributes.SERVER_PORT not in attrs

    # Content captured on the span (span_and_event mode).
    input_messages = json.loads(attrs[GenAI.GEN_AI_INPUT_MESSAGES])
    assert input_messages[0]["role"] == "user"
    assert input_messages[0]["parts"][0]["content"] == _MESSAGES[0]["content"]
    output_messages = json.loads(attrs[GenAI.GEN_AI_OUTPUT_MESSAGES])
    assert (
        output_messages[0]["parts"][0]["content"]
        == "Why did the span cross the trace?"
    )

    # Metrics: duration + token usage.
    _assert_metrics(metric_reader, expect_tokens=True)


def test_chat_positional_model_and_messages(
    instrument_with_content, span_exporter, mock_ollama
):
    # ollama accepts model + messages positionally; the request model and
    # captured input must not depend on them being passed as keywords.
    mock_ollama(_chat_responder)

    Client().chat(_MODEL, _MESSAGES)

    span = _get_span(span_exporter)
    assert span.name == f"chat {_MODEL}"
    attrs = span.attributes
    assert attrs[GenAI.GEN_AI_REQUEST_MODEL] == _MODEL
    assert isinstance(attrs[GenAI.GEN_AI_REQUEST_MODEL], str)
    input_messages = json.loads(attrs[GenAI.GEN_AI_INPUT_MESSAGES])
    assert input_messages[0]["parts"][0]["content"] == _MESSAGES[0]["content"]


def test_chat_streaming(
    instrument_with_content, span_exporter, metric_reader, mock_ollama
):
    mock_ollama(_chat_stream_responder)

    stream = Client().chat(model=_MODEL, messages=_MESSAGES, stream=True)
    collected = "".join(chunk["message"]["content"] for chunk in stream)
    assert collected == "Why did the span cross?"

    span = _get_span(span_exporter)
    assert span.name == f"chat {_MODEL}"
    attrs = span.attributes
    assert attrs[GenAI.GEN_AI_OPERATION_NAME] == "chat"
    assert attrs[GenAI.GEN_AI_REQUEST_MODEL] == _MODEL
    assert attrs[GenAI.GEN_AI_RESPONSE_MODEL] == _MODEL
    assert attrs[GenAI.GEN_AI_USAGE_INPUT_TOKENS] == 17
    assert attrs[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] == 24
    assert tuple(attrs[GenAI.GEN_AI_RESPONSE_FINISH_REASONS]) == ("stop",)

    output_messages = json.loads(attrs[GenAI.GEN_AI_OUTPUT_MESSAGES])
    assert (
        output_messages[0]["parts"][0]["content"]
        == "Why did the span cross?"
    )

    _assert_metrics(metric_reader, expect_tokens=True)


def test_chat_error(
    instrument_with_content, span_exporter, metric_reader, mock_ollama
):
    mock_ollama(_error_responder)

    with pytest.raises(ResponseError):
        Client().chat(model=_MODEL, messages=_MESSAGES)

    span = _get_span(span_exporter)
    attrs = span.attributes
    assert attrs[GenAI.GEN_AI_OPERATION_NAME] == "chat"
    assert attrs[GenAI.GEN_AI_REQUEST_MODEL] == _MODEL
    assert error_attributes.ERROR_TYPE in attrs
    assert attrs[error_attributes.ERROR_TYPE] == "ResponseError"
    assert span.status.status_code.name == "ERROR"

    # Duration metric recorded with error.type; no token metrics.
    _assert_metrics(metric_reader, expect_tokens=False, expect_error=True)


@pytest.mark.asyncio
async def test_async_chat_non_streaming(
    instrument_with_content, span_exporter, metric_reader, mock_ollama
):
    mock_ollama(_chat_responder)

    response = await AsyncClient().chat(model=_MODEL, messages=_MESSAGES)
    assert response["message"]["content"] == "Why did the span cross the trace?"

    span = _get_span(span_exporter)
    attrs = span.attributes
    assert attrs[GenAI.GEN_AI_OPERATION_NAME] == "chat"
    assert attrs[GenAI.GEN_AI_REQUEST_MODEL] == _MODEL
    assert attrs[GenAI.GEN_AI_USAGE_INPUT_TOKENS] == 17
    assert attrs[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] == 24


@pytest.mark.asyncio
async def test_async_chat_streaming(
    instrument_with_content, span_exporter, metric_reader, mock_ollama
):
    mock_ollama(_chat_stream_responder)

    stream = await AsyncClient().chat(
        model=_MODEL, messages=_MESSAGES, stream=True
    )
    collected = ""
    async for chunk in stream:
        collected += chunk["message"]["content"]
    assert collected == "Why did the span cross?"

    span = _get_span(span_exporter)
    attrs = span.attributes
    assert attrs[GenAI.GEN_AI_OPERATION_NAME] == "chat"
    assert attrs[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] == 24
    assert tuple(attrs[GenAI.GEN_AI_RESPONSE_FINISH_REASONS]) == ("stop",)


def test_chat_no_content(
    instrument_no_content, span_exporter, mock_ollama
):
    mock_ollama(_chat_responder)

    Client().chat(model=_MODEL, messages=_MESSAGES)

    span = _get_span(span_exporter)
    attrs = span.attributes
    # No content capture without the content-mode env var.
    assert GenAI.GEN_AI_INPUT_MESSAGES not in attrs
    assert GenAI.GEN_AI_OUTPUT_MESSAGES not in attrs
    # But token/model attributes still present.
    assert attrs[GenAI.GEN_AI_USAGE_INPUT_TOKENS] == 17
    assert attrs[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] == 24


def _collect_metrics(metric_reader):
    data = metric_reader.get_metrics_data()
    metrics = {}
    for resource_metric in data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                metrics[metric.name] = metric
    return metrics


def _assert_metrics(metric_reader, *, expect_tokens, expect_error=False):
    metrics = _collect_metrics(metric_reader)
    duration = metrics[gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION]
    assert isinstance(duration.data, Histogram)
    point = list(duration.data.data_points)[0]
    assert point.attributes[GenAI.GEN_AI_OPERATION_NAME] == "chat"
    assert point.attributes[GenAI.GEN_AI_REQUEST_MODEL] == _MODEL
    assert point.sum >= 0
    if expect_error:
        assert point.attributes[error_attributes.ERROR_TYPE] == "ResponseError"

    if expect_tokens:
        token_metric = metrics[gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE]
        token_types = {
            p.attributes[GenAI.GEN_AI_TOKEN_TYPE]
            for p in token_metric.data.data_points
        }
        assert token_types == {"input", "output"}
    else:
        assert gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE not in metrics
