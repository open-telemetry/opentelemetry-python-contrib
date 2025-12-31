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

"""Wrapper functions for Pinecone instrumentation."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Optional

from opentelemetry import context as context_api
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.trace.status import Status, StatusCode

from opentelemetry.instrumentation.pinecone.semconv import (
    EventAttributes,
    Events,
    PineconeAttributes,
)
from opentelemetry.instrumentation.pinecone.utils import (
    dont_throw,
    set_span_attribute,
)

logger = logging.getLogger(__name__)


@dont_throw
def _set_input_attributes(span, instance, kwargs: dict) -> None:
    """Set span attributes from instance config."""
    if hasattr(instance, "_config") and hasattr(instance._config, "host"):
        set_span_attribute(span, SpanAttributes.SERVER_ADDRESS, instance._config.host)


@dont_throw
def _set_query_input_attributes(span, kwargs: dict) -> None:
    """Set span attributes for query operation input."""
    set_span_attribute(span, PineconeAttributes.QUERY_ID, kwargs.get("id"))
    set_span_attribute(span, PineconeAttributes.QUERY_TOP_K, kwargs.get("top_k"))
    set_span_attribute(span, PineconeAttributes.QUERY_NAMESPACE, kwargs.get("namespace"))

    filter_val = kwargs.get("filter")
    if isinstance(filter_val, dict):
        set_span_attribute(span, PineconeAttributes.QUERY_FILTER, json.dumps(filter_val))
    else:
        set_span_attribute(span, PineconeAttributes.QUERY_FILTER, filter_val)

    set_span_attribute(
        span, PineconeAttributes.QUERY_INCLUDE_VALUES, kwargs.get("include_values")
    )
    set_span_attribute(
        span, PineconeAttributes.QUERY_INCLUDE_METADATA, kwargs.get("include_metadata")
    )

    # Log query embeddings as events
    vector = kwargs.get("vector")
    if vector:
        span.add_event(
            name=Events.DB_QUERY_EMBEDDINGS,
            attributes={EventAttributes.DB_QUERY_EMBEDDINGS_VECTOR: str(vector)},
        )

    sparse_vector = kwargs.get("sparse_vector")
    if sparse_vector:
        span.add_event(
            name=Events.DB_QUERY_EMBEDDINGS,
            attributes={EventAttributes.DB_QUERY_EMBEDDINGS_VECTOR: str(sparse_vector)},
        )

    queries = kwargs.get("queries")
    if queries:
        for query_vector in queries:
            span.add_event(
                name=Events.DB_QUERY_EMBEDDINGS,
                attributes={EventAttributes.DB_QUERY_EMBEDDINGS_VECTOR: str(query_vector)},
            )


@dont_throw
def _set_query_response_attributes(
    span, scores_metric, shared_attributes: dict, response: Any
) -> None:
    """Set span attributes and events from query response."""
    if response is None:
        return

    matches = response.get("matches", [])
    for match in matches:
        score = match.get("score")
        if scores_metric and score is not None:
            scores_metric.record(score, shared_attributes)

        event_attrs = {
            EventAttributes.DB_QUERY_RESULT_ID: match.get("id"),
        }
        if score is not None:
            event_attrs[EventAttributes.DB_QUERY_RESULT_SCORE] = score
        if match.get("metadata") is not None:
            event_attrs[EventAttributes.DB_QUERY_RESULT_METADATA] = str(
                match.get("metadata")
            )
        if match.get("values") is not None:
            event_attrs[EventAttributes.DB_QUERY_RESULT_VECTOR] = str(match.get("values"))

        span.add_event(name=Events.DB_QUERY_RESULT, attributes=event_attrs)


@dont_throw
def _set_usage_attributes(
    span, read_units_metric, write_units_metric, shared_attributes: dict, response: Any
) -> None:
    """Set span attributes for usage from response."""
    if response is None:
        return

    usage = response.get("usage")
    if usage:
        read_units = usage.get("read_units") or 0
        write_units = usage.get("write_units") or 0

        if read_units_metric:
            read_units_metric.add(read_units, shared_attributes)
        set_span_attribute(span, PineconeAttributes.USAGE_READ_UNITS, read_units)

        if write_units_metric:
            write_units_metric.add(write_units, shared_attributes)
        set_span_attribute(span, PineconeAttributes.USAGE_WRITE_UNITS, write_units)


def create_wrapper(
    tracer: Tracer,
    method_name: str,
    span_name: str,
    query_duration_metric: Optional[Any] = None,
    read_units_metric: Optional[Any] = None,
    write_units_metric: Optional[Any] = None,
    scores_metric: Optional[Any] = None,
) -> Callable:
    """Create a wrapper function for a Pinecone method."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            span_name,
            kind=SpanKind.CLIENT,
            attributes={
                SpanAttributes.DB_SYSTEM: "pinecone",
                SpanAttributes.DB_OPERATION: method_name,
            },
        ) as span:
            if span.is_recording():
                _set_input_attributes(span, instance, kwargs)
                if method_name == "query":
                    _set_query_input_attributes(span, kwargs)

            shared_attributes = {}
            if hasattr(instance, "_config") and hasattr(instance._config, "host"):
                shared_attributes["server.address"] = instance._config.host

            start_time = time.time()
            response = wrapped(*args, **kwargs)
            end_time = time.time()

            duration = end_time - start_time
            if duration > 0 and query_duration_metric and method_name == "query":
                query_duration_metric.record(duration, shared_attributes)

            if response and span.is_recording():
                if method_name == "query":
                    _set_query_response_attributes(
                        span, scores_metric, shared_attributes, response
                    )

                _set_usage_attributes(
                    span,
                    read_units_metric,
                    write_units_metric,
                    shared_attributes,
                    response,
                )

                span.set_status(Status(StatusCode.OK))

            return response

    return wrapper
