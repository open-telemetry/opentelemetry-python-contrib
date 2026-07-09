# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests configuration module for the Qdrant instrumentation."""

from __future__ import annotations

import pytest
from qdrant_client import QdrantClient

from opentelemetry.instrumentation.qdrant import QdrantInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


@pytest.fixture(scope="function", name="span_exporter")
def fixture_span_exporter():
    exporter = InMemorySpanExporter()
    yield exporter
    exporter.clear()


@pytest.fixture(scope="function", name="tracer_provider")
def fixture_tracer_provider(span_exporter):
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    return provider


@pytest.fixture(scope="function")
def instrument(tracer_provider):
    instrumentor = QdrantInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)
    try:
        yield instrumentor
    finally:
        instrumentor.uninstrument()


@pytest.fixture(scope="function")
def qdrant_client():
    # ``:memory:`` uses the in-process backend, so tests need no network access.
    return QdrantClient(":memory:")
