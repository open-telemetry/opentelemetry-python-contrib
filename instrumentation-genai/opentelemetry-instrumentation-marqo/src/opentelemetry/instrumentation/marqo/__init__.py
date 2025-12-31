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
OpenTelemetry Marqo Instrumentation
===================================

Instrumentation for the Marqo vector database.

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.marqo import MarqoInstrumentor
    import marqo

    # Enable instrumentation
    MarqoInstrumentor().instrument()

    # Use Marqo client normally
    mq = marqo.Client(url="http://localhost:8882")
    mq.index("my-index").add_documents([
        {"title": "Hello, world!", "_id": "doc1"}
    ])
    results = mq.index("my-index").search("hello")

API
---
"""

import logging
from typing import Any, Callable, Collection, Optional

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.marqo.package import _instruments
from opentelemetry.instrumentation.marqo.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.schemas import Schemas

logger = logging.getLogger(__name__)

# Methods to wrap on Index class
WRAPPED_METHODS = [
    {"method": "add_documents", "span_name": "marqo.add_documents"},
    {"method": "search", "span_name": "marqo.search"},
    {"method": "delete_documents", "span_name": "marqo.delete_documents"},
]


class MarqoInstrumentor(BaseInstrumentor):
    """An instrumentor for the Marqo vector database.

    This instrumentor will automatically trace Marqo operations including
    add_documents, search, and delete_documents operations on indexes.
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
        """Enable Marqo instrumentation.

        Args:
            **kwargs: Optional arguments
                - tracer_provider: TracerProvider instance
        """
        from opentelemetry.trace import get_tracer

        from opentelemetry.instrumentation.marqo.utils import Config
        from opentelemetry.instrumentation.marqo.wrapper import create_wrapper

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

        # Wrap Index methods
        for method_info in WRAPPED_METHODS:
            method_name = method_info["method"]
            span_name = method_info["span_name"]

            try:
                wrap_function_wrapper(
                    "marqo.index",
                    f"Index.{method_name}",
                    create_wrapper(tracer, method_name, span_name),
                )
                logger.debug("Successfully wrapped marqo.index.Index.%s", method_name)
            except Exception as e:
                logger.debug("Failed to wrap marqo.index.Index.%s: %s", method_name, e)

    def _uninstrument(self, **kwargs: Any) -> None:
        """Disable Marqo instrumentation.

        This removes all patches applied during instrumentation.
        """
        for method_info in WRAPPED_METHODS:
            method_name = method_info["method"]
            try:
                unwrap("marqo.index.Index", method_name)
            except Exception:
                pass
