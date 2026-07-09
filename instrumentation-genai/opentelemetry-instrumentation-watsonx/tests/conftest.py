# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests configuration module.

The IBM watsonx.ai ``ModelInference`` class cannot be constructed offline (it
requires IBM Cloud credentials and network access), so these tests exercise the
instrumentation wrappers directly against a ``TelemetryHandler`` wired to
in-memory exporters instead of driving the real SDK.
"""

import os

import pytest

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
)
from opentelemetry.util.genai.handler import TelemetryHandler

# Backward compatibility for InMemoryLogExporter -> InMemoryLogRecordExporter rename
try:
    from opentelemetry.sdk._logs.export import (  # pylint: disable=no-name-in-module
        InMemoryLogRecordExporter,
        SimpleLogRecordProcessor,
    )
except ImportError:
    # Fallback to old name for compatibility with older SDK versions
    from opentelemetry.sdk._logs.export import (
        InMemoryLogExporter as InMemoryLogRecordExporter,
    )
    from opentelemetry.sdk._logs.export import (
        SimpleLogRecordProcessor,
    )
from opentelemetry.sdk.metrics import (
    MeterProvider,
)
from opentelemetry.sdk.metrics.export import (
    InMemoryMetricReader,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


@pytest.fixture(scope="function", name="span_exporter")
def fixture_span_exporter():
    exporter = InMemorySpanExporter()
    yield exporter


@pytest.fixture(scope="function", name="log_exporter")
def fixture_log_exporter():
    exporter = InMemoryLogRecordExporter()
    yield exporter


@pytest.fixture(scope="function", name="metric_reader")
def fixture_metric_reader():
    exporter = InMemoryMetricReader()
    yield exporter


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
    meter_provider = MeterProvider(
        metric_readers=[metric_reader],
    )

    return meter_provider


@pytest.fixture(scope="function")
def experimental_semconv():
    """Enable the latest-experimental GenAI semantic conventions.

    ``_get_opentelemetry_stability_opt_in_mode`` reads a cached mapping that is
    only (re)populated by ``_initialize``. Resetting ``_initialized`` and then
    calling ``_initialize`` forces the mapping to reflect the opt-in set here.
    """
    _OpenTelemetrySemanticConventionStability._initialized = False
    os.environ[OTEL_SEMCONV_STABILITY_OPT_IN] = "gen_ai_latest_experimental"
    _OpenTelemetrySemanticConventionStability._initialize()
    yield
    os.environ.pop(OTEL_SEMCONV_STABILITY_OPT_IN, None)
    _OpenTelemetrySemanticConventionStability._initialized = False


@pytest.fixture(scope="function")
def handler(
    tracer_provider,
    logger_provider,
    meter_provider,
    experimental_semconv,
):
    """A ``TelemetryHandler`` wired to the in-memory exporters (no content)."""
    return TelemetryHandler(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )


@pytest.fixture(scope="function")
def handler_with_content(
    tracer_provider,
    logger_provider,
    meter_provider,
    experimental_semconv,
):
    """A ``TelemetryHandler`` with span content capture enabled."""
    os.environ[OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT] = (
        "span_only"
    )
    yield TelemetryHandler(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )
    os.environ.pop(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None)
