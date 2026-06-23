# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
import asyncio
import os
from unittest import mock
from unittest.mock import AsyncMock, patch

import valkey
import valkey.asyncio

from opentelemetry import trace
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.valkey import ValkeyInstrumentor
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_REDIS_DATABASE_INDEX,
    DB_STATEMENT,
    DB_SYSTEM,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_PEER_NAME,
    NET_PEER_PORT,
    NET_TRANSPORT,
    NetTransportValues,
)
from opentelemetry.semconv.attributes.db_attributes import (
    DB_QUERY_TEXT,
    DB_SYSTEM_NAME,
)
from opentelemetry.semconv.attributes.network_attributes import (
    NETWORK_TRANSPORT,
    NetworkTransportValues,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind


def stability_mode(mode):
    def decorator(test_case):
        @patch.dict(os.environ, {OTEL_SEMCONV_STABILITY_OPT_IN: mode})
        def wrapper(*args, **kwargs):
            _OpenTelemetrySemanticConventionStability._initialized = False
            _OpenTelemetrySemanticConventionStability._initialize()
            return test_case(*args, **kwargs)

        return wrapper

    return decorator


class TestValkey(TestBase):
    def setUp(self):
        super().setUp()
        ValkeyInstrumentor().instrument(tracer_provider=self.tracer_provider)

    def tearDown(self):
        super().tearDown()
        ValkeyInstrumentor().uninstrument()

    def test_span_properties(self):
        valkey_client = valkey.Valkey()

        with mock.patch.object(valkey_client, "connection"):
            valkey_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "GET")
        self.assertEqual(span.kind, SpanKind.CLIENT)

    def test_not_recording(self):
        valkey_client = valkey.Valkey()

        mock_tracer = mock.Mock()
        mock_span = mock.Mock()
        mock_span.is_recording.return_value = False
        mock_tracer.start_span.return_value = mock_span
        with mock.patch("opentelemetry.trace.get_tracer") as tracer:
            with mock.patch.object(valkey_client, "connection"):
                tracer.return_value = mock_tracer
                valkey_client.get("key")
                self.assertFalse(mock_span.is_recording())
                self.assertTrue(mock_span.is_recording.called)
                self.assertFalse(mock_span.set_attribute.called)
                self.assertFalse(mock_span.set_status.called)

    def test_instrument_uninstrument(self):
        valkey_client = valkey.Valkey()

        with mock.patch.object(valkey_client, "connection"):
            valkey_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.memory_exporter.clear()

        # Test uninstrument
        ValkeyInstrumentor().uninstrument()

        with mock.patch.object(valkey_client, "connection"):
            valkey_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)
        self.memory_exporter.clear()

        # Test instrument again
        ValkeyInstrumentor().instrument()

        with mock.patch.object(valkey_client, "connection"):
            valkey_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

    def test_instrument_uninstrument_async_client_command(self):
        valkey_client = valkey.asyncio.Valkey()

        with mock.patch.object(valkey_client, "connection", AsyncMock()):
            asyncio.run(valkey_client.get("key"))

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.memory_exporter.clear()

        # Test uninstrument
        ValkeyInstrumentor().uninstrument()

        with mock.patch.object(valkey_client, "connection", AsyncMock()):
            asyncio.run(valkey_client.get("key"))

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)
        self.memory_exporter.clear()

        # Test instrument again
        ValkeyInstrumentor().instrument()

        with mock.patch.object(valkey_client, "connection", AsyncMock()):
            asyncio.run(valkey_client.get("key"))

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

    def test_response_hook(self):
        valkey_client = valkey.Valkey()
        connection = valkey.connection.Connection()
        valkey_client.connection = connection

        response_attribute_name = "db.valkey.response"

        def response_hook(span, conn, response):
            span.set_attribute(response_attribute_name, response)

        ValkeyInstrumentor().uninstrument()
        ValkeyInstrumentor().instrument(
            tracer_provider=self.tracer_provider, response_hook=response_hook
        )

        test_value = "test_value"

        with mock.patch.object(connection, "send_command"):
            with mock.patch.object(
                valkey_client, "parse_response", return_value=test_value
            ):
                valkey_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertEqual(
            span.attributes.get(response_attribute_name), test_value
        )

    def test_request_hook(self):
        valkey_client = valkey.Valkey()
        connection = valkey.connection.Connection()
        valkey_client.connection = connection

        custom_attribute_name = "my.request.attribute"

        def request_hook(span, conn, args, kwargs):
            if span and span.is_recording():
                span.set_attribute(custom_attribute_name, args[0])

        ValkeyInstrumentor().uninstrument()
        ValkeyInstrumentor().instrument(
            tracer_provider=self.tracer_provider, request_hook=request_hook
        )

        test_value = "test_value"

        with mock.patch.object(connection, "send_command"):
            with mock.patch.object(
                valkey_client, "parse_response", return_value=test_value
            ):
                valkey_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertEqual(span.attributes.get(custom_attribute_name), "GET")

    def test_query_sanitizer_enabled(self):
        valkey_client = valkey.Valkey()
        connection = valkey.connection.Connection()
        valkey_client.connection = connection

        ValkeyInstrumentor().uninstrument()
        ValkeyInstrumentor().instrument(
            tracer_provider=self.tracer_provider,
            sanitize_query=True,
        )

        with mock.patch.object(valkey_client, "connection"):
            valkey_client.set("key", "value")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertEqual(span.attributes.get("db.statement"), "SET ? ?")

    def test_query_sanitizer(self):
        valkey_client = valkey.Valkey()
        connection = valkey.connection.Connection()
        valkey_client.connection = connection

        with mock.patch.object(valkey_client, "connection"):
            valkey_client.set("key", "value")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertEqual(span.attributes.get("db.statement"), "SET ? ?")

    def test_no_op_tracer_provider(self):
        ValkeyInstrumentor().uninstrument()
        tracer_provider = trace.NoOpTracerProvider()
        ValkeyInstrumentor().instrument(tracer_provider=tracer_provider)

        valkey_client = valkey.Valkey()

        with mock.patch.object(valkey_client, "connection"):
            valkey_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def re_instrument_and_clear_exporter(self):
        ValkeyInstrumentor().uninstrument()
        self.memory_exporter.clear()
        ValkeyInstrumentor().instrument(tracer_provider=self.tracer_provider)

    def test_attributes_default(self):
        valkey_client = valkey.Valkey()

        with mock.patch.object(valkey_client, "connection"):
            valkey_client.set("key", "value")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertEqual(span.attributes[DB_SYSTEM], "valkey")
        self.assertEqual(span.attributes[DB_REDIS_DATABASE_INDEX], 0)
        self.assertEqual(span.attributes[NET_PEER_NAME], "localhost")
        self.assertEqual(span.attributes[NET_PEER_PORT], 6379)
        self.assertEqual(
            span.attributes[NET_TRANSPORT],
            NetTransportValues.IP_TCP.value,
        )

    def test_attributes_tcp(self):
        valkey_client = valkey.Valkey.from_url(
            "valkey://foo:bar@1.1.1.1:6380/1"
        )

        with mock.patch.object(valkey_client, "connection"):
            valkey_client.set("key", "value")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertEqual(span.attributes[DB_SYSTEM], "valkey")
        self.assertEqual(span.attributes[DB_REDIS_DATABASE_INDEX], 1)
        self.assertEqual(span.attributes[NET_PEER_NAME], "1.1.1.1")
        self.assertEqual(span.attributes[NET_PEER_PORT], 6380)
        self.assertEqual(
            span.attributes[NET_TRANSPORT],
            NetTransportValues.IP_TCP.value,
        )

    def test_attributes_unix_socket(self):
        valkey_client = valkey.Valkey.from_url(
            "unix://foo@/path/to/socket.sock?db=3&password=bar"
        )

        with mock.patch.object(valkey_client, "connection"):
            valkey_client.set("key", "value")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertEqual(span.attributes[DB_SYSTEM], "valkey")
        self.assertEqual(span.attributes[DB_REDIS_DATABASE_INDEX], 3)
        self.assertEqual(
            span.attributes[NET_PEER_NAME],
            "/path/to/socket.sock",
        )
        self.assertEqual(
            span.attributes[NET_TRANSPORT],
            NetTransportValues.OTHER.value,
        )

    @stability_mode("")
    def test_db_statement_default_mode(self):
        self.re_instrument_and_clear_exporter()
        valkey_client = valkey.Valkey()

        with mock.patch.object(valkey_client, "connection"):
            valkey_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertIn(DB_STATEMENT, span.attributes)
        self.assertEqual(span.attributes[DB_STATEMENT], "GET ?")
        self.assertNotIn(DB_QUERY_TEXT, span.attributes)
        self.assertIn(DB_SYSTEM, span.attributes)
        self.assertEqual(span.attributes[DB_SYSTEM], "valkey")
        self.assertNotIn(DB_SYSTEM_NAME, span.attributes)

    @stability_mode("database")
    def test_db_statement_database_stable_mode(self):
        self.re_instrument_and_clear_exporter()
        valkey_client = valkey.Valkey()

        with mock.patch.object(valkey_client, "connection"):
            valkey_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertNotIn(DB_STATEMENT, span.attributes)
        self.assertIn(DB_QUERY_TEXT, span.attributes)
        self.assertEqual(span.attributes[DB_QUERY_TEXT], "GET ?")
        self.assertNotIn(DB_SYSTEM, span.attributes)
        self.assertIn(DB_SYSTEM_NAME, span.attributes)
        self.assertEqual(span.attributes[DB_SYSTEM_NAME], "valkey")

    @stability_mode("database/dup")
    def test_db_statement_database_dup_mode(self):
        self.re_instrument_and_clear_exporter()
        valkey_client = valkey.Valkey()

        with mock.patch.object(valkey_client, "connection"):
            valkey_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertIn(DB_STATEMENT, span.attributes)
        self.assertEqual(span.attributes[DB_STATEMENT], "GET ?")
        self.assertIn(DB_QUERY_TEXT, span.attributes)
        self.assertEqual(span.attributes[DB_QUERY_TEXT], "GET ?")
        self.assertIn(DB_SYSTEM, span.attributes)
        self.assertEqual(span.attributes[DB_SYSTEM], "valkey")
        self.assertIn(DB_SYSTEM_NAME, span.attributes)
        self.assertEqual(span.attributes[DB_SYSTEM_NAME], "valkey")

    @stability_mode("database")
    def test_db_namespace_database_stable_mode(self):
        self.re_instrument_and_clear_exporter()
        valkey_client = valkey.Valkey()

        with mock.patch.object(valkey_client, "connection"):
            valkey_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        # db.redis.database_index was removed with no replacement in semconv 1.38.0
        self.assertNotIn(DB_REDIS_DATABASE_INDEX, span.attributes)

    @stability_mode("http")
    def test_http_stable_mode(self):
        self.re_instrument_and_clear_exporter()
        valkey_client = valkey.Valkey()

        with mock.patch.object(valkey_client, "connection"):
            valkey_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertIn(SERVER_ADDRESS, span.attributes)
        self.assertEqual(span.attributes[SERVER_ADDRESS], "localhost")
        self.assertIn(SERVER_PORT, span.attributes)
        self.assertEqual(span.attributes[SERVER_PORT], 6379)
        self.assertIn(NETWORK_TRANSPORT, span.attributes)
        self.assertEqual(
            span.attributes[NETWORK_TRANSPORT],
            NetworkTransportValues.TCP.value,
        )
        self.assertNotIn(NET_PEER_NAME, span.attributes)
        self.assertNotIn(NET_PEER_PORT, span.attributes)
        self.assertNotIn(NET_TRANSPORT, span.attributes)

    @stability_mode("http/dup")
    def test_http_dup_mode(self):
        self.re_instrument_and_clear_exporter()
        valkey_client = valkey.Valkey()

        with mock.patch.object(valkey_client, "connection"):
            valkey_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertIn(SERVER_ADDRESS, span.attributes)
        self.assertEqual(span.attributes[SERVER_ADDRESS], "localhost")
        self.assertIn(NET_PEER_NAME, span.attributes)
        self.assertEqual(span.attributes[NET_PEER_NAME], "localhost")
