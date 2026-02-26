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
import types
from unittest import IsolatedAsyncioTestCase, mock

import psycopg
from psycopg.sql import SQL, Composed

import opentelemetry.instrumentation.psycopg
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.sdk import resources
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_STATEMENT,
)
from opentelemetry.test.test_base import TestBase


class MockCursor:
    execute = mock.MagicMock(spec=types.MethodType)
    execute.__name__ = "execute"

    executemany = mock.MagicMock(spec=types.MethodType)
    executemany.__name__ = "executemany"

    callproc = mock.MagicMock(spec=types.MethodType)
    callproc.__name__ = "callproc"

    connection = None

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
    async def execute(
        self, query, params=None, throw_exception=False, delay=0.0
    ):
        if throw_exception:
            raise psycopg.Error("Test Exception")

        if delay:
            await asyncio.sleep(delay)

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


class MockAsyncConnection(psycopg.AsyncConnection):
    commit = mock.MagicMock(spec=types.MethodType)
    commit.__name__ = "commit"

    rollback = mock.MagicMock(spec=types.MethodType)
    rollback.__name__ = "rollback"

    def __init__(self, *args, **kwargs):
        self.cursor_factory = kwargs.pop("cursor_factory", None)

    @staticmethod
    async def connect(*args, **kwargs):
        return MockAsyncConnection(**kwargs)

    def cursor(self, *args, **kwargs):
        if self.cursor_factory:
            cur = self.cursor_factory(self)
            return cur
        return MockAsyncCursor(*args, **kwargs)

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
            "opentelemetry.instrumentation.psycopg.psycopg.Cursor", MockCursor
        )
        self.cursor_async_mock = mock.patch(
            "opentelemetry.instrumentation.psycopg.psycopg.AsyncCursor",
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

        self.assertTrue(issubclass(cnx.cursor_factory, MockCursor))

        cursor = cnx.cursor()

        query = "SELECT * FROM test"
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationScope(
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

        self.assertTrue(issubclass(cnx.cursor_factory, MockCursor))

        cursor = cnx.cursor()

        query = "SELECT * FROM test"
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationScope(
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

        self.assertTrue(issubclass(cnx.cursor_factory, MockCursor))
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

    def test_span_params_attribute(self):
        PsycopgInstrumentor().instrument(capture_parameters=True)
        cnx = psycopg.connect(database="test")
        self.assertTrue(issubclass(cnx.cursor_factory, MockCursor))
        query = "SELECT * FROM mytable WHERE myparam1 = %s AND myparam2 = %s"
        params = ("test", 42)

        cursor = cnx.cursor()

        cursor.execute(query, params)
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        self.assertEqual(spans_list[0].name, "SELECT")
        assert spans_list[0].attributes is not None
        self.assertEqual(spans_list[0].attributes["db.statement"], query)
        self.assertEqual(
            spans_list[0].attributes["db.statement.parameters"], str(params)
        )

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
        self.assertTrue(issubclass(cnx.cursor_factory, MockCursor))
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

        self.assertTrue(issubclass(cnx.cursor_factory, MockCursor))

        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    def test_instrument_connection_typed_sql_query(self):
        cnx = psycopg.connect(database="test")
        query = SQL("SELECT * FROM test")

        cnx = PsycopgInstrumentor().instrument_connection(cnx)

        self.assertTrue(issubclass(cnx.cursor_factory, MockCursor))

        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        self.assertEqual(spans_list[0].name, "SELECT")
        self.assertEqual(
            spans_list[0].attributes["db.statement"], "SELECT * FROM test"
        )

    def test_instrument_connection_composed_query(self):
        cnx = psycopg.connect(database="test")
        query: Composed = SQL("SELECT * FROM test").format()

        cnx = PsycopgInstrumentor().instrument_connection(cnx)
        self.assertTrue(issubclass(cnx.cursor_factory, MockCursor))

        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        self.assertEqual(spans_list[0].name, "SELECT")
        self.assertEqual(
            spans_list[0].attributes["db.statement"], "SELECT * FROM test"
        )

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
        self.assertTrue(issubclass(cnx.cursor_factory, MockCursor))
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

    def test_sqlcommenter_enabled_instrument_connection_defaults(self):
        with (
            mock.patch(
                "opentelemetry.instrumentation.psycopg.psycopg.__version__",
                "foobar",
            ),
            mock.patch(
                "opentelemetry.instrumentation.psycopg.psycopg.pq.__build_version__",
                "foobaz",
            ),
            mock.patch(
                "opentelemetry.instrumentation.psycopg.psycopg.pq.version",
                new=lambda: "foobaz",
            ),
            mock.patch(
                "opentelemetry.instrumentation.psycopg.psycopg.threadsafety",
                "123",
            ),
            mock.patch(
                "opentelemetry.instrumentation.psycopg.psycopg.apilevel",
                "123",
            ),
            mock.patch(
                "opentelemetry.instrumentation.psycopg.psycopg.paramstyle",
                "test",
            ),
        ):
            cnx = psycopg.connect(database="test")
            cnx = PsycopgInstrumentor().instrument_connection(
                cnx,
                enable_commenter=True,
            )
            query = "Select 1"
            cursor = cnx.cursor()
            cursor.execute(query)
            spans_list = self.memory_exporter.get_finished_spans()
            span = spans_list[0]
            span_id = format(span.get_span_context().span_id, "016x")
            trace_id = format(span.get_span_context().trace_id, "032x")
            trace_flags = int(span.get_span_context().trace_flags)
            self.assertEqual(
                MockCursor.execute.call_args[0][0],
                f"Select 1 /*db_driver='psycopg%%3Afoobar',dbapi_level='123',dbapi_threadsafety='123',driver_paramstyle='test',libpq_version='foobaz',traceparent='00-{trace_id}-{span_id}-{trace_flags:02x}'*/",
            )
            self.assertEqual(
                span.attributes[DB_STATEMENT],
                "Select 1",
            )

    def test_sqlcommenter_enabled_instrument_connection_stmt_enabled(self):
        with (
            mock.patch(
                "opentelemetry.instrumentation.psycopg.psycopg.__version__",
                "foobar",
            ),
            mock.patch(
                "opentelemetry.instrumentation.psycopg.psycopg.pq.__build_version__",
                "foobaz",
            ),
            mock.patch(
                "opentelemetry.instrumentation.psycopg.psycopg.pq.version",
                new=lambda: "foobaz",
            ),
            mock.patch(
                "opentelemetry.instrumentation.psycopg.psycopg.threadsafety",
                "123",
            ),
            mock.patch(
                "opentelemetry.instrumentation.psycopg.psycopg.apilevel",
                "123",
            ),
            mock.patch(
                "opentelemetry.instrumentation.psycopg.psycopg.paramstyle",
                "test",
            ),
        ):
            cnx = psycopg.connect(database="test")
            cnx = PsycopgInstrumentor().instrument_connection(
                cnx,
                enable_commenter=True,
                enable_attribute_commenter=True,
            )
            query = "Select 1"
            cursor = cnx.cursor()
            cursor.execute(query)
            spans_list = self.memory_exporter.get_finished_spans()
            span = spans_list[0]
            span_id = format(span.get_span_context().span_id, "016x")
            trace_id = format(span.get_span_context().trace_id, "032x")
            trace_flags = int(span.get_span_context().trace_flags)
            self.assertEqual(
                MockCursor.execute.call_args[0][0],
                f"Select 1 /*db_driver='psycopg%%3Afoobar',dbapi_level='123',dbapi_threadsafety='123',driver_paramstyle='test',libpq_version='foobaz',traceparent='00-{trace_id}-{span_id}-{trace_flags:02x}'*/",
            )
            self.assertEqual(
                span.attributes[DB_STATEMENT],
                f"Select 1 /*db_driver='psycopg%%3Afoobar',dbapi_level='123',dbapi_threadsafety='123',driver_paramstyle='test',libpq_version='foobaz',traceparent='00-{trace_id}-{span_id}-{trace_flags:02x}'*/",
            )

    def test_sqlcommenter_enabled_instrument_connection_with_options(self):
        with (
            mock.patch(
                "opentelemetry.instrumentation.psycopg.psycopg.__version__",
                "foobar",
            ),
            mock.patch(
                "opentelemetry.instrumentation.psycopg.psycopg.pq.__build_version__",
                "foobaz",
            ),
            mock.patch(
                "opentelemetry.instrumentation.psycopg.psycopg.pq.version",
                new=lambda: "foobaz",
            ),
            mock.patch(
                "opentelemetry.instrumentation.psycopg.psycopg.threadsafety",
                "123",
            ),
        ):
            cnx = psycopg.connect(database="test")
            cnx = PsycopgInstrumentor().instrument_connection(
                cnx,
                enable_commenter=True,
                commenter_options={
                    "dbapi_level": False,
                    "dbapi_threadsafety": True,
                    "driver_paramstyle": False,
                    "foo": "ignored",
                },
            )
            query = "Select 1"
            cursor = cnx.cursor()
            cursor.execute(query)
            spans_list = self.memory_exporter.get_finished_spans()
            span = spans_list[0]
            span_id = format(span.get_span_context().span_id, "016x")
            trace_id = format(span.get_span_context().trace_id, "032x")
            trace_flags = int(span.get_span_context().trace_flags)
            self.assertEqual(
                MockCursor.execute.call_args[0][0],
                f"Select 1 /*db_driver='psycopg%%3Afoobar',dbapi_threadsafety='123',libpq_version='foobaz',traceparent='00-{trace_id}-{span_id}-{trace_flags:02x}'*/",
            )
            self.assertEqual(
                span.attributes[DB_STATEMENT],
                "Select 1",
            )

    @mock.patch("opentelemetry.instrumentation.dbapi.wrap_connect")
    def test_sqlcommenter_disabled(self, event_mocked):
        cnx = psycopg.connect(database="test")
        PsycopgInstrumentor().instrument()
        query = "SELECT * FROM test"
        cursor = cnx.cursor()
        cursor.execute(query)
        kwargs = event_mocked.call_args[1]
        self.assertEqual(kwargs["enable_commenter"], False)

    def test_sqlcommenter_disabled_default_instrument_connection(self):
        cnx = psycopg.connect(database="test")
        cnx = PsycopgInstrumentor().instrument_connection(
            cnx,
        )
        query = "Select 1"
        cursor = cnx.cursor()
        cursor.execute(query)
        self.assertEqual(
            MockCursor.execute.call_args[0][0],
            "Select 1",
        )
        spans_list = self.memory_exporter.get_finished_spans()
        span = spans_list[0]
        self.assertEqual(
            span.attributes[DB_STATEMENT],
            "Select 1",
        )

    def test_sqlcommenter_disabled_explicit_instrument_connection(self):
        cnx = psycopg.connect(database="test")
        cnx = PsycopgInstrumentor().instrument_connection(
            cnx,
            enable_commenter=False,
        )
        query = "Select 1"
        cursor = cnx.cursor()
        cursor.execute(query)
        self.assertEqual(
            MockCursor.execute.call_args[0][0],
            "Select 1",
        )
        spans_list = self.memory_exporter.get_finished_spans()
        span = spans_list[0]
        self.assertEqual(
            span.attributes[DB_STATEMENT],
            "Select 1",
        )


class TestPostgresqlIntegrationAsync(
    PostgresqlIntegrationTestMixin, TestBase, IsolatedAsyncioTestCase
):
    async def test_wrap_async_connection_class_with_cursor(self):
        PsycopgInstrumentor().instrument()

        async def test_async_connection():
            acnx = await psycopg.AsyncConnection.connect("test")
            async with acnx as cnx:
                self.assertTrue(
                    issubclass(cnx.cursor_factory, MockAsyncCursor)
                )
                async with cnx.cursor() as cursor:
                    await cursor.execute("SELECT * FROM test")

        await test_async_connection()
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationScope(
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
                self.assertTrue(
                    issubclass(cnx.cursor_factory, MockAsyncCursor)
                )
                await cnx.execute("SELECT * FROM test")

        await test_async_connection()

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationScope(
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
        self.assertTrue(issubclass(cnx.cursor_factory, MockAsyncCursor))
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

    async def test_span_params_attribute(self):
        PsycopgInstrumentor().instrument(capture_parameters=True)
        cnx = await psycopg.AsyncConnection.connect("test")
        self.assertTrue(issubclass(cnx.cursor_factory, MockAsyncCursor))
        query = "SELECT * FROM mytable WHERE myparam1 = %s AND myparam2 = %s"
        params = ("test", 42)
        async with cnx.cursor() as cursor:
            await cursor.execute(query, params)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        self.assertEqual(spans_list[0].name, "SELECT")
        assert spans_list[0].attributes is not None
        self.assertEqual(spans_list[0].attributes["db.statement"], query)
        self.assertEqual(
            spans_list[0].attributes["db.statement.parameters"], str(params)
        )

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

    async def test_tracing_is_async(self):
        PsycopgInstrumentor().instrument()

        # before this async fix cursor.execute would take 14000 ns, delaying for
        # 100,000ns
        delay = 0.0001

        async def test_async_connection():
            acnx = await psycopg.AsyncConnection.connect("test")
            self.assertTrue(issubclass(acnx.cursor_factory, MockAsyncCursor))
            async with acnx as cnx:
                async with cnx.cursor() as cursor:
                    await cursor.execute("SELECT * FROM test", delay=delay)

        await test_async_connection()
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        # duration is nanoseconds
        duration = span.end_time - span.start_time
        self.assertGreater(duration, delay * 1e9)

        PsycopgInstrumentor().uninstrument()

    async def test_instrument_connection_uses_async_cursor_factory(self):
        query = b"SELECT * FROM test"

        acnx = await psycopg.AsyncConnection.connect("test")
        async with acnx:
            await acnx.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

        acnx = PsycopgInstrumentor().instrument_connection(acnx)

        self.assertTrue(acnx._is_instrumented_by_opentelemetry)

        # The new cursor_factory should be a subclass of MockAsyncCursor,
        # the async traced cursor factory returned by _new_cursor_async_factory
        self.assertTrue(issubclass(acnx.cursor_factory, MockAsyncCursor))

        cursor = acnx.cursor()
        await cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationScope(
            span, opentelemetry.instrumentation.psycopg
        )
