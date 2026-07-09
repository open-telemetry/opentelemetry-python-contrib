# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Span-emitting wrappers for Marqo index operations.

The wrappers here emit generic OpenTelemetry database spans (``db.*``) using a
tracer directly. There is no util-genai handler for databases and no
vector-specific semantic conventions, so only the standard, well-established
database attributes are recorded. Vector-database-specific fields (such as the
number of documents, ``limit`` / ``top_k``, query vectors, or filters) are not
emitted because there is currently no stable semantic convention for them.
"""

from __future__ import annotations

from typing import Any, Callable

from opentelemetry import context as context_api
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_COLLECTION_NAME,
    DB_OPERATION_NAME,
    DB_SYSTEM_NAME,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.trace.status import Status, StatusCode

# There is no ``DbSystemNameValues`` enum member for Marqo, so we use the
# literal value recommended by the semantic conventions for otherwise-unlisted
# database systems.
_DB_SYSTEM_MARQO = "marqo"


def _collection_name_from_instance(instance: Any) -> str | None:
    """Extract the index name from a Marqo ``Index`` instance.

    A ``marqo.index.Index`` carries the index (collection) name on its
    ``index_name`` attribute.
    """
    index_name = getattr(instance, "index_name", None)
    if isinstance(index_name, str) and index_name:
        return index_name
    return None


def _span_name(operation: str, collection_name: str | None) -> str:
    if collection_name:
        return f"{operation} {collection_name}"
    return operation


def _set_attributes(
    span: Any, operation: str, collection_name: str | None
) -> None:
    span.set_attribute(DB_SYSTEM_NAME, _DB_SYSTEM_MARQO)
    span.set_attribute(DB_OPERATION_NAME, operation)
    if collection_name is not None:
        span.set_attribute(DB_COLLECTION_NAME, collection_name)


def _record_exception(span: Any, exc: BaseException) -> None:
    if span.is_recording():
        span.set_attribute(ERROR_TYPE, type(exc).__qualname__)
        span.record_exception(exc)
        span.set_status(Status(StatusCode.ERROR, str(exc)))


def _wrap(tracer: Tracer, operation: str) -> Callable[..., Any]:
    """Build a ``wrapt`` wrapper that emits a CLIENT span for ``operation``."""

    def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        collection_name = _collection_name_from_instance(instance)

        with tracer.start_as_current_span(
            _span_name(operation, collection_name),
            kind=SpanKind.CLIENT,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            if span.is_recording():
                _set_attributes(span, operation, collection_name)

            try:
                return wrapped(*args, **kwargs)
            except Exception as exc:
                _record_exception(span, exc)
                raise

    return wrapper
