# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=too-many-locals

"""Offline tests for the Replicate instrumentation.

These tests never hit the network and never require a real API token: an
``httpx`` mock transport (via ``respx``) returns canned Replicate prediction
responses so the real ``replicate`` SDK parses real prediction objects and the
instrumentation wrapper runs against them.
"""

from __future__ import annotations

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
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)

MODEL_REF = "meta/meta-llama-3-8b-instruct"
PREDICTIONS_URL = (
    f"https://api.replicate.com/v1/models/{MODEL_REF}/predictions"
)
STREAM_URL = "https://stream.replicate.com/v1/streams/abc"
PREDICTION_ID = "pred-0001"
USER_PROMPT = {"prompt": "Say this is a test."}

_REPLICATE_PROVIDER = "replicate"
_TEXT_COMPLETION = (
    GenAIAttributes.GenAiOperationNameValues.TEXT_COMPLETION.value
)


def _succeeded_prediction_body() -> dict:
    return {
        "id": PREDICTION_ID,
        "model": MODEL_REF,
        "version": "v1",
        "status": "succeeded",
        "input": USER_PROMPT,
        "output": ["This ", "is ", "a ", "test."],
        "urls": {
            "get": f"https://api.replicate.com/v1/predictions/{PREDICTION_ID}",
        },
    }


def _streaming_prediction_body() -> dict:
    return {
        "id": PREDICTION_ID,
        "model": MODEL_REF,
        "version": "v1",
        "status": "processing",
        "input": USER_PROMPT,
        "output": None,
        "urls": {
            "get": f"https://api.replicate.com/v1/predictions/{PREDICTION_ID}",
            "stream": STREAM_URL,
        },
    }


def _sse_body() -> str:
    # Replicate's SSE decoder requires an ``id:`` field per event.
    return (
        "event: output\nid: 1\ndata: This \n\n"
        "event: output\nid: 2\ndata: is \n\n"
        "event: output\nid: 3\ndata: a \n\n"
        "event: output\nid: 4\ndata: test.\n\n"
        "event: done\nid: 5\ndata: {}\n\n"
    )


def _failed_prediction_body() -> dict:
    return {
        "id": PREDICTION_ID,
        "model": MODEL_REF,
        "version": "v1",
        "status": "failed",
        "input": USER_PROMPT,
        "output": None,
        "error": "boom",
        "urls": {
            "get": f"https://api.replicate.com/v1/predictions/{PREDICTION_ID}",
        },
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


def _assert_common_success_attributes(span):
    attributes = span.attributes

    assert span.name == f"{_TEXT_COMPLETION} {MODEL_REF}"

    assert (
        attributes[GenAIAttributes.GEN_AI_OPERATION_NAME] == _TEXT_COMPLETION
    )
    assert isinstance(attributes[GenAIAttributes.GEN_AI_OPERATION_NAME], str)

    assert (
        attributes[GenAIAttributes.GEN_AI_PROVIDER_NAME] == _REPLICATE_PROVIDER
    )
    assert isinstance(attributes[GenAIAttributes.GEN_AI_PROVIDER_NAME], str)

    assert attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == MODEL_REF
    assert isinstance(attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL], str)

    finish_reasons = attributes[GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS]
    assert isinstance(finish_reasons, (tuple, list))
    assert list(finish_reasons) == ["stop"]

    # Replicate does not report token usage, so token attributes must be absent.
    assert GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS not in attributes
    assert GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS not in attributes


def _assert_duration_metric_recorded(metric_reader):
    duration_metric = _find_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
    )
    assert duration_metric is not None
    duration_point = duration_metric.data.data_points[0]
    assert duration_point.sum >= 0
    assert (
        duration_point.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == _TEXT_COMPLETION
    )
    assert (
        duration_point.attributes[GenAIAttributes.GEN_AI_PROVIDER_NAME]
        == _REPLICATE_PROVIDER
    )

    # Replicate does not report token usage, so no token metric is emitted.
    token_metric = _find_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE
    )
    assert token_metric is None


@respx.mock
def test_run_non_streaming(
    span_exporter, metric_reader, replicate_client, instrument_with_content
):
    respx.post(PREDICTIONS_URL).mock(
        return_value=httpx.Response(201, json=_succeeded_prediction_body())
    )

    output = replicate_client.run(MODEL_REF, input=USER_PROMPT)

    assert "".join(str(item) for item in output) == "This is a test."

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    _assert_common_success_attributes(span)

    if ServerAttributes.SERVER_ADDRESS in span.attributes:
        assert (
            span.attributes[ServerAttributes.SERVER_ADDRESS]
            == "api.replicate.com"
        )
        assert isinstance(
            span.attributes[ServerAttributes.SERVER_ADDRESS], str
        )

    _assert_duration_metric_recorded(metric_reader)


