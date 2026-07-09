# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Offline tests for the HuggingFace transformers instrumentation.

These tests never touch the network and never download or run a real model.
``transformers`` imports fine in this environment but has no ML backend
(PyTorch/TensorFlow/Flax), so a real ``TextGenerationPipeline`` cannot execute.

The tests therefore use a direct-wrapper strategy: they build the
``traced_method`` wrapper returned by ``text_generation(handler)`` and invoke it
against a fake pipeline ``instance`` and a fake ``wrapped`` callable that returns
the pipeline-shaped result (a list of ``{"generated_text": ...}`` dicts) or
raises. A separate pair of tests verifies that
``TransformersInstrumentor.instrument()`` / ``uninstrument()`` actually wrap and
unwrap ``TextGenerationPipeline.__call__``.

A local transformers pipeline exposes no token usage and no finish reason, so
``gen_ai.usage.*`` and ``gen_ai.response.finish_reasons`` are intentionally not
emitted.
"""

import json
import types

import pytest
from transformers import TextGenerationPipeline

from opentelemetry.instrumentation.transformers import TransformersInstrumentor
from opentelemetry.instrumentation.transformers.patch import text_generation
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.trace import StatusCode
from opentelemetry.util.genai.handler import TelemetryHandler

GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"
HUGGINGFACE = "huggingface"
TEST_MODEL = "gpt2"


def _fake_instance(name_or_path=TEST_MODEL, config_name=TEST_MODEL):
    """A fake ``TextGenerationPipeline`` instance exposing ``model``."""
    return types.SimpleNamespace(
        model=types.SimpleNamespace(
            name_or_path=name_or_path,
            config=types.SimpleNamespace(_name_or_path=config_name),
        )
    )


def _handler(tracer_provider, logger_provider, meter_provider):
    return TelemetryHandler(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )


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


def test_text_generation_success(
    span_exporter,
    metric_reader,
    tracer_provider,
    logger_provider,
    meter_provider,
    handler_env,
):
    handler = _handler(tracer_provider, logger_provider, meter_provider)
    wrapper = text_generation(handler)

    def wrapped(*args, **kwargs):
        return [{"generated_text": "hello world"}]

    result = wrapper(wrapped, _fake_instance(), ("Say hi",), {})
    assert result == [{"generated_text": "hello world"}]

    span = _get_span(span_exporter)
    assert span.name == f"chat {TEST_MODEL}"

    operation_name = span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
    assert (
        operation_name == GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    assert isinstance(operation_name, str)

    provider = span.attributes[GEN_AI_PROVIDER_NAME]
    assert provider == HUGGINGFACE
    assert isinstance(provider, str)

    request_model = span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
    assert request_model == TEST_MODEL
    assert isinstance(request_model, str)

    # Local inference: no token usage / finish reason attributes.
    assert GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS not in span.attributes
    assert GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS not in span.attributes
    assert (
        GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS not in span.attributes
    )

    duration_metric = _get_metric(
        metric_reader, gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
    )
    assert duration_metric is not None
    duration_points = list(duration_metric.data.data_points)
    assert len(duration_points) == 1
    assert duration_points[0].sum >= 0
    for point in duration_points:
        assert point.attributes[GEN_AI_PROVIDER_NAME] == HUGGINGFACE
        assert (
            point.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
            == TEST_MODEL
        )


def test_text_generation_captures_content(
    span_exporter,
    tracer_provider,
    logger_provider,
    meter_provider,
    handler_env,
):
    handler = _handler(tracer_provider, logger_provider, meter_provider)
    wrapper = text_generation(handler)

    def wrapped(*args, **kwargs):
        return [{"generated_text": "hello world"}]

    wrapper(wrapped, _fake_instance(), ("Say hi",), {})

    span = _get_span(span_exporter)

    input_messages = json.loads(
        span.attributes[GenAIAttributes.GEN_AI_INPUT_MESSAGES]
    )
    assert input_messages[0]["role"] == "user"
    assert input_messages[0]["parts"][0]["content"] == "Say hi"

    output_messages = json.loads(
        span.attributes[GenAIAttributes.GEN_AI_OUTPUT_MESSAGES]
    )
    assert output_messages[0]["role"] == "assistant"
    assert output_messages[0]["parts"][0]["content"] == "hello world"
    # Local pipeline exposes no finish reason.
    assert output_messages[0]["finish_reason"] is None


def test_text_generation_list_prompt_captures_content(
    span_exporter,
    tracer_provider,
    logger_provider,
    meter_provider,
    handler_env,
):
    handler = _handler(tracer_provider, logger_provider, meter_provider)
    wrapper = text_generation(handler)

    def wrapped(*args, **kwargs):
        # Batched pipelines return a list of lists.
        return [
            [{"generated_text": "hello world"}],
            [{"generated_text": "goodbye world"}],
        ]

    wrapper(wrapped, _fake_instance(), (["Say hi", "Say bye"],), {})

    span = _get_span(span_exporter)

    input_messages = json.loads(
        span.attributes[GenAIAttributes.GEN_AI_INPUT_MESSAGES]
    )
    assert [m["parts"][0]["content"] for m in input_messages] == [
        "Say hi",
        "Say bye",
    ]

    output_messages = json.loads(
        span.attributes[GenAIAttributes.GEN_AI_OUTPUT_MESSAGES]
    )
    assert [m["parts"][0]["content"] for m in output_messages] == [
        "hello world",
        "goodbye world",
    ]


def test_request_model_falls_back_to_config(
    span_exporter,
    tracer_provider,
    logger_provider,
    meter_provider,
    handler_env,
):
    handler = _handler(tracer_provider, logger_provider, meter_provider)
    wrapper = text_generation(handler)

    def wrapped(*args, **kwargs):
        return [{"generated_text": "hello world"}]

    # name_or_path missing -> fall back to model.config._name_or_path.
    instance = types.SimpleNamespace(
        model=types.SimpleNamespace(
            name_or_path=None,
            config=types.SimpleNamespace(_name_or_path="distilgpt2"),
        )
    )
    wrapper(wrapped, instance, ("Say hi",), {})

    span = _get_span(span_exporter)
    request_model = span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
    assert request_model == "distilgpt2"
    assert isinstance(request_model, str)


def test_text_generation_error(
    span_exporter,
    metric_reader,
    tracer_provider,
    logger_provider,
    meter_provider,
    handler_env,
):
    handler = _handler(tracer_provider, logger_provider, meter_provider)
    wrapper = text_generation(handler)

    class BoomError(RuntimeError):
        pass

    def wrapped(*args, **kwargs):
        raise BoomError("boom")

    with pytest.raises(BoomError) as exc_info:
        wrapper(wrapped, _fake_instance(), ("Say hi",), {})
    assert str(exc_info.value) == "boom"

    span = _get_span(span_exporter)
    assert span.status.status_code == StatusCode.ERROR

    error_type = span.attributes[ErrorAttributes.ERROR_TYPE]
    assert isinstance(error_type, str)
    assert error_type == BoomError.__qualname__

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


def test_instrument_wraps_call(instrument):
    assert hasattr(TextGenerationPipeline.__call__, "__wrapped__")


def test_uninstrument_unwraps_call(
    tracer_provider, logger_provider, meter_provider
):
    instrumentor = TransformersInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )
    assert hasattr(TextGenerationPipeline.__call__, "__wrapped__")

    instrumentor.uninstrument()
    assert not hasattr(TextGenerationPipeline.__call__, "__wrapped__")
