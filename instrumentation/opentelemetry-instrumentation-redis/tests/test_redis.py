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
from unittest import IsolatedAsyncioTestCase, mock
from unittest.mock import AsyncMock

import fakeredis
import pytest
import redis
import redis.asyncio
from fakeredis.aioredis import FakeRedis
from redis.exceptions import ConnectionError as redis_ConnectionError
from redis.exceptions import WatchError

from opentelemetry import trace
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.semconv.trace import (
    DbSystemValues,
    NetTransportValues,
    SpanAttributes,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind


class TestRedis(TestBase):
    def setUp(self):
        super().setUp()
        RedisInstrumentor().instrument(tracer_provider=self.tracer_provider)

    def tearDown(self):
        super().tearDown()
        RedisInstrumentor().uninstrument()

    def test_span_properties(self):
        redis_client = redis.Redis()

        with mock.patch.object(redis_client, "connection"):
            redis_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "GET")
        self.assertEqual(span.kind, SpanKind.CLIENT)

    def test_not_recording(self):
        redis_client = redis.Redis()

        mock_tracer = mock.Mock()
        mock_span = mock.Mock()
        mock_span.is_recording.return_value = False
        mock_tracer.start_span.return_value = mock_span
        with mock.patch("opentelemetry.trace.get_tracer") as tracer:
            with mock.patch.object(redis_client, "connection"):
                tracer.return_value = mock_tracer
                redis_client.get("key")
                self.assertFalse(mock_span.is_recording())
                self.assertTrue(mock_span.is_recording.called)
                self.assertFalse(mock_span.set_attribute.called)
                self.assertFalse(mock_span.set_status.called)

    def test_instrument_uninstrument(self):
        redis_client = redis.Redis()

        with mock.patch.object(redis_client, "connection"):
            redis_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.memory_exporter.clear()

        # Test uninstrument
        RedisInstrumentor().uninstrument()

        with mock.patch.object(redis_client, "connection"):
            redis_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)
        self.memory_exporter.clear()

        # Test instrument again
        RedisInstrumentor().instrument()

        with mock.patch.object(redis_client, "connection"):
            redis_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

    def test_instrument_uninstrument_async_client_command(self):
        redis_client = redis.asyncio.Redis()

        with mock.patch.object(redis_client, "connection", AsyncMock()):
            asyncio.run(redis_client.get("key"))

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.memory_exporter.clear()

        # Test uninstrument
        RedisInstrumentor().uninstrument()

        with mock.patch.object(redis_client, "connection", AsyncMock()):
            asyncio.run(redis_client.get("key"))

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)
        self.memory_exporter.clear()

        # Test instrument again
        RedisInstrumentor().instrument()

        with mock.patch.object(redis_client, "connection", AsyncMock()):
            asyncio.run(redis_client.get("key"))

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

    def test_response_hook(self):
        redis_client = redis.Redis()
        connection = redis.connection.Connection()
        redis_client.connection = connection

        response_attribute_name = "db.redis.response"

        def response_hook(span, conn, response):
            span.set_attribute(response_attribute_name, response)

        RedisInstrumentor().uninstrument()
        RedisInstrumentor().instrument(
            tracer_provider=self.tracer_provider, response_hook=response_hook
        )

        test_value = "test_value"

        with mock.patch.object(connection, "send_command"):
            with mock.patch.object(
                redis_client, "parse_response", return_value=test_value
            ):
                redis_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertEqual(
            span.attributes.get(response_attribute_name), test_value
        )

    def test_request_hook(self):
        redis_client = redis.Redis()
        connection = redis.connection.Connection()
        redis_client.connection = connection

        custom_attribute_name = "my.request.attribute"

        def request_hook(span, conn, args, kwargs):
            if span and span.is_recording():
                span.set_attribute(custom_attribute_name, args[0])

        RedisInstrumentor().uninstrument()
        RedisInstrumentor().instrument(
            tracer_provider=self.tracer_provider, request_hook=request_hook
        )

        test_value = "test_value"

        with mock.patch.object(connection, "send_command"):
            with mock.patch.object(
                redis_client, "parse_response", return_value=test_value
            ):
                redis_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertEqual(span.attributes.get(custom_attribute_name), "GET")

    def test_query_sanitizer_enabled(self):
        redis_client = redis.Redis()
        connection = redis.connection.Connection()
        redis_client.connection = connection

        RedisInstrumentor().uninstrument()
        RedisInstrumentor().instrument(
            tracer_provider=self.tracer_provider,
            sanitize_query=True,
        )

        with mock.patch.object(redis_client, "connection"):
            redis_client.set("key", "value")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertEqual(span.attributes.get("db.statement"), "SET ? ?")

    def test_query_sanitizer(self):
        redis_client = redis.Redis()
        connection = redis.connection.Connection()
        redis_client.connection = connection

        with mock.patch.object(redis_client, "connection"):
            redis_client.set("key", "value")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertEqual(span.attributes.get("db.statement"), "SET ? ?")

    def test_no_op_tracer_provider(self):
        RedisInstrumentor().uninstrument()
        tracer_provider = trace.NoOpTracerProvider()
        RedisInstrumentor().instrument(tracer_provider=tracer_provider)

        redis_client = redis.Redis()

        with mock.patch.object(redis_client, "connection"):
            redis_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_attributes_default(self):
        redis_client = redis.Redis()

        with mock.patch.object(redis_client, "connection"):
            redis_client.set("key", "value")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertEqual(
            span.attributes[SpanAttributes.DB_SYSTEM],
            DbSystemValues.REDIS.value,
        )
        self.assertEqual(
            span.attributes[SpanAttributes.DB_REDIS_DATABASE_INDEX], 0
        )
        self.assertEqual(
            span.attributes[SpanAttributes.NET_PEER_NAME], "localhost"
        )
        self.assertEqual(span.attributes[SpanAttributes.NET_PEER_PORT], 6379)
        self.assertEqual(
            span.attributes[SpanAttributes.NET_TRANSPORT],
            NetTransportValues.IP_TCP.value,
        )

    def test_attributes_tcp(self):
        redis_client = redis.Redis.from_url("redis://foo:bar@1.1.1.1:6380/1")

        with mock.patch.object(redis_client, "connection"):
            redis_client.set("key", "value")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertEqual(
            span.attributes[SpanAttributes.DB_SYSTEM],
            DbSystemValues.REDIS.value,
        )
        self.assertEqual(
            span.attributes[SpanAttributes.DB_REDIS_DATABASE_INDEX], 1
        )
        self.assertEqual(
            span.attributes[SpanAttributes.NET_PEER_NAME], "1.1.1.1"
        )
        self.assertEqual(span.attributes[SpanAttributes.NET_PEER_PORT], 6380)
        self.assertEqual(
            span.attributes[SpanAttributes.NET_TRANSPORT],
            NetTransportValues.IP_TCP.value,
        )

    def test_attributes_unix_socket(self):
        redis_client = redis.Redis.from_url(
            "unix://foo@/path/to/socket.sock?db=3&password=bar"
        )

        with mock.patch.object(redis_client, "connection"):
            redis_client.set("key", "value")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertEqual(
            span.attributes[SpanAttributes.DB_SYSTEM],
            DbSystemValues.REDIS.value,
        )
        self.assertEqual(
            span.attributes[SpanAttributes.DB_REDIS_DATABASE_INDEX], 3
        )
        self.assertEqual(
            span.attributes[SpanAttributes.NET_PEER_NAME],
            "/path/to/socket.sock",
        )
        self.assertEqual(
            span.attributes[SpanAttributes.NET_TRANSPORT],
            NetTransportValues.OTHER.value,
        )

    def test_connection_error(self):
        server = fakeredis.FakeServer()
        server.connected = False
        redis_client = fakeredis.FakeStrictRedis(server=server)
        try:
            redis_client.set("foo", "bar")
        except redis_ConnectionError:
            pass

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]

        self.assertEqual(span.name, "SET")
        self.assertEqual(span.kind, SpanKind.CLIENT)
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)

    def test_response_error(self):
        redis_client = fakeredis.FakeStrictRedis()
        redis_client.lpush("mylist", "value")
        try:
            redis_client.incr(
                "mylist"
            )  # Trying to increment a list, which is invalid
        except redis.ResponseError:
            pass

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)

        span = spans[0]
        self.assertEqual(span.name, "LPUSH")
        self.assertEqual(span.kind, SpanKind.CLIENT)
        self.assertEqual(span.status.status_code, trace.StatusCode.UNSET)

        span = spans[1]
        self.assertEqual(span.name, "INCRBY")
        self.assertEqual(span.kind, SpanKind.CLIENT)
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)

    def test_watch_error_sync(self):
        def redis_operations():
            with pytest.raises(WatchError):
                redis_client = fakeredis.FakeStrictRedis()
                pipe = redis_client.pipeline(transaction=True)
                pipe.watch("a")
                redis_client.set("a", "bad")  # This will cause the WatchError
                pipe.multi()
                pipe.set("a", "1")
                pipe.execute()

        redis_operations()

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 3)

        # there should be 3 tests, we start watch operation and have 2 set operation on same key
        self.assertEqual(len(spans), 3)

        self.assertEqual(spans[0].attributes.get("db.statement"), "WATCH ?")
        self.assertEqual(spans[0].kind, SpanKind.CLIENT)
        self.assertEqual(spans[0].status.status_code, trace.StatusCode.UNSET)

        for span in spans[1:]:
            self.assertEqual(span.attributes.get("db.statement"), "SET ? ?")
            self.assertEqual(span.kind, SpanKind.CLIENT)
            self.assertEqual(span.status.status_code, trace.StatusCode.UNSET)


