# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests configuration module for the Milvus instrumentation."""

from __future__ import annotations

import pytest
from pymilvus import MilvusClient

from opentelemetry.instrumentation.milvus import MilvusInstrumentor
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
    instrumentor = MilvusInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)
    try:
        yield instrumentor
    finally:
        instrumentor.uninstrument()


@pytest.fixture(scope="function")
def milvus_client(tmp_path):
    # A local ``.db`` path uses the embedded milvus-lite backend, so tests
    # need no server or network access.
    db_path = tmp_path / "milvus_test.db"
    client = MilvusClient(str(db_path))
    try:
        yield client
    finally:
        client.close()
