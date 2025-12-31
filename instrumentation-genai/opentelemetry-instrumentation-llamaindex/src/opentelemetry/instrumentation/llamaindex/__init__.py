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
LlamaIndex instrumentation for OpenTelemetry.

This instrumentation provides automatic tracing of LlamaIndex operations,
including:
- Query engine executions
- Retriever operations
- Synthesizer operations
- Embedding operations
- Agent operations
- Tool executions
- Query pipelines

LlamaIndex is a data framework for LLM applications that provides tools
for data ingestion, indexing, and querying.

This instrumentation supports LlamaIndex 0.10.0+ and uses the native
dispatcher pattern for automatic instrumentation.

Usage
-----
.. code:: python

    from opentelemetry.instrumentation.llamaindex import LlamaIndexInstrumentor
    from llama_index.core import VectorStoreIndex, SimpleDirectoryReader

    LlamaIndexInstrumentor().instrument()

    # Load documents and create index
    documents = SimpleDirectoryReader('data').load_data()
    index = VectorStoreIndex.from_documents(documents)

    # Query the index
    query_engine = index.as_query_engine()
    response = query_engine.query("What is the document about?")

    LlamaIndexInstrumentor().uninstrument()

API
---
"""

import logging
from typing import Any, Collection

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.llamaindex.package import _instruments
from opentelemetry.instrumentation.llamaindex.version import __version__
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer

logger = logging.getLogger(__name__)


def _get_llamaindex_version() -> str:
    """Get the installed LlamaIndex version.

    Returns:
        The version string, or "unknown" if not found.
    """
    try:
        from importlib.metadata import version

        return version("llama-index-core")
    except Exception:
        try:
            from importlib.metadata import version

            return version("llama-index")
        except Exception:
            return "unknown"


def _instrument_with_dispatcher(tracer: Any) -> bool:
    """Instrument LlamaIndex using the dispatcher pattern.

    This is the preferred method for LlamaIndex 0.10.20+.

    Args:
        tracer: The OpenTelemetry tracer.

    Returns:
        True if instrumentation succeeded, False otherwise.
    """
    try:
        from llama_index.core.instrumentation import get_dispatcher

        from opentelemetry.instrumentation.llamaindex.span_handler import (
            OpenTelemetryEventHandler,
            OpenTelemetrySpanHandler,
        )

        dispatcher = get_dispatcher()
        span_handler = OpenTelemetrySpanHandler(tracer)
        event_handler = OpenTelemetryEventHandler(span_handler)

        dispatcher.add_span_handler(span_handler)
        dispatcher.add_event_handler(event_handler)

        return True
    except ImportError:
        logger.debug(
            "LlamaIndex dispatcher not available, instrumentation not applied"
        )
        return False
    except Exception as e:
        logger.debug("Failed to instrument with dispatcher: %s", e)
        return False


class LlamaIndexInstrumentor(BaseInstrumentor):
    """OpenTelemetry instrumentor for LlamaIndex.

    This instrumentor uses LlamaIndex's native dispatcher pattern to
    automatically create spans for various operations.

    Features:
        - Automatic span creation for query engine operations
        - Retriever operation tracing
        - Synthesizer operation tracing
        - Embedding operation tracing
        - Agent and tool execution tracing
        - Support for streaming responses
        - Token usage metrics

    Example:
        >>> from opentelemetry.instrumentation.llamaindex import LlamaIndexInstrumentor
        >>> instrumentor = LlamaIndexInstrumentor()
        >>> instrumentor.instrument()
        >>> # Use LlamaIndex as normal
        >>> instrumentor.uninstrument()

    Attributes:
        All spans use the `gen_ai.llamaindex.*` namespace for custom attributes,
        following OpenTelemetry semantic conventions.

    Note:
        This instrumentation requires LlamaIndex 0.10.0 or higher.
        The dispatcher pattern is used for versions 0.10.20+.
    """

    def __init__(self) -> None:
        """Initialize the LlamaIndex instrumentor."""
        super().__init__()
        self._instrumented = False

    def instrumentation_dependencies(self) -> Collection[str]:
        """Return the instrumented package dependencies."""
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable LlamaIndex instrumentation.

        Args:
            **kwargs: Additional configuration options.
                - tracer_provider: Custom TracerProvider
                - meter_provider: Custom MeterProvider
        """
        tracer_provider = kwargs.get("tracer_provider")

        tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=Schemas.V1_28_0.value,
        )

        # Get LlamaIndex version
        version = _get_llamaindex_version()
        logger.debug("LlamaIndex version: %s", version)

        # Try to instrument with dispatcher (0.10.20+)
        if _instrument_with_dispatcher(tracer):
            self._instrumented = True
            logger.debug("LlamaIndex instrumented using dispatcher")
        else:
            logger.warning(
                "LlamaIndex instrumentation could not be applied. "
                "Ensure llama-index-core >= 0.10.0 is installed."
            )

    def _uninstrument(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Disable LlamaIndex instrumentation.

        Note: Due to the dispatcher pattern, uninstrumentation
        may not fully remove all instrumentation hooks.
        """
        self._instrumented = False
        logger.debug("LlamaIndex instrumentation uninstrumented")