class TestRedisAsync(TestBase, IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        RedisInstrumentor().instrument(tracer_provider=self.tracer_provider)

    def tearDown(self):
        super().tearDown()
        RedisInstrumentor().uninstrument()

    @pytest.mark.asyncio
    async def test_watch_error_async(self):
        async def redis_operations():
            with pytest.raises(WatchError):
                redis_client = FakeRedis()
                async with redis_client.pipeline(transaction=False) as pipe:
                    await pipe.watch("a")
                    await redis_client.set("a", "bad")
                    pipe.multi()
                    await pipe.set("a", "1")
                    await pipe.execute()

        await redis_operations()

        spans = self.memory_exporter.get_finished_spans()

        # there should be 3 tests, we start watch operation and have 2 set operation on same key
        self.assertEqual(len(spans), 3)

        self.assertEqual(spans[0].attributes.get("db.statement"), "WATCH ?")
        self.assertEqual(spans[0].kind, SpanKind.CLIENT)
        self.assertEqual(spans[0].status.status_code, trace.StatusCode.UNSET)

        for span in spans[1:]:
            self.assertEqual(span.attributes.get("db.statement"), "SET ? ?")
            self.assertEqual(span.kind, SpanKind.CLIENT)
            self.assertEqual(span.status.status_code, trace.StatusCode.UNSET)
