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

"""Tests for LlamaIndex instrumentation."""

import unittest
from unittest.mock import MagicMock, patch

from opentelemetry import trace
from opentelemetry.instrumentation.llamaindex import LlamaIndexInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


class TestLlamaIndexInstrumentor(unittest.TestCase):
    """Test cases for LlamaIndexInstrumentor."""

    def setUp(self):
        """Set up test fixtures."""
        self.span_exporter = InMemorySpanExporter()
        self.provider = TracerProvider()
        self.provider.add_span_processor(
            SimpleSpanProcessor(self.span_exporter)
        )
        trace.set_tracer_provider(self.provider)

    def tearDown(self):
        """Clean up after tests."""
        self.span_exporter.clear()

    def test_instrumentor_initialization(self):
        """Test that instrumentor initializes correctly."""
        instrumentor = LlamaIndexInstrumentor()
        self.assertIsNotNone(instrumentor)
        self.assertFalse(instrumentor._instrumented)

    def test_instrumentation_dependencies(self):
        """Test that instrumentation dependencies are correct."""
        instrumentor = LlamaIndexInstrumentor()
        deps = instrumentor.instrumentation_dependencies()
        self.assertIn("llama-index-core >= 0.10.0", deps)

    @patch("opentelemetry.instrumentation.llamaindex._instrument_with_dispatcher")
    def test_instrument_with_dispatcher(self, mock_dispatcher):
        """Test instrumentation with dispatcher pattern."""
        mock_dispatcher.return_value = True
        instrumentor = LlamaIndexInstrumentor()
        # Call _instrument directly to bypass dependency check
        instrumentor._instrument(tracer_provider=self.provider)
        self.assertTrue(instrumentor._instrumented)

    @patch("opentelemetry.instrumentation.llamaindex._instrument_with_dispatcher")
    def test_instrument_without_dispatcher(self, mock_dispatcher):
        """Test behavior when dispatcher is not available."""
        mock_dispatcher.return_value = False
        instrumentor = LlamaIndexInstrumentor()
        # Call _instrument directly to bypass dependency check
        instrumentor._instrument(tracer_provider=self.provider)
        self.assertFalse(instrumentor._instrumented)

    def test_uninstrument(self):
        """Test uninstrumentation."""
        instrumentor = LlamaIndexInstrumentor()
        instrumentor._instrumented = True
        # Call _uninstrument directly to test the internal method
        instrumentor._uninstrument()
        self.assertFalse(instrumentor._instrumented)


class TestLlamaIndexUtils(unittest.TestCase):
    """Test cases for LlamaIndex utility functions."""

    def test_get_llamaindex_version_not_installed(self):
        """Test version detection when LlamaIndex is not installed."""
        from opentelemetry.instrumentation.llamaindex import (
            _get_llamaindex_version,
        )

        with patch("importlib.metadata.version", side_effect=Exception):
            version = _get_llamaindex_version()
            self.assertEqual(version, "unknown")


class TestSpanHandler(unittest.TestCase):
    """Test cases for OpenTelemetrySpanHandler."""

    def setUp(self):
        """Set up test fixtures."""
        self.span_exporter = InMemorySpanExporter()
        self.provider = TracerProvider()
        self.provider.add_span_processor(
            SimpleSpanProcessor(self.span_exporter)
        )
        trace.set_tracer_provider(self.provider)
        self.tracer = trace.get_tracer(__name__)

    def tearDown(self):
        """Clean up after tests."""
        self.span_exporter.clear()

    def test_span_handler_initialization(self):
        """Test OpenTelemetrySpanHandler initialization."""
        from opentelemetry.instrumentation.llamaindex.span_handler import (
            OpenTelemetrySpanHandler,
        )

        handler = OpenTelemetrySpanHandler(self.tracer)
        self.assertIsNotNone(handler)
        self.assertEqual(handler._tracer, self.tracer)

    def test_event_handler_initialization(self):
        """Test OpenTelemetryEventHandler initialization."""
        from opentelemetry.instrumentation.llamaindex.span_handler import (
            OpenTelemetryEventHandler,
            OpenTelemetrySpanHandler,
        )

        span_handler = OpenTelemetrySpanHandler(self.tracer)
        event_handler = OpenTelemetryEventHandler(span_handler)
        self.assertIsNotNone(event_handler)
        self.assertEqual(event_handler._span_handler, span_handler)


class TestUtilityFunctions(unittest.TestCase):
    """Test cases for utility functions."""

    def test_should_capture_content_default(self):
        """Test default content capture setting."""
        from opentelemetry.instrumentation.llamaindex.utils import (
            should_capture_content,
        )

        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(should_capture_content())

    def test_should_capture_content_enabled(self):
        """Test content capture when enabled."""
        from opentelemetry.instrumentation.llamaindex.utils import (
            should_capture_content,
        )

        with patch.dict(
            "os.environ",
            {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true"},
        ):
            self.assertTrue(should_capture_content())

    def test_safe_json_dumps(self):
        """Test safe JSON serialization."""
        from opentelemetry.instrumentation.llamaindex.utils import (
            safe_json_dumps,
        )

        # Test with simple dict
        result = safe_json_dumps({"key": "value"})
        self.assertEqual(result, '{"key": "value"}')

        # Test with None
        result = safe_json_dumps(None)
        self.assertIsNone(result)

    def test_get_operation_name(self):
        """Test operation name extraction."""
        from opentelemetry.instrumentation.llamaindex.utils import (
            get_operation_name,
        )

        self.assertEqual(get_operation_name("retrieve"), "task")
        self.assertEqual(get_operation_name("synthesize"), "task")
        self.assertEqual(get_operation_name("get_query_embedding"), "embeddings")
        self.assertEqual(get_operation_name("chat"), "agent")
        self.assertEqual(get_operation_name("run"), "workflow")
        self.assertEqual(get_operation_name("unknown"), "task")


if __name__ == "__main__":
    unittest.main()
