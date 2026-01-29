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

# pylint: disable=import-outside-toplevel,no-self-use,redefined-outer-name,unused-variable
# ruff: noqa: PLC0415

"""Unit tests for OpenTelemetry Aerospike Instrumentation."""

from unittest import mock
from unittest.mock import MagicMock, patch

import pytest

from opentelemetry import trace
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind, StatusCode


class TestAerospikeInstrumentation(TestBase):
    """Unit tests using TestBase for consistent test infrastructure."""

    instrumentor = None  # Will be set in _instrument()

    def setUp(self):
        super().setUp()
        self.mock_aerospike = MagicMock()
        self.mock_client = MagicMock()
        self.mock_aerospike.client.return_value = self.mock_client

    def _instrument(self, **kwargs):
        """Helper to instrument with mocked aerospike."""
        with patch.dict("sys.modules", {"aerospike": self.mock_aerospike}):
            from opentelemetry.instrumentation.aerospike import (
                AerospikeInstrumentor,
            )

            self.instrumentor = AerospikeInstrumentor()
            self.instrumentor.instrument(
                tracer_provider=self.tracer_provider, **kwargs
            )

    def _uninstrument(self):
        """Helper to uninstrument."""
        with patch.dict("sys.modules", {"aerospike": self.mock_aerospike}):
            self.instrumentor.uninstrument()

    def test_instrument_uninstrument(self):
        """Test instrument and uninstrument cycle."""
        self._instrument()

        # Verify client function was wrapped
        self.assertTrue(hasattr(self.mock_aerospike.client, "__wrapped__"))

        self._uninstrument()

        # Verify client function was unwrapped
        self.assertFalse(hasattr(self.mock_aerospike.client, "__wrapped__"))

    def test_span_properties(self):
        """Test that spans have correct properties."""
        self.mock_client.get.return_value = (
            ("test", "demo", "key1"),
            {"gen": 1, "ttl": 100},
            {"bin1": "value1"},
        )
        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            client.get(("test", "demo", "key1"))

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)

            span = spans[0]
            self.assertEqual(span.name, "GET test.demo")
            self.assertEqual(span.kind, SpanKind.CLIENT)
            self.assertEqual(span.attributes["db.system"], "aerospike")
            self.assertEqual(span.attributes["db.namespace"], "test")
            self.assertEqual(span.attributes["db.collection.name"], "demo")
            self.assertEqual(span.attributes["db.operation.name"], "GET")
        finally:
            self._uninstrument()

    def test_not_recording(self):
        """Test that attributes are not set when span is not recording."""
        self.mock_client.get.return_value = (
            ("test", "demo", "key1"),
            {"gen": 1, "ttl": 100},
            {"bin1": "value1"},
        )

        mock_tracer = mock.Mock()
        mock_span = mock.Mock()
        mock_span.is_recording.return_value = False
        mock_tracer.start_as_current_span.return_value.__enter__ = mock.Mock(
            return_value=mock_span
        )
        mock_tracer.start_as_current_span.return_value.__exit__ = mock.Mock(
            return_value=False
        )

        with patch.dict("sys.modules", {"aerospike": self.mock_aerospike}):
            with mock.patch("opentelemetry.trace.get_tracer") as tracer:
                tracer.return_value = mock_tracer
                from opentelemetry.instrumentation.aerospike import (
                    AerospikeInstrumentor,
                )

                instrumentor = AerospikeInstrumentor()
                instrumentor.instrument()

                try:
                    client = self.mock_aerospike.client({})
                    client.get(("test", "demo", "key1"))

                    self.assertFalse(mock_span.is_recording())
                    self.assertTrue(mock_span.is_recording.called)
                    self.assertFalse(mock_span.set_attribute.called)
                finally:
                    instrumentor.uninstrument()

    def test_suppress_instrumentation(self):
        """Test that instrumentation can be suppressed."""
        self.mock_client.get.return_value = (
            ("test", "demo", "key1"),
            {"gen": 1, "ttl": 100},
            {"bin1": "value1"},
        )
        self._instrument()

        try:
            client = self.mock_aerospike.client({})

            # Execute with suppression
            with suppress_instrumentation():
                client.get(("test", "demo", "key1"))

            # No spans should be created
            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 0)

            # Verify instrumentation works again after exiting context
            client.get(("test", "demo", "key1"))
            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)
        finally:
            self._uninstrument()

    def test_error_sets_span_status(self):
        """Test that errors set span status correctly."""
        error = ValueError("Record not found")
        error.code = 2  # KEY_NOT_FOUND
        self.mock_client.get.side_effect = error
        self._instrument()

        try:
            client = self.mock_aerospike.client({})

            with self.assertRaises(ValueError):
                client.get(("test", "demo", "key1"))

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)

            span = spans[0]
            self.assertEqual(span.status.status_code, StatusCode.ERROR)
            self.assertEqual(span.attributes["error.type"], "ValueError")
            self.assertEqual(span.attributes["db.response.status_code"], "2")
        finally:
            self._uninstrument()

    def test_batch_operation_includes_size(self):
        """Test that batch operations include batch size attribute."""
        self.mock_client.batch_read.return_value = []
        self._instrument()

        try:
            client = self.mock_aerospike.client({})

            keys = [
                ("test", "demo", "key1"),
                ("test", "demo", "key2"),
                ("test", "demo", "key3"),
            ]
            client.batch_read(keys)

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)

            span = spans[0]
            self.assertEqual(span.attributes["db.operation.batch.size"], 3)
        finally:
            self._uninstrument()

    def test_request_hook(self):
        """Test that request hook is called."""
        self.mock_client.put.return_value = None
        hook_calls = []

        def request_hook(span, operation, args, kwargs):
            hook_calls.append({"operation": operation})
            span.set_attribute("custom.attr", "test")

        self._instrument(request_hook=request_hook)

        try:
            client = self.mock_aerospike.client({})
            client.put(("test", "demo", "key1"), {"bin": "value"})

            self.assertEqual(len(hook_calls), 1)
            self.assertEqual(hook_calls[0]["operation"], "PUT")

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(spans[0].attributes.get("custom.attr"), "test")
        finally:
            self._uninstrument()

    def test_response_hook(self):
        """Test that response hook is called."""
        self.mock_client.get.return_value = (
            ("test", "demo", "key1"),
            {"gen": 1},
            {"bin": "value"},
        )
        hook_calls = []

        def response_hook(span, operation, result):
            hook_calls.append({"operation": operation, "result": result})

        self._instrument(response_hook=response_hook)

        try:
            client = self.mock_aerospike.client({})
            client.get(("test", "demo", "key1"))

            self.assertEqual(len(hook_calls), 1)
            self.assertEqual(hook_calls[0]["operation"], "GET")
        finally:
            self._uninstrument()

    def test_error_hook(self):
        """Test that error hook is called on exception."""
        self.mock_client.get.side_effect = RuntimeError("Test error")
        hook_calls = []

        def error_hook(span, operation, exception):
            hook_calls.append(
                {"operation": operation, "error": str(exception)}
            )

        self._instrument(error_hook=error_hook)

        try:
            client = self.mock_aerospike.client({})

            with self.assertRaises(RuntimeError):
                client.get(("test", "demo", "key1"))

            self.assertEqual(len(hook_calls), 1)
            self.assertEqual(hook_calls[0]["operation"], "GET")
            self.assertIn("Test error", hook_calls[0]["error"])
        finally:
            self._uninstrument()

    def test_capture_key_enabled(self):
        """Test that key is captured when enabled."""
        self.mock_client.put.return_value = None
        self._instrument(capture_key=True)

        try:
            client = self.mock_aerospike.client({})
            client.put(("test", "demo", "my_key"), {"bin": "value"})

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(
                spans[0].attributes.get("db.aerospike.key"), "my_key"
            )
        finally:
            self._uninstrument()

    def test_capture_key_disabled_by_default(self):
        """Test that key is not captured by default."""
        self.mock_client.put.return_value = None
        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            client.put(("test", "demo", "secret_key"), {"bin": "value"})

            spans = self.memory_exporter.get_finished_spans()
            self.assertNotIn("db.aerospike.key", spans[0].attributes)
        finally:
            self._uninstrument()

    def test_no_op_tracer_provider(self):
        """Test with NoOpTracerProvider."""
        self.mock_client.get.return_value = (
            ("test", "demo", "key1"),
            {"gen": 1, "ttl": 100},
            {"bin1": "value1"},
        )

        with patch.dict("sys.modules", {"aerospike": self.mock_aerospike}):
            from opentelemetry.instrumentation.aerospike import (
                AerospikeInstrumentor,
            )

            tracer_provider = trace.NoOpTracerProvider()
            instrumentor = AerospikeInstrumentor()
            instrumentor.instrument(tracer_provider=tracer_provider)

            try:
                client = self.mock_aerospike.client({})
                client.get(("test", "demo", "key1"))

                spans = self.memory_exporter.get_finished_spans()
                self.assertEqual(len(spans), 0)
            finally:
                instrumentor.uninstrument()


