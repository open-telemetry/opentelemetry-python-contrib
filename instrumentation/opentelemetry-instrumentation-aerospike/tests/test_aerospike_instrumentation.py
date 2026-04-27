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

# pylint: disable=import-outside-toplevel,no-self-use,redefined-outer-name,unused-variable,too-many-lines
# ruff: noqa: PLC0415

"""Unit tests for OpenTelemetry Aerospike Instrumentation."""

from unittest import mock
from unittest.mock import MagicMock, patch

from opentelemetry import trace
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind, StatusCode


class TestAerospikeInstrumentation(TestBase):  # pylint: disable=too-many-public-methods
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
            self.assertEqual(span.attributes["db.system.name"], "aerospike")
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

    def test_instrumentation_dependencies(self):
        """Test that dependencies are correctly specified."""
        with patch.dict("sys.modules", {"aerospike": self.mock_aerospike}):
            from opentelemetry.instrumentation.aerospike import (
                AerospikeInstrumentor,
            )

            instrumentor = AerospikeInstrumentor()
            deps = instrumentor.instrumentation_dependencies()

            self.assertEqual(len(deps), 1)
            self.assertIn("aerospike >= 17.0.0", deps[0])

    def test_proxy_passthrough(self):
        """Test that non-instrumented methods pass through."""
        self.mock_client.is_connected.return_value = True
        self.mock_client.some_other_method.return_value = "result"
        self._instrument()

        try:
            client = self.mock_aerospike.client({})

            client.connect()
            self.mock_client.connect.assert_called_once()

            self.assertTrue(client.is_connected())

            client.close()
            self.mock_client.close.assert_called_once()
        finally:
            self._uninstrument()

    def test_query_factory_no_span(self):
        """Test that client.query() factory alone creates no span."""
        mock_query = MagicMock()
        self.mock_client.query.return_value = mock_query
        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            client.query("test", "users")

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 0)
        finally:
            self._uninstrument()

    def test_query_results_creates_span(self):
        """Test that query.results() creates the correct span."""
        mock_query = MagicMock()
        mock_query.results.return_value = []
        self.mock_client.query.return_value = mock_query
        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            query = client.query("test", "users")
            query.results()

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)

            span = spans[0]
            self.assertEqual(span.name, "QUERY test.users")
            self.assertEqual(span.attributes["db.operation.name"], "QUERY")
            self.assertEqual(span.attributes["db.namespace"], "test")
            self.assertEqual(span.attributes["db.collection.name"], "users")
        finally:
            self._uninstrument()

    def test_query_foreach_creates_span(self):
        """Test that query.foreach() creates the correct span."""
        mock_query = MagicMock()
        mock_query.foreach.return_value = None
        self.mock_client.query.return_value = mock_query
        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            query = client.query("test", "users")
            query.foreach(lambda rec: None)

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)

            span = spans[0]
            self.assertEqual(span.name, "QUERY test.users")
            self.assertEqual(span.attributes["db.operation.name"], "QUERY")
        finally:
            self._uninstrument()

    def test_query_config_methods_passthrough(self):
        """Test that config methods (select, where) pass through without span."""
        mock_query = MagicMock()
        mock_query.select.return_value = None
        mock_query.where.return_value = None
        self.mock_client.query.return_value = mock_query
        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            query = client.query("test", "users")
            query.select("bin1", "bin2")
            query.where(MagicMock())

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 0)

            # Verify calls were forwarded to the inner object
            mock_query.select.assert_called_once_with("bin1", "bin2")
            mock_query.where.assert_called_once()
        finally:
            self._uninstrument()

    def test_query_results_with_error(self):
        """Test that errors during query.results() set span error status."""
        mock_query = MagicMock()
        error = RuntimeError("Query failed")
        mock_query.results.side_effect = error
        self.mock_client.query.return_value = mock_query
        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            query = client.query("test", "users")

            with self.assertRaises(RuntimeError):
                query.results()

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)

            span = spans[0]
            self.assertEqual(span.status.status_code, StatusCode.ERROR)
            self.assertEqual(span.attributes["error.type"], "RuntimeError")
        finally:
            self._uninstrument()

    def test_query_results_hooks(self):
        """Test that request/response/error hooks work with query.results()."""
        mock_query = MagicMock()
        mock_query.results.return_value = [("key", "meta", "bins")]
        self.mock_client.query.return_value = mock_query

        request_calls = []
        response_calls = []

        def request_hook(span, operation, args, kwargs):
            request_calls.append(operation)

        def response_hook(span, operation, result):
            response_calls.append(operation)

        self._instrument(
            request_hook=request_hook, response_hook=response_hook
        )

        try:
            client = self.mock_aerospike.client({})
            query = client.query("test", "users")
            query.results()

            self.assertEqual(len(request_calls), 1)
            self.assertEqual(request_calls[0], "QUERY")
            self.assertEqual(len(response_calls), 1)
            self.assertEqual(response_calls[0], "QUERY")
        finally:
            self._uninstrument()

    def test_query_suppress_instrumentation(self):
        """Test that suppress_instrumentation prevents query span creation."""
        mock_query = MagicMock()
        mock_query.results.return_value = []
        self.mock_client.query.return_value = mock_query
        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            query = client.query("test", "users")

            with suppress_instrumentation():
                query.results()

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 0)
        finally:
            self._uninstrument()

    def test_query_method_chaining(self):
        """Test that chaining config methods preserves instrumentation."""
        mock_query = MagicMock()
        # select() returns the inner query object (self-chaining pattern)
        mock_query.select.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.results.return_value = [("key", "meta", "bins")]
        self.mock_client.query.return_value = mock_query
        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            # This chain must produce a span on .results()
            client.query("test", "users").select("bin1").where(
                MagicMock()
            ).results()

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)

            span = spans[0]
            self.assertEqual(span.name, "QUERY test.users")
            self.assertEqual(span.attributes["db.operation.name"], "QUERY")
        finally:
            self._uninstrument()

    def test_udf_operation_captures_module_function(self):
        """Test UDF operation captures module and function names."""
        self.mock_client.apply.return_value = "result"
        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            client.apply(
                ("test", "demo", "key1"),
                "mymodule",
                "myfunction",
                ["arg1"],
            )

            spans = self.memory_exporter.get_finished_spans()
            span = spans[0]

            self.assertEqual(span.name, "APPLY test.demo")
            self.assertEqual(
                span.attributes.get("db.aerospike.udf.module"), "mymodule"
            )
            self.assertEqual(
                span.attributes.get("db.aerospike.udf.function"), "myfunction"
            )
        finally:
            self._uninstrument()

    def test_result_metadata_captured(self):
        """Test that generation and TTL are captured from results."""
        self.mock_client.get.return_value = (
            ("test", "demo", "key1"),
            {"gen": 5, "ttl": 3600},
            {"bin": "value"},
        )
        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            client.get(("test", "demo", "key1"))

            spans = self.memory_exporter.get_finished_spans()
            span = spans[0]

            self.assertEqual(span.attributes.get("db.aerospike.generation"), 5)
            self.assertEqual(span.attributes.get("db.aerospike.ttl"), 3600)
        finally:
            self._uninstrument()

    def test_span_name_format(self):
        """Test span name follows {operation} {namespace}.{set} format."""
        self.mock_client.put.return_value = None
        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            client.put(("production", "orders", "order123"), {"total": 100})

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(spans[0].name, "PUT production.orders")
        finally:
            self._uninstrument()

    def test_span_name_without_set(self):
        """Test span name when set is None."""
        self.mock_client.put.return_value = None
        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            client.put(("test", None, "key1"), {"bin": "value"})

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(spans[0].name, "PUT test")
        finally:
            self._uninstrument()

    def test_scan_apply_creates_correct_span(self):
        """Test scan_apply uses namespace/set args, not key_tuple."""
        self.mock_client.scan_apply.return_value = 12345
        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            client.scan_apply("test", "demo", "mymodule", "myfunc", ["arg1"])

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)

            span = spans[0]
            self.assertEqual(span.name, "SCAN APPLY test.demo")
            self.assertEqual(span.attributes["db.namespace"], "test")
            self.assertEqual(span.attributes["db.collection.name"], "demo")
            self.assertEqual(
                span.attributes["db.operation.name"], "SCAN APPLY"
            )
            self.assertEqual(
                span.attributes["db.aerospike.udf.module"], "mymodule"
            )
            self.assertEqual(
                span.attributes["db.aerospike.udf.function"], "myfunc"
            )
        finally:
            self._uninstrument()

    def test_query_apply_creates_correct_span(self):
        """Test query_apply uses namespace/set args with predicate offset."""
        self.mock_client.query_apply.return_value = 67890
        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            predicate = MagicMock()
            client.query_apply(
                "test", "demo", predicate, "mymodule", "myfunc", ["arg1"]
            )

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)

            span = spans[0]
            self.assertEqual(span.name, "QUERY APPLY test.demo")
            self.assertEqual(span.attributes["db.namespace"], "test")
            self.assertEqual(span.attributes["db.collection.name"], "demo")
            self.assertEqual(
                span.attributes["db.operation.name"], "QUERY APPLY"
            )
            self.assertEqual(
                span.attributes["db.aerospike.udf.module"], "mymodule"
            )
            self.assertEqual(
                span.attributes["db.aerospike.udf.function"], "myfunc"
            )
        finally:
            self._uninstrument()

    def test_scan_results_creates_span(self):
        """Test that scan.results() creates the correct span."""
        mock_scan = MagicMock()
        mock_scan.results.return_value = []
        self.mock_client.scan.return_value = mock_scan
        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            scan = client.scan("test", "demo")
            scan.results()

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)

            span = spans[0]
            self.assertEqual(span.name, "SCAN test.demo")
            self.assertEqual(span.attributes["db.operation.name"], "SCAN")
            self.assertEqual(span.attributes["db.namespace"], "test")
            self.assertEqual(span.attributes["db.collection.name"], "demo")
        finally:
            self._uninstrument()

    def test_scan_foreach_creates_span(self):
        """Test that scan.foreach() creates the correct span."""
        mock_scan = MagicMock()
        mock_scan.foreach.return_value = None
        self.mock_client.scan.return_value = mock_scan
        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            scan = client.scan("test", "demo")
            scan.foreach(lambda rec: None)

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)

            span = spans[0]
            self.assertEqual(span.name, "SCAN test.demo")
            self.assertEqual(span.attributes["db.operation.name"], "SCAN")
        finally:
            self._uninstrument()

    def test_truncate_admin_method(self):
        """Test truncate admin operation creates correct span."""
        self.mock_client.truncate.return_value = None
        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            client.truncate("test", "demo", 0)

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)

            span = spans[0]
            self.assertEqual(span.name, "TRUNCATE test.demo")
            self.assertEqual(span.attributes["db.operation.name"], "TRUNCATE")
        finally:
            self._uninstrument()

    def test_info_all_admin_method(self):
        """Test info_all admin operation creates correct span without namespace."""
        self.mock_client.info_all.return_value = {}
        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            client.info_all("status")

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)

            span = spans[0]
            self.assertEqual(span.attributes["db.operation.name"], "INFO_ALL")
            # info_all takes a command string, not namespace — must not leak
            self.assertNotIn("db.namespace", span.attributes)
        finally:
            self._uninstrument()

    def test_connect_returns_self(self):
        """Test that connect() returns the instrumented client (self)."""
        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            result = client.connect()

            self.assertIs(result, client)
        finally:
            self._uninstrument()

    def test_update_server_info_from_nodes(self):
        """Test that server info is updated from connected nodes."""
        mock_node = MagicMock()
        mock_node.name = "192.168.1.1:3000"
        self.mock_client.get_nodes.return_value = [mock_node]

        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            client.connect()

            self.assertEqual(client._server_address, "192.168.1.1")
            self.assertEqual(client._server_port, 3000)
        finally:
            self._uninstrument()

    def test_update_server_info_from_tuple_nodes(self):
        """Test that server info handles tuple-style node return."""
        self.mock_client.get_nodes.return_value = [("10.0.0.1", 3000)]

        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            client.connect()

            self.assertEqual(client._server_address, "10.0.0.1")
            self.assertEqual(client._server_port, 3000)
        finally:
            self._uninstrument()

    def test_update_server_info_no_nodes(self):
        """Test that server info gracefully handles no nodes."""
        self.mock_client.get_nodes.return_value = []

        config = {"hosts": [("127.0.0.1", 3000)]}
        self._instrument()

        try:
            client = self.mock_aerospike.client(config)
            client.connect()

            # Should keep the config-based values
            self.assertEqual(client._server_address, "127.0.0.1")
            self.assertEqual(client._server_port, 3000)
        finally:
            self._uninstrument()

    def test_batch_empty_keys(self):
        """Test batch operation with empty keys list."""
        self.mock_client.batch_read.return_value = []
        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            client.batch_read([])

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)

            span = spans[0]
            self.assertEqual(span.name, "BATCH READ")
            self.assertNotIn("db.namespace", span.attributes)
        finally:
            self._uninstrument()

    def test_single_record_with_malformed_key(self):
        """Test single record operation with non-tuple key."""
        self.mock_client.get.return_value = (None, None, None)
        self._instrument()

        try:
            client = self.mock_aerospike.client({})
            client.get("not_a_tuple")

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)

            span = spans[0]
            self.assertEqual(span.name, "GET")
            self.assertNotIn("db.namespace", span.attributes)
        finally:
            self._uninstrument()

    def test_wrapper_caching(self):
        """Test that __getattr__ caches wrapped methods."""
        self.mock_client.get.return_value = (
            ("test", "demo", "key1"),
            {"gen": 1, "ttl": 100},
            {"bin1": "value1"},
        )
        self._instrument()

        try:
            client = self.mock_aerospike.client({})

            # First call triggers __getattr__ and caches the wrapper
            wrapper1 = client.get
            # Second call should return the cached wrapper
            wrapper2 = client.get

            self.assertIs(wrapper1, wrapper2)
        finally:
            self._uninstrument()

    def test_user_attribute_from_config(self):
        """Test that user attribute is captured from config."""
        self.mock_client.get.return_value = (
            ("test", "demo", "key1"),
            {"gen": 1, "ttl": 100},
            {"bin1": "value1"},
        )

        config = {"hosts": [("127.0.0.1", 3000)], "user": "test_user"}
        self._instrument()

        try:
            client = self.mock_aerospike.client(config)
            client.get(("test", "demo", "key1"))

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)

            span = spans[0]
            self.assertEqual(span.attributes.get("db.user"), "test_user")
        finally:
            self._uninstrument()

    def test_request_hook_exception_does_not_break_operation(self):
        """Test that request_hook exception does not break the operation."""
        self.mock_client.put.return_value = None

        def bad_request_hook(span, operation, args, kwargs):
            raise RuntimeError("request_hook failed")

        self._instrument(request_hook=bad_request_hook)

        try:
            client = self.mock_aerospike.client({})
            # Should NOT raise despite hook failure
            client.put(("test", "demo", "key1"), {"bin": "value"})

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)
            self.assertEqual(spans[0].name, "PUT test.demo")
            # Verify the underlying method was still called
            self.mock_client.put.assert_called_once()
        finally:
            self._uninstrument()

    def test_response_hook_exception_does_not_break_operation(self):
        """Test that response_hook exception does not break the operation."""
        self.mock_client.get.return_value = (
            ("test", "demo", "key1"),
            {"gen": 1, "ttl": 100},
            {"bin1": "value1"},
        )

        def bad_response_hook(span, operation, result):
            raise RuntimeError("response_hook failed")

        self._instrument(response_hook=bad_response_hook)

        try:
            client = self.mock_aerospike.client({})
            # Should NOT raise despite hook failure
            result = client.get(("test", "demo", "key1"))

            # Verify result is returned correctly
            self.assertIsNotNone(result)
            self.assertEqual(result[2], {"bin1": "value1"})

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)
            self.assertEqual(spans[0].name, "GET test.demo")
        finally:
            self._uninstrument()

    def test_error_hook_exception_does_not_break_operation(self):
        """Test that error_hook exception does not suppress the original error."""
        original_error = ValueError("Record not found")
        original_error.code = 2
        self.mock_client.get.side_effect = original_error

        def bad_error_hook(span, operation, exception):
            raise RuntimeError("error_hook failed")

        self._instrument(error_hook=bad_error_hook)

        try:
            client = self.mock_aerospike.client({})
            # Should raise the ORIGINAL error, not the hook error
            with self.assertRaises(ValueError) as ctx:
                client.get(("test", "demo", "key1"))

            self.assertEqual(str(ctx.exception), "Record not found")

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)
            self.assertEqual(spans[0].status.status_code, StatusCode.ERROR)
        finally:
            self._uninstrument()

    def test_bins_attribute(self):
        """Test that bins are captured for PUT and SELECT."""
        self.mock_client.put.return_value = None
        self.mock_client.select.return_value = (
            ("test", "demo", "key1"),
            {"gen": 1, "ttl": 100},
            {"bin1": "value1"},
        )
        self._instrument()

        try:
            client = self.mock_aerospike.client({})

            # Test PUT with bins dict
            client.put(
                ("test", "demo", "key1"), {"bin1": "val1", "bin2": "val2"}
            )
            # Test SELECT with bins list
            client.select(("test", "demo", "key1"), ["bin1", "bin2"])

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 2)

            put_span = spans[0]
            self.assertEqual(put_span.name, "PUT test.demo")
            # Verify bins keys are captured
            captured_bins = put_span.attributes.get("db.aerospike.bins")
            self.assertIn("bin1", captured_bins)
            self.assertIn("bin2", captured_bins)

            select_span = spans[1]
            self.assertEqual(select_span.name, "SELECT test.demo")
            # Verify bins list is captured
            captured_bins = select_span.attributes.get("db.aerospike.bins")
            self.assertIn("bin1", captured_bins)
            self.assertIn("bin2", captured_bins)
        finally:
            self._uninstrument()
