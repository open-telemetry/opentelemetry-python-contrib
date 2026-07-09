# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Pinecone instrumentation.

These tests run fully offline: the Pinecone ``Index`` transport is mocked (see
``conftest.py``), so no network access or real API key is required. They assert
the exact generic database (``db.*``) attribute names and value types, the span
name and kind, and the error path.
"""

from __future__ import annotations

from typing import Any

import pinecone
import pytest

from opentelemetry.instrumentation.pinecone import PineconeInstrumentor
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_COLLECTION_NAME,
    DB_NAMESPACE,
    DB_OPERATION_NAME,
    DB_SYSTEM_NAME,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.trace import SpanKind, StatusCode

from .conftest import TEST_HOST, TEST_INDEX_NAME, _mock_transport

NAMESPACE = "ns1"


def _call(index: Any, operation: str) -> Any:
    calls = {
        "query": lambda: index.query(
            top_k=2, vector=[0.1, 0.2], namespace=NAMESPACE
        ),
        "upsert": lambda: index.upsert(
            vectors=[("id1", [0.1, 0.2])], namespace=NAMESPACE
        ),
        "delete": lambda: index.delete(ids=["id1"], namespace=NAMESPACE),
        "fetch": lambda: index.fetch(ids=["id1"], namespace=NAMESPACE),
        "update": lambda: index.update(
            id="id1", values=[0.1, 0.2], namespace=NAMESPACE
        ),
        "describe_index_stats": lambda: index.describe_index_stats(),
    }
    return calls[operation]()


@pytest.mark.parametrize(
    "operation",
    ["query", "upsert", "delete", "fetch", "update", "describe_index_stats"],
)
def test_operation_emits_db_span(span_exporter, index, operation):
    _call(index, operation)

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.kind is SpanKind.CLIENT

    attributes = span.attributes
    # db.system.name is the literal "pinecone".
    assert attributes[DB_SYSTEM_NAME] == "pinecone"
    assert isinstance(attributes[DB_SYSTEM_NAME], str)

    assert attributes[DB_OPERATION_NAME] == operation
    assert isinstance(attributes[DB_OPERATION_NAME], str)

    assert attributes[DB_COLLECTION_NAME] == TEST_INDEX_NAME
    assert isinstance(attributes[DB_COLLECTION_NAME], str)

    # describe_index_stats() takes no namespace argument.
    if operation == "describe_index_stats":
        assert DB_NAMESPACE not in attributes
        assert span.name == f"{operation} {TEST_INDEX_NAME}"
    else:
        assert attributes[DB_NAMESPACE] == NAMESPACE
        assert isinstance(attributes[DB_NAMESPACE], str)
        assert span.name == f"{operation} {TEST_INDEX_NAME}"

    assert span.status.status_code is StatusCode.UNSET
    assert ERROR_TYPE not in attributes


def test_query_without_namespace(span_exporter, index):
    index.query(top_k=1, vector=[0.1, 0.2])

    (span,) = span_exporter.get_finished_spans()
    assert DB_NAMESPACE not in span.attributes
    assert span.attributes[DB_COLLECTION_NAME] == TEST_INDEX_NAME
    assert span.name == f"query {TEST_INDEX_NAME}"


def test_error_sets_status_and_reraises(span_exporter, index):
    boom = RuntimeError("connection refused")
    # ``query`` issues its request via ``.post`` (v9) or ``.query`` (v5) on the
    # transport; fail both so the test is SDK-version agnostic.
    index.transport_mock.post.side_effect = boom
    index.transport_mock.query.side_effect = boom

    with pytest.raises(RuntimeError) as exc_info:
        index.query(top_k=2, vector=[0.1, 0.2], namespace=NAMESPACE)

    # The original exception is re-raised unmodified.
    assert exc_info.value is boom

    (span,) = span_exporter.get_finished_spans()
    assert span.kind is SpanKind.CLIENT
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes[ERROR_TYPE] == "RuntimeError"
    assert isinstance(span.attributes[ERROR_TYPE], str)
    # Generic db.* attributes are still present on the failed span.
    assert span.attributes[DB_SYSTEM_NAME] == "pinecone"
    assert span.attributes[DB_OPERATION_NAME] == "query"
    # The exception was recorded as a span event.
    assert any(event.name == "exception" for event in span.events)


def test_uninstrument_removes_wrappers(span_exporter, tracer_provider):
    instrumentor = PineconeInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)
    instrumentor.uninstrument()

    index = pinecone.Index(host=TEST_HOST, api_key="test-pinecone-api-key")
    _mock_transport(index)

    index.query(top_k=1, vector=[0.1, 0.2], namespace=NAMESPACE)

    assert span_exporter.get_finished_spans() == ()
