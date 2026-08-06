# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import asyncio
import contextlib
from unittest import mock

import asyncpg
import asyncpg.connection
import pytest
from asyncpg import Connection, Record, cursor
from asyncpg.prepared_stmt import PreparedStatement

try:
    # wrapt 2.0.0+
    from wrapt import BaseObjectProxy  # pylint: disable=no-name-in-module
except ImportError:
    from wrapt import ObjectProxy as BaseObjectProxy

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.asyncpg import (
    _PREPARED_STMT_METHODS,
    AsyncPGInstrumentor,
)
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_NAME,
    DB_STATEMENT,
    DB_SYSTEM,
    DB_USER,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_PEER_NAME,
    NET_PEER_PORT,
    NET_TRANSPORT,
    NetTransportValues,
)
from opentelemetry.semconv.attributes.db_attributes import (
    DB_NAMESPACE,
    DB_QUERY_TEXT,
    DB_SYSTEM_NAME,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.test.test_base import TestBase


@contextlib.contextmanager
def use_semconv_opt_in(sem_conv_mode):
    env_patch = mock.patch.dict(
        "os.environ",
        {OTEL_SEMCONV_STABILITY_OPT_IN: sem_conv_mode},
    )
    _OpenTelemetrySemanticConventionStability._initialized = False
    env_patch.start()
    try:
        yield
    finally:
        env_patch.stop()
        _OpenTelemetrySemanticConventionStability._initialized = False


class TestAsyncPGInstrumentation(TestBase):
    def tearDown(self):
        super().tearDown()
        AsyncPGInstrumentor().uninstrument()

    def test_duplicated_instrumentation_can_be_uninstrumented(self):
        AsyncPGInstrumentor().instrument()
        AsyncPGInstrumentor().instrument()
        AsyncPGInstrumentor().instrument()
        AsyncPGInstrumentor().uninstrument()
        for method_name in ["execute", "fetch"]:
            method = getattr(Connection, method_name, None)
            self.assertFalse(
                hasattr(method, "_opentelemetry_ext_asyncpg_applied")
            )

    def test_duplicated_instrumentation_works(self):
        first = AsyncPGInstrumentor()
        first.instrument()
        second = AsyncPGInstrumentor()
        second.instrument()
        self.assertIsNotNone(first._tracer)
        self.assertIsNotNone(second._tracer)

    def test_duplicated_uninstrumentation(self):
        AsyncPGInstrumentor().instrument()
        AsyncPGInstrumentor().uninstrument()
        AsyncPGInstrumentor().uninstrument()
        AsyncPGInstrumentor().uninstrument()
        for method_name in ["execute", "fetch"]:
            method = getattr(Connection, method_name, None)
            self.assertFalse(
                hasattr(method, "_opentelemetry_ext_asyncpg_applied")
            )

    def test_cursor_instrumentation(self):
        def assert_wrapped(assert_fnc):
            for cls, methods in [
                (cursor.Cursor, ("forward", "fetch", "fetchrow")),
                (cursor.CursorIterator, ("__anext__",)),
            ]:
                for method_name in methods:
                    method = getattr(cls, method_name, None)
                    assert_fnc(
                        isinstance(method, BaseObjectProxy),
                        f"{method} isinstance {type(method)}",
                    )

        assert_wrapped(self.assertFalse)
        AsyncPGInstrumentor().instrument()
        assert_wrapped(self.assertTrue)
        AsyncPGInstrumentor().uninstrument()
        assert_wrapped(self.assertFalse)

    def test_cursor_span_creation(self):
        """Test the cursor wrapper if it creates spans correctly."""

        # Mock out all interaction with postgres
        async def bind_mock(*args, **kwargs):
            return []

        async def exec_mock(*args, **kwargs):
            return [], None, True

        conn = mock.Mock()
        conn.is_closed = lambda: False

        conn._protocol = mock.Mock()
        conn._protocol.bind = bind_mock
        conn._protocol.execute = exec_mock
        conn._protocol.bind_execute = exec_mock
        conn._protocol.close_portal = bind_mock

        state = mock.Mock()
        state.closed = False

        apg = AsyncPGInstrumentor()
        apg.instrument(tracer_provider=self.tracer_provider)

        # init the cursor and fetch a single record
        crs = cursor.Cursor(conn, "SELECT * FROM test", state, [], Record)
        asyncio.run(crs._init(1))
        asyncio.run(crs.fetch(1))

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "CURSOR: SELECT")
        self.assertTrue(spans[0].status.is_ok)

        # Now test that the StopAsyncIteration of the cursor does not get recorded as an ERROR
        crs_iter = cursor.CursorIterator(
            conn, "SELECT * FROM test", state, [], Record, 1, 1
        )

        with pytest.raises(StopAsyncIteration):
            asyncio.run(anext(crs_iter))

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        self.assertEqual([span.status.is_ok for span in spans], [True, True])

    def test_no_op_tracer_provider(self):
        AsyncPGInstrumentor().uninstrument()
        AsyncPGInstrumentor().instrument(
            tracer_provider=trace_api.NoOpTracerProvider()
        )

        # Mock out all interaction with postgres
        async def bind_mock(*args, **kwargs):
            return []

        async def exec_mock(*args, **kwargs):
            return [], None, True

        conn = mock.Mock()
        conn.is_closed = lambda: False

        conn._protocol = mock.Mock()
        conn._protocol.bind = bind_mock
        conn._protocol.execute = exec_mock
        conn._protocol.bind_execute = exec_mock
        conn._protocol.close_portal = bind_mock

        state = mock.Mock()
        state.closed = False

        # init the cursor and fetch a single record
        crs = cursor.Cursor(conn, "SELECT * FROM test", state, [], Record)
        asyncio.run(crs._init(1))
        asyncio.run(crs.fetch(1))

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_prepared_statement_instrumentation(self):
        methods = [
            m for m in _PREPARED_STMT_METHODS if hasattr(PreparedStatement, m)
        ]

        for method_name in methods:
            with self.subTest(method=method_name, phase="before"):
                self.assertFalse(
                    isinstance(
                        getattr(PreparedStatement, method_name),
                        BaseObjectProxy,
                    )
                )

        AsyncPGInstrumentor().instrument()

        for method_name in methods:
            with self.subTest(method=method_name, phase="instrumented"):
                self.assertTrue(
                    isinstance(
                        getattr(PreparedStatement, method_name),
                        BaseObjectProxy,
                    )
                )

        AsyncPGInstrumentor().uninstrument()

        for method_name in methods:
            with self.subTest(method=method_name, phase="uninstrumented"):
                self.assertFalse(
                    isinstance(
                        getattr(PreparedStatement, method_name),
                        BaseObjectProxy,
                    )
                )

    @staticmethod
    def _make_prepared_stmt_conn():
        async def bind_execute_mock(*args, **kwargs):
            return [], b"SELECT 1", True

        async def bind_execute_many_mock(*args, **kwargs):
            return None

        conn = mock.Mock()
        conn._pool_release_ctr = 0
        conn.is_closed = lambda: False
        conn._protocol = mock.Mock()
        conn._protocol.bind_execute = bind_execute_mock
        conn._protocol.bind_execute_many = bind_execute_many_mock

        state = mock.Mock()
        state.closed = False
        return conn, state

    def test_prepared_statement_span(self):
        # Per-method: (query, call_args, expected_span_name)
        method_cases = {
            "fetch": ("SELECT * FROM users", (), "SELECT"),
            "fetchval": ("SELECT id FROM users WHERE id=$1", (1,), "SELECT"),
            "fetchrow": ("SELECT * FROM t WHERE v=$1", ("x",), "SELECT"),
            "executemany": (
                "INSERT INTO t (v) VALUES ($1)",
                ([("a",), ("b",)],),
                "INSERT",
            ),
            "fetchmany": ("SELECT * FROM t", ([],), "SELECT"),
        }

        for method_name in _PREPARED_STMT_METHODS:
            if not hasattr(PreparedStatement, method_name):
                continue
            query, call_args, expected_name = method_cases[method_name]
            with self.subTest(method=method_name):
                self.memory_exporter.clear()
                conn, state = self._make_prepared_stmt_conn()
                apg = AsyncPGInstrumentor()
                apg.instrument(tracer_provider=self.tracer_provider)

                stmt = PreparedStatement(conn, query, state)
                asyncio.run(getattr(stmt, method_name)(*call_args))

                spans = self.memory_exporter.get_finished_spans()
                self.assertEqual(len(spans), 1)
                self.assertEqual(spans[0].name, expected_name)
                self.assertTrue(spans[0].status.is_ok)
                self.assertEqual(
                    spans[0].attributes.get("db.statement"), query
                )
                self.assertEqual(
                    spans[0].attributes.get("db.system"), "postgresql"
                )

                apg.uninstrument()

    def test_prepared_statement_error_span(self):
        async def bind_execute_error(*args, **kwargs):
            raise RuntimeError("db error")

        conn = mock.Mock()
        conn._pool_release_ctr = 0
        conn.is_closed = lambda: False
        conn._protocol = mock.Mock()
        conn._protocol.bind_execute = bind_execute_error

        state = mock.Mock()
        state.closed = False

        apg = AsyncPGInstrumentor()
        apg.instrument(tracer_provider=self.tracer_provider)

        stmt = PreparedStatement(conn, "SELECT 1", state)
        with self.assertRaises(RuntimeError):
            asyncio.run(stmt.fetch())

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertFalse(spans[0].status.is_ok)


