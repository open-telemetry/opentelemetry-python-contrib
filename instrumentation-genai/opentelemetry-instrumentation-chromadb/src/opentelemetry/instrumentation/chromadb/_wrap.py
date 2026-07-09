# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Span-emitting wrappers for ChromaDB operations.

The wrappers here emit generic OpenTelemetry database spans (``db.*``) using a
tracer directly. There is no util-genai handler for databases and no
vector-specific semantic conventions, so only the standard, well-established
database attributes are recorded.
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

# There is no DbSystemNameValues enum member for ChromaDB, so we use the
# literal value recommended by the semantic conventions for otherwise-unlisted
# database systems.
_DB_SYSTEM_CHROMADB = "chromadb"


def _collection_name(instance: Any) -> str | None:
    """Best-effort extraction of the collection name from the wrapped instance.

    ``chromadb.api.models.Collection.Collection`` exposes a ``name`` attribute.
    Client-level operations pass the collection name as an argument instead, so
    this returns ``None`` for those and the caller supplies the name.
    """
    name = getattr(instance, "name", None)
    if isinstance(name, str):
        return name
    return None


def _span_name(operation: str, collection_name: str | None) -> str:
    if collection_name:
        return f"{operation} {collection_name}"
    return operation


def _wrap(
    tracer: Tracer,
    operation: str,
    collection_name_from_args: Callable[[Any, Any], str | None] | None = None,
) -> Callable[..., Any]:
    """Build a ``wrapt`` wrapper that emits a CLIENT span for ``operation``.

    ``collection_name_from_args`` is an optional callable used for client-level
    operations where the collection name is passed as an argument rather than
    being an attribute of the wrapped instance.
    """

    def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        collection_name = _collection_name(instance)
        if collection_name is None and collection_name_from_args is not None:
            collection_name = collection_name_from_args(args, kwargs)

        with tracer.start_as_current_span(
            _span_name(operation, collection_name),
            kind=SpanKind.CLIENT,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            if span.is_recording():
                span.set_attribute(DB_SYSTEM_NAME, _DB_SYSTEM_CHROMADB)
                span.set_attribute(DB_OPERATION_NAME, operation)
                if collection_name is not None:
                    span.set_attribute(DB_COLLECTION_NAME, collection_name)

            try:
                return wrapped(*args, **kwargs)
            except Exception as exc:
                if span.is_recording():
                    span.set_attribute(ERROR_TYPE, type(exc).__qualname__)
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise

    return wrapper


def _collection_name_from_create_args(
    args: tuple[Any, ...], kwargs: dict[str, Any]
) -> str | None:
    """Extract the collection name for client ``*_collection`` operations.

    These methods accept the collection name as the first positional argument
    or as the ``name`` keyword argument.
    """
    if "name" in kwargs and isinstance(kwargs["name"], str):
        return kwargs["name"]
    if args and isinstance(args[0], str):
        return args[0]
    return None
