# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests configuration module for the Pinecone instrumentation.

Pinecone talks to a remote service over HTTP and has no in-memory mode. To keep
the tests fully offline we construct a real ``Index`` client (which performs no
network I/O at construction) with a dummy API key, then replace the instance's
transport (``_http``) and response adapter (``_adapter``) with mocks. The real
``Index`` method bodies and the instrumentation wrapper both run; only the
network boundary is mocked.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock

import pytest

# The Pinecone SDK requires an API key to construct an Index. No network call is
# made at construction time, so a dummy key is sufficient for offline tests.
os.environ.setdefault("PINECONE_API_KEY", "test-pinecone-api-key")

import pinecone  # noqa: E402

from opentelemetry.instrumentation.pinecone import (  # noqa: E402
    PineconeInstrumentor,
)
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)

TEST_HOST = "https://my-index-abc123.svc.us-east-1.pinecone.io"
TEST_INDEX_NAME = "my-index-abc123"


@pytest.fixture(name="span_exporter")
def fixture_span_exporter():
    exporter = InMemorySpanExporter()
    yield exporter
    exporter.clear()


@pytest.fixture(name="tracer_provider")
def fixture_tracer_provider(span_exporter):
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    return provider


@pytest.fixture(name="instrument")
def fixture_instrument(tracer_provider):
    instrumentor = PineconeInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)
    try:
        yield instrumentor
    finally:
        instrumentor.uninstrument()


def _mock_transport(index: Any) -> MagicMock:
    """Replace the network transport of an ``Index`` with mocks.

    Pinecone's internal transport differs by SDK version:

    * v9 uses ``_http`` (an httpx client) plus a ``_adapter`` that parses the
      raw response bytes.
    * v5 uses a generated ``_vector_api`` OpenAPI client.

    We mock whichever attributes are present so the same tests run offline
    against both the oldest and latest supported Pinecone releases. Returns the
    mock that stands in for the request-issuing object so tests can inject
    errors (e.g. ``.post`` / ``.query`` side effects).
    """
    if hasattr(index, "_http"):
        http = MagicMock(name="http_client")
        http.post.return_value = MagicMock(content=b"{}")
        http.get.return_value = MagicMock(content=b"{}")
        index._http = http

        adapter = MagicMock(name="adapter")
        adapter.to_query_response.return_value = MagicMock(matches=[])
        adapter.to_fetch_response.return_value = MagicMock(vectors={})
        adapter.to_update_response.return_value = MagicMock()
        adapter.to_stats_response.return_value = MagicMock()
        index._adapter = adapter
        return http

    vector_api = MagicMock(name="vector_api")
    index._vector_api = vector_api
    return vector_api


@pytest.fixture(name="index")
def fixture_index(instrument):
    """A Pinecone ``Index`` client with its transport mocked.

    Depends on ``instrument`` so the client is created *after* instrumentation
    (the order the instrumentor expects). The request-issuing transport mock is
    attached as ``client.transport_mock`` so tests can inject errors without
    caring about the SDK-version-specific transport attribute name.
    """
    client = pinecone.Index(host=TEST_HOST, api_key="test-pinecone-api-key")
    client.transport_mock = _mock_transport(client)
    return client
