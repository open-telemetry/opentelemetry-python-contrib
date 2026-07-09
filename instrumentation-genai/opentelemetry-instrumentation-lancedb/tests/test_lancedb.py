# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest

from opentelemetry.instrumentation.lancedb import LanceDBInstrumentor
from opentelemetry.instrumentation.lancedb._wrap import _wrap
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_COLLECTION_NAME,
    DB_OPERATION_NAME,
    DB_SYSTEM_NAME,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.trace import SpanKind, StatusCode, get_tracer

_COLLECTION = "mytable"
_VECTOR = [0.1, 0.2, 0.3, 0.4]


def _span_by_operation(spans, operation):
    for span in spans:
        if span.attributes.get(DB_OPERATION_NAME) == operation:
            return span
    raise AssertionError(f"no span for operation {operation!r}")


def test_search_span(instrument, lancedb_table, span_exporter):
    span_exporter.clear()

    result = lancedb_table.search(_VECTOR).limit(1).to_list()
    assert len(result) == 1

    spans = span_exporter.get_finished_spans()
    span = _span_by_operation(spans, "search")

    assert span.name == f"search {_COLLECTION}"
    assert span.kind is SpanKind.CLIENT

    attributes = span.attributes
    assert attributes[DB_SYSTEM_NAME] == "lancedb"
    assert isinstance(attributes[DB_SYSTEM_NAME], str)
    assert attributes[DB_OPERATION_NAME] == "search"
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


def test_add_span(instrument, lancedb_table, span_exporter):
    span_exporter.clear()

    lancedb_table.add([{"id": 3, "vector": [0.9, 0.1, 0.1, 0.1], "text": "c"}])

    spans = span_exporter.get_finished_spans()
    span = _span_by_operation(spans, "add")

    assert span.name == f"add {_COLLECTION}"
    assert span.kind is SpanKind.CLIENT
    assert span.attributes[DB_SYSTEM_NAME] == "lancedb"
    assert span.attributes[DB_OPERATION_NAME] == "add"
    assert span.attributes[DB_COLLECTION_NAME] == _COLLECTION


def test_delete_span(instrument, lancedb_table, span_exporter):
    span_exporter.clear()

    lancedb_table.delete("id = 1")

    spans = span_exporter.get_finished_spans()
    span = _span_by_operation(spans, "delete")

    assert span.name == f"delete {_COLLECTION}"
    assert span.kind is SpanKind.CLIENT
    assert span.attributes[DB_SYSTEM_NAME] == "lancedb"
    assert span.attributes[DB_OPERATION_NAME] == "delete"
    assert span.attributes[DB_COLLECTION_NAME] == _COLLECTION


def test_error_records_exception(instrument, lancedb_table, span_exporter):
    span_exporter.clear()

    # ``delete`` with a predicate referencing an unknown column raises inside
    # the wrapped call.
    with pytest.raises(Exception) as exc_info:
        lancedb_table.delete("nonexistent_column = 999")

    span = _span_by_operation(span_exporter.get_finished_spans(), "delete")
    assert span.kind is SpanKind.CLIENT
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes[ERROR_TYPE] == type(exc_info.value).__qualname__
    assert isinstance(span.attributes[ERROR_TYPE], str)
    assert span.attributes[DB_COLLECTION_NAME] == _COLLECTION
    # The original exception must be recorded as an event.
    assert any(event.name == "exception" for event in span.events)


def test_original_exception_is_reraised_unmodified(
    instrument, lancedb_table, span_exporter
):
    with pytest.raises(RuntimeError) as exc_info:
        lancedb_table.delete("nonexistent_column = 999")

    # The instrumentation must re-raise the original exception unchanged.
    assert isinstance(exc_info.value, RuntimeError)


def test_uninstrument_stops_spans(
    tracer_provider, lancedb_table, span_exporter
):
    instrumentor = LanceDBInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)
    lancedb_table.add([{"id": 4, "vector": [0.2, 0.2, 0.2, 0.2], "text": "d"}])
    assert span_exporter.get_finished_spans()

    span_exporter.clear()
    instrumentor.uninstrument()

    lancedb_table.add([{"id": 5, "vector": [0.3, 0.3, 0.3, 0.3], "text": "e"}])
    assert span_exporter.get_finished_spans() == ()


def test_wrap_error_path_directly(tracer_provider):
    """Unit-test the wrapper's error handling without a real table.

    This exercises the span error branch deterministically: the wrapped
    callable raises, and the wrapper must set ``error.type``, mark the span as
    errored, and re-raise the original exception unmodified.
    """
    tracer = get_tracer(__name__, tracer_provider=tracer_provider)
    exporter = tracer_provider._active_span_processor._span_processors[
        0
    ].span_exporter
    exporter.clear()

    class _FakeTable:
        name = _COLLECTION

    sentinel = KeyError("boom")

    def _raising(*args, **kwargs):
        raise sentinel

    wrapper = _wrap(tracer, "search")

    with pytest.raises(KeyError) as exc_info:
        wrapper(_raising, _FakeTable(), (), {})

    assert exc_info.value is sentinel

    (span,) = exporter.get_finished_spans()
    assert span.name == f"search {_COLLECTION}"
    assert span.kind is SpanKind.CLIENT
    assert span.attributes[DB_SYSTEM_NAME] == "lancedb"
    assert span.attributes[DB_OPERATION_NAME] == "search"
    assert span.attributes[DB_COLLECTION_NAME] == _COLLECTION
    assert span.attributes[ERROR_TYPE] == "KeyError"
    assert span.status.status_code is StatusCode.ERROR


def test_wrap_without_collection_name(tracer_provider):
    """When the instance has no usable ``name``, no collection attr is set."""
    tracer = get_tracer(__name__, tracer_provider=tracer_provider)
    exporter = tracer_provider._active_span_processor._span_processors[
        0
    ].span_exporter
    exporter.clear()

    class _NamelessTable:
        name = ""

    wrapper = _wrap(tracer, "add")
    wrapper(lambda *a, **k: "ok", _NamelessTable(), (), {})

    (span,) = exporter.get_finished_spans()
    assert span.name == "add"
    assert DB_COLLECTION_NAME not in span.attributes
    assert span.attributes[DB_OPERATION_NAME] == "add"
