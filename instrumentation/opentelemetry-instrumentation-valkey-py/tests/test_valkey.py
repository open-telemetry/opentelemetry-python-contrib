# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=too-many-lines

import logging
from unittest import IsolatedAsyncioTestCase, mock

import valkey
import valkey.asyncio
import valkey.asyncio.cluster
import valkey.cluster
from fakeredis import FakeAsyncValkey, FakeServer, FakeStrictValkey

from opentelemetry import trace
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.instrumentation.valkey import ValkeyInstrumentor
from opentelemetry.semconv.attributes.db_attributes import (
    DB_NAMESPACE,
    DB_OPERATION_BATCH_SIZE,
    DB_OPERATION_NAME,
    DB_QUERY_TEXT,
    DB_RESPONSE_STATUS_CODE,
    DB_STORED_PROCEDURE_NAME,
    DB_SYSTEM_NAME,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.semconv.attributes.network_attributes import (
    NETWORK_PEER_ADDRESS,
    NETWORK_PEER_PORT,
    NETWORK_TRANSPORT,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.semconv.metrics.db_metrics import DB_CLIENT_OPERATION_DURATION
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind, StatusCode

_LOGGER_NAME = "opentelemetry.instrumentation.valkey"


def _assert_duration_metric(test_case, expected_attributes):
    """Assert the operation duration metric holds exactly the expected points."""
    metrics = test_case.get_sorted_metrics()
    test_case.assertEqual(len(metrics), 1)
    metric = metrics[0]
    test_case.assertEqual(metric.name, DB_CLIENT_OPERATION_DURATION)
    test_case.assertEqual(metric.unit, "s")
    data_points = list(metric.data.data_points)
    test_case.assertEqual(len(data_points), len(expected_attributes))
    for data_point, expected in zip(data_points, expected_attributes):
        test_case.assertEqual(dict(data_point.attributes), expected)
        test_case.assertEqual(data_point.count, 1)


class _ValkeyTestBase(TestBase):
    """Instruments every client for the duration of the test."""

    def setUp(self):
        super().setUp()
        ValkeyInstrumentor().instrument(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )

    def tearDown(self):
        super().tearDown()
        ValkeyInstrumentor().uninstrument()

    @staticmethod
    def _mocked_client(**kwargs):
        """A real client whose connection is mocked out, so nothing is sent."""
        return valkey.Valkey(**kwargs)

    @staticmethod
    def _mocked_async_client(**kwargs):
        """A real async client whose connection is mocked out, so nothing is sent."""
        return valkey.asyncio.Valkey(**kwargs)

    def _reinstrument(self, **kwargs):
        """Uninstrument and re-instrument, defaulting to this test's providers."""
        kwargs.setdefault("tracer_provider", self.tracer_provider)
        kwargs.setdefault("meter_provider", self.meter_provider)
        ValkeyInstrumentor().uninstrument()
        ValkeyInstrumentor().instrument(**kwargs)


class TestValkey(_ValkeyTestBase):
    def test_span_name_and_kind(self):
        client = self._mocked_client()
        with mock.patch.object(client, "connection"):
            client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "GET")
        self.assertEqual(spans[0].kind, SpanKind.CLIENT)
        self.assertIs(spans[0].status.status_code, StatusCode.UNSET)

    def test_instrumentation_scope(self):
        client = self._mocked_client()
        with mock.patch.object(client, "connection"):
            client.get("key")

        span = self.memory_exporter.get_finished_spans()[0]
        self.assertEqual(span.instrumentation_scope.name, "opentelemetry.instrumentation.valkey")
        self.assertEqual(
            span.instrumentation_scope.schema_url,
            "https://opentelemetry.io/schemas/1.25.0",
        )


class TestValkeyAttributes(_ValkeyTestBase):
    """Span attributes reported for the different connection shapes."""

    def test_attributes_for_connection_shapes(self):
        def client_without_connection_pool():
            client = self._mocked_client()
            client.connection_pool = mock.Mock(spec=["disconnect"])
            return client

        cases = [
            (
                "default",
                self._mocked_client,
                lambda client: client.set("key", "value"),
                {
                    DB_SYSTEM_NAME: "valkey",
                    DB_OPERATION_NAME: "SET",
                    DB_NAMESPACE: "0",
                    DB_QUERY_TEXT: "SET ? ?",
                    SERVER_ADDRESS: "localhost",
                    SERVER_PORT: 6379,
                    NETWORK_PEER_ADDRESS: "localhost",
                    NETWORK_PEER_PORT: 6379,
                    NETWORK_TRANSPORT: "tcp",
                },
            ),
            (
                "tcp from a url",
                lambda: valkey.Valkey.from_url("valkey://foo:bar@1.1.1.1:6380/1"),
                lambda client: client.get("key"),
                {
                    DB_SYSTEM_NAME: "valkey",
                    DB_OPERATION_NAME: "GET",
                    DB_NAMESPACE: "1",
                    DB_QUERY_TEXT: "GET ?",
                    SERVER_ADDRESS: "1.1.1.1",
                    SERVER_PORT: 6380,
                    NETWORK_PEER_ADDRESS: "1.1.1.1",
                    NETWORK_PEER_PORT: 6380,
                    NETWORK_TRANSPORT: "tcp",
                },
            ),
            (
                "unix socket",
                lambda: valkey.Valkey.from_url("unix://foo@/path/to/socket.sock?db=3&password=bar"),
                lambda client: client.get("key"),
                {
                    DB_SYSTEM_NAME: "valkey",
                    DB_OPERATION_NAME: "GET",
                    DB_NAMESPACE: "3",
                    DB_QUERY_TEXT: "GET ?",
                    SERVER_ADDRESS: "/path/to/socket.sock",
                    NETWORK_PEER_ADDRESS: "/path/to/socket.sock",
                    NETWORK_TRANSPORT: "unix",
                },
            ),
            (
                "explicit db=None falls back to the default namespace",
                lambda: self._mocked_client(db=None),
                lambda client: client.get("key"),
                {
                    DB_SYSTEM_NAME: "valkey",
                    DB_OPERATION_NAME: "GET",
                    DB_NAMESPACE: "0",
                    DB_QUERY_TEXT: "GET ?",
                    SERVER_ADDRESS: "localhost",
                    SERVER_PORT: 6379,
                    NETWORK_PEER_ADDRESS: "localhost",
                    NETWORK_PEER_PORT: 6379,
                    NETWORK_TRANSPORT: "tcp",
                },
            ),
            (
                # Without a connection pool the span still carries the command
                # details, just without any connection-derived attributes.
                "without a connection pool",
                client_without_connection_pool,
                lambda client: client.get("key"),
                {
                    DB_SYSTEM_NAME: "valkey",
                    DB_OPERATION_NAME: "GET",
                    DB_QUERY_TEXT: "GET ?",
                },
            ),
        ]
        for name, make_client, issue_command, expected_attributes in cases:
            with self.subTest(name):
                client = make_client()
                with mock.patch.object(client, "connection"):
                    issue_command(client)

                span = self.memory_exporter.get_finished_spans()[-1]
                self.assertEqual(span.name, expected_attributes[DB_OPERATION_NAME])
                self.assertEqual(dict(span.attributes), expected_attributes)

    def test_operation_name_and_query_text(self):
        client = FakeStrictValkey()
        cases = [
            ("delete", lambda client: client.delete("key"), "DEL", "DEL ?"),
            ("exists", lambda client: client.exists("key"), "EXISTS", "EXISTS ?"),
            ("expire", lambda client: client.expire("key", 10), "EXPIRE", "EXPIRE ? ?"),
            ("incr", lambda client: client.incr("counter"), "INCRBY", "INCRBY ? ?"),
            ("ttl", lambda client: client.ttl("key"), "TTL", "TTL ?"),
            ("keys", lambda client: client.keys("*"), "KEYS", "KEYS ?"),
            ("ping", lambda client: client.ping(), "PING", "PING"),
            ("lpush", lambda client: client.lpush("list", "value"), "LPUSH", "LPUSH ? ?"),
            ("sadd", lambda client: client.sadd("set", "member"), "SADD", "SADD ? ?"),
            (
                "hset",
                lambda client: client.hset("hash", "field", "value"),
                "HSET",
                "HSET ? ? ?",
            ),
        ]
        for name, issue_command, expected_operation, expected_query_text in cases:
            with self.subTest(name):
                issue_command(client)

                span = self.memory_exporter.get_finished_spans()[-1]
                self.assertEqual(span.name, expected_operation)
                self.assertEqual(span.attributes[DB_OPERATION_NAME], expected_operation)
                self.assertEqual(span.attributes[DB_QUERY_TEXT], expected_query_text)

    def test_stored_procedure_name(self):
        cases = [
            ("evalsha", lambda client: client.evalsha("abc123", 1, "key"), "EVALSHA", "abc123"),
            ("fcall", lambda client: client.fcall("myfunc", 0), "FCALL", "myfunc"),
            # EVAL carries the script body, which is not a stored procedure name.
            ("eval is not a stored procedure", lambda client: client.eval("return 1", 0), "EVAL", None),
        ]
        for name, call, expected_operation, expected_stored_procedure in cases:
            with self.subTest(name):
                client = self._mocked_client()
                with mock.patch.object(client, "connection"):
                    call(client)

                span = self.memory_exporter.get_finished_spans()[-1]
                self.assertEqual(span.name, expected_operation)
                self.assertEqual(span.attributes[DB_OPERATION_NAME], expected_operation)
                if expected_stored_procedure is None:
                    self.assertNotIn(DB_STORED_PROCEDURE_NAME, span.attributes)
                else:
                    self.assertEqual(span.attributes[DB_STORED_PROCEDURE_NAME], expected_stored_procedure)

    def test_query_text_is_sanitized(self):
        client = self._mocked_client()
        with mock.patch.object(client, "connection"):
            client.set("key", "a-secret-value")

        span = self.memory_exporter.get_finished_spans()[0]
        self.assertEqual(span.attributes[DB_QUERY_TEXT], "SET ? ?")
        self.assertNotIn("a-secret-value", span.attributes[DB_QUERY_TEXT])

    def test_query_text_is_truncated(self):
        client = self._mocked_client()
        with mock.patch.object(client, "connection"):
            client.mget(*[f"key-{index}" for index in range(1000)])

        query_text = self.memory_exporter.get_finished_spans()[0].attributes[DB_QUERY_TEXT]
        self.assertEqual(len(query_text), 1000)
        self.assertTrue(query_text.endswith("..."))


class TestValkeyBehaviour(_ValkeyTestBase):
    """Instrumentation lifecycle, pipelines, errors, hooks and suppression."""

    def test_not_recording(self):
        client = self._mocked_client()
        mock_tracer = mock.Mock()
        mock_span = mock.Mock()
        mock_span.is_recording.return_value = False
        mock_tracer.start_span.return_value = mock_span
        with mock.patch("opentelemetry.trace.get_tracer") as tracer:
            tracer.return_value = mock_tracer
            with mock.patch.object(client, "connection"):
                client.get("key")
            self.assertFalse(mock_span.is_recording())
            self.assertTrue(mock_span.is_recording.called)
            self.assertFalse(mock_span.set_attribute.called)

    def test_no_op_tracer_provider(self):
        self._reinstrument(tracer_provider=trace.NoOpTracerProvider())
        client = self._mocked_client()
        with mock.patch.object(client, "connection"):
            client.get("key")

        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 0)

    def test_instrument_uninstrument(self):
        client = self._mocked_client()

        ValkeyInstrumentor().uninstrument()
        with mock.patch.object(client, "connection"):
            client.get("key")
        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 0)

        self._reinstrument()
        with mock.patch.object(client, "connection"):
            client.get("key")
        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 1)

    def test_pipeline_naming(self):
        cases = [
            (
                "multiple different commands",
                False,
                [lambda p: p.set("key", "value"), lambda p: p.get("key")],
                "PIPELINE",
                "SET ? ?\nGET ?",
            ),
            (
                # The shared command is appended, and identical query texts collapse.
                "a shared command",
                False,
                [lambda p: p.get("one"), lambda p: p.get("two")],
                "PIPELINE GET",
                "GET ?",
            ),
            (
                # A pipeline is a transaction unless transaction=False is passed.
                "a transaction",
                True,
                [lambda p: p.get("one"), lambda p: p.get("two")],
                "MULTI GET",
                "GET ?",
            ),
        ]
        for name, transaction, queue_commands, expected_name, expected_query_text in cases:
            with self.subTest(name):
                client = FakeStrictValkey()
                with client.pipeline(transaction=transaction) as pipeline:
                    for queue_command in queue_commands:
                        queue_command(pipeline)
                    pipeline.execute()

                span = self.memory_exporter.get_finished_spans()[-1]
                self.assertEqual(span.name, expected_name)
                self.assertEqual(span.attributes[DB_OPERATION_NAME], expected_name)
                self.assertEqual(span.attributes[DB_QUERY_TEXT], expected_query_text)
                self.assertEqual(span.attributes[DB_OPERATION_BATCH_SIZE], 2)
                self.assertIsInstance(span.attributes[DB_OPERATION_BATCH_SIZE], int)

    def test_single_command_pipeline_or_transaction_is_not_a_batch(self):
        # Shared across cases: each FakeStrictValkey() instance gets its own
        # connection identity, which would otherwise keep the metric points
        # below from collapsing into one.
        client = FakeStrictValkey()
        for name, transaction in [("pipeline", False), ("transaction", True)]:
            with self.subTest(name):
                client.get("key")
                direct_span = self.memory_exporter.get_finished_spans()[-1]

                with client.pipeline(transaction=transaction) as pipeline:
                    pipeline.get("key")
                    pipeline.execute()
                pipeline_span = self.memory_exporter.get_finished_spans()[-1]

                # A pipeline or transaction holding a single command is traced
                # identically to that command executed directly, regardless of
                # transaction mode.
                self.assertEqual(pipeline_span.name, direct_span.name)
                self.assertEqual(dict(pipeline_span.attributes), dict(direct_span.attributes))
                self.assertNotIn(DB_OPERATION_BATCH_SIZE, pipeline_span.attributes)

        # Every recording above shares identical attributes, so they all
        # collapse into a single metric data point rather than one per call.
        metrics = self.get_sorted_metrics()
        self.assertEqual(len(metrics), 1)
        data_points = list(metrics[0].data.data_points)
        self.assertEqual(len(data_points), 1)
        self.assertEqual(data_points[0].count, 4)

    def test_empty_pipeline(self):
        client = FakeStrictValkey()
        with client.pipeline(transaction=False) as pipeline:
            pipeline.execute()

        span = self.memory_exporter.get_finished_spans()[0]
        self.assertEqual(span.name, "PIPELINE")
        self.assertEqual(span.attributes[DB_QUERY_TEXT], "")
        # An empty batch is still a batch, and reports a size of zero.
        self.assertEqual(span.attributes[DB_OPERATION_BATCH_SIZE], 0)

    def test_watch_error_is_not_an_error(self):
        client = FakeStrictValkey()
        with self.assertRaises(valkey.WatchError):
            with client.pipeline() as pipeline:
                pipeline.watch("key")
                # Change the value from outside of the transaction.
                client.set("key", "other")
                pipeline.multi()
                pipeline.set("key", "value")
                pipeline.execute()

        batch_span = self.memory_exporter.get_finished_spans()[-1]
        self.assertIs(batch_span.status.status_code, StatusCode.UNSET)
        self.assertNotIn(ERROR_TYPE, batch_span.attributes)
        self.assertEqual(len(batch_span.events), 0)

    def test_response_error(self):
        client = FakeStrictValkey()
        client.lpush("mylist", "value")
        with self.assertRaises(valkey.ResponseError):
            client.incr("mylist")

        span = self.memory_exporter.get_finished_spans()[-1]
        self.assertEqual(span.name, "INCRBY")
        self.assertIs(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.attributes[ERROR_TYPE], "ResponseError")
        self.assertEqual(span.attributes[DB_RESPONSE_STATUS_CODE], "WRONGTYPE")
        self.assertEqual(len(span.events), 1)
        self.assertEqual(span.events[0].name, "exception")

    def test_connection_error(self):
        server = FakeServer()
        server.connected = False
        client = FakeStrictValkey(server=server)
        with self.assertRaises(valkey.ConnectionError):
            client.get("key")

        span = self.memory_exporter.get_finished_spans()[0]
        self.assertIs(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.attributes[ERROR_TYPE], "ConnectionError")
        # A transport failure carries no server error code.
        self.assertNotIn(DB_RESPONSE_STATUS_CODE, span.attributes)

    def test_metric(self):
        client = self._mocked_client()
        with mock.patch.object(client, "connection"):
            client.get("key")

        _assert_duration_metric(
            self,
            [
                {
                    DB_SYSTEM_NAME: "valkey",
                    DB_NAMESPACE: "0",
                    DB_OPERATION_NAME: "GET",
                    DB_QUERY_TEXT: "GET ?",
                    SERVER_ADDRESS: "localhost",
                    SERVER_PORT: 6379,
                    NETWORK_PEER_ADDRESS: "localhost",
                    NETWORK_PEER_PORT: 6379,
                    NETWORK_TRANSPORT: "tcp",
                }
            ],
        )

    def test_metric_on_error(self):
        client = FakeStrictValkey()
        client.lpush("mylist", "value")
        self.memory_exporter.clear()
        with self.assertRaises(valkey.ResponseError):
            client.incr("mylist")

        metric = self.get_sorted_metrics()[0]
        error_points = [point for point in metric.data.data_points if ERROR_TYPE in dict(point.attributes)]
        self.assertEqual(len(error_points), 1)
        attributes = dict(error_points[0].attributes)
        self.assertEqual(attributes[ERROR_TYPE], "ResponseError")
        self.assertEqual(attributes[DB_RESPONSE_STATUS_CODE], "WRONGTYPE")
        self.assertEqual(attributes[DB_OPERATION_NAME], "INCRBY")

    def test_request_and_response_hooks(self):
        def request_hook(span, instance, args, kwargs):
            span.set_attribute("request_hook_args_count", len(args))

        def response_hook(span, instance, response):
            span.set_attribute("response_hook_response", str(response))

        self._reinstrument(request_hook=request_hook, response_hook=response_hook)

        client = FakeStrictValkey()
        client.get("key")

        span = self.memory_exporter.get_finished_spans()[0]
        self.assertEqual(span.attributes["request_hook_args_count"], 2)
        self.assertEqual(span.attributes["response_hook_response"], "None")

    def test_hooks_are_called_for_pipelines(self):
        calls = []

        def request_hook(span, instance, args, kwargs):
            calls.append("request")

        def response_hook(span, instance, response):
            calls.append("response")

        self._reinstrument(request_hook=request_hook, response_hook=response_hook)

        client = FakeStrictValkey()
        with client.pipeline(transaction=False) as pipeline:
            pipeline.get("key")
            pipeline.execute()

        self.assertEqual(calls, ["request", "response"])

    def test_hook_exception_is_swallowed(self):
        def request_hook(span, instance, args, kwargs):
            raise ValueError("request hook failed")

        def response_hook(span, instance, response):
            raise ValueError("response hook failed")

        self._reinstrument(request_hook=request_hook, response_hook=response_hook)

        client = FakeStrictValkey()
        with self.assertLogs(_LOGGER_NAME, level=logging.WARNING) as logs:
            client.get("key")

        self.assertEqual(len(logs.records), 2)
        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 1)

    def test_suppress_instrumentation(self):
        client = self._mocked_client()
        with suppress_instrumentation():
            with mock.patch.object(client, "connection"):
                client.get("key")

        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 0)

    def test_suppress_instrumentation_pipeline(self):
        client = FakeStrictValkey()
        with suppress_instrumentation():
            with client.pipeline(transaction=False) as pipeline:
                pipeline.get("key")
                pipeline.execute()

        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 0)

    def test_cluster_classes_are_wrapped(self):
        targets = [
            (valkey.cluster.ValkeyCluster, "execute_command"),
            (valkey.cluster.ClusterPipeline, "execute"),
            (valkey.asyncio.cluster.ValkeyCluster, "execute_command"),
            (valkey.asyncio.cluster.ClusterPipeline, "execute"),
        ]

        for cls, method in targets:
            with self.subTest(f"{cls.__name__}.{method} is instrumented"):
                self.assertTrue(hasattr(getattr(cls, method), "__wrapped__"))

        ValkeyInstrumentor().uninstrument()

        for cls, method in targets:
            with self.subTest(f"{cls.__name__}.{method} is uninstrumented"):
                self.assertFalse(hasattr(getattr(cls, method), "__wrapped__"))


