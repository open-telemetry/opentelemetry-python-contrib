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

"""Wrapper functions for LanceDB instrumentation."""

from __future__ import annotations

import logging
from typing import Any, Callable

from opentelemetry import context as context_api
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import SpanKind, Tracer

from opentelemetry.instrumentation.lancedb.semconv import LanceDBAttributes
from opentelemetry.instrumentation.lancedb.utils import (
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
        span, LanceDBAttributes.ADD_DATA_COUNT, count_or_none(kwargs.get("data"))
    )


@dont_throw
def _set_search_attributes(span, kwargs: dict) -> None:
    """Set span attributes for search operation."""
    _set_span_attribute(
        span, LanceDBAttributes.SEARCH_QUERY, to_string_or_none(kwargs.get("query"))
    )
    _set_span_attribute(span, LanceDBAttributes.SEARCH_LIMIT, kwargs.get("limit"))


@dont_throw
def _set_delete_attributes(span, kwargs: dict) -> None:
    """Set span attributes for delete operation."""
    _set_span_attribute(
        span, LanceDBAttributes.DELETE_WHERE, to_string_or_none(kwargs.get("where"))
    )


# Map of method names to attribute setter functions
ATTRIBUTE_SETTERS = {
    "add": _set_add_attributes,
    "search": _set_search_attributes,
    "delete": _set_delete_attributes,
}


def create_wrapper(
    tracer: Tracer,
    method_name: str,
    span_name: str,
) -> Callable:
    """Create a wrapper function for a LanceDB method."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            span_name,
            kind=SpanKind.CLIENT,
            attributes={
                SpanAttributes.DB_SYSTEM: "lancedb",
                SpanAttributes.DB_OPERATION: method_name,
            },
        ) as span:
            # Set method-specific attributes
            if method_name in ATTRIBUTE_SETTERS:
                ATTRIBUTE_SETTERS[method_name](span, kwargs)

            # Execute the wrapped function
            result = wrapped(*args, **kwargs)

            return result

    return wrapper
