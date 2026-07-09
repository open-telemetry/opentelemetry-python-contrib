# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests configuration module."""

import os

import pytest

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.mcp import McpInstrumentor
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


@pytest.fixture(scope="function", name="tracer_provider")
def fixture_tracer_provider(span_exporter):
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    return provider


@pytest.fixture(scope="function")
def instrument(tracer_provider):
    """Instrument MCP on the latest experimental semconv path."""
    _OpenTelemetrySemanticConventionStability._initialized = False
    os.environ[OTEL_SEMCONV_STABILITY_OPT_IN] = "gen_ai_latest_experimental"

    instrumentor = McpInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)

    yield instrumentor

    os.environ.pop(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None)
    os.environ.pop(OTEL_SEMCONV_STABILITY_OPT_IN, None)
    instrumentor.uninstrument()


@pytest.fixture(scope="function")
def instrument_with_content(tracer_provider):
    """Instrument with content capture enabled (span attributes)."""
    _OpenTelemetrySemanticConventionStability._initialized = False
    os.environ[OTEL_SEMCONV_STABILITY_OPT_IN] = "gen_ai_latest_experimental"
    os.environ[OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT] = (
        "span_only"
    )

    instrumentor = McpInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)

    yield instrumentor

    os.environ.pop(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None)
    os.environ.pop(OTEL_SEMCONV_STABILITY_OPT_IN, None)
    instrumentor.uninstrument()