class TestValkeyAsync(_ValkeyTestBase, IsolatedAsyncioTestCase):
    async def test_span_name_and_kind(self):
        client = self._mocked_async_client()
        with mock.patch.object(client, "connection", mock.AsyncMock()):
            await client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "GET")
        self.assertEqual(spans[0].kind, SpanKind.CLIENT)
        self.assertIs(spans[0].status.status_code, StatusCode.UNSET)

    async def test_instrumentation_scope(self):
        client = self._mocked_async_client()
        with mock.patch.object(client, "connection", mock.AsyncMock()):
            await client.get("key")

        span = self.memory_exporter.get_finished_spans()[0]
        self.assertEqual(span.instrumentation_scope.name, "opentelemetry.instrumentation.valkey")
        self.assertEqual(
            span.instrumentation_scope.schema_url,
            "https://opentelemetry.io/schemas/1.25.0",
        )


class TestValkeyAsyncAttributes(_ValkeyTestBase, IsolatedAsyncioTestCase):
    """Span attributes reported for the different connection shapes."""

    async def test_attributes_for_connection_shapes(self):
        def client_without_connection_pool():
            client = self._mocked_async_client()
            client.connection_pool = mock.Mock(spec=["disconnect"])
            return client

        cases = [
            (
                "default",
                self._mocked_async_client,
                lambda client: client.set("key", "value"),
                {
                    DB_SYSTEM_NAME: "valkey",
                    DB_OPERATION_NAME: "SET",
                    DB_NAMESPACE: "0",
                    DB_QUERY_TEXT: "SET ? ?",
                    SERVER_ADDRESS: "localhost",
                    SERVER_PORT: 6379,
                    NETWORK_PEER_ADDRESS: "localhost",
                    NETWORK_PEER_PORT: 6379,
                    NETWORK_TRANSPORT: "tcp",
                },
            ),
            (
                "tcp from a url",
                lambda: valkey.asyncio.Valkey.from_url("valkey://foo:bar@1.1.1.1:6380/1"),
                lambda client: client.get("key"),
                {
                    DB_SYSTEM_NAME: "valkey",
                    DB_OPERATION_NAME: "GET",
                    DB_NAMESPACE: "1",
                    DB_QUERY_TEXT: "GET ?",
                    SERVER_ADDRESS: "1.1.1.1",
                    SERVER_PORT: 6380,
                    NETWORK_PEER_ADDRESS: "1.1.1.1",
                    NETWORK_PEER_PORT: 6380,
                    NETWORK_TRANSPORT: "tcp",
                },
            ),
            (
                "unix socket",
                lambda: valkey.asyncio.Valkey.from_url("unix://foo@/path/to/socket.sock?db=3&password=bar"),
                lambda client: client.get("key"),
                {
                    DB_SYSTEM_NAME: "valkey",
                    DB_OPERATION_NAME: "GET",
                    DB_NAMESPACE: "3",
                    DB_QUERY_TEXT: "GET ?",
                    SERVER_ADDRESS: "/path/to/socket.sock",
                    NETWORK_PEER_ADDRESS: "/path/to/socket.sock",
                    NETWORK_TRANSPORT: "unix",
                },
            ),
            (
                "explicit db=None falls back to the default namespace",
                lambda: self._mocked_async_client(db=None),
                lambda client: client.get("key"),
                {
                    DB_SYSTEM_NAME: "valkey",
                    DB_OPERATION_NAME: "GET",
                    DB_NAMESPACE: "0",
                    DB_QUERY_TEXT: "GET ?",
                    SERVER_ADDRESS: "localhost",
                    SERVER_PORT: 6379,
                    NETWORK_PEER_ADDRESS: "localhost",
                    NETWORK_PEER_PORT: 6379,
                    NETWORK_TRANSPORT: "tcp",
                },
            ),
            (
                # Without a connection pool the span still carries the command
                # details, just without any connection-derived attributes.
                "without a connection pool",
                client_without_connection_pool,
                lambda client: client.get("key"),
                {
                    DB_SYSTEM_NAME: "valkey",
                    DB_OPERATION_NAME: "GET",
                    DB_QUERY_TEXT: "GET ?",
                },
            ),
        ]
        for name, make_client, issue_command, expected_attributes in cases:
            with self.subTest(name):
                client = make_client()
                with mock.patch.object(client, "connection", mock.AsyncMock()):
                    await issue_command(client)

                span = self.memory_exporter.get_finished_spans()[-1]
                self.assertEqual(span.name, expected_attributes[DB_OPERATION_NAME])
                self.assertEqual(dict(span.attributes), expected_attributes)

    async def test_operation_name_and_query_text(self):
        client = FakeAsyncValkey()
        cases = [
            ("delete", lambda client: client.delete("key"), "DEL", "DEL ?"),
            ("exists", lambda client: client.exists("key"), "EXISTS", "EXISTS ?"),
            ("expire", lambda client: client.expire("key", 10), "EXPIRE", "EXPIRE ? ?"),
            ("incr", lambda client: client.incr("counter"), "INCRBY", "INCRBY ? ?"),
            ("ttl", lambda client: client.ttl("key"), "TTL", "TTL ?"),
            ("keys", lambda client: client.keys("*"), "KEYS", "KEYS ?"),
            ("ping", lambda client: client.ping(), "PING", "PING"),
            ("lpush", lambda client: client.lpush("list", "value"), "LPUSH", "LPUSH ? ?"),
            ("sadd", lambda client: client.sadd("set", "member"), "SADD", "SADD ? ?"),
            (
                "hset",
                lambda client: client.hset("hash", "field", "value"),
                "HSET",
                "HSET ? ? ?",
            ),
        ]
        for name, issue_command, expected_operation, expected_query_text in cases:
            with self.subTest(name):
                await issue_command(client)

                span = self.memory_exporter.get_finished_spans()[-1]
                self.assertEqual(span.name, expected_operation)
                self.assertEqual(span.attributes[DB_OPERATION_NAME], expected_operation)
                self.assertEqual(span.attributes[DB_QUERY_TEXT], expected_query_text)

    async def test_stored_procedure_name(self):
        cases = [
            ("evalsha", lambda client: client.evalsha("abc123", 1, "key"), "EVALSHA", "abc123"),
            ("fcall", lambda client: client.fcall("myfunc", 0), "FCALL", "myfunc"),
            # EVAL carries the script body, which is not a stored procedure name.
            ("eval is not a stored procedure", lambda client: client.eval("return 1", 0), "EVAL", None),
        ]
        for name, call, expected_operation, expected_stored_procedure in cases:
            with self.subTest(name):
                client = self._mocked_async_client()
                with mock.patch.object(client, "connection", mock.AsyncMock()):
                    await call(client)

                span = self.memory_exporter.get_finished_spans()[-1]
                self.assertEqual(span.name, expected_operation)
                self.assertEqual(span.attributes[DB_OPERATION_NAME], expected_operation)
                if expected_stored_procedure is None:
                    self.assertNotIn(DB_STORED_PROCEDURE_NAME, span.attributes)
                else:
                    self.assertEqual(span.attributes[DB_STORED_PROCEDURE_NAME], expected_stored_procedure)

    async def test_query_text_is_sanitized(self):
        client = self._mocked_async_client()
        with mock.patch.object(client, "connection", mock.AsyncMock()):
            await client.set("key", "a-secret-value")

        span = self.memory_exporter.get_finished_spans()[0]
        self.assertEqual(span.attributes[DB_QUERY_TEXT], "SET ? ?")
        self.assertNotIn("a-secret-value", span.attributes[DB_QUERY_TEXT])

    async def test_query_text_is_truncated(self):
        client = self._mocked_async_client()
        with mock.patch.object(client, "connection", mock.AsyncMock()):
            await client.mget(*[f"key-{index}" for index in range(1000)])

        query_text = self.memory_exporter.get_finished_spans()[0].attributes[DB_QUERY_TEXT]
        self.assertEqual(len(query_text), 1000)
        self.assertTrue(query_text.endswith("..."))


