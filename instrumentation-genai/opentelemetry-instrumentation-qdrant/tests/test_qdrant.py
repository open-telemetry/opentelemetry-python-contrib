# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio

import pytest
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from opentelemetry.instrumentation.qdrant import QdrantInstrumentor
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_COLLECTION_NAME,
    DB_OPERATION_NAME,
    DB_SYSTEM_NAME,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.trace import SpanKind, StatusCode

_COLLECTION = "test_collection"
_VECTOR = [0.1, 0.2, 0.3, 0.4]


def _create_collection(client) -> None:
    client.create_collection(
        _COLLECTION,
        vectors_config=VectorParams(size=4, distance=Distance.COSINE),
    )


def _upsert_point(client) -> None:
    client.upsert(
        _COLLECTION,
        points=[PointStruct(id=1, vector=_VECTOR, payload={"kind": "test"})],
    )


def _span_by_operation(spans, operation):
    for span in spans:
        if span.attributes.get(DB_OPERATION_NAME) == operation:
            return span
    raise AssertionError(f"no span for operation {operation!r}")


def _search_points(client) -> str:
    """Search using whichever API the installed client version exposes.

    ``query_points`` replaced ``search`` in qdrant-client 1.10; the oldest
    supported version (1.7.0) only exposes ``search``. Returns the name of the
    operation that was invoked so callers can assert against it.
    """
    if hasattr(client, "query_points"):
        result = client.query_points(_COLLECTION, query=_VECTOR, limit=1)
        assert len(result.points) == 1
        return "query_points"
    result = client.search(_COLLECTION, query_vector=_VECTOR, limit=1)
    assert len(result) == 1
    return "search"


def test_create_collection_span(instrument, qdrant_client, span_exporter):
    _create_collection(qdrant_client)

    spans = span_exporter.get_finished_spans()
    span = _span_by_operation(spans, "create_collection")

    assert span.name == f"create_collection {_COLLECTION}"
    assert span.kind is SpanKind.CLIENT

    attributes = span.attributes
    assert attributes[DB_SYSTEM_NAME] == "qdrant"
    assert isinstance(attributes[DB_SYSTEM_NAME], str)
    assert attributes[DB_OPERATION_NAME] == "create_collection"
    assert isinstance(attributes[DB_OPERATION_NAME], str)
    assert attributes[DB_COLLECTION_NAME] == _COLLECTION
    assert isinstance(attributes[DB_COLLECTION_NAME], str)

    # No vector-specific attributes should be emitted.
    assert set(attributes) == {
        DB_SYSTEM_NAME,
        DB_OPERATION_NAME,
        DB_COLLECTION_NAME,
    }
    assert span.status.status_code is not StatusCode.ERROR


def test_upsert_span(instrument, qdrant_client, span_exporter):
    _create_collection(qdrant_client)
    span_exporter.clear()

    _upsert_point(qdrant_client)

    spans = span_exporter.get_finished_spans()
    span = _span_by_operation(spans, "upsert")

    assert span.name == f"upsert {_COLLECTION}"
    assert span.kind is SpanKind.CLIENT
    assert span.attributes[DB_SYSTEM_NAME] == "qdrant"
    assert span.attributes[DB_OPERATION_NAME] == "upsert"
    assert span.attributes[DB_COLLECTION_NAME] == _COLLECTION


def test_query_points_span(instrument, qdrant_client, span_exporter):
    _create_collection(qdrant_client)
    _upsert_point(qdrant_client)
    span_exporter.clear()

    operation = _search_points(qdrant_client)

    spans = span_exporter.get_finished_spans()
    span = _span_by_operation(spans, operation)

    assert span.name == f"{operation} {_COLLECTION}"
    assert span.kind is SpanKind.CLIENT
    assert span.attributes[DB_SYSTEM_NAME] == "qdrant"
    assert span.attributes[DB_OPERATION_NAME] == operation
    assert span.attributes[DB_COLLECTION_NAME] == _COLLECTION


def test_retrieve_and_delete_spans(instrument, qdrant_client, span_exporter):
    _create_collection(qdrant_client)
    _upsert_point(qdrant_client)
    span_exporter.clear()

    qdrant_client.retrieve(_COLLECTION, ids=[1])
    qdrant_client.delete(_COLLECTION, points_selector=[1])

    spans = span_exporter.get_finished_spans()

    retrieve_span = _span_by_operation(spans, "retrieve")
    assert retrieve_span.name == f"retrieve {_COLLECTION}"
    assert retrieve_span.kind is SpanKind.CLIENT
    assert retrieve_span.attributes[DB_COLLECTION_NAME] == _COLLECTION

    delete_span = _span_by_operation(spans, "delete")
    assert delete_span.name == f"delete {_COLLECTION}"
    assert delete_span.kind is SpanKind.CLIENT
    assert delete_span.attributes[DB_OPERATION_NAME] == "delete"


