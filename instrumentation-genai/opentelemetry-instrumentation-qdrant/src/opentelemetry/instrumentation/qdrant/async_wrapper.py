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

"""Wrapper functions for Qdrant instrumentation (async)."""

from __future__ import annotations

import logging
from typing import Callable

from opentelemetry import context as context_api
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.trace.status import Status, StatusCode

from opentelemetry.instrumentation.qdrant.wrapper import (
    _set_batch_search_attributes,
    _set_collection_name_attribute,
    _set_search_attributes,
    _set_upload_attributes,
    _set_upsert_attributes,
)

logger = logging.getLogger(__name__)


def create_async_wrapper(
    tracer: Tracer,
    method_name: str,
    span_name: str,
) -> Callable:
    """Create a wrapper function for a Qdrant async method."""

    async def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return await wrapped(*args, **kwargs)

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
            response = await wrapped(*args, **kwargs)

            if response:
                span.set_status(Status(StatusCode.OK))

            return response

    return wrapper
