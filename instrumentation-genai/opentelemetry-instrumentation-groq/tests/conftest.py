# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests configuration module for the Groq instrumentation."""

from __future__ import annotations

import os

import pytest
from groq import AsyncGroq, Groq

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.groq import GroqInstrumentor
from opentelemetry.sdk._logs import LoggerProvider

# Backward compatibility for InMemoryLogExporter -> InMemoryLogRecordExporter
try:
    from opentelemetry.sdk._logs.export import (  # pylint: disable=no-name-in-module
        InMemoryLogRecordExporter,
        SimpleLogRecordProcessor,
    )
except ImportError:  # pragma: no cover - depends on SDK version
    from opentelemetry.sdk._logs.export import (
        InMemoryLogExporter as InMemoryLogRecordExporter,
    )
    from opentelemetry.sdk._logs.export import (
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


@pytest.fixture(scope="function", name="span_exporter")
def fixture_span_exporter():
    exporter = InMemorySpanExporter()
    yield exporter
    exporter.clear()


@pytest.fixture(scope="function", name="log_exporter")
def fixture_log_exporter():
    exporter = InMemoryLogRecordExporter()
    yield exporter
    exporter.clear()


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
    provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))
    return provider


@pytest.fixture(scope="function", name="meter_provider")
def fixture_meter_provider(metric_reader):
    provider = MeterProvider(metric_readers=[metric_reader])
    return provider


@pytest.fixture(autouse=True)
def environment():
    """Ensure the SDK can build a client without a real API key."""
    if not os.getenv("GROQ_API_KEY"):
        os.environ["GROQ_API_KEY"] = "test_groq_api_key"


@pytest.fixture
def groq_client():
    return Groq()


@pytest.fixture
def async_groq_client():
    return AsyncGroq()


@pytest.fixture(
    scope="function",
    params=[(True, "span_only"), (False, "True")],
    name="content_mode",
)
def fixture_content_mode(request):
    # (latest_experimental_enabled: bool, content_mode_value: str)
    # We do not test (True, "event_only") / (True, "span_and_event") because
    # that is util-genai's responsibility, not the instrumentation's.
    return request.param


def _instrument(
    tracer_provider,
    logger_provider,
    meter_provider,
    *,
    latest_experimental_enabled: bool,
    content_mode_value: str | None,
):
    _OpenTelemetrySemanticConventionStability._initialized = False

    if content_mode_value is not None:
        os.environ[OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT] = (
            content_mode_value
        )

    os.environ[OTEL_SEMCONV_STABILITY_OPT_IN] = (
        "gen_ai_latest_experimental" if latest_experimental_enabled else ""
    )

    instrumentor = GroqInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )
    return instrumentor


@pytest.fixture(scope="function")
def instrument_no_content(
    tracer_provider, logger_provider, meter_provider, content_mode
):
    latest_experimental_enabled, _ = content_mode
    instrumentor = _instrument(
        tracer_provider,
        logger_provider,
        meter_provider,
        latest_experimental_enabled=latest_experimental_enabled,
        content_mode_value=None,
    )

    try:
        yield instrumentor
    finally:
        os.environ.pop(
            OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None
        )
        os.environ.pop(OTEL_SEMCONV_STABILITY_OPT_IN, None)
        instrumentor.uninstrument()
        _OpenTelemetrySemanticConventionStability._initialized = False


@pytest.fixture(scope="function")
def instrument_with_content(
    tracer_provider, logger_provider, meter_provider, content_mode
):
    latest_experimental_enabled, content_mode_value = content_mode
    instrumentor = _instrument(
        tracer_provider,
        logger_provider,
        meter_provider,
        latest_experimental_enabled=latest_experimental_enabled,
        content_mode_value=content_mode_value,
    )

    try:
        yield instrumentor
    finally:
        os.environ.pop(
            OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None
        )
        os.environ.pop(OTEL_SEMCONV_STABILITY_OPT_IN, None)
        instrumentor.uninstrument()
        _OpenTelemetrySemanticConventionStability._initialized = False
