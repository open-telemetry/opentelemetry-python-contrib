# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Wrapper functions for ChromaDB instrumentation."""

from __future__ import annotations

import json
import logging
from itertools import zip_longest
from typing import Any, Callable, Optional

from opentelemetry import context as context_api
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import SpanKind, Tracer

from opentelemetry.instrumentation.chromadb.semconv import (
    ChromaDBAttributes,
    EventAttributes,
    Events,
)
from opentelemetry.instrumentation.chromadb.utils import (
    count_or_none,
    dont_throw,
    to_string_or_none,
)

logger = logging.getLogger(__name__)


def _set_span_attribute(span, name: str, value: Any) -> None:
    """Set a span attribute if the value is not None or empty."""
    if value is not None and value != "":
        span.set_attribute(name, value)


@dont_throw
def _set_add_attributes(span, kwargs: dict) -> None:
    """Set span attributes for add operation."""
    _set_span_attribute(
        span, ChromaDBAttributes.ADD_IDS_COUNT, count_or_none(kwargs.get("ids"))
    )
    _set_span_attribute(
        span,
        ChromaDBAttributes.ADD_EMBEDDINGS_COUNT,
        count_or_none(kwargs.get("embeddings")),
    )
    _set_span_attribute(
        span,
        ChromaDBAttributes.ADD_METADATAS_COUNT,
        count_or_none(kwargs.get("metadatas")),
    )
    _set_span_attribute(
        span,
        ChromaDBAttributes.ADD_DOCUMENTS_COUNT,
        count_or_none(kwargs.get("documents")),
    )


@dont_throw
def _set_get_attributes(span, kwargs: dict) -> None:
    """Set span attributes for get operation."""
    _set_span_attribute(
        span, ChromaDBAttributes.GET_IDS_COUNT, count_or_none(kwargs.get("ids"))
    )
    _set_span_attribute(
        span, ChromaDBAttributes.GET_WHERE, to_string_or_none(kwargs.get("where"))
    )
    _set_span_attribute(span, ChromaDBAttributes.GET_LIMIT, kwargs.get("limit"))
    _set_span_attribute(span, ChromaDBAttributes.GET_OFFSET, kwargs.get("offset"))
    _set_span_attribute(
        span,
        ChromaDBAttributes.GET_WHERE_DOCUMENT,
        to_string_or_none(kwargs.get("where_document")),
    )
    _set_span_attribute(
        span, ChromaDBAttributes.GET_INCLUDE, to_string_or_none(kwargs.get("include"))
    )


@dont_throw
def _set_peek_attributes(span, kwargs: dict) -> None:
    """Set span attributes for peek operation."""
    _set_span_attribute(span, ChromaDBAttributes.PEEK_LIMIT, kwargs.get("limit"))


@dont_throw
def _set_query_attributes(span, kwargs: dict) -> None:
    """Set span attributes for query operation."""
    _set_span_attribute(
        span,
        ChromaDBAttributes.QUERY_EMBEDDINGS_COUNT,
        count_or_none(kwargs.get("query_embeddings")),
    )
    _set_span_attribute(
        span,
        ChromaDBAttributes.QUERY_TEXTS_COUNT,
        count_or_none(kwargs.get("query_texts")),
    )
    _set_span_attribute(
        span, ChromaDBAttributes.QUERY_N_RESULTS, kwargs.get("n_results")
    )
    _set_span_attribute(
        span, ChromaDBAttributes.QUERY_WHERE, to_string_or_none(kwargs.get("where"))
    )
    _set_span_attribute(
        span,
        ChromaDBAttributes.QUERY_WHERE_DOCUMENT,
        to_string_or_none(kwargs.get("where_document")),
    )
    _set_span_attribute(
        span, ChromaDBAttributes.QUERY_INCLUDE, to_string_or_none(kwargs.get("include"))
    )


@dont_throw
def _set_modify_attributes(span, kwargs: dict) -> None:
    """Set span attributes for modify operation."""
    _set_span_attribute(span, ChromaDBAttributes.MODIFY_NAME, kwargs.get("name"))


@dont_throw
def _set_update_attributes(span, kwargs: dict) -> None:
    """Set span attributes for update operation."""
    _set_span_attribute(
        span, ChromaDBAttributes.UPDATE_IDS_COUNT, count_or_none(kwargs.get("ids"))
    )
    _set_span_attribute(
        span,
        ChromaDBAttributes.UPDATE_EMBEDDINGS_COUNT,
        count_or_none(kwargs.get("embeddings")),
    )
    _set_span_attribute(
        span,
        ChromaDBAttributes.UPDATE_METADATAS_COUNT,
        count_or_none(kwargs.get("metadatas")),
    )
    _set_span_attribute(
        span,
        ChromaDBAttributes.UPDATE_DOCUMENTS_COUNT,
        count_or_none(kwargs.get("documents")),
    )