class TestValkeyAsyncBehaviour(_ValkeyTestBase, IsolatedAsyncioTestCase):
    """Instrumentation lifecycle, pipelines, errors, hooks and suppression."""

    async def test_not_recording(self):
        client = self._mocked_async_client()
        mock_tracer = mock.Mock()
        mock_span = mock.Mock()
        mock_span.is_recording.return_value = False
        mock_tracer.start_span.return_value = mock_span
        with mock.patch("opentelemetry.trace.get_tracer") as tracer:
            tracer.return_value = mock_tracer
            with mock.patch.object(client, "connection", mock.AsyncMock()):
                await client.get("key")
            self.assertFalse(mock_span.is_recording())
            self.assertTrue(mock_span.is_recording.called)
            self.assertFalse(mock_span.set_attribute.called)

    async def test_no_op_tracer_provider(self):
        self._reinstrument(tracer_provider=trace.NoOpTracerProvider())
        client = self._mocked_async_client()
        with mock.patch.object(client, "connection", mock.AsyncMock()):
            await client.get("key")

        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 0)

    async def test_instrument_uninstrument(self):
        client = FakeAsyncValkey()

        ValkeyInstrumentor().uninstrument()
        await client.get("key")
        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 0)

        self._reinstrument()
        await client.get("key")
        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 1)

    async def test_pipeline_naming(self):
        cases = [
            (
                "multiple different commands",
                False,
                [lambda p: p.set("key", "value"), lambda p: p.get("key")],
                "PIPELINE",
                "SET ? ?\nGET ?",
            ),
            (
                # The async client keeps Valkey.transaction as a method and
                # stores the flag under a different name, so a bare getattr
                # would read as truthy; this confirms it's read correctly.
                "not reported as a transaction",
                False,
                [lambda p: p.get("one"), lambda p: p.get("two")],
                "PIPELINE GET",
                "GET ?",
            ),
            (
                "a transaction",
                True,
                [lambda p: p.get("one"), lambda p: p.get("two")],
                "MULTI GET",
                "GET ?",
            ),
        ]
        for name, transaction, queue_commands, expected_name, expected_query_text in cases:
            with self.subTest(name):
                client = FakeAsyncValkey()
                async with client.pipeline(transaction=transaction) as pipeline:
                    for queue_command in queue_commands:
                        queue_command(pipeline)
                    await pipeline.execute()

                span = self.memory_exporter.get_finished_spans()[-1]
                self.assertEqual(span.name, expected_name)
                self.assertEqual(span.attributes[DB_OPERATION_NAME], expected_name)
                self.assertEqual(span.attributes[DB_QUERY_TEXT], expected_query_text)
                self.assertEqual(span.attributes[DB_OPERATION_BATCH_SIZE], 2)
                self.assertIsInstance(span.attributes[DB_OPERATION_BATCH_SIZE], int)

    async def test_single_command_pipeline_or_transaction_is_not_a_batch(self):
        # Shared across cases: each FakeAsyncValkey() instance gets its own
        # connection identity, which would otherwise keep the metric points
        # below from collapsing into one.
        client = FakeAsyncValkey()
        for name, transaction in [("pipeline", False), ("transaction", True)]:
            with self.subTest(name):
                await client.get("key")
                direct_span = self.memory_exporter.get_finished_spans()[-1]

                async with client.pipeline(transaction=transaction) as pipeline:
                    pipeline.get("key")
                    await pipeline.execute()
                pipeline_span = self.memory_exporter.get_finished_spans()[-1]

                # A pipeline or transaction holding a single command is traced
                # identically to that command executed directly, regardless of
                # transaction mode.
                self.assertEqual(pipeline_span.name, direct_span.name)
                self.assertEqual(dict(pipeline_span.attributes), dict(direct_span.attributes))
                self.assertNotIn(DB_OPERATION_BATCH_SIZE, pipeline_span.attributes)

        # Every recording above shares identical attributes, so they all
        # collapse into a single metric data point rather than one per call.
        metrics = self.get_sorted_metrics()
        self.assertEqual(len(metrics), 1)
        data_points = list(metrics[0].data.data_points)
        self.assertEqual(len(data_points), 1)
        self.assertEqual(data_points[0].count, 4)

    async def test_empty_pipeline(self):
        client = FakeAsyncValkey()
        async with client.pipeline(transaction=False) as pipeline:
            await pipeline.execute()

        span = self.memory_exporter.get_finished_spans()[0]
        self.assertEqual(span.name, "PIPELINE")
        self.assertEqual(span.attributes[DB_QUERY_TEXT], "")
        # An empty batch is still a batch, and reports a size of zero.
        self.assertEqual(span.attributes[DB_OPERATION_BATCH_SIZE], 0)

    async def test_watch_error_is_not_an_error(self):
        client = FakeAsyncValkey()
        with self.assertRaises(valkey.WatchError):
            async with client.pipeline() as pipeline:
                await pipeline.watch("key")
                # Change the value from outside of the transaction.
                await client.set("key", "other")
                pipeline.multi()
                pipeline.set("key", "value")
                await pipeline.execute()

        # The pipeline holds a single queued command (SET), so it's traced
        # identically to a direct call and isn't named MULTI; its execute()
        # span is the last one finished.
        batch_span = self.memory_exporter.get_finished_spans()[-1]
        self.assertIs(batch_span.status.status_code, StatusCode.UNSET)
        self.assertNotIn(ERROR_TYPE, batch_span.attributes)
        self.assertEqual(len(batch_span.events), 0)

    async def test_response_error(self):
        client = FakeAsyncValkey()
        # The error is raised through a patched parse_response because the
        # asyncio side of fakeredis reports redis-py's exception types even when
        # it fakes a Valkey client.
        error = valkey.ResponseError("WRONGTYPE Operation against a key holding the wrong kind of value")
        with mock.patch.object(client, "parse_response", mock.AsyncMock(side_effect=error)):
            with self.assertRaises(valkey.ResponseError):
                await client.incr("mylist")

        span = self.memory_exporter.get_finished_spans()[-1]
        self.assertEqual(span.name, "INCRBY")
        self.assertIs(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.attributes[ERROR_TYPE], "ResponseError")
        self.assertEqual(span.attributes[DB_RESPONSE_STATUS_CODE], "WRONGTYPE")

    async def test_connection_error(self):
        server = FakeServer()
        server.connected = False
        client = FakeAsyncValkey(server=server)
        with self.assertRaises(valkey.ConnectionError):
            await client.get("key")

        span = self.memory_exporter.get_finished_spans()[0]
        self.assertIs(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.attributes[ERROR_TYPE], "ConnectionError")
        # A transport failure carries no server error code.
        self.assertNotIn(DB_RESPONSE_STATUS_CODE, span.attributes)

    async def test_metric(self):
        client = self._mocked_async_client()
        with mock.patch.object(client, "connection", mock.AsyncMock()):
            await client.get("key")

        _assert_duration_metric(
            self,
            [
                {
                    DB_SYSTEM_NAME: "valkey",
                    DB_NAMESPACE: "0",
                    DB_OPERATION_NAME: "GET",
                    DB_QUERY_TEXT: "GET ?",
                    SERVER_ADDRESS: "localhost",
                    SERVER_PORT: 6379,
                    NETWORK_PEER_ADDRESS: "localhost",
                    NETWORK_PEER_PORT: 6379,
                    NETWORK_TRANSPORT: "tcp",
                }
            ],
        )

    async def test_metric_on_error(self):
        client = FakeAsyncValkey()
        await client.lpush("mylist", "value")
        self.memory_exporter.clear()
        error = valkey.ResponseError("WRONGTYPE Operation against a key holding the wrong kind of value")
        with mock.patch.object(client, "parse_response", mock.AsyncMock(side_effect=error)):
            with self.assertRaises(valkey.ResponseError):
                await client.incr("mylist")

        metric = self.get_sorted_metrics()[0]
        error_points = [point for point in metric.data.data_points if ERROR_TYPE in dict(point.attributes)]
        self.assertEqual(len(error_points), 1)
        attributes = dict(error_points[0].attributes)
        self.assertEqual(attributes[ERROR_TYPE], "ResponseError")
        self.assertEqual(attributes[DB_RESPONSE_STATUS_CODE], "WRONGTYPE")
        self.assertEqual(attributes[DB_OPERATION_NAME], "INCRBY")

    async def test_request_and_response_hooks(self):
        def request_hook(span, instance, args, kwargs):
            span.set_attribute("request_hook_args_count", len(args))

        def response_hook(span, instance, response):
            span.set_attribute("response_hook_response", str(response))

        self._reinstrument(request_hook=request_hook, response_hook=response_hook)

        client = FakeAsyncValkey()
        await client.get("key")

        span = self.memory_exporter.get_finished_spans()[0]
        self.assertEqual(span.attributes["request_hook_args_count"], 2)
        self.assertEqual(span.attributes["response_hook_response"], "None")

    async def test_hooks_are_called_for_pipelines(self):
        calls = []

        def request_hook(span, instance, args, kwargs):
            calls.append("request")

        def response_hook(span, instance, response):
            calls.append("response")

        self._reinstrument(request_hook=request_hook, response_hook=response_hook)

        client = FakeAsyncValkey()
        async with client.pipeline(transaction=False) as pipeline:
            pipeline.get("key")
            await pipeline.execute()

        self.assertEqual(calls, ["request", "response"])

    async def test_hook_exception_is_swallowed(self):
        def request_hook(span, instance, args, kwargs):
            raise ValueError("request hook failed")

        def response_hook(span, instance, response):
            raise ValueError("response hook failed")

        self._reinstrument(request_hook=request_hook, response_hook=response_hook)

        client = FakeAsyncValkey()
        with self.assertLogs(_LOGGER_NAME, level=logging.WARNING) as logs:
            await client.get("key")

        self.assertEqual(len(logs.records), 2)
        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 1)

    async def test_suppress_instrumentation(self):
        client = FakeAsyncValkey()
        with suppress_instrumentation():
            await client.get("key")

        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 0)

    async def test_suppress_instrumentation_pipeline(self):
        client = FakeAsyncValkey()
        with suppress_instrumentation():
            async with client.pipeline(transaction=False) as pipeline:
                pipeline.get("key")
                await pipeline.execute()

        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 0)


