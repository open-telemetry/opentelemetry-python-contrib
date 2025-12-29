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

"""Wrapper and instrumentor classes for Weaviate instrumentation."""

import logging
from typing import Optional

from opentelemetry import context as context_api
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
from opentelemetry.instrumentation.weaviate.utils import ArgsGetter, dont_throw
from opentelemetry.semconv.trace import SpanAttributes

logger = logging.getLogger(__name__)


def _set_span_attribute(span, name, value):
    """Set a span attribute if value is not None or empty."""
    if value is not None and value != "":
        span.set_attribute(name, value)


def _with_tracer_wrapper(func):
    """Helper for providing tracer for wrapper functions."""

    def _with_tracer(tracer, to_wrap):
        def wrapper(wrapped, instance, args, kwargs):
            return func(tracer, to_wrap, wrapped, instance, args, kwargs)

        return wrapper

    return _with_tracer


@_with_tracer_wrapper
def _wrap(tracer, to_wrap, wrapped, instance, args, kwargs):
    """Instruments and calls every function defined in wrapped methods."""
    if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
        return wrapped(*args, **kwargs)

    name = to_wrap.get("span_name")
    with tracer.start_as_current_span(name) as span:
        span.set_attribute(SpanAttributes.DB_SYSTEM, "weaviate")
        span.set_attribute(SpanAttributes.DB_OPERATION, to_wrap.get("method"))

        obj = to_wrap.get("object")
        instrumentor = InstrumentorFactory.from_name(obj)
        if instrumentor:
            instrumentor.instrument(
                to_wrap.get("method"), span, instance, args, kwargs
            )

        return wrapped(*args, **kwargs)


class _Instrumentor:
    """Base class for operation-specific instrumentors."""

    namespace: str = ""
    mapped_attributes: dict = {}

    def map_attributes(self, span, method_name, attributes, args, kwargs):
        """Map arguments to span attributes."""
        getter = ArgsGetter(args, kwargs)
        for idx, attribute in enumerate(attributes):
            _set_span_attribute(
                span,
                f"{self.namespace}.{method_name}.{attribute}",
                getter(idx, attribute),
            )

    @dont_throw
    def instrument(self, method_name, span, instance, args, kwargs):
        """Add operation-specific attributes to the span."""
        # Try to extract collection name from instance
        self._set_collection_from_instance(span, instance)

        attributes = self.mapped_attributes.get(method_name)
        if attributes:
            self.map_attributes(span, method_name, attributes, args, kwargs)

    def _set_collection_from_instance(self, span, instance):
        """Try to get collection name from instance."""
        try:
            if hasattr(instance, "name"):
                _set_span_attribute(
                    span, "db.weaviate.collection", instance.name
                )
            elif hasattr(instance, "_name"):
                _set_span_attribute(
                    span, "db.weaviate.collection", instance._name
                )
        except Exception:
            pass


# V3 Instrumentors (Legacy)


class _SchemaInstrumentorV3(_Instrumentor):
    """Instrumentor for v3 Schema operations."""

    namespace = "db.weaviate.schema"
    mapped_attributes = {
        "get": ["class_name"],
        "create_class": ["schema_class"],
        "create": ["schema"],
        "delete_class": ["class_name"],
        "delete_all": [],
    }


class _DataObjectInstrumentorV3(_Instrumentor):
    """Instrumentor for v3 DataObject operations."""

    namespace = "db.weaviate.data"
    mapped_attributes = {
        "create": [
            "data_object",
            "class_name",
            "uuid",
            "vector",
            "consistency_level",
            "tenant",
        ],
        "validate": [
            "data_object",
            "class_name",
            "uuid",
            "vector",
        ],
        "get": [
            "uuid",
            "additional_properties",
            "with_vector",
            "class_name",
            "node_name",
            "consistency_level",
            "limit",
            "after",
            "offset",
            "sort",
            "tenant",
        ],
    }


class _BatchInstrumentorV3(_Instrumentor):
    """Instrumentor for v3 Batch operations."""

    namespace = "db.weaviate.batch"
    mapped_attributes = {
        "add_data_object": [
            "data_object",
            "class_name",
            "uuid",
            "vector",
            "tenant",
        ],
        "flush": [],
    }