def test_collection_name_from_positional_arg(
    instrument, qdrant_client, span_exporter
):
    _create_collection(qdrant_client)
    span_exporter.clear()

    # Pass collection name positionally rather than as a keyword.
    qdrant_client.get_collection(_COLLECTION)

    span = _span_by_operation(
        span_exporter.get_finished_spans(), "get_collection"
    )
    assert span.attributes[DB_COLLECTION_NAME] == _COLLECTION
    assert span.name == f"get_collection {_COLLECTION}"


def test_error_records_exception(instrument, qdrant_client, span_exporter):
    with pytest.raises(ValueError):
        qdrant_client.get_collection("does_not_exist")

    span = _span_by_operation(
        span_exporter.get_finished_spans(), "get_collection"
    )
    assert span.kind is SpanKind.CLIENT
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes[ERROR_TYPE] == "ValueError"
    assert isinstance(span.attributes[ERROR_TYPE], str)
    assert span.attributes[DB_COLLECTION_NAME] == "does_not_exist"
    # The original exception must be recorded as an event.
    assert any(event.name == "exception" for event in span.events)


def test_original_exception_is_reraised_unmodified(
    instrument, qdrant_client, span_exporter
):
    with pytest.raises(ValueError) as exc_info:
        qdrant_client.get_collection("missing")

    # The instrumentation must re-raise the original exception unchanged.
    assert isinstance(exc_info.value, ValueError)


def test_uninstrument_stops_spans(
    tracer_provider, qdrant_client, span_exporter
):
    instrumentor = QdrantInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)
    _create_collection(qdrant_client)
    assert span_exporter.get_finished_spans()

    span_exporter.clear()
    instrumentor.uninstrument()

    qdrant_client.get_collection(_COLLECTION)
    assert span_exporter.get_finished_spans() == ()


def test_async_client_spans(instrument, span_exporter):
    async def _run():
        client = AsyncQdrantClient(":memory:")
        await client.create_collection(
            _COLLECTION,
            vectors_config=VectorParams(size=4, distance=Distance.COSINE),
        )
        await client.upsert(
            _COLLECTION,
            points=[PointStruct(id=1, vector=_VECTOR)],
        )
        if hasattr(client, "query_points"):
            operation = "query_points"
            result = await client.query_points(
                _COLLECTION, query=_VECTOR, limit=1
            )
            count = len(result.points)
        else:
            operation = "search"
            result = await client.search(
                _COLLECTION, query_vector=_VECTOR, limit=1
            )
            count = len(result)
        await client.close()
        return operation, count

    operation, count = asyncio.run(_run())
    assert count == 1

    spans = span_exporter.get_finished_spans()

    upsert_span = _span_by_operation(spans, "upsert")
    assert upsert_span.kind is SpanKind.CLIENT
    assert upsert_span.attributes[DB_SYSTEM_NAME] == "qdrant"
    assert upsert_span.attributes[DB_COLLECTION_NAME] == _COLLECTION

    query_span = _span_by_operation(spans, operation)
    assert query_span.name == f"{operation} {_COLLECTION}"
    assert query_span.attributes[DB_OPERATION_NAME] == operation


def test_async_error_records_exception(instrument, span_exporter):
    async def _run():
        client = AsyncQdrantClient(":memory:")
        try:
            await client.get_collection("does_not_exist")
        finally:
            await client.close()

    with pytest.raises(ValueError):
        asyncio.run(_run())

    span = _span_by_operation(
        span_exporter.get_finished_spans(), "get_collection"
    )
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes[ERROR_TYPE] == "ValueError"


def test_async_upload_collection_runs_and_spans(instrument, span_exporter):
    async def _setup():
        client = AsyncQdrantClient(":memory:")
        await client.create_collection(
            _COLLECTION,
            vectors_config=VectorParams(size=4, distance=Distance.COSINE),
        )
        return client

    client = asyncio.run(_setup())

    # ``upload_collection`` is synchronous: calling it must run the upload
    # inline (not return an un-awaited coroutine) and emit a span.
    result = client.upload_collection(
        collection_name=_COLLECTION, vectors=[_VECTOR], ids=[1]
    )
    assert not asyncio.iscoroutine(result)

    span = _span_by_operation(
        span_exporter.get_finished_spans(), "upload_collection"
    )
    assert span.kind is SpanKind.CLIENT
    assert span.attributes[DB_COLLECTION_NAME] == _COLLECTION

    asyncio.run(client.close())