@dont_throw
def _set_upsert_attributes(span, kwargs: dict) -> None:
    """Set span attributes for upsert operation."""
    _set_span_attribute(
        span,
        ChromaDBAttributes.UPSERT_EMBEDDINGS_COUNT,
        count_or_none(kwargs.get("embeddings")),
    )
    _set_span_attribute(
        span,
        ChromaDBAttributes.UPSERT_METADATAS_COUNT,
        count_or_none(kwargs.get("metadatas")),
    )
    _set_span_attribute(
        span,
        ChromaDBAttributes.UPSERT_DOCUMENTS_COUNT,
        count_or_none(kwargs.get("documents")),
    )


@dont_throw
def _set_delete_attributes(span, kwargs: dict) -> None:
    """Set span attributes for delete operation."""
    _set_span_attribute(
        span, ChromaDBAttributes.DELETE_IDS_COUNT, count_or_none(kwargs.get("ids"))
    )
    _set_span_attribute(
        span, ChromaDBAttributes.DELETE_WHERE, to_string_or_none(kwargs.get("where"))
    )
    _set_span_attribute(
        span,
        ChromaDBAttributes.DELETE_WHERE_DOCUMENT,
        to_string_or_none(kwargs.get("where_document")),
    )


@dont_throw
def _set_segment_query_attributes(span, kwargs: dict) -> None:
    """Set span attributes for segment _query operation."""
    collection_id = kwargs.get("collection_id")
    if collection_id:
        _set_span_attribute(
            span, ChromaDBAttributes.QUERY_SEGMENT_COLLECTION_ID, str(collection_id)
        )


@dont_throw
def _add_query_result_events(span, result: Any) -> None:
    """Add events for query results."""
    if result is None:
        return

    # ChromaDB query returns a dict with ids, distances, metadatas, documents
    ids = result.get("ids", [[]])[0] if isinstance(result, dict) else []
    distances = result.get("distances", [[]])[0] if isinstance(result, dict) else []
    metadatas = result.get("metadatas", [[]])[0] if isinstance(result, dict) else []
    documents = result.get("documents", [[]])[0] if isinstance(result, dict) else []

    for id_val, distance, metadata, document in zip_longest(
        ids, distances, metadatas, documents
    ):
        event_attributes = {}

        if id_val is not None:
            event_attributes[EventAttributes.DB_QUERY_RESULT_ID] = str(id_val)

        if distance is not None:
            event_attributes[EventAttributes.DB_QUERY_RESULT_DISTANCE] = float(distance)

        if metadata is not None:
            if isinstance(metadata, dict):
                event_attributes[EventAttributes.DB_QUERY_RESULT_METADATA] = json.dumps(
                    metadata
                )
            else:
                event_attributes[EventAttributes.DB_QUERY_RESULT_METADATA] = str(
                    metadata
                )

        if document is not None:
            event_attributes[EventAttributes.DB_QUERY_RESULT_DOCUMENT] = str(document)

        if event_attributes:
            span.add_event(Events.DB_QUERY_RESULT, attributes=event_attributes)


@dont_throw
def _add_query_embeddings_events(span, kwargs: dict) -> None:
    """Add events for query embeddings (used in segment _query)."""
    embeddings = kwargs.get("query_embeddings")
    if embeddings:
        for embedding in embeddings:
            try:
                vector_str = json.dumps(list(embedding))
                span.add_event(
                    Events.DB_QUERY_EMBEDDINGS,
                    attributes={EventAttributes.DB_QUERY_EMBEDDINGS_VECTOR: vector_str},
                )
            except (TypeError, ValueError):
                pass


# Map of method names to attribute setter functions
ATTRIBUTE_SETTERS = {
    "add": _set_add_attributes,
    "get": _set_get_attributes,
    "peek": _set_peek_attributes,
    "query": _set_query_attributes,
    "modify": _set_modify_attributes,
    "update": _set_update_attributes,
    "upsert": _set_upsert_attributes,
    "delete": _set_delete_attributes,
    "_query": _set_segment_query_attributes,
}


def create_wrapper(
    tracer: Tracer,
    method_name: str,
    span_name: str,
) -> Callable:
    """Create a wrapper function for a ChromaDB method."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            span_name,
            kind=SpanKind.CLIENT,
            attributes={
                SpanAttributes.DB_SYSTEM: "chromadb",
                SpanAttributes.DB_OPERATION: method_name,
            },
        ) as span:
            # Set method-specific attributes
            if method_name in ATTRIBUTE_SETTERS:
                ATTRIBUTE_SETTERS[method_name](span, kwargs)

            # For segment _query, also add embeddings events
            if method_name == "_query":
                _add_query_embeddings_events(span, kwargs)

            # Execute the wrapped function
            result = wrapped(*args, **kwargs)

            # For query method, add result events
            if method_name == "query":
                _add_query_result_events(span, result)

            return result

    return wrapper
