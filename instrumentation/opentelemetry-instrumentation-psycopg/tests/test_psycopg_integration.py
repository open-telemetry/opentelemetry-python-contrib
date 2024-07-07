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

import types
from unittest import IsolatedAsyncioTestCase, mock

import psycopg

import opentelemetry.instrumentation.psycopg
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.sdk import resources
from opentelemetry.test.test_base import TestBase


class MockCursor:
    execute = mock.MagicMock(spec=types.MethodType)
    execute.__name__ = "execute"

    executemany = mock.MagicMock(spec=types.MethodType)
    executemany.__name__ = "executemany"

    callproc = mock.MagicMock(spec=types.MethodType)
    callproc.__name__ = "callproc"

    rowcount = "SomeRowCount"

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return self


class MockAsyncCursor:
    def __init__(self, *args, **kwargs):
        pass

    # pylint: disable=unused-argument, no-self-use
    async def execute(self, query, params=None, throw_exception=False):
        if throw_exception:
            raise psycopg.Error("Test Exception")

    # pylint: disable=unused-argument, no-self-use
    async def executemany(self, query, params=None, throw_exception=False):
        if throw_exception:
            raise psycopg.Error("Test Exception")

    # pylint: disable=unused-argument, no-self-use
    async def callproc(self, query, params=None, throw_exception=False):
        if throw_exception:
            raise psycopg.Error("Test Exception")

    async def __aenter__(self, *args, **kwargs):
        return self

    async def __aexit__(self, *args, **kwargs):
        pass

    def close(self):
        pass


class MockConnection:
    commit = mock.MagicMock(spec=types.MethodType)
    commit.__name__ = "commit"

    rollback = mock.MagicMock(spec=types.MethodType)
    rollback.__name__ = "rollback"

    def __init__(self, *args, **kwargs):
        self.cursor_factory = kwargs.pop("cursor_factory", None)

    def cursor(self):
        if self.cursor_factory:
            return self.cursor_factory(self)
        return MockCursor()

    def get_dsn_parameters(self):  # pylint: disable=no-self-use
        return {"dbname": "test"}


class MockAsyncConnection:
    commit = mock.MagicMock(spec=types.MethodType)
    commit.__name__ = "commit"

    rollback = mock.MagicMock(spec=types.MethodType)
    rollback.__name__ = "rollback"

    def __init__(self, *args, **kwargs):
        self.cursor_factory = kwargs.pop("cursor_factory", None)

    @staticmethod
    async def connect(*args, **kwargs):
        return MockAsyncConnection(**kwargs)

    def cursor(self):
        if self.cursor_factory:
            cur = self.cursor_factory(self)
            return cur
        return MockAsyncCursor()

    def execute(self, query, params=None, *, prepare=None, binary=False):
        cur = self.cursor()
        return cur.execute(query, params, prepare=prepare)

    def get_dsn_parameters(self):  # pylint: disable=no-self-use
        return {"dbname": "test"}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return mock.MagicMock(spec=types.MethodType)


class PostgresqlIntegrationTestMixin:
    # pylint: disable=invalid-name
    def setUp(self):
        super().setUp()
        self.cursor_mock = mock.patch(
            "opentelemetry.instrumentation.psycopg.pg_cursor", MockCursor
        )
        self.cursor_async_mock = mock.patch(
            "opentelemetry.instrumentation.psycopg.pg_async_cursor",
            MockAsyncCursor,
        )
        self.connection_mock = mock.patch("psycopg.connect", MockConnection)
        self.connection_sync_mock = mock.patch(
            "psycopg.Connection.connect", MockConnection
        )
        self.connection_async_mock = mock.patch(
            "psycopg.AsyncConnection.connect", MockAsyncConnection.connect
        )

        self.cursor_mock.start()
        self.cursor_async_mock.start()
        self.connection_mock.start()
        self.connection_sync_mock.start()
        self.connection_async_mock.start()

    # pylint: disable=invalid-name
    def tearDown(self):
        super().tearDown()
        self.memory_exporter.clear()
        self.cursor_mock.stop()
        self.cursor_async_mock.stop()
        self.connection_mock.stop()
        self.connection_sync_mock.stop()
        self.connection_async_mock.stop()
        with self.disable_logging():
            PsycopgInstrumentor().uninstrument()


