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
OpenTelemetry Milvus Instrumentation
====================================

Instrumentation for the Milvus vector database.

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.milvus import MilvusInstrumentor
    from pymilvus import MilvusClient

    # Enable instrumentation
    MilvusInstrumentor().instrument()

    # Use Milvus client normally
    client = MilvusClient("./milvus.db")
    client.create_collection(
        collection_name="my_collection",
        dimension=128
    )
    client.insert(
        collection_name="my_collection",
        data=[{"id": 1, "vector": [0.1] * 128}]
    )
    results = client.search(
        collection_name="my_collection",
        data=[[0.1] * 128],
        limit=10
    )

API
---
"""

import logging
from typing import Any, Callable, Collection, Optional

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.milvus.package import _instruments
from opentelemetry.instrumentation.milvus.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.schemas import Schemas

logger = logging.getLogger(__name__)

# Methods to wrap on MilvusClient class
WRAPPED_METHODS = [
    {"method": "create_collection", "span_name": "milvus.create_collection"},
    {"method": "insert", "span_name": "milvus.insert"},
    {"method": "upsert", "span_name": "milvus.upsert"},
    {"method": "delete", "span_name": "milvus.delete"},
    {"method": "search", "span_name": "milvus.search"},
    {"method": "get", "span_name": "milvus.get"},
    {"method": "query", "span_name": "milvus.query"},
    {"method": "hybrid_search", "span_name": "milvus.hybrid_search"},
]


class MilvusInstrumentor(BaseInstrumentor):
    """An instrumentor for the Milvus vector database.

    This instrumentor will automatically trace Milvus operations including
    create_collection, insert, upsert, delete, search, get, query, and
    hybrid_search operations.
    """

    def __init__(
        self,
        exception_logger: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        super().__init__()
        self._tracer = None
        self._exception_logger = exception_logger
        self._metrics = None

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable Milvus instrumentation.

        Args:
            **kwargs: Optional arguments
                - tracer_provider: TracerProvider instance
                - meter_provider: MeterProvider instance
        """
        import pymilvus

        from opentelemetry.metrics import get_meter
        from opentelemetry.trace import get_tracer

        from opentelemetry.instrumentation.milvus.utils import (
            Config,
            is_metrics_enabled,
        )
        from opentelemetry.instrumentation.milvus.wrapper import create_wrapper
        from opentelemetry.instrumentation.milvus.instruments import create_metrics

        # Set exception logger
        if self._exception_logger:
            Config.exception_logger = self._exception_logger

        # Get tracer
        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=Schemas.V1_28_0.value,
        )

        self._tracer = tracer

        # Setup metrics if enabled
        query_duration_metric = None
        distance_metric = None
        insert_units_metric = None
        upsert_units_metric = None
        delete_units_metric = None

        if is_metrics_enabled():
            meter_provider = kwargs.get("meter_provider")
            meter = get_meter(__name__, __version__, meter_provider)
            self._metrics = create_metrics(meter)
            query_duration_metric = self._metrics["query_duration"]
            distance_metric = self._metrics["distance"]
            insert_units_metric = self._metrics["insert_units"]
            upsert_units_metric = self._metrics["upsert_units"]
            delete_units_metric = self._metrics["delete_units"]

        # Wrap MilvusClient methods
        for method_info in WRAPPED_METHODS:
            method_name = method_info["method"]
            span_name = method_info["span_name"]

            if getattr(pymilvus, "MilvusClient", None):
                try:
                    wrap_function_wrapper(
                        "pymilvus",
                        f"MilvusClient.{method_name}",
                        create_wrapper(
                            tracer,
                            method_name,
                            span_name,
                            query_duration_metric,
                            distance_metric,
                            insert_units_metric,
                            upsert_units_metric,
                            delete_units_metric,
                        ),
                    )
                    logger.debug(
                        "Successfully wrapped pymilvus.MilvusClient.%s", method_name
                    )
                except Exception as e:
                    logger.debug(
                        "Failed to wrap pymilvus.MilvusClient.%s: %s", method_name, e
                    )

    def _uninstrument(self, **kwargs: Any) -> None:
        """Disable Milvus instrumentation.

        This removes all patches applied during instrumentation.
        """
        import pymilvus

        for method_info in WRAPPED_METHODS:
            method_name = method_info["method"]
            try:
                if getattr(pymilvus, "MilvusClient", None):
                    unwrap(pymilvus.MilvusClient, method_name)
            except Exception:
                pass