# Legacy pytest-style tests for backward compatibility
@pytest.fixture
def tracer_setup():
    """Create a tracer provider with in-memory exporter."""
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


class TestAerospikeInstrumentorUnit:
    """Unit tests for AerospikeInstrumentor using mocks."""

    def test_instrumentation_dependencies(self):
        """Test that dependencies are correctly specified."""
        # Create a mock aerospike module
        mock_aerospike = MagicMock()
        mock_aerospike.client = MagicMock()

        with patch.dict("sys.modules", {"aerospike": mock_aerospike}):
            from opentelemetry.instrumentation.aerospike import (
                AerospikeInstrumentor,
            )

            instrumentor = AerospikeInstrumentor()
            deps = instrumentor.instrumentation_dependencies()

            assert len(deps) == 1
            assert "aerospike >= 17.0.0" in deps[0]

    def test_instrument_uninstrument(self, tracer_setup):
        """Test instrument and uninstrument cycle."""
        provider, exporter = tracer_setup

        mock_aerospike = MagicMock()
        original_client = MagicMock()
        mock_aerospike.client = original_client

        with patch.dict("sys.modules", {"aerospike": mock_aerospike}):
            from opentelemetry.instrumentation.aerospike import (
                AerospikeInstrumentor,
            )

            instrumentor = AerospikeInstrumentor()

            # Instrument
            instrumentor.instrument(tracer_provider=provider)

            # Verify client function was wrapped (wrapped function has __wrapped__)
            assert hasattr(mock_aerospike.client, "__wrapped__")

            # Uninstrument
            instrumentor.uninstrument()

            # Verify client function was unwrapped
            assert not hasattr(mock_aerospike.client, "__wrapped__")


