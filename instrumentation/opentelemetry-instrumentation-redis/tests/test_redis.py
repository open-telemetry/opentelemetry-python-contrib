# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=too-many-lines

import asyncio
import os
from unittest import IsolatedAsyncioTestCase, mock
from unittest.mock import AsyncMock, patch

import fakeredis
import pytest
import redis
import redis.asyncio
from fakeredis.aioredis import FakeRedis
from redis.exceptions import ConnectionError as redis_ConnectionError
from redis.exceptions import WatchError

from opentelemetry import trace
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_REDIS_DATABASE_INDEX,
    DB_STATEMENT,
    DB_SYSTEM,
    DbSystemValues,
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


# pylint: disable=too-many-public-methods
class TestRedis(TestBase):
    def assert_span_count(self, count: int):
        """
        Assert that the memory exporter has the expected number of spans.
        Returns the spans list if assertion passes
        """
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), count)
        return spans

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
            span.attributes[DB_SYSTEM],
            DbSystemValues.REDIS.value,
        )
        self.assertEqual(span.attributes[DB_REDIS_DATABASE_INDEX], 0)
        self.assertEqual(span.attributes[NET_PEER_NAME], "localhost")
        self.assertEqual(span.attributes[NET_PEER_PORT], 6379)
        self.assertEqual(
            span.attributes[NET_TRANSPORT],
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
            span.attributes[DB_SYSTEM],
            DbSystemValues.REDIS.value,
        )
        self.assertEqual(span.attributes[DB_REDIS_DATABASE_INDEX], 1)
        self.assertEqual(span.attributes[NET_PEER_NAME], "1.1.1.1")
        self.assertEqual(span.attributes[NET_PEER_PORT], 6380)
        self.assertEqual(
            span.attributes[NET_TRANSPORT],
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
            span.attributes[DB_SYSTEM],
            DbSystemValues.REDIS.value,
        )
        self.assertEqual(span.attributes[DB_REDIS_DATABASE_INDEX], 3)
        self.assertEqual(
            span.attributes[NET_PEER_NAME],
            "/path/to/socket.sock",
        )
        self.assertEqual(
            span.attributes[NET_TRANSPORT],
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

    def test_span_name_empty_pipeline(self):
        redis_client = fakeredis.FakeStrictRedis()
        pipe = redis_client.pipeline()
        pipe.execute()

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "redis")
        self.assertEqual(spans[0].kind, SpanKind.CLIENT)
        self.assertEqual(spans[0].status.status_code, trace.StatusCode.UNSET)

    def test_suppress_instrumentation_command(self):
        redis_client = redis.Redis()

        with mock.patch.object(redis_client, "connection"):
            # Execute command with suppression
            with suppress_instrumentation():
                redis_client.get("key")

        # No spans should be created
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

        # Verify that instrumentation works again after exiting the context
        with mock.patch.object(redis_client, "connection"):
            redis_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

    def test_suppress_instrumentation_pipeline(self):
        redis_client = fakeredis.FakeStrictRedis()

        with suppress_instrumentation():
            pipe = redis_client.pipeline()
            pipe.set("key1", "value1")
            pipe.set("key2", "value2")
            pipe.get("key1")
            pipe.execute()

        # No spans should be created
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

        # Verify that instrumentation works again after exiting the context
        pipe = redis_client.pipeline()
        pipe.set("key3", "value3")
        pipe.execute()

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        # Pipeline span could be "SET" or "redis.pipeline" depending on implementation
        self.assertIn(spans[0].name, ["SET", "redis.pipeline"])

    def test_suppress_instrumentation_mixed(self):
        redis_client = redis.Redis()

        # Regular instrumented call
        with mock.patch.object(redis_client, "connection"):
            redis_client.set("key1", "value1")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.memory_exporter.clear()

        # Suppressed call
        with suppress_instrumentation():
            with mock.patch.object(redis_client, "connection"):
                redis_client.set("key2", "value2")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

        # Another regular instrumented call
        with mock.patch.object(redis_client, "connection"):
            redis_client.get("key1")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)