@respx.mock
def test_module_level_run_non_streaming(
    span_exporter, metric_reader, instrument_with_content
):
    """The module-level ``replicate.run`` helper is instrumented too.

    ``replicate.run`` is a bound method of the default client captured at import
    time, so it is a distinct wrap point from ``Client.run``.
    """
    import replicate

    respx.post(PREDICTIONS_URL).mock(
        return_value=httpx.Response(201, json=_succeeded_prediction_body())
    )

    output = replicate.run(MODEL_REF, input=USER_PROMPT)

    assert "".join(str(item) for item in output) == "This is a test."

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    _assert_common_success_attributes(spans[0])
    _assert_duration_metric_recorded(metric_reader)


@pytest.mark.asyncio
@respx.mock
async def test_async_run_non_streaming(
    span_exporter, metric_reader, replicate_client, instrument_with_content
):
    respx.post(PREDICTIONS_URL).mock(
        return_value=httpx.Response(201, json=_succeeded_prediction_body())
    )

    output = await replicate_client.async_run(MODEL_REF, input=USER_PROMPT)

    assert "".join(str(item) for item in output) == "This is a test."

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    _assert_common_success_attributes(spans[0])
    _assert_duration_metric_recorded(metric_reader)


@respx.mock
def test_stream(
    span_exporter, metric_reader, replicate_client, instrument_with_content
):
    respx.post(PREDICTIONS_URL).mock(
        return_value=httpx.Response(201, json=_streaming_prediction_body())
    )
    respx.get(STREAM_URL).mock(
        return_value=httpx.Response(
            200,
            text=_sse_body(),
            headers={"content-type": "text/event-stream"},
        )
    )

    collected = "".join(
        str(event)
        for event in replicate_client.stream(MODEL_REF, input=USER_PROMPT)
    )
    assert collected == "This is a test."

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.name == f"{_TEXT_COMPLETION} {MODEL_REF}"
    assert (
        span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == _TEXT_COMPLETION
    )
    assert (
        span.attributes[GenAIAttributes.GEN_AI_PROVIDER_NAME]
        == _REPLICATE_PROVIDER
    )
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == MODEL_REF

    finish_reasons = span.attributes[
        GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS
    ]
    assert isinstance(finish_reasons, (tuple, list))
    assert list(finish_reasons) == ["stop"]

    assert GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS not in span.attributes
    assert GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS not in span.attributes

    _assert_duration_metric_recorded(metric_reader)


@pytest.mark.asyncio
@respx.mock
async def test_async_stream(
    span_exporter, metric_reader, replicate_client, instrument_with_content
):
    respx.post(PREDICTIONS_URL).mock(
        return_value=httpx.Response(201, json=_streaming_prediction_body())
    )
    respx.get(STREAM_URL).mock(
        return_value=httpx.Response(
            200,
            text=_sse_body(),
            headers={"content-type": "text/event-stream"},
        )
    )

    collected = ""
    async for event in await replicate_client.async_stream(
        MODEL_REF, input=USER_PROMPT
    ):
        collected += str(event)
    assert collected == "This is a test."

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == f"{_TEXT_COMPLETION} {MODEL_REF}"
    assert (
        span.attributes[GenAIAttributes.GEN_AI_PROVIDER_NAME]
        == _REPLICATE_PROVIDER
    )
    finish_reasons = span.attributes[
        GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS
    ]
    assert list(finish_reasons) == ["stop"]

    _assert_duration_metric_recorded(metric_reader)


@respx.mock
def test_run_error_is_reraised(
    span_exporter, metric_reader, replicate_client, instrument_no_content
):
    from replicate.exceptions import ModelError

    respx.post(PREDICTIONS_URL).mock(
        return_value=httpx.Response(201, json=_failed_prediction_body())
    )

    with pytest.raises(ModelError):
        replicate_client.run(MODEL_REF, input=USER_PROMPT)

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    error_type = span.attributes[ErrorAttributes.ERROR_TYPE]
    assert error_type == "ModelError"
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
        == "ModelError"
    )


@respx.mock
def test_run_connection_error_propagates(
    span_exporter, replicate_client, instrument_no_content
):
    """A transport failure raised inside the SDK call must propagate unmodified.

    The instrumentation must record ``error.type`` and re-raise the original
    exception without wrapping or swallowing it.
    """
    respx.post(PREDICTIONS_URL).mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    with pytest.raises(httpx.ConnectError):
        replicate_client.run(MODEL_REF, input=USER_PROMPT)

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    error_type = spans[0].attributes[ErrorAttributes.ERROR_TYPE]
    assert error_type == "ConnectError"
    assert isinstance(error_type, str)
