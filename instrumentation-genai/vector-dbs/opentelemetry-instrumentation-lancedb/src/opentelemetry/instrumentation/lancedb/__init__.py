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
OpenTelemetry LanceDB Instrumentation
=====================================

Instrumentation for the LanceDB vector database.

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.lancedb import LanceDBInstrumentor
    import lancedb

    # Enable instrumentation
    LanceDBInstrumentor().instrument()

    # Use LanceDB client normally
    db = lancedb.connect("./lancedb")
    table = db.create_table("my_table", [{"vector": [1.0, 2.0], "text": "hello"}])
    table.add([{"vector": [3.0, 4.0], "text": "world"}])
    results = table.search([1.0, 2.0]).limit(10).to_list()

API
---
"""

import logging
from typing import Any, Callable, Collection, Optional

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.lancedb.package import _instruments
from opentelemetry.instrumentation.lancedb.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.schemas import Schemas

logger = logging.getLogger(__name__)

# Methods to wrap on LanceTable class
WRAPPED_METHODS = [
    {"method": "add", "span_name": "lancedb.add"},
    {"method": "search", "span_name": "lancedb.search"},
    {"method": "delete", "span_name": "lancedb.delete"},
]


class LanceDBInstrumentor(BaseInstrumentor):
    """An instrumentor for the LanceDB vector database.

    This instrumentor will automatically trace LanceDB operations including
    add, search, and delete operations on tables.
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
        """Enable LanceDB instrumentation.

        Args:
            **kwargs: Optional arguments
                - tracer_provider: TracerProvider instance
        """
        from opentelemetry.trace import get_tracer

        from opentelemetry.instrumentation.lancedb.utils import Config
        from opentelemetry.instrumentation.lancedb.wrapper import create_wrapper

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

        # Wrap LanceTable methods
        for method_info in WRAPPED_METHODS:
            method_name = method_info["method"]
            span_name = method_info["span_name"]

            try:
                wrap_function_wrapper(
                    "lancedb.table",
                    f"LanceTable.{method_name}",
                    create_wrapper(tracer, method_name, span_name),
                )
                logger.debug(
                    "Successfully wrapped lancedb.table.LanceTable.%s", method_name
                )
            except Exception as e:
                logger.debug(
                    "Failed to wrap lancedb.table.LanceTable.%s: %s", method_name, e
                )

    def _uninstrument(self, **kwargs: Any) -> None:
        """Disable LanceDB instrumentation.

        This removes all patches applied during instrumentation.
        """
        for method_info in WRAPPED_METHODS:
            method_name = method_info["method"]
            try:
                unwrap("lancedb.table.LanceTable", method_name)
            except Exception:
                pass
