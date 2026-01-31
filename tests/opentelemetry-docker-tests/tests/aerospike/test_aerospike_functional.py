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

import os
import pathlib

import aerospike
from aerospike import exception as aerospike_exc

from opentelemetry.instrumentation.aerospike import AerospikeInstrumentor
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind, StatusCode

AEROSPIKE_HOST = os.getenv("AEROSPIKE_HOST", "localhost")
AEROSPIKE_PORT = int(os.getenv("AEROSPIKE_PORT", "3000"))

_UDF_PATH = str(pathlib.Path(__file__).with_name("test_udf.lua"))


class TestFunctionalAerospike(TestBase):
    """Functional tests against a real Aerospike server."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Register UDF once for the entire test class
        config = {"hosts": [(AEROSPIKE_HOST, AEROSPIKE_PORT)]}
        client = aerospike.client(config).connect()
        client.udf_put(_UDF_PATH)
        client.close()

    def setUp(self):
        super().setUp()
        self._tracer = self.tracer_provider.get_tracer(__name__)
        AerospikeInstrumentor().instrument(
            tracer_provider=self.tracer_provider
        )
        config = {"hosts": [(AEROSPIKE_HOST, AEROSPIKE_PORT)]}
        self._client = aerospike.client(config)
        self._client.connect()

    def tearDown(self):
        self._client.close()
        AerospikeInstrumentor().uninstrument()
        super().tearDown()

    # -- helpers --

    def _get_spans(self):
        return self.memory_exporter.get_finished_spans()

    def _assert_base_attrs(
        self, span, operation, namespace=None, set_name=None
    ):
        """Assert common span attributes."""
        self.assertEqual(span.kind, SpanKind.CLIENT)
        self.assertEqual(span.attributes["db.system"], "aerospike")
        self.assertEqual(span.attributes["db.operation.name"], operation)
        if namespace:
            self.assertEqual(span.attributes["db.namespace"], namespace)
        if set_name:
            self.assertEqual(span.attributes["db.collection.name"], set_name)
        self.assertIn("server.address", span.attributes)
        self.assertIn("server.port", span.attributes)

    # -- tests --

    def test_put_and_get(self):
        """Test put and get create correct spans."""
        key = ("test", "demo", "func_key1")
        self._client.put(key, {"name": "alice", "age": 30})
        _, meta, bins = self._client.get(key)

        self.assertEqual(bins["name"], "alice")
        self.assertEqual(bins["age"], 30)

        spans = self._get_spans()
        self.assertEqual(len(spans), 2)

        put_span, get_span = spans[0], spans[1]

        self.assertEqual(put_span.name, "PUT test.demo")
        self._assert_base_attrs(put_span, "PUT", "test", "demo")

        self.assertEqual(get_span.name, "GET test.demo")
        self._assert_base_attrs(get_span, "GET", "test", "demo")
        # get should capture generation/ttl metadata
        self.assertIn("db.aerospike.generation", get_span.attributes)
        self.assertIn("db.aerospike.ttl", get_span.attributes)

        # cleanup
        self._client.remove(key)

    def test_exists(self):
        """Test exists operation."""
        key = ("test", "demo", "func_exists")
        self._client.put(key, {"x": 1})
        self.memory_exporter.clear()

        _, meta = self._client.exists(key)
        self.assertIsNotNone(meta)

        spans = self._get_spans()
        self.assertEqual(len(spans), 1)
        self._assert_base_attrs(spans[0], "EXISTS", "test", "demo")

        self._client.remove(key)

    def test_remove(self):
        """Test remove operation."""
        key = ("test", "demo", "func_remove")
        self._client.put(key, {"x": 1})
        self.memory_exporter.clear()

        self._client.remove(key)

        spans = self._get_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "REMOVE test.demo")
        self._assert_base_attrs(spans[0], "REMOVE", "test", "demo")

    def test_batch_read(self):
        """Test batch_read operation."""
        keys = [("test", "demo", f"func_batch_{i}") for i in range(3)]
        for k in keys:
            self._client.put(k, {"v": 1})
        self.memory_exporter.clear()

        self._client.batch_read(keys)

        spans = self._get_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "BATCH READ test.demo")
        self._assert_base_attrs(span, "BATCH READ", "test", "demo")
        self.assertEqual(span.attributes["db.operation.batch.size"], 3)

        for k in keys:
            self._client.remove(k)

    def test_query_no_span_on_factory(self):
        """Test that query factory alone does not create a span."""
        self._client.query("test", "demo")

        spans = self._get_spans()
        self.assertEqual(len(spans), 0)

    def test_query(self):
        """Test query.results() creates a span with actual data."""
        key = ("test", "demo", "func_query")
        self._client.put(key, {"name": "bob"})
        self.memory_exporter.clear()

        query = self._client.query("test", "demo")
        records = query.results()

        self.assertTrue(len(records) > 0)

        spans = self._get_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "QUERY test.demo")
        self._assert_base_attrs(spans[0], "QUERY", "test", "demo")

        self._client.remove(key)

    def test_query_foreach(self):
        """Test query.foreach() creates a span and invokes the callback."""
        key = ("test", "demo", "func_qforeach")
        self._client.put(key, {"name": "carol"})
        self.memory_exporter.clear()

        received = []

        def callback(record):
            received.append(record)

        query = self._client.query("test", "demo")
        query.foreach(callback)

        self.assertTrue(len(received) > 0)

        spans = self._get_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "QUERY test.demo")
        self._assert_base_attrs(spans[0], "QUERY", "test", "demo")

        self._client.remove(key)

    def test_scan(self):
        """Test scan.results() creates a span with actual data."""
        key = ("test", "demo", "func_scan")
        self._client.put(key, {"name": "dave"})
        self.memory_exporter.clear()

        scan = self._client.scan("test", "demo")
        records = scan.results()

        self.assertTrue(len(records) > 0)

        spans = self._get_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "SCAN test.demo")
        self._assert_base_attrs(spans[0], "SCAN", "test", "demo")

        self._client.remove(key)

    def test_apply_udf(self):
        """Test apply (single-record UDF) creates correct span."""
        key = ("test", "demo", "func_udf")
        self._client.put(key, {"x": 1})
        self.memory_exporter.clear()

        result = self._client.apply(key, "test_udf", "echo", [42])
        self.assertEqual(result, 42)

        spans = self._get_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "APPLY test.demo")
        self._assert_base_attrs(span, "APPLY", "test", "demo")
        self.assertEqual(
            span.attributes["db.aerospike.udf.module"], "test_udf"
        )
        self.assertEqual(span.attributes["db.aerospike.udf.function"], "echo")

        self._client.remove(key)

    def test_scan_apply_udf(self):
        """Test scan_apply creates correct span with UDF attributes."""
        key = ("test", "demo", "func_scan_apply")
        self._client.put(key, {"x": 1})
        self.memory_exporter.clear()

        job_id = self._client.scan_apply("test", "demo", "test_udf", "noop")
        self.assertIsNotNone(job_id)

        spans = self._get_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "SCAN APPLY test.demo")
        self._assert_base_attrs(span, "SCAN APPLY", "test", "demo")
        self.assertEqual(
            span.attributes["db.aerospike.udf.module"], "test_udf"
        )
        self.assertEqual(span.attributes["db.aerospike.udf.function"], "noop")

        self._client.remove(key)

    def test_truncate(self):
        """Test truncate admin operation."""
        key = ("test", "demo", "func_trunc")
        self._client.put(key, {"x": 1})
        self.memory_exporter.clear()

        self._client.truncate("test", "demo", 0)

        spans = self._get_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "TRUNCATE test.demo")
        self._assert_base_attrs(spans[0], "TRUNCATE", "test", "demo")

    def test_error_case_record_not_found(self):
        """Test that a missing record raises an error with proper span status."""
        key = ("test", "demo", "nonexistent_key_xyz")

        with self.assertRaises(aerospike_exc.RecordNotFound):
            self._client.get(key)

        spans = self._get_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertIn("error.type", span.attributes)

    def test_parent_span_propagation(self):
        """Test that parent span context is propagated to child spans."""
        key = ("test", "demo", "func_parent")

        with self._tracer.start_as_current_span("parent-op"):
            self._client.put(key, {"v": 1})
            self._client.get(key)

        spans = self._get_spans()
        # Should have 3 spans: parent, put, get
        self.assertEqual(len(spans), 3)

        parent_span = [s for s in spans if s.name == "parent-op"][0]
        child_spans = [s for s in spans if s.name != "parent-op"]

        for child in child_spans:
            self.assertEqual(
                child.context.trace_id,
                parent_span.context.trace_id,
            )
            self.assertEqual(
                child.parent.span_id,
                parent_span.context.span_id,
            )

        self._client.remove(key)

    def test_connect_span_not_created(self):
        """Test that connect itself does not create a span (it's not instrumented as an operation)."""
        # connect() is called in setUp, clear spans
        self.memory_exporter.clear()

        # Create a new client and connect
        config = {"hosts": [(AEROSPIKE_HOST, AEROSPIKE_PORT)]}
        client2 = aerospike.client(config)
        client2.connect()
        client2.close()

        spans = self._get_spans()
        # connect/close are not in the instrumented method lists
        self.assertEqual(len(spans), 0)