class TestRedisAsync(TestBase, IsolatedAsyncioTestCase):
    def assert_span_count(self, count: int):
        """
        Assert that the memory exporter has the expected number of spans.
        Returns the spans list if assertion passes
        """
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), count)
        return spans

    def setUp(self):
        super().setUp()
        self.instrumentor = RedisInstrumentor()
        self.client: FakeRedis = FakeRedis()

    @staticmethod
    async def _redis_pipeline_operations(client: FakeRedis):
        with pytest.raises(WatchError):
            async with client.pipeline(transaction=False) as pipe:
                await pipe.watch("a")
                await client.set("a", "bad")
                pipe.multi()
                await pipe.set("a", "1")
                await pipe.execute()

    @pytest.mark.asyncio
    async def test_watch_error_async(self):
        # this tests also ensures the response_hook is called
        response_attr = "my.response.attribute"
        count = 0

        def response_hook(span, conn, args):
            nonlocal count
            if span and span.is_recording():
                span.set_attribute(response_attr, count)
                count += 1

        self.instrumentor.instrument(
            tracer_provider=self.tracer_provider, response_hook=response_hook
        )
        redis_client = FakeRedis()
        await self._redis_pipeline_operations(redis_client)

        # there should be 3 tests, we start watch operation and have 2 set operation on same key
        spans = self.assert_span_count(3)

        self.assertEqual(spans[0].attributes.get("db.statement"), "WATCH ?")
        self.assertEqual(spans[0].kind, SpanKind.CLIENT)
        self.assertEqual(spans[0].status.status_code, trace.StatusCode.UNSET)
        self.assertEqual(spans[0].attributes.get(response_attr), 0)

        for span_index, span in enumerate(spans[1:], 1):
            self.assertEqual(span.attributes.get("db.statement"), "SET ? ?")
            self.assertEqual(span.kind, SpanKind.CLIENT)
            self.assertEqual(span.status.status_code, trace.StatusCode.UNSET)
            self.assertEqual(span.attributes.get(response_attr), span_index)
        RedisInstrumentor().uninstrument()

    @pytest.mark.asyncio
    async def test_watch_error_async_only_client(self):
        self.instrumentor.instrument_client(
            tracer_provider=self.tracer_provider, client=self.client
        )
        redis_client = FakeRedis()
        await self._redis_pipeline_operations(redis_client)

        spans = self.memory_exporter.get_finished_spans()

        # there should be 3 tests, we start watch operation and have 2 set operation on same key
        self.assertEqual(len(spans), 0)

        # now with the instrumented client we should get proper spans
        await self._redis_pipeline_operations(self.client)

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
        RedisInstrumentor().uninstrument_client(self.client)

    @pytest.mark.asyncio
    async def test_request_response_hooks(self):
        request_attr = "my.request.attribute"
        response_attr = "my.response.attribute"

        def request_hook(span, conn, args, kwargs):
            if span and span.is_recording():
                span.set_attribute(request_attr, args[0])

        def response_hook(span, conn, args):
            if span and span.is_recording():
                span.set_attribute(response_attr, args)

        self.instrumentor.instrument(
            tracer_provider=self.tracer_provider,
            request_hook=request_hook,
            response_hook=response_hook,
        )
        await self.client.set("key", "value")

        spans = self.assert_span_count(1)

        span = spans[0]
        self.assertEqual(span.attributes.get(request_attr), "SET")
        self.assertEqual(span.attributes.get(response_attr), True)
        self.instrumentor.uninstrument()

    @pytest.mark.asyncio
    async def test_request_response_hooks_connection_only(self):
        request_attr = "my.request.attribute"
        response_attr = "my.response.attribute"

        def request_hook(span, conn, args, kwargs):
            if span and span.is_recording():
                span.set_attribute(request_attr, args[0])

        def response_hook(span, conn, args):
            if span and span.is_recording():
                span.set_attribute(response_attr, args)

        self.instrumentor.instrument_client(
            client=self.client,
            tracer_provider=self.tracer_provider,
            request_hook=request_hook,
            response_hook=response_hook,
        )
        await self.client.set("key", "value")

        spans = self.assert_span_count(1)

        span = spans[0]
        self.assertEqual(span.attributes.get(request_attr), "SET")
        self.assertEqual(span.attributes.get(response_attr), True)
        # fresh client should not record any spans
        fresh_client = FakeRedis()
        self.memory_exporter.clear()
        await fresh_client.set("key", "value")
        self.assert_span_count(0)
        self.instrumentor.uninstrument_client(self.client)
        # after un-instrumenting the query should not be recorder
        await self.client.set("key", "value")
        spans = self.assert_span_count(0)

    @pytest.mark.asyncio
    async def test_span_name_empty_pipeline(self):
        redis_client = fakeredis.aioredis.FakeRedis()
        self.instrumentor.instrument_client(
            client=redis_client, tracer_provider=self.tracer_provider
        )
        async with redis_client.pipeline() as pipe:
            await pipe.execute()

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "redis")
        self.assertEqual(spans[0].kind, SpanKind.CLIENT)
        self.assertEqual(spans[0].status.status_code, trace.StatusCode.UNSET)
        self.instrumentor.uninstrument_client(client=redis_client)

    @pytest.mark.asyncio
    async def test_suppress_instrumentation_async_command(self):
        self.instrumentor.instrument(tracer_provider=self.tracer_provider)
        redis_client = FakeRedis()

        # Execute command with suppression
        with suppress_instrumentation():
            await redis_client.get("key")

        # No spans should be created
        self.assert_span_count(0)

        # Verify that instrumentation works again after exiting the context
        await redis_client.set("key", "value")
        self.assert_span_count(1)
        self.instrumentor.uninstrument()

    @pytest.mark.asyncio
    async def test_suppress_instrumentation_async_pipeline(self):
        self.instrumentor.instrument(tracer_provider=self.tracer_provider)
        redis_client = FakeRedis()

        # Execute pipeline with suppression
        with suppress_instrumentation():
            async with redis_client.pipeline() as pipe:
                await pipe.set("key1", "value1")
                await pipe.set("key2", "value2")
                await pipe.get("key1")
                await pipe.execute()

        # No spans should be created
        self.assert_span_count(0)

        # Verify that instrumentation works again after exiting the context
        async with redis_client.pipeline() as pipe:
            await pipe.set("key3", "value3")
            await pipe.execute()

        spans = self.assert_span_count(1)
        # Pipeline span could be "SET" or "redis.pipeline" depending on implementation
        self.assertIn(spans[0].name, ["SET", "redis.pipeline"])
        self.instrumentor.uninstrument()

    @pytest.mark.asyncio
    async def test_suppress_instrumentation_async_mixed(self):
        self.instrumentor.instrument(tracer_provider=self.tracer_provider)
        redis_client = FakeRedis()

        # Regular instrumented call
        await redis_client.set("key1", "value1")
        self.assert_span_count(1)
        self.memory_exporter.clear()

        # Suppressed call
        with suppress_instrumentation():
            await redis_client.set("key2", "value2")

        self.assert_span_count(0)

        # Another regular instrumented call
        await redis_client.get("key1")
        self.assert_span_count(1)
        self.instrumentor.uninstrument()


