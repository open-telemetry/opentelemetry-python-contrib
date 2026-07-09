# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import chromadb
import pytest

from opentelemetry.instrumentation.chromadb import ChromaInstrumentor
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_COLLECTION_NAME,
    DB_OPERATION_NAME,
    DB_SYSTEM_NAME,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.trace import SpanKind, StatusCode

# Explicit constant names, mirroring the semconv spec, to make the assertions
# robust even if the constant values change.
_DB_SYSTEM_NAME = "db.system.name"
_DB_OPERATION_NAME = "db.operation.name"
_DB_COLLECTION_NAME = "db.collection.name"
_ERROR_TYPE = "error.type"


def _spans_by_operation(
    span_exporter: InMemorySpanExporter,
) -> dict[str, ReadableSpan]:
    result: dict[str, ReadableSpan] = {}
    for span in span_exporter.get_finished_spans():
        operation = span.attributes.get(_DB_OPERATION_NAME)
        if operation is not None:
            result[operation] = span
    return result


def _assert_common(span: ReadableSpan, operation: str) -> None:
    # SpanKind
    assert span.kind is SpanKind.CLIENT

    # Attribute names match the semconv constants exactly.
    assert DB_SYSTEM_NAME == _DB_SYSTEM_NAME
    assert DB_OPERATION_NAME == _DB_OPERATION_NAME
    assert DB_COLLECTION_NAME == _DB_COLLECTION_NAME
    assert ERROR_TYPE == _ERROR_TYPE

    # db.system.name is the literal "chromadb" string.
    assert span.attributes[_DB_SYSTEM_NAME] == "chromadb"
    assert isinstance(span.attributes[_DB_SYSTEM_NAME], str)

    # db.operation.name matches the wrapped method and is a string.
    assert span.attributes[_DB_OPERATION_NAME] == operation
    assert isinstance(span.attributes[_DB_OPERATION_NAME], str)


def test_create_collection_span(
    instrument: ChromaInstrumentor,
    span_exporter: InMemorySpanExporter,
    chroma_client: chromadb.ClientAPI,
) -> None:
    chroma_client.create_collection("books")

    spans = _spans_by_operation(span_exporter)
    assert "create_collection" in spans
    span = spans["create_collection"]
    _assert_common(span, "create_collection")
    assert span.attributes[_DB_COLLECTION_NAME] == "books"
    assert isinstance(span.attributes[_DB_COLLECTION_NAME], str)
    assert span.name == "create_collection books"
    assert span.status.status_code is not StatusCode.ERROR


def test_add_query_delete_spans(
    instrument: ChromaInstrumentor,
    span_exporter: InMemorySpanExporter,
    chroma_client: chromadb.ClientAPI,
) -> None:
    collection = chroma_client.create_collection("docs")
    span_exporter.clear()

    collection.add(
        ids=["a", "b", "c"],
        documents=["alpha", "beta", "gamma"],
    )
    results = collection.query(query_texts=["alpha"], n_results=1)
    assert results["ids"]  # real query returned real data
    collection.delete(ids=["a"])

    spans = _spans_by_operation(span_exporter)

    for operation in ("add", "query", "delete"):
        assert operation in spans, f"missing span for {operation}"
        span = spans[operation]
        _assert_common(span, operation)
        assert span.attributes[_DB_COLLECTION_NAME] == "docs"
        assert isinstance(span.attributes[_DB_COLLECTION_NAME], str)
        assert span.name == f"{operation} docs"
        # No vector-specific attributes should be emitted.
        assert _ERROR_TYPE not in span.attributes
        for attr in span.attributes:
            assert attr.startswith("db."), (
                f"unexpected non-db attribute {attr!r} on span {operation}"
            )


def test_get_count_peek_update_upsert_modify_spans(
    instrument: ChromaInstrumentor,
    span_exporter: InMemorySpanExporter,
    chroma_client: chromadb.ClientAPI,
) -> None:
    collection = chroma_client.create_collection("items")
    collection.add(ids=["x"], documents=["xray"])
    span_exporter.clear()

    collection.get(ids=["x"])
    collection.count()
    collection.peek()
    collection.update(ids=["x"], documents=["updated"])
    collection.upsert(ids=["y"], documents=["yankee"])
    collection.modify(name="items")

    spans = _spans_by_operation(span_exporter)
    for operation in ("get", "count", "peek", "update", "upsert", "modify"):
        assert operation in spans, f"missing span for {operation}"
        span = spans[operation]
        _assert_common(span, operation)
        assert span.attributes[_DB_COLLECTION_NAME] == "items"


def test_get_or_create_and_delete_collection_spans(
    instrument: ChromaInstrumentor,
    span_exporter: InMemorySpanExporter,
    chroma_client: chromadb.ClientAPI,
) -> None:
    chroma_client.get_or_create_collection("cache")
    chroma_client.delete_collection("cache")

    spans = _spans_by_operation(span_exporter)
    for operation in ("get_or_create_collection", "delete_collection"):
        assert operation in spans, f"missing span for {operation}"
        span = spans[operation]
        _assert_common(span, operation)
        assert span.attributes[_DB_COLLECTION_NAME] == "cache"
        assert span.name == f"{operation} cache"


def test_error_records_status_and_error_type(
    instrument: ChromaInstrumentor,
    span_exporter: InMemorySpanExporter,
    chroma_client: chromadb.ClientAPI,
) -> None:
    # Deleting a collection that does not exist raises the original chromadb
    # exception; the instrumentation must set the error status and re-raise.
    with pytest.raises(Exception) as exc_info:
        chroma_client.delete_collection("does-not-exist")

    spans = _spans_by_operation(span_exporter)
    assert "delete_collection" in spans
    span = spans["delete_collection"]

    assert span.kind is SpanKind.CLIENT
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes[_ERROR_TYPE] == type(exc_info.value).__qualname__
    assert isinstance(span.attributes[_ERROR_TYPE], str)
    # The exception must be recorded as a span event and re-raised unmodified.
    event_names = [event.name for event in span.events]
    assert "exception" in event_names


def test_uninstrument_stops_spans(
    span_exporter: InMemorySpanExporter,
    tracer_provider,
    chroma_client: chromadb.ClientAPI,
) -> None:
    instrumentor = ChromaInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)
    collection = chroma_client.create_collection("temp")
    assert span_exporter.get_finished_spans()

    span_exporter.clear()
    instrumentor.uninstrument()

    collection.add(ids=["z"], documents=["zulu"])
    collection.query(query_texts=["zulu"], n_results=1)
    assert not span_exporter.get_finished_spans()