class TestAsyncPGSemconvMigration(TestBase):
    def setUp(self):
        super().setUp()
        _OpenTelemetrySemanticConventionStability._initialized = False

    def tearDown(self):
        super().tearDown()
        AsyncPGInstrumentor().uninstrument()
        _OpenTelemetrySemanticConventionStability._initialized = False

    @staticmethod
    def _make_execute_conn(addr=("testhost", 5432)):
        async def query_mock(*args, **kwargs):
            return b"SELECT 1", [], True

        async def execute_mock(*args, **kwargs):
            return [], b"SELECT 1", True

        conn = mock.Mock()
        conn.is_closed = lambda: False
        conn._pool_release_ctr = 0
        conn._query_loggers = []
        conn._execute = execute_mock
        conn._protocol = mock.Mock()
        conn._protocol.query = query_mock
        conn._addr = addr
        params = mock.Mock()
        params.database = "testdb"
        params.user = "testuser"
        conn._params = params
        return conn

    def _run_execute(self, conn, query="SELECT 1"):
        apg = AsyncPGInstrumentor()
        apg.instrument(tracer_provider=self.tracer_provider)

        async def do_execute():
            # Use __get__ to bind conn as the instance so wrapt correctly
            # receives instance=conn instead of instance=None.
            execute = asyncpg.connection.Connection.execute.__get__(  # pylint: disable=no-value-for-parameter
                conn, asyncpg.connection.Connection
            )
            await execute(query)

        asyncio.run(do_execute())
        return self.memory_exporter.get_finished_spans()

    def test_schema_url(self):
        apg = AsyncPGInstrumentor()
        apg.instrument(tracer_provider=self.tracer_provider)
        self.assertEqual(
            apg._tracer._instrumentation_scope.schema_url,
            "https://opentelemetry.io/schemas/1.11.0",
        )

    def test_schema_url_new_semconv(self):
        with use_semconv_opt_in("database"):
            apg = AsyncPGInstrumentor()
            apg.instrument(tracer_provider=self.tracer_provider)
            self.assertEqual(
                apg._tracer._instrumentation_scope.schema_url,
                "https://opentelemetry.io/schemas/1.25.0",
            )

    def test_span(self):
        conn = self._make_execute_conn()
        spans = self._run_execute(conn)

        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.attributes[DB_SYSTEM], "postgresql")
        self.assertEqual(span.attributes[DB_NAME], "testdb")
        self.assertEqual(span.attributes[DB_USER], "testuser")
        self.assertEqual(span.attributes[NET_PEER_NAME], "testhost")
        self.assertEqual(span.attributes[NET_PEER_PORT], 5432)
        self.assertEqual(span.attributes[DB_STATEMENT], "SELECT 1")

    def test_span_database_only_new_semconv(self):
        with use_semconv_opt_in("database"):
            conn = self._make_execute_conn()
            spans = self._run_execute(conn)

        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.attributes[DB_SYSTEM_NAME], "postgresql")
        self.assertEqual(span.attributes[DB_NAMESPACE], "testdb")
        self.assertEqual(span.attributes[DB_QUERY_TEXT], "SELECT 1")
        self.assertEqual(span.attributes[SERVER_ADDRESS], "testhost")
        self.assertEqual(span.attributes[SERVER_PORT], 5432)
        self.assertNotIn(NET_PEER_NAME, span.attributes)
        self.assertNotIn(NET_PEER_PORT, span.attributes)

    def test_span_both_semconv(self):
        with use_semconv_opt_in("database/dup,http/dup"):
            conn = self._make_execute_conn()
            spans = self._run_execute(conn)

        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.attributes[DB_SYSTEM], "postgresql")
        self.assertEqual(span.attributes[DB_NAME], "testdb")
        self.assertEqual(span.attributes[DB_STATEMENT], "SELECT 1")
        self.assertEqual(span.attributes[DB_USER], "testuser")
        self.assertEqual(span.attributes[NET_PEER_NAME], "testhost")
        self.assertEqual(span.attributes[NET_PEER_PORT], 5432)
        self.assertEqual(span.attributes[DB_SYSTEM_NAME], "postgresql")
        self.assertEqual(span.attributes[DB_NAMESPACE], "testdb")
        self.assertEqual(span.attributes[DB_QUERY_TEXT], "SELECT 1")
        self.assertEqual(span.attributes[SERVER_ADDRESS], "testhost")
        self.assertEqual(span.attributes[SERVER_PORT], 5432)

    def test_span_new_semconv(self):
        with use_semconv_opt_in("database,http"):
            conn = self._make_execute_conn()
            spans = self._run_execute(conn)

        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.attributes[DB_SYSTEM_NAME], "postgresql")
        self.assertEqual(span.attributes[DB_NAMESPACE], "testdb")
        self.assertEqual(span.attributes[DB_QUERY_TEXT], "SELECT 1")
        self.assertEqual(span.attributes[SERVER_ADDRESS], "testhost")
        self.assertEqual(span.attributes[SERVER_PORT], 5432)

    def test_span_unix_socket_default_semconv(self):
        conn = self._make_execute_conn(
            addr="/var/run/postgresql/.s.PGSQL.5432"
        )
        spans = self._run_execute(conn)

        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(
            span.attributes[NET_PEER_NAME],
            "/var/run/postgresql/.s.PGSQL.5432",
        )
        self.assertEqual(
            span.attributes[NET_TRANSPORT], NetTransportValues.OTHER.value
        )
        self.assertNotIn(NET_PEER_PORT, span.attributes)
        self.assertNotIn(SERVER_ADDRESS, span.attributes)

    def _run_execute_capture(self, query, *query_args):
        apg = AsyncPGInstrumentor(capture_parameters=True)
        apg.instrument(tracer_provider=self.tracer_provider)
        conn = self._make_execute_conn()

        async def do_execute():
            execute = asyncpg.connection.Connection.execute.__get__(  # pylint: disable=no-value-for-parameter
                conn, asyncpg.connection.Connection
            )
            await execute(query, *query_args)

        asyncio.run(do_execute())
        return self.memory_exporter.get_finished_spans()

    def test_span_capture_parameters(self):
        spans = self._run_execute_capture("SELECT $1", "hello")
        self.assertEqual(len(spans), 1)
        self.assertIn("db.statement.parameters", spans[0].attributes)
        self.assertIn("hello", spans[0].attributes["db.statement.parameters"])

    def test_capture_parameters_default_semconv(self):
        spans = self._run_execute_capture("SELECT $1", "hello")
        self.assertEqual(len(spans), 1)
        attributes = spans[0].attributes
        self.assertIn("db.statement.parameters", attributes)
        self.assertIsInstance(attributes["db.statement.parameters"], str)
        self.assertNotIn("db.query.parameter.0", attributes)

    def test_capture_parameters_new_semconv(self):
        with use_semconv_opt_in("database"):
            spans = self._run_execute_capture("SELECT $1", "hello")
        self.assertEqual(len(spans), 1)
        attributes = spans[0].attributes
        self.assertEqual(attributes["db.query.parameter.0"], "hello")
        self.assertIsInstance(attributes["db.query.parameter.0"], str)
        self.assertNotIn("db.statement.parameters", attributes)

    def test_capture_parameters_both_semconv(self):
        with use_semconv_opt_in("database/dup"):
            spans = self._run_execute_capture("SELECT $1", "hello")
        self.assertEqual(len(spans), 1)
        attributes = spans[0].attributes
        self.assertIn("db.statement.parameters", attributes)
        self.assertIsInstance(attributes["db.statement.parameters"], str)
        self.assertEqual(attributes["db.query.parameter.0"], "hello")
        self.assertIsInstance(attributes["db.query.parameter.0"], str)

    def test_capture_parameters_batch_no_query_parameter_new_semconv(self):
        conn, state = self._make_prepared_stmt_conn()
        apg = AsyncPGInstrumentor(capture_parameters=True)
        with use_semconv_opt_in("database"):
            apg.instrument(tracer_provider=self.tracer_provider)
            stmt = PreparedStatement(
                conn, "INSERT INTO t (v) VALUES ($1)", state
            )
            asyncio.run(stmt.executemany([("a",), ("b",)]))

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        attributes = spans[0].attributes
        self.assertFalse(
            any(k.startswith("db.query.parameter.") for k in attributes)
        )

    @staticmethod
    def _make_prepared_stmt_conn():
        async def bind_execute_mock(*args, **kwargs):
            return [], b"SELECT 1", True

        async def bind_execute_many_mock(*args, **kwargs):
            return None

        conn = mock.Mock()
        conn._pool_release_ctr = 0
        conn.is_closed = lambda: False
        conn._protocol = mock.Mock()
        conn._protocol.bind_execute = bind_execute_mock
        conn._protocol.bind_execute_many = bind_execute_many_mock
        params = mock.Mock()
        params.database = "testdb"
        params.user = "testuser"
        conn._params = params

        state = mock.Mock()
        state.closed = False
        return conn, state

    def _run_execute_error(self, semconv_mode):
        async def error_mock(*args, **kwargs):
            raise RuntimeError("db error")

        conn = mock.Mock()
        conn.is_closed = lambda: False
        conn._pool_release_ctr = 0
        conn._query_loggers = []
        conn._execute = error_mock
        conn._protocol = mock.Mock()
        conn._protocol.query = error_mock
        conn._addr = ("testhost", 5432)
        params = mock.Mock()
        params.database = "testdb"
        params.user = "testuser"
        conn._params = params

        with use_semconv_opt_in(semconv_mode):
            apg = AsyncPGInstrumentor()
            apg.instrument(tracer_provider=self.tracer_provider)

            async def do_execute():
                execute = asyncpg.connection.Connection.execute.__get__(  # pylint: disable=no-value-for-parameter
                    conn, asyncpg.connection.Connection
                )
                await execute("SELECT 1")

            with self.assertRaises(RuntimeError):
                asyncio.run(do_execute())

        return self.memory_exporter.get_finished_spans()

    def test_error_type_not_set_on_default_semconv(self):
        spans = self._run_execute_error("")
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertFalse(span.status.is_ok)
        self.assertNotIn(ERROR_TYPE, span.attributes)

    def test_error_type_set_on_new_db_semconv(self):
        spans = self._run_execute_error("database")
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertFalse(span.status.is_ok)
        self.assertEqual(span.attributes[ERROR_TYPE], "RuntimeError")

    def test_error_type_set_on_both_semconv(self):
        spans = self._run_execute_error("database/dup,http/dup")
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertFalse(span.status.is_ok)
        self.assertEqual(span.attributes[ERROR_TYPE], "RuntimeError")