class TestRedisInstance(TestBase):
    def assert_span_count(self, count: int):
        """
        Assert that the memory exporter has the expected number of spans.
        Returns the spans list if assertion passes
        """
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), count)
        return spans

    def setUp(self):
        super().setUp()
        self.client = fakeredis.FakeStrictRedis()
        RedisInstrumentor().instrument_client(
            client=self.client, tracer_provider=self.tracer_provider
        )

    def tearDown(self):
        super().tearDown()
        RedisInstrumentor().uninstrument_client(self.client)

    def test_only_client_instrumented(self):
        redis_client = redis.Redis()

        with mock.patch.object(redis_client, "connection"):
            redis_client.get("key")

        spans = self.assert_span_count(0)

        # now use the test client
        with mock.patch.object(self.client, "connection"):
            self.client.get("key")
        spans = self.assert_span_count(1)
        span = spans[0]
        self.assertEqual(span.name, "GET")
        self.assertEqual(span.kind, SpanKind.CLIENT)

    @staticmethod
    def redis_operations(client):
        with pytest.raises(WatchError):
            pipe = client.pipeline(transaction=True)
            pipe.watch("a")
            client.set("a", "bad")  # This will cause the WatchError
            pipe.multi()
            pipe.set("a", "1")
            pipe.execute()

    def test_watch_error_sync_only_client(self):
        redis_client = fakeredis.FakeStrictRedis()

        self.redis_operations(redis_client)

        self.assert_span_count(0)

        self.redis_operations(self.client)

        # there should be 3 tests, we start watch operation and have 2 set operation on same key
        spans = self.assert_span_count(3)

        self.assertEqual(spans[0].attributes.get("db.statement"), "WATCH ?")
        self.assertEqual(spans[0].kind, SpanKind.CLIENT)
        self.assertEqual(spans[0].status.status_code, trace.StatusCode.UNSET)

        for span in spans[1:]:
            self.assertEqual(span.attributes.get("db.statement"), "SET ? ?")
            self.assertEqual(span.kind, SpanKind.CLIENT)
            self.assertEqual(span.status.status_code, trace.StatusCode.UNSET)


