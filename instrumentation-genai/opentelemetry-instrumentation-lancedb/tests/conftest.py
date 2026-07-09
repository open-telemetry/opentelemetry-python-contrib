# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests configuration module for the LanceDB instrumentation."""

from __future__ import annotations

import lancedb
import pytest

from opentelemetry.instrumentation.lancedb import LanceDBInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

_COLLECTION = "mytable"
_VECTOR = [0.1, 0.2, 0.3, 0.4]


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
    instrumentor = LanceDBInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)
    try:
        yield instrumentor
    finally:
        instrumentor.uninstrument()


@pytest.fixture(scope="function")
def lancedb_table(tmp_path):
    # LanceDB is embedded, so tests need no network access; the table is
    # created in a temporary directory.
    db = lancedb.connect(tmp_path)
    return db.create_table(
        _COLLECTION,
        data=[
            {"id": 1, "vector": _VECTOR, "text": "a"},
            {"id": 2, "vector": [0.5, 0.6, 0.7, 0.8], "text": "b"},
        ],
    )
