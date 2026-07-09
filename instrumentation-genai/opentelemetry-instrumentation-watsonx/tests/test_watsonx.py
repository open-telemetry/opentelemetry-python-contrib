# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Offline unit tests for the IBM watsonx.ai instrumentation.

The watsonx ``ModelInference`` class cannot be constructed without IBM
credentials and network access, so these tests call the instrumentation
wrappers directly. Each test builds the ``traced_method`` returned by a patch
factory, a fake ``instance`` carrying a ``model_id``, and a fake ``wrapped``
callable returning canned watsonx payloads (or raising), then asserts the
emitted span and metrics.
"""

import json
import types

import pytest
from ibm_watsonx_ai.foundation_models import ModelInference

from opentelemetry.instrumentation.watsonx import WatsonxInstrumentor
from opentelemetry.instrumentation.watsonx.patch import (
    chat,
    generate,
    generate_text_stream,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)

TEST_MODEL = "google/flan-ul2"
TEST_RESPONSE_MODEL = "google/flan-ul2"
CHAT_MODEL = "meta-llama/llama-3-8b-instruct"
GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"
IBM_WATSONX_AI = "ibm.watsonx.ai"


def _instance(model_id):
    return types.SimpleNamespace(model_id=model_id)


def _generate_body():
    return {
        "model_id": TEST_RESPONSE_MODEL,
        "created_at": "2024-01-01T00:00:00.000Z",
        "results": [
            {
                "generated_text": "This is a test",
                "generated_token_count": 5,
                "input_token_count": 12,
                "stop_reason": "eos_token",
            }
        ],
    }


def _chat_body():
    return {
        "id": "chat-test-123",
        "model_id": CHAT_MODEL,
        "created": 1727795200,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "This is a chat test",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 20,
            "completion_tokens": 7,
            "total_tokens": 27,
        },
    }


def _stream_chunks():
    """``generate_text_stream(raw_response=True)`` yields ``generate``-shaped
    dicts; the final chunk carries the stop reason and token counts."""
    return [
        {
            "model_id": TEST_RESPONSE_MODEL,
            "results": [
                {
                    "generated_text": "This ",
                    "generated_token_count": 1,
                    "input_token_count": 12,
                    "stop_reason": "not_finished",
                }
            ],
        },
        {
            "model_id": TEST_RESPONSE_MODEL,
            "results": [
                {
                    "generated_text": "is a test",
                    "generated_token_count": 4,
                    "input_token_count": 0,
                    "stop_reason": "eos_token",
                }
            ],
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


def _assert_token_and_duration_metrics(metric_reader, request_model):
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
        assert point.attributes[GEN_AI_PROVIDER_NAME] == IBM_WATSONX_AI
        assert (
            point.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
            == request_model
        )

    duration_metric = _get_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
    )
    assert duration_metric is not None
    duration_points = list(duration_metric.data.data_points)
    assert len(duration_points) == 1
    assert duration_points[0].sum >= 0


def test_generate_non_streaming(span_exporter, metric_reader, handler):
    traced = generate(handler)
    instance = _instance(TEST_MODEL)

    def wrapped(*args, **kwargs):
        return _generate_body()

    result = traced(
        wrapped,
        instance,
        (),
        {"prompt": "Say this is a test"},
    )
    assert result["results"][0]["generated_text"] == "This is a test"

    span = _get_span(span_exporter)
    assert span.name == f"text_completion {TEST_MODEL}"
    assert (
        span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.TEXT_COMPLETION.value
    )
    assert isinstance(
        span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME], str
    )
    assert span.attributes[GEN_AI_PROVIDER_NAME] == IBM_WATSONX_AI
    assert isinstance(span.attributes[GEN_AI_PROVIDER_NAME], str)
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == TEST_MODEL
    assert isinstance(
        span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL], str
    )
    assert (
        span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL]
        == TEST_RESPONSE_MODEL
    )
    assert isinstance(
        span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL], str
    )

    finish_reasons = span.attributes[
        GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS
    ]
    assert isinstance(finish_reasons, (list, tuple))
    assert list(finish_reasons) == ["eos_token"]

    input_tokens = span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
    output_tokens = span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
    assert input_tokens == 12
    assert output_tokens == 5
    assert isinstance(input_tokens, int)
    assert isinstance(output_tokens, int)

    _assert_token_and_duration_metrics(metric_reader, TEST_MODEL)


def test_generate_with_params(span_exporter, handler):
    traced = generate(handler)
    instance = _instance(TEST_MODEL)

    def wrapped(*args, **kwargs):
        return _generate_body()

    traced(
        wrapped,
        instance,
        (),
        {
            "prompt": "hello",
            "params": {
                "temperature": 0.5,
                "top_p": 0.9,
                "max_new_tokens": 100,
                "random_seed": 42,
                "stop_sequences": ["\n"],
            },
        },
    )

    span = _get_span(span_exporter)
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE] == 0.5
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_TOP_P] == 0.9
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS] == 100
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_SEED] == 42
    stop_sequences = span.attributes[
        GenAIAttributes.GEN_AI_REQUEST_STOP_SEQUENCES
    ]
    assert list(stop_sequences) == ["\n"]


def test_generate_with_content(span_exporter, handler_with_content):
    traced = generate(handler_with_content)
    instance = _instance(TEST_MODEL)

    def wrapped(*args, **kwargs):
        return _generate_body()

    # prompt passed positionally to exercise args handling.
    traced(wrapped, instance, ("Say this is a test",), {})

    span = _get_span(span_exporter)
    input_messages = json.loads(
        span.attributes[GenAIAttributes.GEN_AI_INPUT_MESSAGES]
    )
    assert input_messages[0]["role"] == "user"
    assert input_messages[0]["parts"][0]["content"] == "Say this is a test"

    output_messages = json.loads(
        span.attributes[GenAIAttributes.GEN_AI_OUTPUT_MESSAGES]
    )
    assert output_messages[0]["role"] == "assistant"
    assert output_messages[0]["finish_reason"] == "eos_token"
    assert output_messages[0]["parts"][0]["content"] == "This is a test"


def test_chat_non_streaming(span_exporter, metric_reader, handler):
    traced = chat(handler)
    instance = _instance(CHAT_MODEL)

    def wrapped(*args, **kwargs):
        return _chat_body()

    messages = [{"role": "user", "content": "Say this is a test"}]
    result = traced(wrapped, instance, (), {"messages": messages})
    assert result["choices"][0]["message"]["content"] == "This is a chat test"

    span = _get_span(span_exporter)
    assert span.name == f"chat {CHAT_MODEL}"
    assert (
        span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    assert span.attributes[GEN_AI_PROVIDER_NAME] == IBM_WATSONX_AI
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == CHAT_MODEL
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL] == CHAT_MODEL
    assert (
        span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID] == "chat-test-123"
    )
    assert isinstance(span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID], str)

    finish_reasons = span.attributes[
        GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS
    ]
    assert isinstance(finish_reasons, (list, tuple))
    assert list(finish_reasons) == ["stop"]

    input_tokens = span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
    output_tokens = span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
    assert input_tokens == 20
    assert output_tokens == 7
    assert isinstance(input_tokens, int)
    assert isinstance(output_tokens, int)

    _assert_token_and_duration_metrics(metric_reader, CHAT_MODEL)


def test_chat_with_content(span_exporter, handler_with_content):
    traced = chat(handler_with_content)
    instance = _instance(CHAT_MODEL)

    def wrapped(*args, **kwargs):
        return _chat_body()

    messages = [{"role": "user", "content": "Say this is a test"}]
    traced(wrapped, instance, (), {"messages": messages})

    span = _get_span(span_exporter)
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
    assert output_messages[0]["parts"][0]["content"] == "This is a chat test"


def test_generate_text_stream(span_exporter, metric_reader, handler):
    traced = generate_text_stream(handler)
    instance = _instance(TEST_MODEL)

    def wrapped(*args, **kwargs):
        yield from _stream_chunks()

    stream = traced(
        wrapped,
        instance,
        (),
        {"prompt": "Say this is a test", "raw_response": True},
    )

    collected = "".join(
        chunk["results"][0]["generated_text"] for chunk in stream
    )
    assert collected == "This is a test"

    span = _get_span(span_exporter)
    assert span.name == f"text_completion {TEST_MODEL}"
    assert (
        span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.TEXT_COMPLETION.value
    )
    assert span.attributes[GEN_AI_PROVIDER_NAME] == IBM_WATSONX_AI
    assert (
        span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL]
        == TEST_RESPONSE_MODEL
    )

    finish_reasons = span.attributes[
        GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS
    ]
    assert list(finish_reasons) == ["eos_token"]

    output_tokens = span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
    assert output_tokens == 5
    assert isinstance(output_tokens, int)

    # The prompt token count is reported only on the first chunk (0 on the
    # second); it must not be clobbered back to 0 by the later chunk.
    input_tokens = span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
    assert input_tokens == 12
    assert isinstance(input_tokens, int)

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


def test_generate_text_stream_plain_strings(
    span_exporter, handler_with_content
):
    """Default ``generate_text_stream`` yields plain strings."""
    traced = generate_text_stream(handler_with_content)
    instance = _instance(TEST_MODEL)

    def wrapped(*args, **kwargs):
        yield "This "
        yield "is a test"

    stream = traced(wrapped, instance, (), {"prompt": "hello"})
    collected = "".join(stream)
    assert collected == "This is a test"

    span = _get_span(span_exporter)
    output_messages = json.loads(
        span.attributes[GenAIAttributes.GEN_AI_OUTPUT_MESSAGES]
    )
    assert output_messages[0]["role"] == "assistant"
    assert output_messages[0]["parts"][0]["content"] == "This is a test"


def test_generate_error(span_exporter, metric_reader, handler):
    traced = generate(handler)
    instance = _instance(TEST_MODEL)

    class WatsonxApiError(Exception):
        pass

    error = WatsonxApiError("internal error")

    def wrapped(*args, **kwargs):
        raise error

    with pytest.raises(WatsonxApiError) as exc_info:
        traced(wrapped, instance, (), {"prompt": "Say this is a test"})

    # original exception re-raised unmodified
    assert exc_info.value is error

    span = _get_span(span_exporter)
    assert span.attributes[GEN_AI_PROVIDER_NAME] == IBM_WATSONX_AI
    error_type = span.attributes[ErrorAttributes.ERROR_TYPE]
    assert isinstance(error_type, str)
    assert error_type == WatsonxApiError.__qualname__

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


def test_instrument_wraps_and_unwraps():
    instrumentor = WatsonxInstrumentor()
    instrumentor.instrument()
    try:
        assert hasattr(ModelInference.generate, "__wrapped__")
        assert hasattr(ModelInference.chat, "__wrapped__")
        assert hasattr(ModelInference.generate_text_stream, "__wrapped__")
    finally:
        instrumentor.uninstrument()

    assert not hasattr(ModelInference.generate, "__wrapped__")
    assert not hasattr(ModelInference.chat, "__wrapped__")
    assert not hasattr(ModelInference.generate_text_stream, "__wrapped__")
