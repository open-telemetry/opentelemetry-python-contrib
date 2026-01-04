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

"""
OpenTelemetry Weaviate instrumentation supporting `weaviate-client`.

Usage
-----

.. code:: python

    import weaviate
    from opentelemetry.instrumentation.weaviate import WeaviateInstrumentor

    WeaviateInstrumentor().instrument()

    client = weaviate.connect_to_local()
    # All Weaviate operations will now be traced

API
---
"""

import importlib
import logging
from typing import Callable, Collection, Optional

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.instrumentation.weaviate.package import _instruments
from opentelemetry.instrumentation.weaviate.utils import Config
from opentelemetry.instrumentation.weaviate.version import __version__
from opentelemetry.instrumentation.weaviate.wrapper import _wrap
from opentelemetry.trace import get_tracer

logger = logging.getLogger(__name__)


# Methods to wrap for Weaviate v3 (Legacy)
WRAPPED_METHODS_V3 = [
    # Schema operations
    {
        "module": "weaviate.schema",
        "object": "Schema",
        "method": "get",
        "span_name": "weaviate.schema.get",
    },
    {
        "module": "weaviate.schema",
        "object": "Schema",
        "method": "create_class",
        "span_name": "weaviate.schema.create_class",
    },
    {
        "module": "weaviate.schema",
        "object": "Schema",
        "method": "create",
        "span_name": "weaviate.schema.create",
    },
    {
        "module": "weaviate.schema",
        "object": "Schema",
        "method": "delete_class",
        "span_name": "weaviate.schema.delete_class",
    },
    {
        "module": "weaviate.schema",
        "object": "Schema",
        "method": "delete_all",
        "span_name": "weaviate.schema.delete_all",
    },
    # Data operations
    {
        "module": "weaviate.data.crud_data",
        "object": "DataObject",
        "method": "create",
        "span_name": "weaviate.data.create",
    },
    {
        "module": "weaviate.data.crud_data",
        "object": "DataObject",
        "method": "validate",
        "span_name": "weaviate.data.validate",
    },
    {
        "module": "weaviate.data.crud_data",
        "object": "DataObject",
        "method": "get",
        "span_name": "weaviate.data.get",
    },
    # Batch operations
    {
        "module": "weaviate.batch.crud_batch",
        "object": "Batch",
        "method": "add_data_object",
        "span_name": "weaviate.batch.add_data_object",
    },
    {
        "module": "weaviate.batch.crud_batch",
        "object": "Batch",
        "method": "flush",
        "span_name": "weaviate.batch.flush",
    },
    # Query operations
    {
        "module": "weaviate.gql.query",
        "object": "Query",
        "method": "get",
        "span_name": "weaviate.query.get",
    },
    {
        "module": "weaviate.gql.query",
        "object": "Query",
        "method": "aggregate",
        "span_name": "weaviate.query.aggregate",
    },
    {
        "module": "weaviate.gql.query",
        "object": "Query",
        "method": "raw",
        "span_name": "weaviate.query.raw",
    },
]

# Methods to wrap for Weaviate v4
WRAPPED_METHODS_V4 = [
    # Collections management
    {
        "module": "weaviate.collections.collections",
        "object": "_Collections",
        "method": "get",
        "span_name": "weaviate.collections.get",
    },
    {
        "module": "weaviate.collections.collections",
        "object": "_Collections",
        "method": "create",
        "span_name": "weaviate.collections.create",
    },
    {
        "module": "weaviate.collections.collections",
        "object": "_Collections",
        "method": "create_from_dict",
        "span_name": "weaviate.collections.create_from_dict",
    },
    {
        "module": "weaviate.collections.collections",
        "object": "_Collections",
        "method": "delete",
        "span_name": "weaviate.collections.delete",
    },
    {
        "module": "weaviate.collections.collections",
        "object": "_Collections",
        "method": "delete_all",
        "span_name": "weaviate.collections.delete_all",
    },
    # Data operations
    {
        "module": "weaviate.collections.data",
        "object": "_DataCollection",
        "method": "insert",
        "span_name": "weaviate.data.insert",
    },
    {
        "module": "weaviate.collections.data",
        "object": "_DataCollection",
        "method": "insert_many",
        "span_name": "weaviate.data.insert_many",
    },
    {
        "module": "weaviate.collections.data",
        "object": "_DataCollection",
        "method": "replace",
        "span_name": "weaviate.data.replace",
    },
    {
        "module": "weaviate.collections.data",
        "object": "_DataCollection",
        "method": "update",
        "span_name": "weaviate.data.update",
    },
    # Batch operations
    {
        "module": "weaviate.collections.batch.collection",
        "object": "_BatchCollection",
        "method": "add_object",
        "span_name": "weaviate.batch.add_object",
    },
    # Query operations
    {
        "module": "weaviate.collections.queries.fetch_object_by_id.query",
        "object": "_FetchObjectByIDQuery",
        "method": "fetch_object_by_id",
        "span_name": "weaviate.query.fetch_object_by_id",
    },
    {
        "module": "weaviate.collections.queries.fetch_objects.query",
        "object": "_FetchObjectsQuery",
        "method": "fetch_objects",
        "span_name": "weaviate.query.fetch_objects",
    },
    {
        "module": "weaviate.collections.grpc.query",
        "object": "_QueryGRPC",
        "method": "get",
        "span_name": "weaviate.query.get",
    },
    # GraphQL operations
    {
        "module": "weaviate.gql.get",
        "object": "GetBuilder",
        "method": "do",
        "span_name": "weaviate.gql.get.do",
    },
    {
        "module": "weaviate.gql.aggregate",
        "object": "AggregateBuilder",
        "method": "do",
        "span_name": "weaviate.gql.aggregate.do",
    },
    {
        "module": "weaviate.client",
        "object": "WeaviateClient",
        "method": "graphql_raw_query",
        "span_name": "weaviate.graphql_raw_query",
    },
]

# Combined list of all methods to wrap
WRAPPED_METHODS = WRAPPED_METHODS_V3 + WRAPPED_METHODS_V4


class WeaviateInstrumentor(BaseInstrumentor):
    """An instrumentor for Weaviate's client library."""

    def __init__(
        self, exception_logger: Optional[Callable[[Exception], None]] = None
    ):
        super().__init__()
        Config.exception_logger = exception_logger

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        """Enable Weaviate instrumentation."""
        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
        )

        for wrapped_method in WRAPPED_METHODS:
            wrap_module = wrapped_method.get("module")
            wrap_object = wrapped_method.get("object")
            wrap_method = wrapped_method.get("method")

            try:
                module = importlib.import_module(wrap_module)
                if getattr(module, wrap_object, None):
                    wrap_function_wrapper(
                        wrap_module,
                        f"{wrap_object}.{wrap_method}",
                        _wrap(tracer, wrapped_method),
                    )
            except (ImportError, AttributeError) as e:
                logger.debug(
                    "Could not wrap %s.%s.%s: %s",
                    wrap_module,
                    wrap_object,
                    wrap_method,
                    e,
                )

    def _uninstrument(self, **kwargs):
        """Disable Weaviate instrumentation."""
        for wrapped_method in WRAPPED_METHODS:
            wrap_module = wrapped_method.get("module")
            wrap_object = wrapped_method.get("object")
            wrap_method = wrapped_method.get("method")

            try:
                module = importlib.import_module(wrap_module)
                wrapped = getattr(module, wrap_object, None)
                if wrapped:
                    unwrap(wrapped, wrap_method)
            except (ImportError, AttributeError):
                pass
