# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from pymilvus.exceptions import MilvusException

from opentelemetry.instrumentation.milvus import MilvusInstrumentor
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
    client.create_collection(_COLLECTION, dimension=4)


def _insert_point(client) -> None:
    client.insert(_COLLECTION, data=[{"id": 1, "vector": _VECTOR}])


def _span_by_operation(spans, operation):
    for span in spans:
        if span.attributes.get(DB_OPERATION_NAME) == operation:
            return span
    raise AssertionError(f"no span for operation {operation!r}")


def test_create_collection_span(instrument, milvus_client, span_exporter):
    _create_collection(milvus_client)

    spans = span_exporter.get_finished_spans()
    span = _span_by_operation(spans, "create_collection")

    assert span.name == f"create_collection {_COLLECTION}"
    assert span.kind is SpanKind.CLIENT

    attributes = span.attributes
    assert attributes[DB_SYSTEM_NAME] == "milvus"
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


def test_insert_span(instrument, milvus_client, span_exporter):
    _create_collection(milvus_client)
    span_exporter.clear()

    _insert_point(milvus_client)

    spans = span_exporter.get_finished_spans()
    span = _span_by_operation(spans, "insert")

    assert span.name == f"insert {_COLLECTION}"
    assert span.kind is SpanKind.CLIENT
    assert span.attributes[DB_SYSTEM_NAME] == "milvus"
    assert span.attributes[DB_OPERATION_NAME] == "insert"
    assert span.attributes[DB_COLLECTION_NAME] == _COLLECTION


def test_upsert_span(instrument, milvus_client, span_exporter):
    _create_collection(milvus_client)
    span_exporter.clear()

    milvus_client.upsert(_COLLECTION, data=[{"id": 1, "vector": _VECTOR}])

    spans = span_exporter.get_finished_spans()
    span = _span_by_operation(spans, "upsert")

    assert span.name == f"upsert {_COLLECTION}"
    assert span.kind is SpanKind.CLIENT
    assert span.attributes[DB_SYSTEM_NAME] == "milvus"
    assert span.attributes[DB_OPERATION_NAME] == "upsert"
    assert span.attributes[DB_COLLECTION_NAME] == _COLLECTION


def test_search_span(instrument, milvus_client, span_exporter):
    _create_collection(milvus_client)
    _insert_point(milvus_client)
    span_exporter.clear()

    result = milvus_client.search(_COLLECTION, data=[_VECTOR], limit=1)
    assert len(result) == 1

    spans = span_exporter.get_finished_spans()
    span = _span_by_operation(spans, "search")

    assert span.name == f"search {_COLLECTION}"
    assert span.kind is SpanKind.CLIENT
    assert span.attributes[DB_SYSTEM_NAME] == "milvus"
    assert span.attributes[DB_OPERATION_NAME] == "search"
    assert span.attributes[DB_COLLECTION_NAME] == _COLLECTION


def test_query_span(instrument, milvus_client, span_exporter):
    _create_collection(milvus_client)
    _insert_point(milvus_client)
    span_exporter.clear()

    result = milvus_client.query(_COLLECTION, filter="id == 1")
    assert len(result) == 1

    spans = span_exporter.get_finished_spans()
    span = _span_by_operation(spans, "query")

    assert span.name == f"query {_COLLECTION}"
    assert span.kind is SpanKind.CLIENT
    assert span.attributes[DB_SYSTEM_NAME] == "milvus"
    assert span.attributes[DB_OPERATION_NAME] == "query"
    assert span.attributes[DB_COLLECTION_NAME] == _COLLECTION


def test_get_and_delete_spans(instrument, milvus_client, span_exporter):
    _create_collection(milvus_client)
    _insert_point(milvus_client)
    span_exporter.clear()

    milvus_client.get(_COLLECTION, ids=[1])
    milvus_client.delete(_COLLECTION, ids=[1])

    spans = span_exporter.get_finished_spans()

    get_span = _span_by_operation(spans, "get")
    assert get_span.name == f"get {_COLLECTION}"
    assert get_span.kind is SpanKind.CLIENT
    assert get_span.attributes[DB_COLLECTION_NAME] == _COLLECTION

    delete_span = _span_by_operation(spans, "delete")
    assert delete_span.name == f"delete {_COLLECTION}"
    assert delete_span.kind is SpanKind.CLIENT
    assert delete_span.attributes[DB_OPERATION_NAME] == "delete"


def test_collection_name_from_positional_arg(
    instrument, milvus_client, span_exporter
):
    _create_collection(milvus_client)
    _insert_point(milvus_client)
    span_exporter.clear()

    # Pass collection name positionally rather than as a keyword.
    milvus_client.query(_COLLECTION, filter="id == 1")

    span = _span_by_operation(span_exporter.get_finished_spans(), "query")
    assert span.attributes[DB_COLLECTION_NAME] == _COLLECTION
    assert span.name == f"query {_COLLECTION}"


def test_collection_name_from_kwarg(instrument, milvus_client, span_exporter):
    _create_collection(milvus_client)
    _insert_point(milvus_client)
    span_exporter.clear()

    # Pass collection name as a keyword rather than positionally.
    milvus_client.query(collection_name=_COLLECTION, filter="id == 1")

    span = _span_by_operation(span_exporter.get_finished_spans(), "query")
    assert span.attributes[DB_COLLECTION_NAME] == _COLLECTION
    assert span.name == f"query {_COLLECTION}"


def test_error_records_exception(instrument, milvus_client, span_exporter):
    with pytest.raises(MilvusException):
        milvus_client.search("does_not_exist", data=[_VECTOR], limit=1)

    span = _span_by_operation(span_exporter.get_finished_spans(), "search")
    assert span.kind is SpanKind.CLIENT
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes[ERROR_TYPE] == "MilvusException"
    assert isinstance(span.attributes[ERROR_TYPE], str)
    assert span.attributes[DB_COLLECTION_NAME] == "does_not_exist"
    # The original exception must be recorded as an event.
    assert any(event.name == "exception" for event in span.events)


def test_original_exception_is_reraised_unmodified(
    instrument, milvus_client, span_exporter
):
    with pytest.raises(MilvusException) as exc_info:
        milvus_client.search("missing", data=[_VECTOR], limit=1)

    # The instrumentation must re-raise the original exception unchanged.
    assert isinstance(exc_info.value, MilvusException)


def test_uninstrument_stops_spans(
    tracer_provider, milvus_client, span_exporter
):
    instrumentor = MilvusInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)
    _create_collection(milvus_client)
    assert span_exporter.get_finished_spans()

    span_exporter.clear()
    instrumentor.uninstrument()

    milvus_client.insert(_COLLECTION, data=[{"id": 2, "vector": _VECTOR}])
    assert span_exporter.get_finished_spans() == ()
