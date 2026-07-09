# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the Marqo instrumentation.

Marqo ``Index`` methods make HTTP calls to a running Marqo server, so these
tests do not hit the network. They exercise the span-emitting wrapper directly
with fake ``wrapped`` callables and a fake ``Index`` instance, and verify that
the instrumentor wraps/unwraps the real ``marqo.index.Index`` methods.
"""

from __future__ import annotations

from typing import Any

import pytest
from marqo.index import Index

from opentelemetry.instrumentation.marqo import MarqoInstrumentor
from opentelemetry.instrumentation.marqo._wrap import _wrap
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_COLLECTION_NAME,
    DB_OPERATION_NAME,
    DB_SYSTEM_NAME,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.trace import SpanKind, StatusCode, get_tracer

_INDEX_NAME = "my-index"


class _FakeIndex:
    """Stand-in for ``marqo.index.Index`` carrying an ``index_name``."""

    def __init__(self, index_name: str | None = _INDEX_NAME) -> None:
        self.index_name = index_name


def _call_wrapped(
    tracer_provider: Any,
    operation: str,
    *,
    instance: Any,
    result: Any = None,
    error: BaseException | None = None,
) -> Any:
    tracer = get_tracer(__name__, tracer_provider=tracer_provider)
    wrapper = _wrap(tracer, operation)

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        if error is not None:
            raise error
        return result

    return wrapper(wrapped, instance, (), {})


def _span_by_operation(spans, operation):
    for span in spans:
        if span.attributes.get(DB_OPERATION_NAME) == operation:
            return span
    raise AssertionError(f"no span for operation {operation!r}")


@pytest.mark.parametrize(
    "operation",
    ["add_documents", "search", "delete_documents"],
)
def test_operation_span(tracer_provider, span_exporter, operation):
    canned = {"result": "ok"}
    returned = _call_wrapped(
        tracer_provider,
        operation,
        instance=_FakeIndex(),
        result=canned,
    )
    assert returned is canned

    spans = span_exporter.get_finished_spans()
    span = _span_by_operation(spans, operation)

    assert span.name == f"{operation} {_INDEX_NAME}"
    assert span.kind is SpanKind.CLIENT

    attributes = span.attributes
    assert attributes[DB_SYSTEM_NAME] == "marqo"
    assert isinstance(attributes[DB_SYSTEM_NAME], str)
    assert attributes[DB_OPERATION_NAME] == operation
    assert isinstance(attributes[DB_OPERATION_NAME], str)
    assert attributes[DB_COLLECTION_NAME] == _INDEX_NAME
    assert isinstance(attributes[DB_COLLECTION_NAME], str)

    # No vector-specific attributes should be emitted.
    assert set(attributes) == {
        DB_SYSTEM_NAME,
        DB_OPERATION_NAME,
        DB_COLLECTION_NAME,
    }
    assert span.status.status_code is not StatusCode.ERROR


def test_span_name_without_collection(tracer_provider, span_exporter):
    _call_wrapped(
        tracer_provider,
        "search",
        instance=_FakeIndex(index_name=None),
        result={},
    )

    span = _span_by_operation(span_exporter.get_finished_spans(), "search")
    assert span.name == "search"
    assert DB_COLLECTION_NAME not in span.attributes
    assert span.attributes[DB_SYSTEM_NAME] == "marqo"


def test_error_records_exception(tracer_provider, span_exporter):
    original = ValueError("boom")

    with pytest.raises(ValueError) as exc_info:
        _call_wrapped(
            tracer_provider,
            "add_documents",
            instance=_FakeIndex(),
            error=original,
        )

    # The original exception must be re-raised unmodified.
    assert exc_info.value is original

    span = _span_by_operation(
        span_exporter.get_finished_spans(), "add_documents"
    )
    assert span.kind is SpanKind.CLIENT
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes[ERROR_TYPE] == "ValueError"
    assert isinstance(span.attributes[ERROR_TYPE], str)
    assert span.attributes[DB_COLLECTION_NAME] == _INDEX_NAME
    # The original exception must be recorded as an event.
    assert any(event.name == "exception" for event in span.events)


def test_instrument_wraps_index_methods(instrument):
    for method in ("add_documents", "search", "delete_documents"):
        assert hasattr(getattr(Index, method), "__wrapped__")


def test_uninstrument_unwraps_index_methods(tracer_provider):
    instrumentor = MarqoInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)
    assert hasattr(Index.search, "__wrapped__")

    instrumentor.uninstrument()
    for method in ("add_documents", "search", "delete_documents"):
        assert not hasattr(getattr(Index, method), "__wrapped__")