class TestValkeyInstrumentClient(TestBase):
    def test_only_the_instrumented_client_is_traced(self):
        instrumented = FakeStrictValkey()
        other = FakeStrictValkey()
        ValkeyInstrumentor.instrument_client(
            instrumented,
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )

        other.get("key")
        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 0)

        instrumented.get("key")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "GET")

    def test_pipeline_of_instrumented_client(self):
        client = FakeStrictValkey()
        ValkeyInstrumentor.instrument_client(
            client,
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )

        with client.pipeline(transaction=False) as pipeline:
            pipeline.set("key", "value")
            pipeline.get("key")
            pipeline.execute()

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "PIPELINE")
        self.assertEqual(spans[0].attributes[DB_OPERATION_BATCH_SIZE], 2)

    def test_uninstrument_client(self):
        client = FakeStrictValkey()
        ValkeyInstrumentor.instrument_client(client, tracer_provider=self.tracer_provider)
        client.get("key")
        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 1)

        ValkeyInstrumentor.uninstrument_client(client)
        client.get("key")
        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 1)

    def test_client_can_be_reinstrumented(self):
        client = FakeStrictValkey()
        ValkeyInstrumentor.instrument_client(client, tracer_provider=self.tracer_provider)
        ValkeyInstrumentor.uninstrument_client(client)
        ValkeyInstrumentor.instrument_client(client, tracer_provider=self.tracer_provider)

        client.get("key")
        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 1)

    def test_instrument_client_twice_warns(self):
        client = FakeStrictValkey()
        ValkeyInstrumentor.instrument_client(client, tracer_provider=self.tracer_provider)
        with self.assertLogs(_LOGGER_NAME, level=logging.WARNING) as logs:
            ValkeyInstrumentor.instrument_client(client, tracer_provider=self.tracer_provider)
        self.assertIn("already instrumented", logs.output[0])

    def test_uninstrument_client_that_was_never_instrumented(self):
        client = FakeStrictValkey()
        with self.assertLogs(_LOGGER_NAME, level=logging.WARNING) as logs:
            ValkeyInstrumentor.uninstrument_client(client)
        self.assertIn("wasn't instrumented", logs.output[0])