class TestInstrumentedAerospikeClient:
    """Unit tests for InstrumentedAerospikeClient."""

    def test_proxy_passthrough(self, tracer_setup):
        """Test that non-instrumented methods pass through."""
        provider, exporter = tracer_setup

        mock_aerospike = MagicMock()
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.some_other_method.return_value = "result"
        mock_aerospike.client.return_value = mock_client

        with patch.dict("sys.modules", {"aerospike": mock_aerospike}):
            from opentelemetry.instrumentation.aerospike import (
                AerospikeInstrumentor,
            )

            instrumentor = AerospikeInstrumentor()
            instrumentor.instrument(tracer_provider=provider)

            try:
                # Get instrumented client
                client = mock_aerospike.client({})

                # Test connect method
                client.connect()
                mock_client.connect.assert_called_once()

                # Test is_connected
                assert client.is_connected() is True

                # Test close
                client.close()
                mock_client.close.assert_called_once()
            finally:
                instrumentor.uninstrument()

    def test_single_record_operation_creates_span(self, tracer_setup):
        """Test that single record operations create spans."""
        provider, exporter = tracer_setup

        mock_aerospike = MagicMock()
        mock_client = MagicMock()
        mock_client.get.return_value = (
            ("test", "demo", "key1"),
            {"gen": 1, "ttl": 100},
            {"bin1": "value1"},
        )
        mock_aerospike.client.return_value = mock_client

        with patch.dict("sys.modules", {"aerospike": mock_aerospike}):
            from opentelemetry.instrumentation.aerospike import (
                AerospikeInstrumentor,
            )

            instrumentor = AerospikeInstrumentor()
            instrumentor.instrument(tracer_provider=provider)

            try:
                client = mock_aerospike.client({})
                client.get(("test", "demo", "key1"))

                spans = exporter.get_finished_spans()
                assert len(spans) == 1

                span = spans[0]
                assert span.name == "GET test.demo"
                assert span.attributes["db.system"] == "aerospike"
                assert span.attributes["db.namespace"] == "test"
                assert span.attributes["db.collection.name"] == "demo"
                assert span.attributes["db.operation.name"] == "GET"
            finally:
                instrumentor.uninstrument()

    def test_batch_operation_includes_size(self, tracer_setup):
        """Test that batch operations include batch size attribute."""
        provider, exporter = tracer_setup

        mock_aerospike = MagicMock()
        mock_client = MagicMock()
        mock_client.batch_read.return_value = []
        mock_aerospike.client.return_value = mock_client

        with patch.dict("sys.modules", {"aerospike": mock_aerospike}):
            from opentelemetry.instrumentation.aerospike import (
                AerospikeInstrumentor,
            )

            instrumentor = AerospikeInstrumentor()
            instrumentor.instrument(tracer_provider=provider)

            try:
                client = mock_aerospike.client({})

                keys = [
                    ("test", "demo", "key1"),
                    ("test", "demo", "key2"),
                    ("test", "demo", "key3"),
                ]
                client.batch_read(keys)

                spans = exporter.get_finished_spans()
                assert len(spans) == 1

                span = spans[0]
                assert span.attributes["db.operation.batch.size"] == 3
            finally:
                instrumentor.uninstrument()

    def test_error_sets_span_status(self, tracer_setup):
        """Test that errors set span status correctly."""
        provider, exporter = tracer_setup

        mock_aerospike = MagicMock()
        mock_client = MagicMock()

        error = ValueError("Record not found")
        error.code = 2  # KEY_NOT_FOUND
        mock_client.get.side_effect = error
        mock_aerospike.client.return_value = mock_client

        with patch.dict("sys.modules", {"aerospike": mock_aerospike}):
            from opentelemetry.instrumentation.aerospike import (
                AerospikeInstrumentor,
            )

            instrumentor = AerospikeInstrumentor()
            instrumentor.instrument(tracer_provider=provider)

            try:
                client = mock_aerospike.client({})

                with pytest.raises(ValueError):
                    client.get(("test", "demo", "key1"))

                spans = exporter.get_finished_spans()
                assert len(spans) == 1

                span = spans[0]
                assert span.status.status_code == StatusCode.ERROR
                assert span.attributes["error.type"] == "ValueError"
                assert span.attributes["db.response.status_code"] == "2"
            finally:
                instrumentor.uninstrument()

    def test_request_hook_called(self, tracer_setup):
        """Test that request hook is called."""
        provider, exporter = tracer_setup

        mock_aerospike = MagicMock()
        mock_client = MagicMock()
        mock_client.put.return_value = None
        mock_aerospike.client.return_value = mock_client

        hook_calls = []

        def request_hook(span, operation, args, kwargs):
            hook_calls.append({"operation": operation})
            span.set_attribute("custom.attr", "test")

        with patch.dict("sys.modules", {"aerospike": mock_aerospike}):
            from opentelemetry.instrumentation.aerospike import (
                AerospikeInstrumentor,
            )

            instrumentor = AerospikeInstrumentor()
            instrumentor.instrument(
                tracer_provider=provider, request_hook=request_hook
            )

            try:
                client = mock_aerospike.client({})
                client.put(("test", "demo", "key1"), {"bin": "value"})

                assert len(hook_calls) == 1
                assert hook_calls[0]["operation"] == "PUT"

                spans = exporter.get_finished_spans()
                assert spans[0].attributes.get("custom.attr") == "test"
            finally:
                instrumentor.uninstrument()

    def test_response_hook_called(self, tracer_setup):
        """Test that response hook is called."""
        provider, exporter = tracer_setup

        mock_aerospike = MagicMock()
        mock_client = MagicMock()
        mock_client.get.return_value = (
            ("test", "demo", "key1"),
            {"gen": 1},
            {"bin": "value"},
        )
        mock_aerospike.client.return_value = mock_client

        hook_calls = []

        def response_hook(span, operation, result):
            hook_calls.append({"operation": operation, "result": result})

        with patch.dict("sys.modules", {"aerospike": mock_aerospike}):
            from opentelemetry.instrumentation.aerospike import (
                AerospikeInstrumentor,
            )

            instrumentor = AerospikeInstrumentor()
            instrumentor.instrument(
                tracer_provider=provider, response_hook=response_hook
            )

            try:
                client = mock_aerospike.client({})
                client.get(("test", "demo", "key1"))

                assert len(hook_calls) == 1
                assert hook_calls[0]["operation"] == "GET"
            finally:
                instrumentor.uninstrument()

    def test_error_hook_called(self, tracer_setup):
        """Test that error hook is called on exception."""
        provider, exporter = tracer_setup

        mock_aerospike = MagicMock()
        mock_client = MagicMock()
        mock_client.get.side_effect = RuntimeError("Test error")
        mock_aerospike.client.return_value = mock_client

        hook_calls = []

        def error_hook(span, operation, exception):
            hook_calls.append(
                {"operation": operation, "error": str(exception)}
            )

        with patch.dict("sys.modules", {"aerospike": mock_aerospike}):
            from opentelemetry.instrumentation.aerospike import (
                AerospikeInstrumentor,
            )

            instrumentor = AerospikeInstrumentor()
            instrumentor.instrument(
                tracer_provider=provider, error_hook=error_hook
            )

            try:
                client = mock_aerospike.client({})

                with pytest.raises(RuntimeError):
                    client.get(("test", "demo", "key1"))

                assert len(hook_calls) == 1
                assert hook_calls[0]["operation"] == "GET"
                assert "Test error" in hook_calls[0]["error"]
            finally:
                instrumentor.uninstrument()

    def test_capture_key_enabled(self, tracer_setup):
        """Test that key is captured when enabled."""
        provider, exporter = tracer_setup

        mock_aerospike = MagicMock()
        mock_client = MagicMock()
        mock_client.put.return_value = None
        mock_aerospike.client.return_value = mock_client

        with patch.dict("sys.modules", {"aerospike": mock_aerospike}):
            from opentelemetry.instrumentation.aerospike import (
                AerospikeInstrumentor,
            )

            instrumentor = AerospikeInstrumentor()
            instrumentor.instrument(tracer_provider=provider, capture_key=True)

            try:
                client = mock_aerospike.client({})
                client.put(("test", "demo", "my_key"), {"bin": "value"})

                spans = exporter.get_finished_spans()
                assert spans[0].attributes.get("db.aerospike.key") == "my_key"
            finally:
                instrumentor.uninstrument()

    def test_capture_key_disabled_by_default(self, tracer_setup):
        """Test that key is not captured by default."""
        provider, exporter = tracer_setup

        mock_aerospike = MagicMock()
        mock_client = MagicMock()
        mock_client.put.return_value = None
        mock_aerospike.client.return_value = mock_client

        with patch.dict("sys.modules", {"aerospike": mock_aerospike}):
            from opentelemetry.instrumentation.aerospike import (
                AerospikeInstrumentor,
            )

            instrumentor = AerospikeInstrumentor()
            instrumentor.instrument(tracer_provider=provider)

            try:
                client = mock_aerospike.client({})
                client.put(("test", "demo", "secret_key"), {"bin": "value"})

                spans = exporter.get_finished_spans()
                assert "db.aerospike.key" not in spans[0].attributes
            finally:
                instrumentor.uninstrument()

    def test_query_operation(self, tracer_setup):
        """Test query operation creates correct span."""
        provider, exporter = tracer_setup

        mock_aerospike = MagicMock()
        mock_client = MagicMock()
        mock_query = MagicMock()
        mock_client.query.return_value = mock_query
        mock_aerospike.client.return_value = mock_client

        with patch.dict("sys.modules", {"aerospike": mock_aerospike}):
            from opentelemetry.instrumentation.aerospike import (
                AerospikeInstrumentor,
            )

            instrumentor = AerospikeInstrumentor()
            instrumentor.instrument(tracer_provider=provider)

            try:
                client = mock_aerospike.client({})
                client.query("test", "users")

                spans = exporter.get_finished_spans()
                assert len(spans) == 1

                span = spans[0]
                assert span.name == "QUERY test.users"
                assert span.attributes["db.operation.name"] == "QUERY"
            finally:
                instrumentor.uninstrument()

    def test_udf_operation_captures_module_function(self, tracer_setup):
        """Test UDF operation captures module and function names."""
        provider, exporter = tracer_setup

        mock_aerospike = MagicMock()
        mock_client = MagicMock()
        mock_client.apply.return_value = "result"
        mock_aerospike.client.return_value = mock_client

        with patch.dict("sys.modules", {"aerospike": mock_aerospike}):
            from opentelemetry.instrumentation.aerospike import (
                AerospikeInstrumentor,
            )

            instrumentor = AerospikeInstrumentor()
            instrumentor.instrument(tracer_provider=provider)

            try:
                client = mock_aerospike.client({})
                client.apply(
                    ("test", "demo", "key1"),
                    "mymodule",
                    "myfunction",
                    ["arg1"],
                )

                spans = exporter.get_finished_spans()
                span = spans[0]

                assert span.name == "APPLY test.demo"
                assert (
                    span.attributes.get("db.aerospike.udf.module")
                    == "mymodule"
                )
                assert (
                    span.attributes.get("db.aerospike.udf.function")
                    == "myfunction"
                )
            finally:
                instrumentor.uninstrument()

    def test_result_metadata_captured(self, tracer_setup):
        """Test that generation and TTL are captured from results."""
        provider, exporter = tracer_setup

        mock_aerospike = MagicMock()
        mock_client = MagicMock()
        mock_client.get.return_value = (
            ("test", "demo", "key1"),
            {"gen": 5, "ttl": 3600},
            {"bin": "value"},
        )
        mock_aerospike.client.return_value = mock_client

        with patch.dict("sys.modules", {"aerospike": mock_aerospike}):
            from opentelemetry.instrumentation.aerospike import (
                AerospikeInstrumentor,
            )

            instrumentor = AerospikeInstrumentor()
            instrumentor.instrument(tracer_provider=provider)

            try:
                client = mock_aerospike.client({})
                client.get(("test", "demo", "key1"))

                spans = exporter.get_finished_spans()
                span = spans[0]

                assert span.attributes.get("db.aerospike.generation") == 5
                assert span.attributes.get("db.aerospike.ttl") == 3600
            finally:
                instrumentor.uninstrument()


