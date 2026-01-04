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

"""Wrapper functions for Milvus instrumentation."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

from opentelemetry import context as context_api
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.trace import SpanKind, Tracer

from opentelemetry.instrumentation.milvus.semconv import (
    EventAttributes,
    Events,
    MilvusAttributes,
)
from opentelemetry.instrumentation.milvus.utils import (
    count_or_none,
    dont_throw,
    set_span_attribute,
    to_string_or_none,
)

logger = logging.getLogger(__name__)


@dont_throw
def _set_create_collection_attributes(span, kwargs: dict) -> None:
    """Set span attributes for create_collection operation."""
    set_span_attribute(
        span, MilvusAttributes.CREATE_COLLECTION_NAME, kwargs.get("collection_name")
    )
    set_span_attribute(
        span, MilvusAttributes.CREATE_COLLECTION_DIMENSION, kwargs.get("dimension")
    )
    set_span_attribute(
        span,
        MilvusAttributes.CREATE_COLLECTION_PRIMARY_FIELD,
        kwargs.get("primary_field_name"),
    )
    set_span_attribute(
        span, MilvusAttributes.CREATE_COLLECTION_METRIC_TYPE, kwargs.get("metric_type")
    )
    set_span_attribute(
        span, MilvusAttributes.CREATE_COLLECTION_TIMEOUT, kwargs.get("timeout")
    )
    set_span_attribute(
        span, MilvusAttributes.CREATE_COLLECTION_ID_TYPE, kwargs.get("id_type")
    )
    set_span_attribute(
        span,
        MilvusAttributes.CREATE_COLLECTION_VECTOR_FIELD,
        kwargs.get("vector_field_name"),
    )


@dont_throw
def _set_insert_attributes(span, kwargs: dict) -> None:
    """Set span attributes for insert operation."""
    set_span_attribute(
        span, MilvusAttributes.INSERT_COLLECTION_NAME, kwargs.get("collection_name")
    )
    set_span_attribute(
        span, MilvusAttributes.INSERT_DATA_COUNT, count_or_none(kwargs.get("data"))
    )
    set_span_attribute(span, MilvusAttributes.INSERT_TIMEOUT, kwargs.get("timeout"))
    set_span_attribute(
        span,
        MilvusAttributes.INSERT_PARTITION_NAME,
        to_string_or_none(kwargs.get("partition_name")),
    )


@dont_throw
def _set_upsert_attributes(span, kwargs: dict) -> None:
    """Set span attributes for upsert operation."""
    set_span_attribute(
        span, MilvusAttributes.UPSERT_COLLECTION_NAME, kwargs.get("collection_name")
    )
    set_span_attribute(
        span, MilvusAttributes.UPSERT_DATA_COUNT, count_or_none(kwargs.get("data"))
    )
    set_span_attribute(span, MilvusAttributes.UPSERT_TIMEOUT, kwargs.get("timeout"))
    set_span_attribute(
        span,
        MilvusAttributes.UPSERT_PARTITION_NAME,
        to_string_or_none(kwargs.get("partition_name")),
    )


@dont_throw
def _set_delete_attributes(span, kwargs: dict) -> None:
    """Set span attributes for delete operation."""
    set_span_attribute(
        span, MilvusAttributes.DELETE_COLLECTION_NAME, kwargs.get("collection_name")
    )
    set_span_attribute(span, MilvusAttributes.DELETE_TIMEOUT, kwargs.get("timeout"))
    set_span_attribute(
        span,
        MilvusAttributes.DELETE_PARTITION_NAME,
        to_string_or_none(kwargs.get("partition_name")),
    )
    set_span_attribute(
        span, MilvusAttributes.DELETE_IDS_COUNT, count_or_none(kwargs.get("ids"))
    )
    set_span_attribute(
        span, MilvusAttributes.DELETE_FILTER, to_string_or_none(kwargs.get("filter"))
    )


@dont_throw
def _set_search_attributes(span, kwargs: dict) -> None:
    """Set span attributes for search operation."""
    set_span_attribute(
        span, MilvusAttributes.SEARCH_COLLECTION_NAME, kwargs.get("collection_name")
    )
    set_span_attribute(
        span, MilvusAttributes.SEARCH_DATA_COUNT, count_or_none(kwargs.get("data"))
    )
    set_span_attribute(span, MilvusAttributes.SEARCH_FILTER, kwargs.get("filter"))
    set_span_attribute(span, MilvusAttributes.SEARCH_LIMIT, kwargs.get("limit"))
    set_span_attribute(
        span,
        MilvusAttributes.SEARCH_OUTPUT_FIELDS_COUNT,
        count_or_none(kwargs.get("output_fields")),
    )
    set_span_attribute(
        span, MilvusAttributes.SEARCH_PARAMS, to_string_or_none(kwargs.get("search_params"))
    )
    set_span_attribute(span, MilvusAttributes.SEARCH_TIMEOUT, kwargs.get("timeout"))
    set_span_attribute(
        span,
        MilvusAttributes.SEARCH_PARTITION_NAMES_COUNT,
        count_or_none(kwargs.get("partition_names")),
    )
    set_span_attribute(span, MilvusAttributes.SEARCH_ANNS_FIELD, kwargs.get("anns_field"))
    set_span_attribute(
        span,
        MilvusAttributes.SEARCH_PARTITION_NAMES,
        to_string_or_none(kwargs.get("partition_names")),
    )

    # Set query vector dimensions
    query_vectors = kwargs.get("data", [])
    if query_vectors:
        try:
            vector_dims = [len(vec) for vec in query_vectors]
            set_span_attribute(
                span, MilvusAttributes.SEARCH_QUERY_VECTOR_DIMENSION, str(vector_dims)
            )
        except (TypeError, AttributeError):
            pass


@dont_throw
def _set_hybrid_search_attributes(span, kwargs: dict) -> None:
    """Set span attributes for hybrid_search operation."""
    set_span_attribute(
        span, MilvusAttributes.SEARCH_COLLECTION_NAME, kwargs.get("collection_name")
    )

    reqs = kwargs.get("reqs", [])
    reqs_info = []
    for req in reqs:
        try:
            req_info = {
                "anns_field": getattr(req, "anns_field", None),
                "param": getattr(req, "param", None),
            }
            reqs_info.append(req_info)
        except (TypeError, AttributeError):
            pass

    if reqs_info:
        set_span_attribute(span, MilvusAttributes.SEARCH_ANNSEARCH_REQUEST, str(reqs_info))

    ranker = kwargs.get("ranker")
    if ranker:
        set_span_attribute(span, MilvusAttributes.SEARCH_RANKER_TYPE, type(ranker).__name__)

    set_span_attribute(span, MilvusAttributes.SEARCH_LIMIT, kwargs.get("limit"))
    set_span_attribute(span, MilvusAttributes.SEARCH_DATA_COUNT, count_or_none(reqs))
    set_span_attribute(
        span,
        MilvusAttributes.SEARCH_OUTPUT_FIELDS_COUNT,
        count_or_none(kwargs.get("output_fields")),
    )
    set_span_attribute(span, MilvusAttributes.SEARCH_TIMEOUT, kwargs.get("timeout"))
    set_span_attribute(
        span,
        MilvusAttributes.SEARCH_PARTITION_NAMES_COUNT,
        count_or_none(kwargs.get("partition_names")),
    )
    set_span_attribute(
        span,
        MilvusAttributes.SEARCH_PARTITION_NAMES,
        to_string_or_none(kwargs.get("partition_names")),
    )


@dont_throw
def _set_get_attributes(span, kwargs: dict) -> None:
    """Set span attributes for get operation."""
    set_span_attribute(
        span, MilvusAttributes.GET_COLLECTION_NAME, kwargs.get("collection_name")
    )
    set_span_attribute(
        span, MilvusAttributes.GET_IDS_COUNT, count_or_none(kwargs.get("ids"))
    )
    set_span_attribute(
        span,
        MilvusAttributes.GET_OUTPUT_FIELDS_COUNT,
        count_or_none(kwargs.get("output_fields")),
    )
    set_span_attribute(span, MilvusAttributes.GET_TIMEOUT, kwargs.get("timeout"))
    set_span_attribute(
        span,
        MilvusAttributes.GET_PARTITION_NAMES_COUNT,
        count_or_none(kwargs.get("partition_names")),
    )


@dont_throw
def _set_query_attributes(span, kwargs: dict) -> None:
    """Set span attributes for query operation."""
    set_span_attribute(
        span, MilvusAttributes.QUERY_COLLECTION_NAME, kwargs.get("collection_name")
    )
    set_span_attribute(
        span, MilvusAttributes.QUERY_FILTER, to_string_or_none(kwargs.get("filter"))
    )
    set_span_attribute(
        span,
        MilvusAttributes.QUERY_OUTPUT_FIELDS_COUNT,
        count_or_none(kwargs.get("output_fields")),
    )
    set_span_attribute(span, MilvusAttributes.QUERY_TIMEOUT, kwargs.get("timeout"))
    set_span_attribute(
        span, MilvusAttributes.QUERY_IDS_COUNT, count_or_none(kwargs.get("ids"))
    )
    set_span_attribute(
        span,
        MilvusAttributes.QUERY_PARTITION_NAMES_COUNT,
        count_or_none(kwargs.get("partition_names")),
    )
    set_span_attribute(span, MilvusAttributes.QUERY_LIMIT, kwargs.get("limit"))


@dont_throw
def _add_query_result_events(span, result: Any) -> None:
    """Add events for query results."""
    if result is None:
        return

    for element in result:
        if isinstance(element, dict):
            # Filter to only include serializable attributes
            event_attrs = {}
            for key, value in element.items():
                if isinstance(value, (str, int, float, bool)):
                    event_attrs[key] = value
                elif value is not None:
                    event_attrs[key] = str(value)
            if event_attrs:
                span.add_event(name=Events.DB_QUERY_RESULT, attributes=event_attrs)


@dont_throw
def _add_search_result_events(span, result: Any) -> None:
    """Add events for search results."""
    if result is None:
        return

    total_matches = 0
    single_query = len(result) == 1

    for query_idx, query_results in enumerate(result):
        for match in query_results:
            total_matches += 1
            distance = match.get("distance")

            event_attrs = {
                EventAttributes.DB_SEARCH_RESULT_QUERY_ID: query_idx,
            }

            match_id = match.get("id")
            if match_id is not None:
                event_attrs[EventAttributes.DB_SEARCH_RESULT_ID] = str(match_id)

            if distance is not None:
                event_attrs[EventAttributes.DB_SEARCH_RESULT_DISTANCE] = str(distance)

            entity = match.get("entity")
            if entity is not None:
                event_attrs[EventAttributes.DB_SEARCH_RESULT_ENTITY] = str(entity)

            span.add_event(Events.DB_SEARCH_RESULT, attributes=event_attrs)

        if not single_query:
            set_span_attribute(
                span,
                f"{MilvusAttributes.SEARCH_RESULT_COUNT}_{query_idx}",
                len(query_results),
            )

    if single_query:
        set_span_attribute(span, MilvusAttributes.SEARCH_RESULT_COUNT, total_matches)


@dont_throw
def _set_response_metrics(
    insert_units_metric,
    upsert_units_metric,
    delete_units_metric,
    shared_attributes: dict,
    response: Any,
) -> None:
    """Record response metrics."""
    if not isinstance(response, dict):
        return

    if "upsert_count" in response and upsert_units_metric:
        upsert_count = response["upsert_count"] or 0
        upsert_units_metric.add(upsert_count, shared_attributes)

    if "insert_count" in response and insert_units_metric:
        insert_count = response["insert_count"] or 0
        insert_units_metric.add(insert_count, shared_attributes)

    if "delete_count" in response and delete_units_metric:
        delete_count = response["delete_count"] or 0
        delete_units_metric.add(delete_count, shared_attributes)


@dont_throw
def _set_search_response_metrics(
    distance_metric, shared_attributes: dict, response: Any
) -> None:
    """Record search response metrics."""
    if response is None or distance_metric is None:
        return

    for query_result in response:
        for match in query_result:
            distance = match.get("distance")
            if distance is not None:
                distance_metric.record(distance, shared_attributes)


# Map of method names to attribute setter functions
ATTRIBUTE_SETTERS = {
    "create_collection": _set_create_collection_attributes,
    "insert": _set_insert_attributes,
    "upsert": _set_upsert_attributes,
    "delete": _set_delete_attributes,
    "search": _set_search_attributes,
    "get": _set_get_attributes,
    "query": _set_query_attributes,
    "hybrid_search": _set_hybrid_search_attributes,
}


def _get_error_type(exception: Exception) -> str:
    """Get error type from exception, handling Milvus-specific errors."""
    try:
        from pymilvus.client.types import Status
        from pymilvus.exceptions import ErrorCode

        code_to_error_type = {}
        for name in dir(Status):
            value = getattr(Status, name)
            if isinstance(value, int):
                code_to_error_type[value] = name

        code_to_error_type.update({code.value: code.name for code in ErrorCode})

        code = getattr(exception, "code", None)
        if code is not None and code in code_to_error_type:
            return code_to_error_type[code]
    except ImportError:
        pass

    return type(exception).__name__


def create_wrapper(
    tracer: Tracer,
    method_name: str,
    span_name: str,
    query_duration_metric: Optional[Any] = None,
    distance_metric: Optional[Any] = None,
    insert_units_metric: Optional[Any] = None,
    upsert_units_metric: Optional[Any] = None,
    delete_units_metric: Optional[Any] = None,
) -> Callable:
    """Create a wrapper function for a Milvus method."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            span_name,
            kind=SpanKind.CLIENT,
            attributes={
                SpanAttributes.DB_SYSTEM: "milvus",
                SpanAttributes.DB_OPERATION: method_name,
            },
        ) as span:
            # Set method-specific attributes
            if method_name in ATTRIBUTE_SETTERS:
                ATTRIBUTE_SETTERS[method_name](span, kwargs)

            shared_attributes = {
                SpanAttributes.DB_SYSTEM: "milvus",
                SpanAttributes.DB_OPERATION: method_name,
            }

            try:
                start_time = time.time()
                result = wrapped(*args, **kwargs)
                end_time = time.time()

                # Add result events
                if method_name == "query":
                    _add_query_result_events(span, result)
                elif method_name in ("search", "hybrid_search"):
                    _add_search_result_events(span, result)

            except Exception as e:
                error_type = _get_error_type(e)
                span.set_attribute(ERROR_TYPE, error_type)
                raise

            # Record metrics
            duration = end_time - start_time
            if duration > 0 and query_duration_metric and method_name == "query":
                query_duration_metric.record(duration, shared_attributes)

            if result:
                if method_name in ("search", "hybrid_search"):
                    _set_search_response_metrics(
                        distance_metric, shared_attributes, result
                    )

                _set_response_metrics(
                    insert_units_metric,
                    upsert_units_metric,
                    delete_units_metric,
                    shared_attributes,
                    result,
                )

            return result

    return wrapper