class TestValkeyAsyncInstrumentClient(TestBase, IsolatedAsyncioTestCase):
    async def test_only_the_instrumented_client_is_traced(self):
        instrumented = FakeAsyncValkey()
        other = FakeAsyncValkey()
        ValkeyInstrumentor.instrument_client(
            instrumented,
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )

        await other.get("key")
        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 0)

        await instrumented.get("key")
        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 1)

    async def test_pipeline_of_instrumented_client(self):
        client = FakeAsyncValkey()
        ValkeyInstrumentor.instrument_client(client, tracer_provider=self.tracer_provider)

        async with client.pipeline(transaction=False) as pipeline:
            pipeline.set("key", "value")
            pipeline.get("key")
            await pipeline.execute()

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "PIPELINE")
        self.assertEqual(spans[0].attributes[DB_OPERATION_BATCH_SIZE], 2)

    async def test_uninstrument_client(self):
        client = FakeAsyncValkey()
        ValkeyInstrumentor.instrument_client(client, tracer_provider=self.tracer_provider)
        await client.get("key")
        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 1)

        ValkeyInstrumentor.uninstrument_client(client)
        await client.get("key")
        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 1)

    async def test_client_can_be_reinstrumented(self):
        client = FakeAsyncValkey()
        ValkeyInstrumentor.instrument_client(client, tracer_provider=self.tracer_provider)
        ValkeyInstrumentor.uninstrument_client(client)
        ValkeyInstrumentor.instrument_client(client, tracer_provider=self.tracer_provider)

        await client.get("key")
        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 1)

    async def test_instrument_client_twice_warns(self):
        client = FakeAsyncValkey()
        ValkeyInstrumentor.instrument_client(client, tracer_provider=self.tracer_provider)
        with self.assertLogs(_LOGGER_NAME, level=logging.WARNING) as logs:
            ValkeyInstrumentor.instrument_client(client, tracer_provider=self.tracer_provider)
        self.assertIn("already instrumented", logs.output[0])

    async def test_uninstrument_client_that_was_never_instrumented(self):
        client = FakeAsyncValkey()
        with self.assertLogs(_LOGGER_NAME, level=logging.WARNING) as logs:
            ValkeyInstrumentor.uninstrument_client(client)
        self.assertIn("wasn't instrumented", logs.output[0])
