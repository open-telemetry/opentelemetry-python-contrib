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
OpenTelemetry ChromaDB Instrumentation
======================================

Instrumentation for the ChromaDB vector database.

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.chromadb import ChromaInstrumentor
    import chromadb

    # Enable instrumentation
    ChromaInstrumentor().instrument()

    # Use ChromaDB client normally
    client = chromadb.Client()
    collection = client.create_collection("my_collection")
    collection.add(
        documents=["Hello, world!"],
        metadatas=[{"source": "example"}],
        ids=["id1"]
    )
    results = collection.query(query_texts=["Hello"], n_results=1)

API
---
"""

import logging
from typing import Any, Callable, Collection, Optional

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.chromadb.package import _instruments
from opentelemetry.instrumentation.chromadb.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.schemas import Schemas

logger = logging.getLogger(__name__)

# Methods to wrap on Collection class
WRAPPED_COLLECTION_METHODS = [
    {"method": "add", "span_name": "chroma.add"},
    {"method": "get", "span_name": "chroma.get"},
    {"method": "peek", "span_name": "chroma.peek"},
    {"method": "query", "span_name": "chroma.query"},
    {"method": "modify", "span_name": "chroma.modify"},
    {"method": "update", "span_name": "chroma.update"},
    {"method": "upsert", "span_name": "chroma.upsert"},
    {"method": "delete", "span_name": "chroma.delete"},
]

# Internal method on SegmentAPI
WRAPPED_SEGMENT_METHODS = [
    {"method": "_query", "span_name": "chroma.query.segment._query"},
]


class ChromaInstrumentor(BaseInstrumentor):
    """An instrumentor for the ChromaDB vector database.

    This instrumentor will automatically trace ChromaDB operations including
    add, get, query, update, delete, and other collection methods.
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
        """Enable ChromaDB instrumentation.

        Args:
            **kwargs: Optional arguments
                - tracer_provider: TracerProvider instance
        """
        from opentelemetry.trace import get_tracer

        from opentelemetry.instrumentation.chromadb.utils import Config
        from opentelemetry.instrumentation.chromadb.wrapper import create_wrapper

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

        # Wrap Collection methods
        for method_info in WRAPPED_COLLECTION_METHODS:
            method_name = method_info["method"]
            span_name = method_info["span_name"]

            try:
                wrap_function_wrapper(
                    "chromadb",
                    f"Collection.{method_name}",
                    create_wrapper(tracer, method_name, span_name),
                )
                logger.debug("Successfully wrapped chromadb.Collection.%s", method_name)
            except Exception as e:
                logger.debug("Failed to wrap chromadb.Collection.%s: %s", method_name, e)

        # Wrap SegmentAPI methods
        for method_info in WRAPPED_SEGMENT_METHODS:
            method_name = method_info["method"]
            span_name = method_info["span_name"]

            try:
                wrap_function_wrapper(
                    "chromadb.api.segment",
                    f"SegmentAPI.{method_name}",
                    create_wrapper(tracer, method_name, span_name),
                )
                logger.debug(
                    "Successfully wrapped chromadb.api.segment.SegmentAPI.%s",
                    method_name,
                )
            except Exception as e:
                logger.debug(
                    "Failed to wrap chromadb.api.segment.SegmentAPI.%s: %s",
                    method_name,
                    e,
                )

    def _uninstrument(self, **kwargs: Any) -> None:
        """Disable ChromaDB instrumentation.

        This removes all patches applied during instrumentation.
        """
        for method_info in WRAPPED_COLLECTION_METHODS:
            method_name = method_info["method"]
            try:
                unwrap("chromadb.Collection", method_name)
            except Exception:
                pass

        for method_info in WRAPPED_SEGMENT_METHODS:
            method_name = method_info["method"]
            try:
                unwrap("chromadb.api.segment.SegmentAPI", method_name)
            except Exception:
                pass