class TestRedisSemconvConfiguration(TestBase):
    """Tests semconv migration for both Redis pipeline and db_statement"""

    def setUp(self):
        super().setUp()
        RedisInstrumentor().instrument(tracer_provider=self.tracer_provider)

    def tearDown(self):
        super().tearDown()
        RedisInstrumentor().uninstrument()

    def re_instrument_and_clear_exporter(self):
        # Re-instrument to pick up the environment variable change
        RedisInstrumentor().uninstrument()
        self.memory_exporter.clear()  # Clear previous spans
        RedisInstrumentor().instrument(tracer_provider=self.tracer_provider)

    @stability_mode("")
    def test_pipeline_default_mode(self):
        self.re_instrument_and_clear_exporter()
        redis_client = fakeredis.FakeStrictRedis()
        pipe = redis_client.pipeline()
        pipe.get("key1")
        pipe.set("key2", "value2")
        pipe.execute()

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertIn(DB_STATEMENT, span.attributes)
        self.assertIn("GET ?", span.attributes[DB_STATEMENT])
        self.assertIn("SET ? ?", span.attributes[DB_STATEMENT])
        self.assertNotIn(DB_QUERY_TEXT, span.attributes)
        self.assertIn(DB_SYSTEM, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM], DbSystemValues.REDIS.value
        )
        self.assertNotIn(DB_SYSTEM_NAME, span.attributes)

    @stability_mode("database")
    def test_pipeline_database_stable_mode(self):
        self.re_instrument_and_clear_exporter()
        redis_client = fakeredis.FakeStrictRedis()
        pipe = redis_client.pipeline()
        pipe.get("key1")
        pipe.set("key2", "value2")
        pipe.execute()

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertNotIn(DB_STATEMENT, span.attributes)
        self.assertIn(DB_QUERY_TEXT, span.attributes)
        self.assertIn("GET ?", span.attributes[DB_QUERY_TEXT])
        self.assertIn("SET ? ?", span.attributes[DB_QUERY_TEXT])
        self.assertNotIn(DB_SYSTEM, span.attributes)
        self.assertIn(DB_SYSTEM_NAME, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM_NAME], DbSystemValues.REDIS.value
        )

    @stability_mode("database/dup")
    def test_pipeline_database_dup_mode(self):
        self.re_instrument_and_clear_exporter()
        redis_client = fakeredis.FakeStrictRedis()
        pipe = redis_client.pipeline()
        pipe.get("key1")
        pipe.set("key2", "value2")
        pipe.execute()

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertIn(DB_STATEMENT, span.attributes)
        self.assertIn("GET ?", span.attributes[DB_STATEMENT])
        self.assertIn("SET ? ?", span.attributes[DB_STATEMENT])
        self.assertIn(DB_QUERY_TEXT, span.attributes)
        self.assertIn("GET ?", span.attributes[DB_QUERY_TEXT])
        self.assertIn("SET ? ?", span.attributes[DB_QUERY_TEXT])
        self.assertIn(DB_SYSTEM, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM], DbSystemValues.REDIS.value
        )
        self.assertIn(DB_SYSTEM_NAME, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM_NAME], DbSystemValues.REDIS.value
        )

    @stability_mode("")
    def test_db_statement_default_mode(self):
        self.re_instrument_and_clear_exporter()
        redis_client = redis.Redis()

        with mock.patch.object(redis_client, "connection"):
            redis_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertIn(DB_STATEMENT, span.attributes)
        self.assertEqual(span.attributes[DB_STATEMENT], "GET ?")
        self.assertNotIn(DB_QUERY_TEXT, span.attributes)
        self.assertIn(DB_SYSTEM, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM], DbSystemValues.REDIS.value
        )
        self.assertNotIn(DB_SYSTEM_NAME, span.attributes)

    @stability_mode("database")
    def test_db_statement_database_stable_mode(self):
        self.re_instrument_and_clear_exporter()
        redis_client = redis.Redis()

        with mock.patch.object(redis_client, "connection"):
            redis_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertNotIn(DB_STATEMENT, span.attributes)
        self.assertIn(DB_QUERY_TEXT, span.attributes)
        self.assertEqual(span.attributes[DB_QUERY_TEXT], "GET ?")
        self.assertNotIn(DB_SYSTEM, span.attributes)
        self.assertIn(DB_SYSTEM_NAME, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM_NAME], DbSystemValues.REDIS.value
        )

    @stability_mode("database/dup")
    def test_db_statement_database_dup_mode(self):
        self.re_instrument_and_clear_exporter()
        redis_client = redis.Redis()

        with mock.patch.object(redis_client, "connection"):
            redis_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertIn(DB_STATEMENT, span.attributes)
        self.assertEqual(span.attributes[DB_STATEMENT], "GET ?")
        self.assertIn(DB_QUERY_TEXT, span.attributes)
        self.assertEqual(span.attributes[DB_QUERY_TEXT], "GET ?")
        self.assertIn(DB_SYSTEM, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM], DbSystemValues.REDIS.value
        )
        self.assertIn(DB_SYSTEM_NAME, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM_NAME], DbSystemValues.REDIS.value
        )

    @stability_mode("")
    def test_db_namespace_default_mode(self):
        self.re_instrument_and_clear_exporter()
        redis_client = redis.Redis()

        with mock.patch.object(redis_client, "connection"):
            redis_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertIn(DB_REDIS_DATABASE_INDEX, span.attributes)
        self.assertEqual(span.attributes[DB_REDIS_DATABASE_INDEX], 0)

    @stability_mode("database")
    def test_db_namespace_database_stable_mode(self):
        self.re_instrument_and_clear_exporter()
        redis_client = redis.Redis()

        with mock.patch.object(redis_client, "connection"):
            redis_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertNotIn(DB_REDIS_DATABASE_INDEX, span.attributes)

    @stability_mode("database/dup")
    def test_db_namespace_database_dup_mode(self):
        self.re_instrument_and_clear_exporter()
        redis_client = redis.Redis()

        with mock.patch.object(redis_client, "connection"):
            redis_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertIn(DB_REDIS_DATABASE_INDEX, span.attributes)
        self.assertEqual(span.attributes[DB_REDIS_DATABASE_INDEX], 0)

    @stability_mode("http")
    def test_db_statement_http_stable_mode(self):
        # HTTP signal type should not affect database attributes; they stay in default behavior
        self.re_instrument_and_clear_exporter()
        redis_client = redis.Redis()

        with mock.patch.object(redis_client, "connection"):
            redis_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        # HTTP signal type doesn't affect database attributes - they remain in default mode
        self.assertIn(DB_STATEMENT, span.attributes)
        self.assertEqual(span.attributes[DB_STATEMENT], "GET ?")
        self.assertNotIn(DB_QUERY_TEXT, span.attributes)
        self.assertIn(DB_SYSTEM, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM], DbSystemValues.REDIS.value
        )
        self.assertNotIn(DB_SYSTEM_NAME, span.attributes)
        # Network attributes should still be present (HTTP signal type for network attributes)
        self.assertIn(SERVER_ADDRESS, span.attributes)
        self.assertIn(SERVER_PORT, span.attributes)
        self.assertNotIn(NET_TRANSPORT, span.attributes)
        self.assertIn(NETWORK_TRANSPORT, span.attributes)
        self.assertEqual(
            span.attributes[NETWORK_TRANSPORT],
            NetworkTransportValues.TCP.value,
        )

    @stability_mode("http")
    def test_net_transport_http_stable_mode_unix_socket(self):
        # HTTP signal type should suppress old net.transport for unix socket connections too
        self.re_instrument_and_clear_exporter()
        redis_client = redis.Redis.from_url(
            "unix://foo@/path/to/socket.sock?db=3&password=bar"
        )

        with mock.patch.object(redis_client, "connection"):
            redis_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertIn(SERVER_ADDRESS, span.attributes)
        self.assertNotIn(NET_TRANSPORT, span.attributes)
        self.assertIn(NETWORK_TRANSPORT, span.attributes)
        self.assertEqual(
            span.attributes[NETWORK_TRANSPORT],
            NetworkTransportValues.UNIX.value,
        )

    @stability_mode("http/dup")
    def test_db_statement_http_dup_mode(self):
        # HTTP signal type should not affect database attributes; they stay in default behavior
        self.re_instrument_and_clear_exporter()
        redis_client = redis.Redis()

        with mock.patch.object(redis_client, "connection"):
            redis_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        # HTTP signal type doesn't affect database attributes - they remain in default mode
        self.assertIn(DB_STATEMENT, span.attributes)
        self.assertEqual(span.attributes[DB_STATEMENT], "GET ?")
        self.assertNotIn(DB_QUERY_TEXT, span.attributes)
        self.assertIn(DB_SYSTEM, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM], DbSystemValues.REDIS.value
        )
        self.assertNotIn(DB_SYSTEM_NAME, span.attributes)
        # Network attributes should still be present (HTTP signal type for network attributes)
        self.assertIn(SERVER_ADDRESS, span.attributes)
        self.assertIn(SERVER_PORT, span.attributes)
        self.assertIn(NET_TRANSPORT, span.attributes)
        self.assertEqual(
            span.attributes[NET_TRANSPORT],
            NetTransportValues.IP_TCP.value,
        )
        self.assertIn(NETWORK_TRANSPORT, span.attributes)
        self.assertEqual(
            span.attributes[NETWORK_TRANSPORT],
            NetworkTransportValues.TCP.value,
        )

    @stability_mode("http,database")
    def test_db_statement_combined_http_database_mode(self):
        # Both HTTP and DATABASE signal types should be active
        self.re_instrument_and_clear_exporter()
        redis_client = redis.Redis()

        with mock.patch.object(redis_client, "connection"):
            redis_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        # DATABASE signal type should use stable attributes
        self.assertNotIn(DB_STATEMENT, span.attributes)
        self.assertIn(DB_QUERY_TEXT, span.attributes)
        self.assertEqual(span.attributes[DB_QUERY_TEXT], "GET ?")
        self.assertNotIn(DB_SYSTEM, span.attributes)
        self.assertIn(DB_SYSTEM_NAME, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM_NAME], DbSystemValues.REDIS.value
        )
        # Network attributes should still be present (HTTP signal type)
        self.assertIn(SERVER_ADDRESS, span.attributes)
        self.assertIn(SERVER_PORT, span.attributes)

    @stability_mode("database,http")
    def test_db_statement_combined_database_http_mode(self):
        # Both DATABASE and HTTP signal types should be active (order shouldn't matter)
        self.re_instrument_and_clear_exporter()
        redis_client = redis.Redis()

        with mock.patch.object(redis_client, "connection"):
            redis_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        # DATABASE signal type should use stable attributes
        self.assertNotIn(DB_STATEMENT, span.attributes)
        self.assertIn(DB_QUERY_TEXT, span.attributes)
        self.assertEqual(span.attributes[DB_QUERY_TEXT], "GET ?")
        self.assertNotIn(DB_SYSTEM, span.attributes)
        self.assertIn(DB_SYSTEM_NAME, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM_NAME], DbSystemValues.REDIS.value
        )
        # Network attributes should still be present (HTTP signal type)
        self.assertIn(SERVER_ADDRESS, span.attributes)
        self.assertIn(SERVER_PORT, span.attributes)

    @stability_mode("database/dup,http")
    def test_db_statement_combined_database_dup_http_mode(self):
        # Both DATABASE (dup) and HTTP signal types should be active
        self.re_instrument_and_clear_exporter()
        redis_client = redis.Redis()

        with mock.patch.object(redis_client, "connection"):
            redis_client.get("key")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        # DATABASE signal type in dup mode should have both attributes
        self.assertIn(DB_STATEMENT, span.attributes)
        self.assertEqual(span.attributes[DB_STATEMENT], "GET ?")
        self.assertIn(DB_QUERY_TEXT, span.attributes)
        self.assertEqual(span.attributes[DB_QUERY_TEXT], "GET ?")
        self.assertIn(DB_SYSTEM, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM], DbSystemValues.REDIS.value
        )
        self.assertIn(DB_SYSTEM_NAME, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM_NAME], DbSystemValues.REDIS.value
        )
        # Network attributes should still be present (HTTP signal type)
        self.assertIn(SERVER_ADDRESS, span.attributes)
        self.assertIn(SERVER_PORT, span.attributes)

    @stability_mode("http")
    def test_pipeline_http_stable_mode(self):
        # HTTP signal type should not affect database attributes in pipeline
        self.re_instrument_and_clear_exporter()
        redis_client = fakeredis.FakeStrictRedis()
        pipe = redis_client.pipeline()
        pipe.get("key1")
        pipe.set("key2", "value2")
        pipe.execute()

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        # HTTP signal type doesn't affect database attributes - they remain in default mode
        self.assertIn(DB_STATEMENT, span.attributes)
        self.assertIn("GET ?", span.attributes[DB_STATEMENT])
        self.assertIn("SET ? ?", span.attributes[DB_STATEMENT])
        self.assertNotIn(DB_QUERY_TEXT, span.attributes)
        self.assertIn(DB_SYSTEM, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM], DbSystemValues.REDIS.value
        )
        self.assertNotIn(DB_SYSTEM_NAME, span.attributes)

    @stability_mode("http,database")
    def test_pipeline_combined_http_database_mode(self):
        # Both HTTP and DATABASE signal types should be active in pipeline
        self.re_instrument_and_clear_exporter()
        redis_client = fakeredis.FakeStrictRedis()
        pipe = redis_client.pipeline()
        pipe.get("key1")
        pipe.set("key2", "value2")
        pipe.execute()

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        # DATABASE signal type should use stable attributes
        self.assertNotIn(DB_STATEMENT, span.attributes)
        self.assertIn(DB_QUERY_TEXT, span.attributes)
        self.assertIn("GET ?", span.attributes[DB_QUERY_TEXT])
        self.assertIn("SET ? ?", span.attributes[DB_QUERY_TEXT])
        self.assertNotIn(DB_SYSTEM, span.attributes)
        self.assertIn(DB_SYSTEM_NAME, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM_NAME], DbSystemValues.REDIS.value
        )

    @stability_mode("database")
    def test_async_db_statement_database_stable_mode(self):
        self.re_instrument_and_clear_exporter()
        redis_client = fakeredis.aioredis.FakeRedis()

        asyncio.run(redis_client.get("key"))

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertNotIn(DB_STATEMENT, span.attributes)
        self.assertIn(DB_QUERY_TEXT, span.attributes)
        self.assertEqual(span.attributes[DB_QUERY_TEXT], "GET ?")
        self.assertNotIn(DB_SYSTEM, span.attributes)
        self.assertIn(DB_SYSTEM_NAME, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM_NAME], DbSystemValues.REDIS.value
        )
        self.assertNotIn(DB_REDIS_DATABASE_INDEX, span.attributes)
        self.assertIn(NET_TRANSPORT, span.attributes)
        self.assertEqual(
            span.attributes[NET_TRANSPORT],
            NetTransportValues.IP_TCP.value,
        )
        self.assertNotIn(NETWORK_TRANSPORT, span.attributes)
        self.assertNotIn(SERVER_ADDRESS, span.attributes)
        self.assertNotIn(SERVER_PORT, span.attributes)

    @stability_mode("")
    def test_async_db_statement_default_mode(self):
        self.re_instrument_and_clear_exporter()
        redis_client = fakeredis.aioredis.FakeRedis()

        asyncio.run(redis_client.get("key"))

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertIn(DB_STATEMENT, span.attributes)
        self.assertEqual(span.attributes[DB_STATEMENT], "GET ?")
        self.assertNotIn(DB_QUERY_TEXT, span.attributes)
        self.assertIn(DB_SYSTEM, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM], DbSystemValues.REDIS.value
        )
        self.assertNotIn(DB_SYSTEM_NAME, span.attributes)
        self.assertIn(DB_REDIS_DATABASE_INDEX, span.attributes)
        self.assertEqual(span.attributes[DB_REDIS_DATABASE_INDEX], 0)
        self.assertIn(NET_TRANSPORT, span.attributes)
        self.assertEqual(
            span.attributes[NET_TRANSPORT],
            NetTransportValues.IP_TCP.value,
        )
        self.assertNotIn(NETWORK_TRANSPORT, span.attributes)
        self.assertNotIn(SERVER_ADDRESS, span.attributes)
        self.assertNotIn(SERVER_PORT, span.attributes)

    @stability_mode("database/dup")
    def test_async_db_statement_database_dup_mode(self):
        self.re_instrument_and_clear_exporter()
        redis_client = fakeredis.aioredis.FakeRedis()

        asyncio.run(redis_client.get("key"))

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertIn(DB_STATEMENT, span.attributes)
        self.assertEqual(span.attributes[DB_STATEMENT], "GET ?")
        self.assertIn(DB_QUERY_TEXT, span.attributes)
        self.assertEqual(span.attributes[DB_QUERY_TEXT], "GET ?")
        self.assertIn(DB_SYSTEM, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM], DbSystemValues.REDIS.value
        )
        self.assertIn(DB_SYSTEM_NAME, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM_NAME], DbSystemValues.REDIS.value
        )
        self.assertIn(DB_REDIS_DATABASE_INDEX, span.attributes)
        self.assertEqual(span.attributes[DB_REDIS_DATABASE_INDEX], 0)
        self.assertIn(NET_TRANSPORT, span.attributes)
        self.assertEqual(
            span.attributes[NET_TRANSPORT],
            NetTransportValues.IP_TCP.value,
        )
        self.assertNotIn(NETWORK_TRANSPORT, span.attributes)
        self.assertNotIn(SERVER_ADDRESS, span.attributes)
        self.assertNotIn(SERVER_PORT, span.attributes)

    @stability_mode("database")
    def test_async_pipeline_database_stable_mode(self):
        self.re_instrument_and_clear_exporter()
        redis_client = fakeredis.aioredis.FakeRedis()

        async def _run_pipeline():
            async with redis_client.pipeline() as pipe:
                await pipe.get("key1")
                await pipe.set("key2", "value2")
                await pipe.execute()

        asyncio.run(_run_pipeline())

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertNotIn(DB_STATEMENT, span.attributes)
        self.assertIn(DB_QUERY_TEXT, span.attributes)
        self.assertIn("GET ?", span.attributes[DB_QUERY_TEXT])
        self.assertIn("SET ? ?", span.attributes[DB_QUERY_TEXT])
        self.assertNotIn(DB_SYSTEM, span.attributes)
        self.assertIn(DB_SYSTEM_NAME, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM_NAME], DbSystemValues.REDIS.value
        )
        self.assertNotIn(DB_REDIS_DATABASE_INDEX, span.attributes)
        self.assertIn(NET_TRANSPORT, span.attributes)
        self.assertEqual(
            span.attributes[NET_TRANSPORT],
            NetTransportValues.IP_TCP.value,
        )
        self.assertNotIn(NETWORK_TRANSPORT, span.attributes)
        self.assertNotIn(SERVER_ADDRESS, span.attributes)
        self.assertNotIn(SERVER_PORT, span.attributes)

    @stability_mode("")
    def test_async_pipeline_default_mode(self):
        self.re_instrument_and_clear_exporter()
        redis_client = fakeredis.aioredis.FakeRedis()

        async def _run_pipeline():
            async with redis_client.pipeline() as pipe:
                await pipe.get("key1")
                await pipe.set("key2", "value2")
                await pipe.execute()

        asyncio.run(_run_pipeline())

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertIn(DB_STATEMENT, span.attributes)
        self.assertIn("GET ?", span.attributes[DB_STATEMENT])
        self.assertIn("SET ? ?", span.attributes[DB_STATEMENT])
        self.assertNotIn(DB_QUERY_TEXT, span.attributes)
        self.assertIn(DB_SYSTEM, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM], DbSystemValues.REDIS.value
        )
        self.assertNotIn(DB_SYSTEM_NAME, span.attributes)
        self.assertIn(DB_REDIS_DATABASE_INDEX, span.attributes)
        self.assertEqual(span.attributes[DB_REDIS_DATABASE_INDEX], 0)
        self.assertIn(NET_TRANSPORT, span.attributes)
        self.assertEqual(
            span.attributes[NET_TRANSPORT],
            NetTransportValues.IP_TCP.value,
        )
        self.assertNotIn(NETWORK_TRANSPORT, span.attributes)
        self.assertNotIn(SERVER_ADDRESS, span.attributes)
        self.assertNotIn(SERVER_PORT, span.attributes)

    @stability_mode("database/dup")
    def test_async_pipeline_database_dup_mode(self):
        self.re_instrument_and_clear_exporter()
        redis_client = fakeredis.aioredis.FakeRedis()

        async def _run_pipeline():
            async with redis_client.pipeline() as pipe:
                await pipe.get("key1")
                await pipe.set("key2", "value2")
                await pipe.execute()

        asyncio.run(_run_pipeline())

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertIn(DB_STATEMENT, span.attributes)
        self.assertIn("GET ?", span.attributes[DB_STATEMENT])
        self.assertIn("SET ? ?", span.attributes[DB_STATEMENT])
        self.assertIn(DB_QUERY_TEXT, span.attributes)
        self.assertIn("GET ?", span.attributes[DB_QUERY_TEXT])
        self.assertIn("SET ? ?", span.attributes[DB_QUERY_TEXT])
        self.assertIn(DB_SYSTEM, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM], DbSystemValues.REDIS.value
        )
        self.assertIn(DB_SYSTEM_NAME, span.attributes)
        self.assertEqual(
            span.attributes[DB_SYSTEM_NAME], DbSystemValues.REDIS.value
        )
        self.assertIn(DB_REDIS_DATABASE_INDEX, span.attributes)
        self.assertEqual(span.attributes[DB_REDIS_DATABASE_INDEX], 0)
        self.assertIn(NET_TRANSPORT, span.attributes)
        self.assertEqual(
            span.attributes[NET_TRANSPORT],
            NetTransportValues.IP_TCP.value,
        )
        self.assertNotIn(NETWORK_TRANSPORT, span.attributes)
        self.assertNotIn(SERVER_ADDRESS, span.attributes)
        self.assertNotIn(SERVER_PORT, span.attributes)

    @stability_mode("")
    def test_schema_url_default_mode(self):
        """Test schema URL assignment in default stability mode."""
        self.re_instrument_and_clear_exporter()
        with mock.patch(
            "opentelemetry.instrumentation.redis.get_tracer"
        ) as mock_get_tracer:
            mock_tracer = mock.Mock()
            mock_get_tracer.return_value = mock_tracer
            RedisInstrumentor._get_tracer(tracer_provider=self.tracer_provider)

            # Verify get_tracer was called with legacy schema URL in default mode
            mock_get_tracer.assert_called_once()
            call_args = mock_get_tracer.call_args
            self.assertEqual(
                call_args[1]["schema_url"],
                "https://opentelemetry.io/schemas/1.11.0",
            )

    @stability_mode("database")
    def test_schema_url_database_stable_mode(self):
        """Test schema URL assignment in database stable mode."""
        self.re_instrument_and_clear_exporter()
        with mock.patch(
            "opentelemetry.instrumentation.redis.get_tracer"
        ) as mock_get_tracer:
            mock_tracer = mock.Mock()
            mock_get_tracer.return_value = mock_tracer
            RedisInstrumentor._get_tracer(tracer_provider=self.tracer_provider)

            # Verify get_tracer was called with stable schema URL
            mock_get_tracer.assert_called_once()
            call_args = mock_get_tracer.call_args
            self.assertEqual(
                call_args[1]["schema_url"],
                "https://opentelemetry.io/schemas/1.25.0",
            )

    @stability_mode("database/dup")
    def test_schema_url_database_dup_mode(self):
        """Test schema URL assignment in database duplicate mode."""
        self.re_instrument_and_clear_exporter()
        with mock.patch(
            "opentelemetry.instrumentation.redis.get_tracer"
        ) as mock_get_tracer:
            mock_tracer = mock.Mock()
            mock_get_tracer.return_value = mock_tracer
            RedisInstrumentor._get_tracer(tracer_provider=self.tracer_provider)

            # Verify get_tracer was called with stable schema URL
            mock_get_tracer.assert_called_once()
            call_args = mock_get_tracer.call_args
            self.assertEqual(
                call_args[1]["schema_url"],
                "https://opentelemetry.io/schemas/1.25.0",
            )

    @stability_mode("http")
    def test_schema_url_http_mode(self):
        """Test schema URL assignment in HTTP stability mode."""
        self.re_instrument_and_clear_exporter()
        with mock.patch(
            "opentelemetry.instrumentation.redis.get_tracer"
        ) as mock_get_tracer:
            mock_tracer = mock.Mock()
            mock_get_tracer.return_value = mock_tracer
            RedisInstrumentor._get_tracer(tracer_provider=self.tracer_provider)

            # Verify get_tracer was called with stable schema URL
            mock_get_tracer.assert_called_once()
            call_args = mock_get_tracer.call_args
            self.assertEqual(
                call_args[1]["schema_url"],
                "https://opentelemetry.io/schemas/1.21.0",
            )

    @stability_mode("http,database")
    def test_schema_url_combined_mode(self):
        """Test schema URL assignment in combined HTTP and database mode."""
        self.re_instrument_and_clear_exporter()
        with mock.patch(
            "opentelemetry.instrumentation.redis.get_tracer"
        ) as mock_get_tracer:
            mock_tracer = mock.Mock()
            mock_get_tracer.return_value = mock_tracer
            RedisInstrumentor._get_tracer(tracer_provider=self.tracer_provider)

            # Verify get_tracer was called with stable schema URL
            mock_get_tracer.assert_called_once()
            call_args = mock_get_tracer.call_args
            self.assertEqual(
                call_args[1]["schema_url"],
                "https://opentelemetry.io/schemas/1.25.0",
            )
