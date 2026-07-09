# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests configuration module for the ChromaDB instrumentation."""

from __future__ import annotations

from typing import Iterator

import chromadb
import pytest

from opentelemetry.instrumentation.chromadb import ChromaInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


@pytest.fixture(scope="function", name="span_exporter")
def fixture_span_exporter() -> Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    yield exporter
    exporter.clear()


@pytest.fixture(scope="function", name="tracer_provider")
def fixture_tracer_provider(
    span_exporter: InMemorySpanExporter,
) -> TracerProvider:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    return provider


@pytest.fixture(scope="function", name="instrument")
def fixture_instrument(
    tracer_provider: TracerProvider,
) -> Iterator[ChromaInstrumentor]:
    instrumentor = ChromaInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)
    try:
        yield instrumentor
    finally:
        instrumentor.uninstrument()


@pytest.fixture(scope="function", name="chroma_client")
def fixture_chroma_client() -> chromadb.ClientAPI:
    # An in-memory client: no network and no external services required.
    return chromadb.EphemeralClient()
