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

"""Wrapper functions for Marqo instrumentation."""

from __future__ import annotations

import logging
from typing import Any, Callable

from opentelemetry import context as context_api
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import SpanKind, Tracer

from opentelemetry.instrumentation.marqo.semconv import (
    Events,
    MarqoAttributes,
)
from opentelemetry.instrumentation.marqo.utils import (
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
def _set_add_documents_attributes(span, kwargs: dict) -> None:
    """Set span attributes for add_documents operation."""
    _set_span_attribute(
        span,
        MarqoAttributes.ADD_DOCUMENTS_COUNT,
        count_or_none(kwargs.get("documents")),
    )


@dont_throw
def _set_search_attributes(span, kwargs: dict) -> None:
    """Set span attributes for search operation."""
    _set_span_attribute(
        span, MarqoAttributes.SEARCH_QUERY, to_string_or_none(kwargs.get("q"))
    )


@dont_throw
def _set_delete_documents_attributes(span, kwargs: dict) -> None:
    """Set span attributes for delete_documents operation."""
    _set_span_attribute(
        span, MarqoAttributes.DELETE_IDS_COUNT, count_or_none(kwargs.get("ids"))
    )


@dont_throw
def _set_search_result_attributes(span, result: Any) -> None:
    """Set span attributes and events from search results."""
    if result is None:
        return

    # Set processing time
    processing_time = result.get("processingTimeMs")
    if processing_time is not None:
        _set_span_attribute(span, MarqoAttributes.SEARCH_PROCESSING_TIME, processing_time)

    # Add events for each hit
    hits = result.get("hits", [])
    for hit in hits:
        if isinstance(hit, dict):
            # Filter to only include serializable attributes
            event_attrs = {}
            for key, value in hit.items():
                if isinstance(value, (str, int, float, bool)):
                    event_attrs[key] = value
                elif isinstance(value, (list, dict)):
                    event_attrs[key] = str(value)
            if event_attrs:
                span.add_event(name=Events.DB_QUERY_RESULT, attributes=event_attrs)


@dont_throw
def _set_delete_documents_response_attributes(span, result: Any) -> None:
    """Set span attributes from delete documents response."""
    if result is None:
        return

    status = result.get("status")
    if status is not None:
        _set_span_attribute(span, MarqoAttributes.DELETE_STATUS, str(status))


# Map of method names to attribute setter functions
ATTRIBUTE_SETTERS = {
    "add_documents": _set_add_documents_attributes,
    "search": _set_search_attributes,
    "delete_documents": _set_delete_documents_attributes,
}

# Map of method names to result handler functions
RESULT_HANDLERS = {
    "search": _set_search_result_attributes,
    "delete_documents": _set_delete_documents_response_attributes,
}


def create_wrapper(
    tracer: Tracer,
    method_name: str,
    span_name: str,
) -> Callable:
    """Create a wrapper function for a Marqo method."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            span_name,
            kind=SpanKind.CLIENT,
            attributes={
                SpanAttributes.DB_SYSTEM: "marqo",
                SpanAttributes.DB_OPERATION: method_name,
            },
        ) as span:
            # Set method-specific attributes
            if method_name in ATTRIBUTE_SETTERS:
                ATTRIBUTE_SETTERS[method_name](span, kwargs)

            # Execute the wrapped function
            result = wrapped(*args, **kwargs)

            # Handle result-specific attributes
            if method_name in RESULT_HANDLERS:
                RESULT_HANDLERS[method_name](span, result)

            return result

    return wrapper
