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
OpenTelemetry Pinecone Instrumentation
======================================

Instrumentation for the Pinecone vector database.

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.pinecone import PineconeInstrumentor
    from pinecone import Pinecone

    # Enable instrumentation
    PineconeInstrumentor().instrument()

    # Use Pinecone client normally
    pc = Pinecone(api_key="your-api-key")
    index = pc.Index("my-index")
    index.upsert(vectors=[{"id": "vec1", "values": [0.1, 0.2, 0.3]}])
    results = index.query(vector=[0.1, 0.2, 0.3], top_k=10)

API
---
"""

import logging
from typing import Any, Callable, Collection, Optional

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.pinecone.package import _instruments
from opentelemetry.instrumentation.pinecone.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.schemas import Schemas

logger = logging.getLogger(__name__)

# Methods to wrap on GRPCIndex and Index classes
WRAPPED_METHODS = [
    {"object": "GRPCIndex", "method": "query", "span_name": "pinecone.query"},
    {"object": "GRPCIndex", "method": "upsert", "span_name": "pinecone.upsert"},
    {"object": "GRPCIndex", "method": "delete", "span_name": "pinecone.delete"},
    {"object": "Index", "method": "query", "span_name": "pinecone.query"},
    {"object": "Index", "method": "upsert", "span_name": "pinecone.upsert"},
    {"object": "Index", "method": "delete", "span_name": "pinecone.delete"},
]


class PineconeInstrumentor(BaseInstrumentor):
    """An instrumentor for the Pinecone vector database.

    This instrumentor will automatically trace Pinecone operations including
    query, upsert, and delete operations on indexes.
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
        """Enable Pinecone instrumentation.

        Args:
            **kwargs: Optional arguments
                - tracer_provider: TracerProvider instance
                - meter_provider: MeterProvider instance
        """
        import pinecone

        from opentelemetry.metrics import get_meter
        from opentelemetry.trace import get_tracer

        from opentelemetry.instrumentation.pinecone.utils import (
            Config,
            is_metrics_enabled,
        )
        from opentelemetry.instrumentation.pinecone.wrapper import create_wrapper
        from opentelemetry.instrumentation.pinecone.instruments import create_metrics

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
        read_units_metric = None
        write_units_metric = None
        scores_metric = None

        if is_metrics_enabled():
            meter_provider = kwargs.get("meter_provider")
            meter = get_meter(__name__, __version__, meter_provider)
            self._metrics = create_metrics(meter)
            query_duration_metric = self._metrics["query_duration"]
            read_units_metric = self._metrics["read_units"]
            write_units_metric = self._metrics["write_units"]
            scores_metric = self._metrics["scores"]

        # Wrap Index methods
        for method_info in WRAPPED_METHODS:
            wrap_object = method_info["object"]
            method_name = method_info["method"]
            span_name = method_info["span_name"]

            if getattr(pinecone, wrap_object, None):
                try:
                    wrap_function_wrapper(
                        "pinecone",
                        f"{wrap_object}.{method_name}",
                        create_wrapper(
                            tracer,
                            method_name,
                            span_name,
                            query_duration_metric,
                            read_units_metric,
                            write_units_metric,
                            scores_metric,
                        ),
                    )
                    logger.debug(
                        "Successfully wrapped pinecone.%s.%s", wrap_object, method_name
                    )
                except Exception as e:
                    logger.debug(
                        "Failed to wrap pinecone.%s.%s: %s", wrap_object, method_name, e
                    )

    def _uninstrument(self, **kwargs: Any) -> None:
        """Disable Pinecone instrumentation.

        This removes all patches applied during instrumentation.
        """
        for method_info in WRAPPED_METHODS:
            wrap_object = method_info["object"]
            method_name = method_info["method"]
            try:
                unwrap(f"pinecone.{wrap_object}", method_name)
            except Exception:
                pass