class TestPostgresqlIntegration(PostgresqlIntegrationTestMixin, TestBase):
    # pylint: disable=unused-argument
    def test_instrumentor(self):
        PsycopgInstrumentor().instrument()

        cnx = psycopg.connect(database="test")

        cursor = cnx.cursor()

        query = "SELECT * FROM test"
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.psycopg
        )

        # check that no spans are generated after uninstrument
        PsycopgInstrumentor().uninstrument()

        cnx = psycopg.connect(database="test")
        cursor = cnx.cursor()
        query = "SELECT * FROM test"
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    # pylint: disable=unused-argument
    def test_instrumentor_with_connection_class(self):
        PsycopgInstrumentor().instrument()

        cnx = psycopg.Connection.connect(database="test")

        cursor = cnx.cursor()

        query = "SELECT * FROM test"
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.psycopg
        )

        # check that no spans are generated after uninstrument
        PsycopgInstrumentor().uninstrument()

        cnx = psycopg.Connection.connect(database="test")
        cursor = cnx.cursor()
        query = "SELECT * FROM test"
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    def test_span_name(self):
        PsycopgInstrumentor().instrument()

        cnx = psycopg.connect(database="test")

        cursor = cnx.cursor()

        cursor.execute("Test query", ("param1Value", False))
        cursor.execute(
            """multi
        line
        query"""
        )
        cursor.execute("tab\tseparated query")
        cursor.execute("/* leading comment */ query")
        cursor.execute("/* leading comment */ query /* trailing comment */")
        cursor.execute("query /* trailing comment */")
        cursor.execute("")
        cursor.execute("--")
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 8)
        self.assertEqual(spans_list[0].name, "Test")
        self.assertEqual(spans_list[1].name, "multi")
        self.assertEqual(spans_list[2].name, "tab")
        self.assertEqual(spans_list[3].name, "query")
        self.assertEqual(spans_list[4].name, "query")
        self.assertEqual(spans_list[5].name, "query")
        self.assertEqual(spans_list[6].name, "postgresql")
        self.assertEqual(spans_list[7].name, "--")

    # pylint: disable=unused-argument
    def test_not_recording(self):
        mock_tracer = mock.Mock()
        mock_span = mock.Mock()
        mock_span.is_recording.return_value = False
        mock_tracer.start_span.return_value = mock_span
        PsycopgInstrumentor().instrument()
        with mock.patch("opentelemetry.trace.get_tracer") as tracer:
            tracer.return_value = mock_tracer
            cnx = psycopg.connect(database="test")
            cursor = cnx.cursor()
            query = "SELECT * FROM test"
            cursor.execute(query)
            self.assertFalse(mock_span.is_recording())
            self.assertTrue(mock_span.is_recording.called)
            self.assertFalse(mock_span.set_attribute.called)
            self.assertFalse(mock_span.set_status.called)

        PsycopgInstrumentor().uninstrument()

    # pylint: disable=unused-argument
    def test_custom_tracer_provider(self):
        resource = resources.Resource.create({})
        result = self.create_tracer_provider(resource=resource)
        tracer_provider, exporter = result

        PsycopgInstrumentor().instrument(tracer_provider=tracer_provider)

        cnx = psycopg.connect(database="test")
        cursor = cnx.cursor()
        query = "SELECT * FROM test"
        cursor.execute(query)

        spans_list = exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        self.assertIs(span.resource, resource)

    # pylint: disable=unused-argument
    def test_instrument_connection(self):
        cnx = psycopg.connect(database="test")
        query = "SELECT * FROM test"
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

        cnx = PsycopgInstrumentor().instrument_connection(cnx)
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    # pylint: disable=unused-argument
    def test_instrument_connection_with_instrument(self):
        cnx = psycopg.connect(database="test")
        query = "SELECT * FROM test"
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

        PsycopgInstrumentor().instrument()
        cnx = PsycopgInstrumentor().instrument_connection(cnx)
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    # pylint: disable=unused-argument
    def test_uninstrument_connection_with_instrument(self):
        PsycopgInstrumentor().instrument()
        cnx = psycopg.connect(database="test")
        query = "SELECT * FROM test"
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

        cnx = PsycopgInstrumentor().uninstrument_connection(cnx)
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    # pylint: disable=unused-argument
    def test_uninstrument_connection_with_instrument_connection(self):
        cnx = psycopg.connect(database="test")
        PsycopgInstrumentor().instrument_connection(cnx)
        query = "SELECT * FROM test"
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

        cnx = PsycopgInstrumentor().uninstrument_connection(cnx)
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    @mock.patch("opentelemetry.instrumentation.dbapi.wrap_connect")
    def test_sqlcommenter_enabled(self, event_mocked):
        cnx = psycopg.connect(database="test")
        PsycopgInstrumentor().instrument(enable_commenter=True)
        query = "SELECT * FROM test"
        cursor = cnx.cursor()
        cursor.execute(query)
        kwargs = event_mocked.call_args[1]
        self.assertEqual(kwargs["enable_commenter"], True)

    @mock.patch("opentelemetry.instrumentation.dbapi.wrap_connect")
    def test_sqlcommenter_disabled(self, event_mocked):
        cnx = psycopg.connect(database="test")
        PsycopgInstrumentor().instrument()
        query = "SELECT * FROM test"
        cursor = cnx.cursor()
        cursor.execute(query)
        kwargs = event_mocked.call_args[1]
        self.assertEqual(kwargs["enable_commenter"], False)


