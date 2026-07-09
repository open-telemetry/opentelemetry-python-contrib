# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the Weaviate instrumentation.

The ``weaviate-client`` v4 API needs a running gRPC/HTTP server to construct a
real client, so these tests exercise the span-emitting wrapper directly with
fake ``wrapped`` / ``instance`` objects instead of connecting to a server.
"""

from __future__ import annotations

from typing import Any

import pytest
from weaviate.collections.collections import _Collections

from opentelemetry.instrumentation.weaviate import WeaviateInstrumentor
from opentelemetry.instrumentation.weaviate._wrap import _wrap
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_COLLECTION_NAME,
    DB_OPERATION_NAME,
    DB_SYSTEM_NAME,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.trace import SpanKind, StatusCode

_COLLECTION = "MyCollection"


class _FakeInstance:
    """Stand-in for a ``_Collections`` instance."""


def _make_wrapped(return_value: Any):
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        return return_value

    return wrapped


def _make_raising_wrapped(exc: BaseException):
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        raise exc

    return wrapped


def _single_span(span_exporter):
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    return spans[0]


def test_create_span_name_in_positional_arg(tracer_provider, span_exporter):
    tracer = tracer_provider.get_tracer(__name__)
    wrapper = _wrap(tracer, "create")

    result = wrapper(
        _make_wrapped("created"),
        _FakeInstance(),
        args=(_COLLECTION,),
        kwargs={},
    )
    assert result == "created"

    span = _single_span(span_exporter)
    assert span.name == f"create {_COLLECTION}"
    assert span.kind is SpanKind.CLIENT

    attributes = span.attributes
    assert attributes[DB_SYSTEM_NAME] == "weaviate"
    assert isinstance(attributes[DB_SYSTEM_NAME], str)
    assert attributes[DB_OPERATION_NAME] == "create"
    assert isinstance(attributes[DB_OPERATION_NAME], str)
    assert attributes[DB_COLLECTION_NAME] == _COLLECTION
    assert isinstance(attributes[DB_COLLECTION_NAME], str)

    # Only the standard database attributes must be present.
    assert set(attributes) == {
        DB_SYSTEM_NAME,
        DB_OPERATION_NAME,
        DB_COLLECTION_NAME,
    }
    assert span.status.status_code is not StatusCode.ERROR


def test_get_span_name_in_kwarg(tracer_provider, span_exporter):
    tracer = tracer_provider.get_tracer(__name__)
    wrapper = _wrap(tracer, "get")

    wrapper(
        _make_wrapped(object()),
        _FakeInstance(),
        args=(),
        kwargs={"name": _COLLECTION},
    )

    span = _single_span(span_exporter)
    assert span.name == f"get {_COLLECTION}"
    assert span.kind is SpanKind.CLIENT
    assert span.attributes[DB_SYSTEM_NAME] == "weaviate"
    assert span.attributes[DB_OPERATION_NAME] == "get"
    assert span.attributes[DB_COLLECTION_NAME] == _COLLECTION


def test_exists_span_name_in_positional_arg(tracer_provider, span_exporter):
    tracer = tracer_provider.get_tracer(__name__)
    wrapper = _wrap(tracer, "exists")

    result = wrapper(
        _make_wrapped(True),
        _FakeInstance(),
        args=(_COLLECTION,),
        kwargs={},
    )
    assert result is True

    span = _single_span(span_exporter)
    assert span.name == f"exists {_COLLECTION}"
    assert span.attributes[DB_OPERATION_NAME] == "exists"
    assert span.attributes[DB_COLLECTION_NAME] == _COLLECTION


def test_delete_span_name_in_kwarg(tracer_provider, span_exporter):
    tracer = tracer_provider.get_tracer(__name__)
    wrapper = _wrap(tracer, "delete")

    wrapper(
        _make_wrapped(None),
        _FakeInstance(),
        args=(),
        kwargs={"name": _COLLECTION},
    )

    span = _single_span(span_exporter)
    assert span.name == f"delete {_COLLECTION}"
    assert span.attributes[DB_OPERATION_NAME] == "delete"
    assert span.attributes[DB_COLLECTION_NAME] == _COLLECTION


def test_delete_all_span_without_collection_name(
    tracer_provider, span_exporter
):
    tracer = tracer_provider.get_tracer(__name__)
    wrapper = _wrap(tracer, "delete_all")

    wrapper(
        _make_wrapped(None),
        _FakeInstance(),
        args=(),
        kwargs={},
    )

    span = _single_span(span_exporter)
    # No single collection name for ``delete_all``.
    assert span.name == "delete_all"
    assert span.kind is SpanKind.CLIENT
    assert span.attributes[DB_SYSTEM_NAME] == "weaviate"
    assert span.attributes[DB_OPERATION_NAME] == "delete_all"
    assert DB_COLLECTION_NAME not in span.attributes


def test_list_all_span_without_collection_name(tracer_provider, span_exporter):
    tracer = tracer_provider.get_tracer(__name__)
    wrapper = _wrap(tracer, "list_all")

    wrapper(
        _make_wrapped({}),
        _FakeInstance(),
        args=(True,),
        kwargs={},
    )

    span = _single_span(span_exporter)
    # ``list_all``'s first positional arg is a bool (``simple``), not a name.
    assert span.name == "list_all"
    assert span.attributes[DB_OPERATION_NAME] == "list_all"
    assert DB_COLLECTION_NAME not in span.attributes


def test_create_from_dict_span_without_collection_name(
    tracer_provider, span_exporter
):
    tracer = tracer_provider.get_tracer(__name__)
    wrapper = _wrap(tracer, "create_from_dict")

    # ``create_from_dict``'s first positional arg is a ``dict`` config, so no
    # collection name is extracted.
    wrapper(
        _make_wrapped(object()),
        _FakeInstance(),
        args=({"class": _COLLECTION},),
        kwargs={},
    )

    span = _single_span(span_exporter)
    assert span.name == "create_from_dict"
    assert span.attributes[DB_OPERATION_NAME] == "create_from_dict"
    assert DB_COLLECTION_NAME not in span.attributes


def test_error_records_exception_and_reraises(tracer_provider, span_exporter):
    tracer = tracer_provider.get_tracer(__name__)
    wrapper = _wrap(tracer, "create")

    original = ValueError("boom")
    with pytest.raises(ValueError) as exc_info:
        wrapper(
            _make_raising_wrapped(original),
            _FakeInstance(),
            args=(_COLLECTION,),
            kwargs={},
        )

    # The original exception must be re-raised unmodified.
    assert exc_info.value is original

    span = _single_span(span_exporter)
    assert span.kind is SpanKind.CLIENT
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes[ERROR_TYPE] == "ValueError"
    assert isinstance(span.attributes[ERROR_TYPE], str)
    assert span.attributes[DB_COLLECTION_NAME] == _COLLECTION
    # The exception must be recorded as an event.
    assert any(event.name == "exception" for event in span.events)


def test_instrument_wraps_collections_methods(instrument):
    # After instrumentation the wrapped methods carry the wrapt marker. The
    # ``instrument`` fixture handles uninstrumentation on teardown.
    assert hasattr(_Collections.create, "__wrapped__")
    assert hasattr(_Collections.delete_all, "__wrapped__")


def test_uninstrument_removes_wrappers(tracer_provider):
    instrumentor = WeaviateInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)
    assert hasattr(_Collections.create, "__wrapped__")

    instrumentor.uninstrument()
    assert not hasattr(_Collections.create, "__wrapped__")
    assert not hasattr(_Collections.delete_all, "__wrapped__")
