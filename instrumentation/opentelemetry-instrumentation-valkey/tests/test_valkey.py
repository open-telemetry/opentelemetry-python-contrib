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
import asyncio
from unittest import mock
from unittest.mock import AsyncMock

import valkey
import valkey.asyncio

from opentelemetry import trace
from opentelemetry.instrumentation.valkey import ValkeyInstrumentor
from opentelemetry.semconv.trace import (
    NetTransportValues,
    SpanAttributes,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind


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

    def test_attributes_default(self):
        valkey_client = valkey.Valkey()

        with mock.patch.object(valkey_client, "connection"):
            valkey_client.set("key", "value")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertEqual(
            span.attributes[SpanAttributes.DB_SYSTEM],
            "valkey",
        )
        self.assertEqual(span.attributes["db.valkey.database_index"], 0)
        self.assertEqual(
            span.attributes[SpanAttributes.NET_PEER_NAME], "localhost"
        )
        self.assertEqual(span.attributes[SpanAttributes.NET_PEER_PORT], 6379)
        self.assertEqual(
            span.attributes[SpanAttributes.NET_TRANSPORT],
            NetTransportValues.IP_TCP.value,
        )

    def test_attributes_tcp(self):
        valkey_client = valkey.Valkey.from_url("valkey://foo:bar@1.1.1.1:6380/1")

        with mock.patch.object(valkey_client, "connection"):
            valkey_client.set("key", "value")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertEqual(
            span.attributes[SpanAttributes.DB_SYSTEM],
            "valkey",
        )
        self.assertEqual(span.attributes["db.valkey.database_index"], 1)
        self.assertEqual(
            span.attributes[SpanAttributes.NET_PEER_NAME], "1.1.1.1"
        )
        self.assertEqual(span.attributes[SpanAttributes.NET_PEER_PORT], 6380)
        self.assertEqual(
            span.attributes[SpanAttributes.NET_TRANSPORT],
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
        self.assertEqual(
            span.attributes[SpanAttributes.DB_SYSTEM],
            "valkey",
        )
        self.assertEqual(span.attributes["db.valkey.database_index"], 3)
        self.assertEqual(
            span.attributes[SpanAttributes.NET_PEER_NAME],
            "/path/to/socket.sock",
        )
        self.assertEqual(
            span.attributes[SpanAttributes.NET_TRANSPORT],
            NetTransportValues.OTHER.value,
        )
