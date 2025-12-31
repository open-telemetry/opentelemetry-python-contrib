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
OpenTelemetry Qdrant Instrumentation
====================================

Instrumentation for the Qdrant vector database.

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.qdrant import QdrantInstrumentor
    from qdrant_client import QdrantClient

    # Enable instrumentation
    QdrantInstrumentor().instrument()

    # Use Qdrant client normally
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name="my_collection",
        vectors_config={"size": 4, "distance": "Cosine"}
    )
    client.upsert(
        collection_name="my_collection",
        points=[
            {"id": 1, "vector": [0.1, 0.2, 0.3, 0.4], "payload": {"name": "doc1"}}
        ]
    )
    results = client.search(
        collection_name="my_collection",
        query_vector=[0.1, 0.2, 0.3, 0.4],
        limit=10
    )

API
---
"""

import logging
from typing import Any, Callable, Collection, Optional

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.qdrant.package import _instruments
from opentelemetry.instrumentation.qdrant.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.schemas import Schemas

logger = logging.getLogger(__name__)

MODULE = "qdrant_client"


class QdrantInstrumentor(BaseInstrumentor):
    """An instrumentor for the Qdrant vector database.

    This instrumentor will automatically trace Qdrant operations including
    upsert, search, query, delete, and other operations on both sync and
    async clients.
    """

    def __init__(
        self,
        exception_logger: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        super().__init__()
        self._tracer = None
        self._exception_logger = exception_logger

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable Qdrant instrumentation.

        Args:
            **kwargs: Optional arguments
                - tracer_provider: TracerProvider instance
        """
        import qdrant_client

        from opentelemetry.trace import get_tracer

        from opentelemetry.instrumentation.qdrant.utils import Config
        from opentelemetry.instrumentation.qdrant.wrapper import create_wrapper
        from opentelemetry.instrumentation.qdrant.async_wrapper import create_async_wrapper
        from opentelemetry.instrumentation.qdrant.methods import (
            QDRANT_CLIENT_METHODS,
            ASYNC_QDRANT_CLIENT_METHODS,
        )

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

        # Wrap sync QdrantClient methods
        for method_info in QDRANT_CLIENT_METHODS:
            wrap_object = method_info["object"]
            method_name = method_info["method"]
            span_name = method_info["span_name"]

            if getattr(qdrant_client, wrap_object, None):
                try:
                    wrap_function_wrapper(
                        MODULE,
                        f"{wrap_object}.{method_name}",
                        create_wrapper(tracer, method_name, span_name),
                    )
                    logger.debug(
                        "Successfully wrapped %s.%s.%s", MODULE, wrap_object, method_name
                    )
                except Exception as e:
                    logger.debug(
                        "Failed to wrap %s.%s.%s: %s", MODULE, wrap_object, method_name, e
                    )

        # Wrap async AsyncQdrantClient methods
        for method_info in ASYNC_QDRANT_CLIENT_METHODS:
            wrap_object = method_info["object"]
            method_name = method_info["method"]
            span_name = method_info["span_name"]

            if getattr(qdrant_client, wrap_object, None):
                try:
                    wrap_function_wrapper(
                        MODULE,
                        f"{wrap_object}.{method_name}",
                        create_async_wrapper(tracer, method_name, span_name),
                    )
                    logger.debug(
                        "Successfully wrapped %s.%s.%s", MODULE, wrap_object, method_name
                    )
                except Exception as e:
                    logger.debug(
                        "Failed to wrap %s.%s.%s: %s", MODULE, wrap_object, method_name, e
                    )

    def _uninstrument(self, **kwargs: Any) -> None:
        """Disable Qdrant instrumentation.

        This removes all patches applied during instrumentation.
        """
        from opentelemetry.instrumentation.qdrant.methods import WRAPPED_METHODS

        for method_info in WRAPPED_METHODS:
            wrap_object = method_info["object"]
            method_name = method_info["method"]
            try:
                unwrap(f"{MODULE}.{wrap_object}", method_name)
            except Exception:
                pass