class TestSpanNaming:
    """Tests for span naming conventions."""

    def test_span_name_format(self, tracer_setup):
        """Test span name follows {operation} {namespace}.{set} format."""
        provider, exporter = tracer_setup

        mock_aerospike = MagicMock()
        mock_client = MagicMock()
        mock_client.put.return_value = None
        mock_aerospike.client.return_value = mock_client

        with patch.dict("sys.modules", {"aerospike": mock_aerospike}):
            from opentelemetry.instrumentation.aerospike import (
                AerospikeInstrumentor,
            )

            instrumentor = AerospikeInstrumentor()
            instrumentor.instrument(tracer_provider=provider)

            try:
                client = mock_aerospike.client({})
                client.put(
                    ("production", "orders", "order123"), {"total": 100}
                )

                spans = exporter.get_finished_spans()
                assert spans[0].name == "PUT production.orders"
            finally:
                instrumentor.uninstrument()

    def test_span_name_without_set(self, tracer_setup):
        """Test span name when set is None."""
        provider, exporter = tracer_setup

        mock_aerospike = MagicMock()
        mock_client = MagicMock()
        mock_client.put.return_value = None
        mock_aerospike.client.return_value = mock_client

        with patch.dict("sys.modules", {"aerospike": mock_aerospike}):
            from opentelemetry.instrumentation.aerospike import (
                AerospikeInstrumentor,
            )

            instrumentor = AerospikeInstrumentor()
            instrumentor.instrument(tracer_provider=provider)

            try:
                client = mock_aerospike.client({})
                client.put(("test", None, "key1"), {"bin": "value"})

                spans = exporter.get_finished_spans()
                assert spans[0].name == "PUT test"
            finally:
                instrumentor.uninstrument()