class TestPostgresqlIntegrationAsync(
    PostgresqlIntegrationTestMixin, TestBase, IsolatedAsyncioTestCase
):
    async def test_wrap_async_connection_class_with_cursor(self):
        PsycopgInstrumentor().instrument()

        async def test_async_connection():
            acnx = await psycopg.AsyncConnection.connect("test")
            async with acnx as cnx:
                async with cnx.cursor() as cursor:
                    await cursor.execute("SELECT * FROM test")

        await test_async_connection()
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.psycopg
        )

        # check that no spans are generated after uninstrument
        PsycopgInstrumentor().uninstrument()

        await test_async_connection()

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    # pylint: disable=unused-argument
    async def test_instrumentor_with_async_connection_class(self):
        PsycopgInstrumentor().instrument()

        async def test_async_connection():
            acnx = await psycopg.AsyncConnection.connect("test")
            async with acnx as cnx:
                await cnx.execute("SELECT * FROM test")

        await test_async_connection()

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.psycopg
        )

        # check that no spans are generated after uninstrument
        PsycopgInstrumentor().uninstrument()
        await test_async_connection()

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    async def test_span_name_async(self):
        PsycopgInstrumentor().instrument()

        cnx = await psycopg.AsyncConnection.connect("test")
        async with cnx.cursor() as cursor:
            await cursor.execute("Test query", ("param1Value", False))
            await cursor.execute(
                """multi
    line
    query"""
            )
            await cursor.execute("tab\tseparated query")
            await cursor.execute("/* leading comment */ query")
            await cursor.execute(
                "/* leading comment */ query /* trailing comment */"
            )
            await cursor.execute("query /* trailing comment */")

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 6)
        self.assertEqual(spans_list[0].name, "Test")
        self.assertEqual(spans_list[1].name, "multi")
        self.assertEqual(spans_list[2].name, "tab")
        self.assertEqual(spans_list[3].name, "query")
        self.assertEqual(spans_list[4].name, "query")
        self.assertEqual(spans_list[5].name, "query")

    # pylint: disable=unused-argument
    async def test_not_recording_async(self):
        mock_tracer = mock.Mock()
        mock_span = mock.Mock()
        mock_span.is_recording.return_value = False
        mock_tracer.start_span.return_value = mock_span
        PsycopgInstrumentor().instrument()
        with mock.patch("opentelemetry.trace.get_tracer") as tracer:
            tracer.return_value = mock_tracer
            cnx = await psycopg.AsyncConnection.connect("test")
            async with cnx.cursor() as cursor:
                query = "SELECT * FROM test"
                await cursor.execute(query)
            self.assertFalse(mock_span.is_recording())
            self.assertTrue(mock_span.is_recording.called)
            self.assertFalse(mock_span.set_attribute.called)
            self.assertFalse(mock_span.set_status.called)

        PsycopgInstrumentor().uninstrument()
