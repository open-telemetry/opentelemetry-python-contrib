# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
import sys
from typing import Any

import pytest

from opentelemetry.instrumentation import openai_v2
from opentelemetry.instrumentation._semconv import OTEL_SEMCONV_STABILITY_OPT_IN
from opentelemetry.instrumentation.genai.openai import (
    OpenAIInstrumentor as GenAIOpenAIInstrumentor,
)
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics

from .test_utils import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_MODEL,
    GENAI_OPENAI_SCOPE,
    USER_ONLY_PROMPT,
    not_wrapped,
    wrapped_by_genai_openai,
    wrapped_by_v2,
)

pytestmark = pytest.mark.usefixtures("latest_experimental")


@pytest.fixture(name="latest_experimental")
def fixture_latest_experimental(monkeypatch: pytest.MonkeyPatch, reset_instrumentors: None) -> None:
    monkeypatch.setenv(OTEL_SEMCONV_STABILITY_OPT_IN, "gen_ai_latest_experimental")


@pytest.fixture(name="genai_openai_instrument_calls")
def fixture_genai_openai_instrument_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    original = GenAIOpenAIInstrumentor.instrument

    def instrument(self: GenAIOpenAIInstrumentor, **kwargs: Any) -> Any:
        calls.append(kwargs)
        return original(self, **kwargs)

    monkeypatch.setattr(GenAIOpenAIInstrumentor, "instrument", instrument)
    return calls


@pytest.fixture(name="instrument_latest")
def fixture_instrument_latest(
    tracer_provider, logger_provider, meter_provider, latest_experimental: None
) -> OpenAIInstrumentor:
    instrumentor = OpenAIInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )
    return instrumentor


def test_genai_openai_not_installed(tracer_provider, monkeypatch, caplog):
    monkeypatch.setitem(sys.modules, GENAI_OPENAI_SCOPE, None)
    caplog.set_level(logging.WARNING, logger=openai_v2.__name__)

    instrumentor = OpenAIInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)

    assert not_wrapped()
    assert "opentelemetry-instrumentation-genai-openai" in caplog.text

    instrumentor.uninstrument()
    assert not instrumentor.is_instrumented_by_opentelemetry


def test_delegates_to_genai_openai(tracer_provider, meter_provider, genai_openai_instrument_calls):
    completion_hook = object()
    instrumentor = OpenAIInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        completion_hook=completion_hook,
    )

    genai_openai = GenAIOpenAIInstrumentor()
    assert genai_openai.is_instrumented_by_opentelemetry
    assert genai_openai_instrument_calls == [
        {
            "tracer_provider": tracer_provider,
            "meter_provider": meter_provider,
            "completion_hook": completion_hook,
        }
    ]
    assert wrapped_by_genai_openai()
    assert not wrapped_by_v2()

    instrumentor.uninstrument()

    assert not genai_openai.is_instrumented_by_opentelemetry
    assert not_wrapped()


def test_genai_openai_already_instrumented(tracer_provider, genai_openai_instrument_calls):
    genai_openai = GenAIOpenAIInstrumentor()
    genai_openai.instrument()

    instrumentor = OpenAIInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)

    assert genai_openai_instrument_calls == [{}]
    assert wrapped_by_genai_openai()

    instrumentor.uninstrument()

    assert genai_openai.is_instrumented_by_opentelemetry
    assert wrapped_by_genai_openai()


def _assert_genai_openai_telemetry(span_exporter, metric_reader, operation_name: str, request_model: str):
    (span,) = span_exporter.get_finished_spans()
    assert span.instrumentation_scope.name.startswith(GENAI_OPENAI_SCOPE)
    assert span.name == f"{operation_name} {request_model}"
    assert span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME] == operation_name
    assert span.attributes[GenAIAttributes.GEN_AI_PROVIDER_NAME] == "openai"
    assert GenAIAttributes.GEN_AI_SYSTEM not in span.attributes

    metric_names = {
        metric.name
        for resource_metrics in metric_reader.get_metrics_data().resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        if scope_metrics.scope.name.startswith(GENAI_OPENAI_SCOPE)
        for metric in scope_metrics.metrics
    }
    assert gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION in metric_names


@pytest.mark.usefixtures("instrument_latest")
def test_chat_completion_smoke(span_exporter, metric_reader, openai_client, vcr):
    with vcr.use_cassette("test_chat_completion_no_content.yaml"):
        openai_client.chat.completions.create(messages=USER_ONLY_PROMPT, model=DEFAULT_MODEL, stream=False)

    _assert_genai_openai_telemetry(span_exporter, metric_reader, "chat", DEFAULT_MODEL)


@pytest.mark.asyncio
@pytest.mark.usefixtures("instrument_latest")
async def test_async_chat_completion_smoke(span_exporter, metric_reader, async_openai_client, vcr):
    with vcr.use_cassette("test_async_chat_completion_no_content.yaml"):
        await async_openai_client.chat.completions.create(messages=USER_ONLY_PROMPT, model=DEFAULT_MODEL, stream=False)

    _assert_genai_openai_telemetry(span_exporter, metric_reader, "chat", DEFAULT_MODEL)


@pytest.mark.usefixtures("instrument_latest")
def test_embeddings_smoke(span_exporter, metric_reader, openai_client, vcr):
    with vcr.use_cassette("test_embeddings_no_content.yaml"):
        openai_client.embeddings.create(model=DEFAULT_EMBEDDING_MODEL, input="This is a test for embeddings")

    _assert_genai_openai_telemetry(span_exporter, metric_reader, "embeddings", DEFAULT_EMBEDDING_MODEL)
