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

"""Wrapper functions for Qdrant instrumentation (sync)."""

from __future__ import annotations

import logging
from typing import Any, Callable

from opentelemetry import context as context_api
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.trace.status import Status, StatusCode

from opentelemetry.instrumentation.qdrant.semconv import QdrantAttributes
from opentelemetry.instrumentation.qdrant.utils import (
    count_or_none,
    dont_throw,
    set_span_attribute,
)

logger = logging.getLogger(__name__)


@dont_throw
def _set_collection_name_attribute(span, method: str, args, kwargs: dict) -> None:
    """Set the collection name attribute."""
    collection_name = kwargs.get("collection_name")
    if collection_name is None and args:
        collection_name = args[0]
    set_span_attribute(span, QdrantAttributes.COLLECTION_NAME, collection_name)


@dont_throw
def _set_upsert_attributes(span, args, kwargs: dict) -> None:
    """Set span attributes for upsert operation."""
    points = kwargs.get("points")
    if points is None and len(args) > 1:
        points = args[1]

    if points is not None:
        if isinstance(points, list):
            length = len(points)
        else:
            # If using models.Batch instead of list[models.PointStruct]
            try:
                length = len(points.ids)
            except (AttributeError, TypeError):
                length = None
        if length is not None:
            set_span_attribute(span, QdrantAttributes.UPSERT_POINTS_COUNT, length)


@dont_throw
def _set_upload_attributes(
    span, args, kwargs: dict, method_name: str, param_name: str
) -> None:
    """Set span attributes for upload operations."""
    points = kwargs.get(param_name)
    if points is None and len(args) > 1:
        points = args[1]

    if points is not None:
        try:
            points_list = list(points)
            set_span_attribute(span, QdrantAttributes.UPLOAD_POINTS_COUNT, len(points_list))
        except (TypeError, ValueError):
            pass


@dont_throw
def _set_search_attributes(span, args, kwargs: dict) -> None:
    """Set span attributes for search operations."""
    limit = kwargs.get("limit", 10)
    set_span_attribute(span, QdrantAttributes.SEARCH_LIMIT, limit)


@dont_throw
def _set_batch_search_attributes(span, args, kwargs: dict, method: str) -> None:
    """Set span attributes for batch search operations."""
    requests = kwargs.get("requests", [])
    requests_count = count_or_none(requests)

    if method == "search_batch":
        set_span_attribute(span, QdrantAttributes.SEARCH_BATCH_REQUESTS_COUNT, requests_count)
    elif method == "query_batch":
        set_span_attribute(span, QdrantAttributes.QUERY_BATCH_REQUESTS_COUNT, requests_count)
    elif method == "discover_batch":
        set_span_attribute(span, QdrantAttributes.DISCOVER_BATCH_REQUESTS_COUNT, requests_count)
    elif method == "recommend_batch":
        set_span_attribute(span, QdrantAttributes.RECOMMEND_BATCH_REQUESTS_COUNT, requests_count)


def create_wrapper(
    tracer: Tracer,
    method_name: str,
    span_name: str,
) -> Callable:
    """Create a wrapper function for a Qdrant sync method."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            span_name,
            kind=SpanKind.CLIENT,
            attributes={
                SpanAttributes.DB_SYSTEM: "qdrant",
                SpanAttributes.DB_OPERATION: method_name,
            },
        ) as span:
            # Set collection name for all methods
            _set_collection_name_attribute(span, method_name, args, kwargs)

            # Set method-specific attributes
            if method_name == "upsert":
                _set_upsert_attributes(span, args, kwargs)
            elif method_name == "add":
                _set_upload_attributes(span, args, kwargs, method_name, "documents")
            elif method_name == "upload_points":
                _set_upload_attributes(span, args, kwargs, method_name, "points")
            elif method_name == "upload_records":
                _set_upload_attributes(span, args, kwargs, method_name, "records")
            elif method_name == "upload_collection":
                _set_upload_attributes(span, args, kwargs, method_name, "vectors")
            elif method_name in (
                "search",
                "search_groups",
                "query",
                "discover",
                "recommend",
                "recommend_groups",
            ):
                _set_search_attributes(span, args, kwargs)
            elif method_name in (
                "search_batch",
                "query_batch",
                "recommend_batch",
                "discover_batch",
            ):
                _set_batch_search_attributes(span, args, kwargs, method_name)

            # Execute the wrapped function
            response = wrapped(*args, **kwargs)

            if response:
                span.set_status(Status(StatusCode.OK))

            return response

    return wrapper