class _QueryInstrumentorV3(_Instrumentor):
    """Instrumentor for v3 Query operations."""

    namespace = "db.weaviate.query"
    mapped_attributes = {
        "get": ["class_name", "properties"],
        "aggregate": ["class_name"],
        "raw": ["gql_query"],
    }


class _GetBuilderInstrumentorV3(_Instrumentor):
    """Instrumentor for v3 GetBuilder operations."""

    namespace = "db.weaviate.gql.get"
    mapped_attributes = {
        "do": [],
    }


# V4 Instrumentors


class _CollectionsInstrumentor(_Instrumentor):
    """Instrumentor for v4 Collections operations."""

    namespace = "db.weaviate.collections"
    mapped_attributes = {
        "create": ["name"],
        "create_from_dict": ["config"],
        "get": ["name"],
        "delete": ["name"],
        "delete_all": [],
    }


class _DataCollectionInstrumentor(_Instrumentor):
    """Instrumentor for v4 DataCollection operations."""

    namespace = "db.weaviate.data"
    mapped_attributes = {
        "insert": ["properties", "references", "uuid", "vector"],
        "insert_many": ["objects"],
        "replace": ["uuid", "properties", "references", "vector"],
        "update": ["uuid", "properties", "references", "vector"],
    }


class _BatchCollectionInstrumentor(_Instrumentor):
    """Instrumentor for v4 BatchCollection operations."""

    namespace = "db.weaviate.batch"
    mapped_attributes = {
        "add_object": ["properties", "references", "uuid", "vector"],
    }


class _QueryInstrumentor(_Instrumentor):
    """Instrumentor for v4 Query operations."""

    namespace = "db.weaviate.query"
    mapped_attributes = {
        "fetch_object_by_id": [
            "uuid",
            "include_vector",
            "return_properties",
            "return_references",
        ],
        "fetch_objects": [
            "limit",
            "offset",
            "after",
            "filters",
            "sort",
            "include_vector",
            "return_metadata",
            "return_properties",
            "return_references",
        ],
        "get": [],
    }


class _AggregateBuilderInstrumentor(_Instrumentor):
    """Instrumentor for AggregateBuilder operations."""

    namespace = "db.weaviate.gql.aggregate"
    mapped_attributes = {
        "do": [],
    }


class _GetBuilderInstrumentor(_Instrumentor):
    """Instrumentor for GetBuilder operations."""

    namespace = "db.weaviate.gql.get"
    mapped_attributes = {
        "do": [],
    }


class _GraphQLInstrumentor(_Instrumentor):
    """Instrumentor for GraphQL filter operations."""

    namespace = "db.weaviate.gql"
    mapped_attributes = {
        "do": [],
    }


class _RawQueryInstrumentor(_Instrumentor):
    """Instrumentor for raw GraphQL query operations."""

    namespace = "db.weaviate.gql"
    mapped_attributes = {
        "graphql_raw_query": ["gql_query"],
    }


class InstrumentorFactory:
    """Factory for creating operation-specific instrumentors."""

    @classmethod
    def from_name(cls, name: str) -> Optional[_Instrumentor]:
        """Get the appropriate instrumentor for a Weaviate object.

        Args:
            name: The name of the Weaviate class being instrumented

        Returns:
            An instrumentor instance, or None if no match
        """
        # V3 instrumentors
        if name == "Schema":
            return _SchemaInstrumentorV3()
        if name == "DataObject":
            return _DataObjectInstrumentorV3()
        if name == "Batch":
            return _BatchInstrumentorV3()
        if name == "Query":
            return _QueryInstrumentorV3()

        # V4 instrumentors
        if name == "_Collections":
            return _CollectionsInstrumentor()
        if name == "_DataCollection":
            return _DataCollectionInstrumentor()
        if name == "_BatchCollection":
            return _BatchCollectionInstrumentor()
        if name in ("_FetchObjectByIDQuery", "_FetchObjectsQuery", "_QueryGRPC"):
            return _QueryInstrumentor()
        if name == "AggregateBuilder":
            return _AggregateBuilderInstrumentor()
        if name == "GetBuilder":
            return _GetBuilderInstrumentor()
        if name == "GraphQL":
            return _GraphQLInstrumentor()
        if name == "WeaviateClient":
            return _RawQueryInstrumentor()

        return None
