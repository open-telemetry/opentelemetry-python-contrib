# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Offline test fixtures for the ollama instrumentation.

Tests never contact a real ollama server. Instead, ``httpx.Client.send`` and
``httpx.AsyncClient.send`` are monkeypatched to return canned JSON so the real
ollama SDK parses genuine response objects and the instrumentation wrappers run
end to end. Both ``client.request(...)`` (non-streaming) and ``client.stream(...)``
(streaming) funnel through ``send``.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

import httpx
import pytest

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.ollama import OllamaInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    InMemoryLogExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
)

# A JSON responder maps a request to (status_code, body_str).
Responder = Callable[[httpx.Request], "tuple[int, str]"]


@pytest.fixture(scope="function", name="span_exporter")
def fixture_span_exporter():
    exporter = InMemorySpanExporter()
    yield exporter


@pytest.fixture(scope="function", name="log_exporter")
def fixture_log_exporter():
    exporter = InMemoryLogExporter()
    yield exporter


@pytest.fixture(scope="function", name="metric_reader")
def fixture_metric_reader():
    reader = InMemoryMetricReader()
    yield reader


@pytest.fixture(scope="function", name="tracer_provider")
def fixture_tracer_provider(span_exporter):
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    return provider


@pytest.fixture(scope="function", name="logger_provider")
def fixture_logger_provider(log_exporter):
    provider = LoggerProvider()
    provider.add_log_record_processor(
        SimpleLogRecordProcessor(log_exporter)
    )
    return provider


@pytest.fixture(scope="function", name="meter_provider")
def fixture_meter_provider(metric_reader):
    return MeterProvider(metric_readers=[metric_reader])


class _MockSend:
    """Container holding the responder used by the patched ``send`` methods."""

    responder: Responder | None = None


@pytest.fixture(name="mock_ollama", autouse=True)
def fixture_mock_ollama(monkeypatch):
    """Patch httpx send methods so ollama receives canned responses.

    Returns a setter accepting a responder callable ``(request) -> (status, body)``.
    """
    state = _MockSend()

    def _build_response(request: httpx.Request) -> httpx.Response:
        if state.responder is None:
            raise AssertionError("No mock responder configured")
        status_code, body = state.responder(request)
        return httpx.Response(
            status_code=status_code,
            content=body.encode("utf-8"),
            request=request,
            headers={"content-type": "application/x-ndjson"},
        )

    def _sync_send(self, request, *args, **kwargs):  # noqa: ANN001
        return _build_response(request)

    async def _async_send(self, request, *args, **kwargs):  # noqa: ANN001
        return _build_response(request)

    monkeypatch.setattr(httpx.Client, "send", _sync_send)
    monkeypatch.setattr(httpx.AsyncClient, "send", _async_send)

    def set_responder(responder: Responder) -> None:
        state.responder = responder

    return set_responder


def json_body(payload: dict[str, Any]) -> str:
    return json.dumps(payload)


def ndjson_body(payloads: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(p) for p in payloads)


def _enable_experimental(content_mode: str | None) -> None:
    _OpenTelemetrySemanticConventionStability._initialized = False
    os.environ[OTEL_SEMCONV_STABILITY_OPT_IN] = "gen_ai_latest_experimental"
    if content_mode is not None:
        os.environ[OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT] = (
            content_mode
        )
    else:
        os.environ.pop(
            OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None
        )


def _cleanup_env() -> None:
    os.environ.pop(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None)
    os.environ.pop(OTEL_SEMCONV_STABILITY_OPT_IN, None)


@pytest.fixture(scope="function")
def instrument_with_content(
    tracer_provider, logger_provider, meter_provider
):
    _enable_experimental("span_and_event")
    instrumentor = OllamaInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )
    yield instrumentor
    _cleanup_env()
    instrumentor.uninstrument()


@pytest.fixture(scope="function")
def instrument_no_content(
    tracer_provider, logger_provider, meter_provider
):
    _enable_experimental(None)
    instrumentor = OllamaInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )
    yield instrumentor
    _cleanup_env()
    instrumentor.uninstrument()
