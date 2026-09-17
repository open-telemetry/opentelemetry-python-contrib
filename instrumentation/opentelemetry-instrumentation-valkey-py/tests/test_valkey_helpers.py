# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the helper modules backing the Valkey instrumentation."""

from types import SimpleNamespace

import fakeredis
import valkey

from opentelemetry.instrumentation.valkey.utils import (
    _create_duration_histogram,
    _get_batch_operation_name,
    _get_batch_query_text,
    _get_batch_stored_procedure_name,
    _get_command_stack,
    _get_common_attributes,
    _get_connection_attributes,
    _get_error_attributes,
    _get_error_status_code,
    _get_span_name,
    _get_stored_procedure_name,
)
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


class TestValkeyUtil(TestBase):
    def test_get_command_stack(self):
        client = fakeredis.FakeStrictValkey()
        pipeline = client.pipeline(transaction=False)
        pipeline.set("key", "value")
        pipeline.get("key")

        cases = [
            ("pipeline", pipeline, [("SET", "key", "value"), ("GET", "key")]),
            (
                "cluster pipeline",
                SimpleNamespace(
                    command_stack=[
                        SimpleNamespace(args=("SET", "key", "value")),
                        SimpleNamespace(args=("GET", "key")),
                    ]
                ),
                [("SET", "key", "value"), ("GET", "key")],
            ),
            (
                "async cluster pipeline keeps the stack on a private attribute",
                SimpleNamespace(_command_stack=[SimpleNamespace(args=("GET", "key"))]),
                [("GET", "key")],
            ),
            (
                "a non-list command stack is treated as empty",
                SimpleNamespace(command_stack="not-a-list"),
                [],
            ),
            (
                "malformed entries are skipped",
                SimpleNamespace(
                    command_stack=[
                        SimpleNamespace(args=("GET", "key")),
                        object(),
                        SimpleNamespace(args="not-a-tuple"),
                    ]
                ),
                [("GET", "key")],
            ),
        ]
        for name, instance, expected in cases:
            with self.subTest(name):
                self.assertEqual(_get_command_stack(instance), expected)

    def test_get_error_status_code(self):
        cases = [
            (
                "a response error with a status code",
                valkey.ResponseError("WRONGTYPE Operation against a key"),
                "WRONGTYPE",
            ),
            (
                "a response error without a status code",
                valkey.ResponseError("unknown command 'FOO'"),
                None,
            ),
            ("a non-response error", valkey.ConnectionError("connection refused"), None),
        ]
        for name, exception, expected in cases:
            with self.subTest(name):
                self.assertEqual(_get_error_status_code(exception), expected)

    def test_get_span_name(self):
        cases = [
            # The database index is deliberately absent from the span name.
            ("named operation", "GET", "GET"),
            # A command without arguments must still get a usable span name.
            ("empty operation falls back to the system name", "", "valkey"),
        ]
        for name, operation_name, expected in cases:
            with self.subTest(name):
                self.assertEqual(_get_span_name(operation_name), expected)

    def test_get_common_attributes(self):
        instance = SimpleNamespace()
        cases = [
            (
                "required fields only",
                ("GET", None, None, None),
                {DB_SYSTEM_NAME: "valkey", DB_OPERATION_NAME: "GET"},
            ),
            (
                "with optional fields",
                ("PIPELINE", "GET ?", "abc123", 2),
                {
                    DB_SYSTEM_NAME: "valkey",
                    DB_OPERATION_NAME: "PIPELINE",
                    DB_QUERY_TEXT: "GET ?",
                    DB_STORED_PROCEDURE_NAME: "abc123",
                    DB_OPERATION_BATCH_SIZE: 2,
                },
            ),
        ]
        for name, args, expected in cases:
            with self.subTest(name):
                self.assertEqual(_get_common_attributes(instance, *args), expected)

    def test_get_connection_attributes(self):
        cases = [
            ("without a connection pool", SimpleNamespace(), {}),
            (
                "tcp",
                SimpleNamespace(
                    connection_pool=SimpleNamespace(connection_kwargs={"host": "localhost", "port": 6379, "db": 0})
                ),
                {
                    DB_NAMESPACE: "0",
                    SERVER_ADDRESS: "localhost",
                    SERVER_PORT: 6379,
                    NETWORK_PEER_ADDRESS: "localhost",
                    NETWORK_PEER_PORT: 6379,
                    NETWORK_TRANSPORT: "tcp",
                },
            ),
            (
                "unix socket",
                SimpleNamespace(connection_pool=SimpleNamespace(connection_kwargs={"path": "/tmp/valkey.sock"})),
                {
                    DB_NAMESPACE: "0",
                    SERVER_ADDRESS: "/tmp/valkey.sock",
                    NETWORK_PEER_ADDRESS: "/tmp/valkey.sock",
                    NETWORK_TRANSPORT: "unix",
                },
            ),
        ]
        for name, instance, expected in cases:
            with self.subTest(name):
                self.assertEqual(_get_connection_attributes(instance), expected)

    def test_get_stored_procedure_name(self):
        cases = [
            ("evalsha", ("EVALSHA", "abc123", 1, "k"), "abc123"),
            ("evalsha_ro", ("EVALSHA_RO", "abc123", 0), "abc123"),
            ("fcall", ("FCALL", "myfunc", 0), "myfunc"),
            ("fcall_ro", ("FCALL_RO", "myfunc", 0), "myfunc"),
            # EVAL carries the script body rather than a name or a sha1 digest.
            ("eval is not a stored procedure", ("EVAL", "return 1", 0), None),
            ("a plain command is not a stored procedure", ("GET", "key"), None),
            ("evalsha without a name", ("EVALSHA",), None),
        ]
        for name, args, expected in cases:
            with self.subTest(name):
                self.assertEqual(_get_stored_procedure_name(args), expected)

    def test_get_batch_operation_name(self):
        shared = [("GET", "one"), ("GET", "two")]
        mixed = [("SET", "one", 1), ("GET", "two")]

        cases = [
            (
                "pipeline with a shared command",
                SimpleNamespace(transaction=False),
                shared,
                "PIPELINE GET",
            ),
            (
                "pipeline with mixed commands",
                SimpleNamespace(transaction=False),
                mixed,
                "PIPELINE",
            ),
            ("empty pipeline", SimpleNamespace(transaction=False), [], "PIPELINE"),
            (
                "transaction with a shared command",
                SimpleNamespace(transaction=True),
                shared,
                "MULTI GET",
            ),
            (
                # The async pipeline stores the flag under a different name.
                "async transaction",
                SimpleNamespace(is_transaction=True),
                mixed,
                "MULTI",
            ),
            (
                "explicit transaction via .multi()",
                SimpleNamespace(explicit_transaction=True),
                mixed,
                "MULTI",
            ),
        ]
        for name, instance, command_stack, expected in cases:
            with self.subTest(name):
                self.assertEqual(_get_batch_operation_name(instance, command_stack), expected)

    def test_get_batch_stored_procedure_name(self):
        cases = [
            (
                "shared stored procedure",
                [("EVALSHA", "abc123", 1, "k"), ("EVALSHA", "abc123", 1, "k2")],
                "abc123",
            ),
            (
                "mismatched stored procedures",
                [("EVALSHA", "abc123", 1, "k"), ("EVALSHA", "def456", 1, "k")],
                None,
            ),
            ("no stored procedures", [("GET", "one"), ("SET", "two", "v")], None),
            ("empty command stack", [], None),
        ]
        for name, command_stack, expected in cases:
            with self.subTest(name):
                self.assertEqual(_get_batch_stored_procedure_name(command_stack), expected)

    def test_get_batch_query_text(self):
        cases = [
            # Identical query texts collapse to a single entry.
            ("shared query text", [("GET", "one"), ("GET", "two")], "GET ?"),
            (
                "mixed query text",
                [("SET", "one", 1), ("GET", "two")],
                "SET ? ?\nGET ?",
            ),
            ("empty command stack", [], ""),
        ]
        for name, command_stack, expected in cases:
            with self.subTest(name):
                self.assertEqual(_get_batch_query_text(command_stack), expected)


class TestValkeyMetrics(TestBase):
    def test_get_error_attributes(self):
        cases = [
            (
                "with a status code",
                ("ResponseError", "WRONGTYPE"),
                {ERROR_TYPE: "ResponseError", DB_RESPONSE_STATUS_CODE: "WRONGTYPE"},
            ),
            (
                "without a status code",
                ("ConnectionError", None),
                {ERROR_TYPE: "ConnectionError"},
            ),
        ]
        for name, args, expected in cases:
            with self.subTest(name):
                self.assertEqual(_get_error_attributes(*args), expected)

    def test_create_duration_histogram(self):
        meter = self.meter_provider.get_meter(__name__)

        histogram = _create_duration_histogram(meter)
        histogram.record(0.25, attributes={DB_SYSTEM_NAME: "valkey"})

        metrics = self.get_sorted_metrics()
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].name, DB_CLIENT_OPERATION_DURATION)
        self.assertEqual(metrics[0].unit, "s")
        self.assertEqual(metrics[0].description, "Duration of database client operations.")
        data_point = list(metrics[0].data.data_points)[0]
        self.assertEqual(dict(data_point.attributes), {DB_SYSTEM_NAME: "valkey"})
        self.assertEqual(data_point.count, 1)
