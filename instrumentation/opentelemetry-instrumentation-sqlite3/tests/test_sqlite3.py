# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import contextlib
import sqlite3
from sqlite3 import dbapi2
from unittest import mock

from wrapt import ObjectProxy

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_NAME,
    DB_STATEMENT,
    DB_SYSTEM,
    DB_USER,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_PEER_NAME,
    NET_PEER_PORT,
)
from opentelemetry.semconv.attributes.db_attributes import (
    DB_NAMESPACE,
    DB_QUERY_TEXT,
    DB_SYSTEM_NAME,
)
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


class TestSQLite3(TestBase):
    def setUp(self):
        super().setUp()
        SQLite3Instrumentor().instrument(tracer_provider=self.tracer_provider)
        self._tracer = self.tracer_provider.get_tracer(__name__)
        self._connection = sqlite3.connect(":memory:")
        self._cursor = self._connection.cursor()
        self._connection2 = dbapi2.connect(":memory:")
        self._cursor2 = self._connection2.cursor()
        self._connection3 = SQLite3Instrumentor.instrument_connection(dbapi2.connect(":memory:"))
        self._cursor3 = self._connection3.cursor()

    def tearDown(self):
        super().tearDown()
        if self._cursor:
            self._cursor.close()
        if self._connection:
            self._connection.close()
        if self._cursor2:
            self._cursor2.close()
        if self._connection2:
            self._connection2.close()
        if self._cursor3:
            self._cursor3.close()
        if self._connection3:
            self._connection3.close()
        SQLite3Instrumentor().uninstrument()

    def validate_spans(self, span_name):
        spans = self.memory_exporter.get_finished_spans()
        self.memory_exporter.clear()
        self.assertEqual(len(spans), 2)
        root_span = None
        child_span = None
        for span in spans:
            if span.name == "rootSpan":
                root_span = span
            else:
                child_span = span
            self.assertIsInstance(span.start_time, int)
            self.assertIsInstance(span.end_time, int)
        self.assertIsNotNone(root_span)
        self.assertIsNotNone(child_span)
        self.assertEqual(root_span.name, "rootSpan")
        self.assertEqual(child_span.name, span_name)
        self.assertIsNotNone(child_span.parent)
        self.assertIs(child_span.parent, root_span.get_span_context())
        self.assertIs(child_span.kind, trace_api.SpanKind.CLIENT)

    def _create_tables(self):
        stmt = "CREATE TABLE IF NOT EXISTS test (id integer)"
        self._cursor.execute(stmt)
        self._cursor2.execute(stmt)
        self._cursor3.execute(stmt)
        self.memory_exporter.clear()

    def test_execute(self):
        """Should create a child span for execute method"""
        stmt = "CREATE TABLE IF NOT EXISTS test (id integer)"
        with self._tracer.start_as_current_span("rootSpan"):
            self._cursor.execute(stmt)
        self.validate_spans("CREATE")

        with self._tracer.start_as_current_span("rootSpan"):
            self._cursor2.execute(stmt)
        self.validate_spans("CREATE")

        with self._tracer.start_as_current_span("rootSpan"):
            self._cursor3.execute(stmt)
        self.validate_spans("CREATE")

    def test_executemany(self):
        """Should create a child span for executemany"""
        self._create_tables()

        # real spans for executemany
        stmt = "INSERT INTO test (id) VALUES (?)"
        data = [("1",), ("2",), ("3",)]
        with self._tracer.start_as_current_span("rootSpan"):
            self._cursor.executemany(stmt, data)
        self.validate_spans("INSERT")

        with self._tracer.start_as_current_span("rootSpan"):
            self._cursor2.executemany(stmt, data)
        self.validate_spans("INSERT")

        with self._tracer.start_as_current_span("rootSpan"):
            self._cursor3.executemany(stmt, data)
        self.validate_spans("INSERT")

    def test_callproc(self):
        """Should create a child span for callproc"""
        with (
            self._tracer.start_as_current_span("rootSpan"),
            self.assertRaises(Exception),
        ):
            self._cursor.callproc("test", ())
            self.validate_spans("test")


class TestSQLite3Integration(TestBase):
    def tearDown(self):
        super().tearDown()
        SQLite3Instrumentor().uninstrument()

    def _connect(self):
        """Create an in-memory connection with cleanup registered."""
        cnx = sqlite3.connect(":memory:")
        self.addCleanup(cnx.close)
        return cnx

    def test_uninstrument(self):
        """Should stop generating spans after uninstrument."""
        SQLite3Instrumentor().instrument(tracer_provider=self.tracer_provider)
        cnx = self._connect()
        cursor = cnx.cursor()
        self.addCleanup(cursor.close)
        cursor.execute("CREATE TABLE IF NOT EXISTS test (id integer)")

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

        SQLite3Instrumentor().uninstrument()
        self.memory_exporter.clear()

        cnx2 = self._connect()
        cursor2 = cnx2.cursor()
        self.addCleanup(cursor2.close)
        cursor2.execute("CREATE TABLE IF NOT EXISTS test (id integer)")

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

    def test_uninstrument_connection_with_instrument(self):
        """Should stop generating spans for uninstrumented connection."""
        SQLite3Instrumentor().instrument(tracer_provider=self.tracer_provider)
        cnx = self._connect()
        query = "CREATE TABLE IF NOT EXISTS test (id integer)"
        cursor = cnx.cursor()
        self.addCleanup(cursor.close)
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

        self.memory_exporter.clear()
        cnx = SQLite3Instrumentor.uninstrument_connection(cnx)
        cursor = cnx.cursor()
        self.addCleanup(cursor.close)
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

    def test_no_op_tracer_provider(self):
        """Should produce no spans with NoOpTracerProvider."""
        SQLite3Instrumentor().instrument(tracer_provider=trace_api.NoOpTracerProvider())
        cnx = self._connect()
        cursor = cnx.cursor()
        self.addCleanup(cursor.close)
        cursor.execute("CREATE TABLE IF NOT EXISTS test (id integer)")

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

    def test_suppress_instrumentation(self):
        """Should produce no spans when suppressed."""
        SQLite3Instrumentor().instrument(tracer_provider=self.tracer_provider)
        cnx = self._connect()

        with suppress_instrumentation():
            cursor = cnx.cursor()
            self.addCleanup(cursor.close)
            cursor.execute("CREATE TABLE IF NOT EXISTS test (id integer)")

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

    def test_span_failed(self):
        """Should set error status on span when query fails."""
        SQLite3Instrumentor().instrument(tracer_provider=self.tracer_provider)
        cnx = self._connect()
        cursor = cnx.cursor()
        self.addCleanup(cursor.close)

        with self.assertRaises(sqlite3.OperationalError):
            cursor.execute("SELECT * FROM nonexistent_table")

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(
            span.attributes[DB_STATEMENT],
            "SELECT * FROM nonexistent_table",
        )
        self.assertIs(span.status.status_code, trace_api.StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            "OperationalError: no such table: nonexistent_table",
        )

    def test_semconv_default(self):
        """No opt-in emits only legacy attributes."""
        with use_semconv_opt_in(""):
            SQLite3Instrumentor().instrument(tracer_provider=self.tracer_provider)
            cnx = self._connect()
            cursor = cnx.cursor()
            self.addCleanup(cursor.close)
            cursor.execute("SELECT 1")

            spans_list = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans_list), 1)
            span = spans_list[0]

            self.assertEqual(span.attributes[DB_SYSTEM], "sqlite")
            self.assertEqual(span.attributes[DB_STATEMENT], "SELECT 1")
            self.assertNotIn(DB_SYSTEM_NAME, span.attributes)
            self.assertNotIn(DB_QUERY_TEXT, span.attributes)
            # sqlite3 does not capture connection attributes, so neither
            # legacy nor stable database/peer attributes are emitted.
            self.assertNotIn(DB_NAME, span.attributes)
            self.assertNotIn(DB_NAMESPACE, span.attributes)
            self.assertNotIn(DB_USER, span.attributes)
            self.assertNotIn(NET_PEER_NAME, span.attributes)
            self.assertNotIn(NET_PEER_PORT, span.attributes)
            self.assertNotIn(SERVER_ADDRESS, span.attributes)
            self.assertNotIn(SERVER_PORT, span.attributes)

    def test_semconv_stable(self):
        """database,http opt-in emits only stable attributes."""
        with use_semconv_opt_in("database,http"):
            SQLite3Instrumentor().instrument(tracer_provider=self.tracer_provider)
            cnx = self._connect()
            cursor = cnx.cursor()
            self.addCleanup(cursor.close)
            cursor.execute("SELECT 1")

            spans_list = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans_list), 1)
            span = spans_list[0]

            self.assertEqual(span.attributes[DB_SYSTEM_NAME], "sqlite")
            self.assertEqual(span.attributes[DB_QUERY_TEXT], "SELECT 1")
            self.assertNotIn(DB_SYSTEM, span.attributes)
            self.assertNotIn(DB_STATEMENT, span.attributes)
            # sqlite3 does not capture connection attributes, so neither
            # legacy nor stable database/peer attributes are emitted.
            self.assertNotIn(DB_NAME, span.attributes)
            self.assertNotIn(DB_NAMESPACE, span.attributes)
            self.assertNotIn(DB_USER, span.attributes)
            self.assertNotIn(NET_PEER_NAME, span.attributes)
            self.assertNotIn(NET_PEER_PORT, span.attributes)
            self.assertNotIn(SERVER_ADDRESS, span.attributes)
            self.assertNotIn(SERVER_PORT, span.attributes)

    def test_semconv_dup(self):
        """database/dup,http/dup opt-in emits both legacy and stable attributes."""
        with use_semconv_opt_in("database/dup,http/dup"):
            SQLite3Instrumentor().instrument(tracer_provider=self.tracer_provider)
            cnx = self._connect()
            cursor = cnx.cursor()
            self.addCleanup(cursor.close)
            cursor.execute("SELECT 1")

            spans_list = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans_list), 1)
            span = spans_list[0]

            self.assertEqual(span.attributes[DB_SYSTEM], "sqlite")
            self.assertEqual(span.attributes[DB_SYSTEM_NAME], "sqlite")
            self.assertEqual(span.attributes[DB_STATEMENT], "SELECT 1")
            self.assertEqual(span.attributes[DB_QUERY_TEXT], "SELECT 1")


class TestSQLite3ConnectionShortcuts(TestBase):
    def tearDown(self) -> None:
        SQLite3Instrumentor().uninstrument()
        super().tearDown()

    def _connect(self, connection_mode: str) -> sqlite3.Connection:
        SQLite3Instrumentor().uninstrument()
        if connection_mode == "manual":
            connection = sqlite3.connect(":memory:")
            connection = SQLite3Instrumentor.instrument_connection(connection, tracer_provider=self.tracer_provider)
        else:
            SQLite3Instrumentor().instrument(tracer_provider=self.tracer_provider)
            module = sqlite3 if connection_mode == "sqlite3" else dbapi2
            connection = module.connect(":memory:")
        self.addCleanup(connection.close)
        self.memory_exporter.clear()
        return connection

    def test_connection_execute(self) -> None:
        for mode in ("sqlite3", "dbapi2", "manual"):
            with self.subTest(connection_mode=mode):
                connection = self._connect(mode)
                with self.tracer_provider.get_tracer(__name__).start_as_current_span("parent") as parent:
                    cursor = connection.execute("SELECT ?", (7,))
                self.addCleanup(cursor.close)
                self.assertEqual(cursor.fetchall(), [(7,)])
                spans = self.memory_exporter.get_finished_spans()
                self.assertEqual(len(spans), 2)
                span = spans[0]
                self.assertEqual(span.name, "SELECT")
                self.assertEqual(span.attributes[DB_STATEMENT], "SELECT ?")
                self.assertIsInstance(span.attributes[DB_STATEMENT], str)
                self.assertEqual(span.parent, parent.get_span_context())
                self.assertIs(span.kind, trace_api.SpanKind.CLIENT)
                cursor.execute("SELECT 8")
                self.assertEqual(cursor.fetchone(), (8,))
                self.assertEqual(len(self.memory_exporter.get_finished_spans()), 3)

    def test_connection_executemany(self) -> None:
        for mode in ("sqlite3", "dbapi2", "manual"):
            with self.subTest(connection_mode=mode):
                connection = self._connect(mode)
                cursor = connection.cursor()
                self.addCleanup(cursor.close)
                cursor.execute("CREATE TABLE test (id integer)")
                self.memory_exporter.clear()
                result = connection.executemany("INSERT INTO test VALUES (?)", [(1,), (2,)])
                self.addCleanup(result.close)
                self.assertEqual(result.rowcount, 2)
                spans = self.memory_exporter.get_finished_spans()
                self.assertEqual(len(spans), 1)
                self.assertEqual(spans[0].name, "INSERT")
                self.assertEqual(spans[0].attributes[DB_STATEMENT], "INSERT INTO test VALUES (?)")
                result.execute("SELECT id FROM test ORDER BY id")
                self.assertEqual(result.fetchall(), [(1,), (2,)])
                self.assertEqual(len(self.memory_exporter.get_finished_spans()), 2)

    def test_connection_executescript(self) -> None:
        for mode in ("sqlite3", "dbapi2", "manual"):
            with self.subTest(connection_mode=mode):
                connection = self._connect(mode)
                script = "CREATE TABLE test (id integer); INSERT INTO test VALUES (1);"
                cursor = connection.executescript(script)
                self.addCleanup(cursor.close)
                spans = self.memory_exporter.get_finished_spans()
                self.assertEqual(len(spans), 1)
                self.assertEqual(spans[0].attributes[DB_STATEMENT], script)
                cursor.execute("SELECT id FROM test")
                self.assertEqual(cursor.fetchone(), (1,))
                self.assertEqual(len(self.memory_exporter.get_finished_spans()), 2)

    def test_connection_shortcut_errors(self) -> None:
        connection = self._connect("sqlite3")
        for method, args in (
            ("execute", ("SELECT * FROM nonexistent_table",)),
            ("executemany", ("INSERT INTO nonexistent_table VALUES (?)", [(1,)])),
            ("executescript", ("SELECT * FROM nonexistent_table;",)),
        ):
            with self.subTest(method=method):
                self.memory_exporter.clear()
                with self.assertRaisesRegex(sqlite3.OperationalError, "no such table: nonexistent_table"):
                    getattr(connection, method)(*args)
                spans = self.memory_exporter.get_finished_spans()
                self.assertEqual(len(spans), 1)
                self.assertIs(spans[0].status.status_code, trace_api.StatusCode.ERROR)

    def test_connection_shortcuts_suppressed(self) -> None:
        connection = self._connect("sqlite3")
        setup_cursor = connection.cursor()
        self.addCleanup(setup_cursor.close)
        setup_cursor.execute("CREATE TABLE test (id integer)")
        self.memory_exporter.clear()
        with suppress_instrumentation():
            for method, args in (
                ("execute", ("INSERT INTO test VALUES (?)", (1,))),
                ("executemany", ("INSERT INTO test VALUES (?)", [(2,)])),
                ("executescript", ("INSERT INTO test VALUES (3);",)),
            ):
                cursor = getattr(connection, method)(*args)
                self.addCleanup(cursor.close)
        self.assertEqual(self.memory_exporter.get_finished_spans(), ())
        setup_cursor.execute("SELECT id FROM test ORDER BY id")
        self.assertEqual(setup_cursor.fetchall(), [(1,), (2,), (3,)])

    def test_connection_execute_uninstrumented(self) -> None:
        connection = self._connect("manual")
        connection = SQLite3Instrumentor.uninstrument_connection(connection)
        cursor = connection.execute("SELECT 1")
        self.addCleanup(cursor.close)
        self.assertEqual(cursor.fetchone(), (1,))
        self.assertEqual(self.memory_exporter.get_finished_spans(), ())

    def test_connection_execute_semconv(self) -> None:
        for mode, query_attribute in (
            ("database", DB_QUERY_TEXT),
            ("database/dup", DB_QUERY_TEXT),
        ):
            with self.subTest(semconv_mode=mode), use_semconv_opt_in(mode):
                connection = self._connect("sqlite3")
                cursor = connection.execute("SELECT 1")
                self.addCleanup(cursor.close)
                spans = self.memory_exporter.get_finished_spans()
                self.assertEqual(len(spans), 1)
                self.assertEqual(spans[0].attributes[query_attribute], "SELECT 1")
                self.assertIsInstance(spans[0].attributes[query_attribute], str)
                self.assertEqual(spans[0].attributes[DB_SYSTEM_NAME], "sqlite")
                if mode == "database":
                    self.assertNotIn(DB_STATEMENT, spans[0].attributes)
                else:
                    self.assertEqual(spans[0].attributes[DB_STATEMENT], "SELECT 1")

    def test_connection_execute_no_op_tracer_provider(self) -> None:
        SQLite3Instrumentor().instrument(tracer_provider=trace_api.NoOpTracerProvider())
        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        cursor = connection.execute("SELECT 1")
        self.addCleanup(cursor.close)
        self.assertEqual(cursor.fetchone(), (1,))
        self.assertEqual(self.memory_exporter.get_finished_spans(), ())

    def test_connection_factory_preserves_shortcuts(self) -> None:
        class CustomConnection(sqlite3.Connection):
            def execute(self, sql: str, parameters: tuple[int, ...] = ()) -> sqlite3.Cursor:
                self.execute_calls = getattr(self, "execute_calls", 0) + 1
                return super().execute(sql, parameters)

        SQLite3Instrumentor().instrument(tracer_provider=self.tracer_provider)
        connection = sqlite3.connect(":memory:", factory=CustomConnection)
        self.addCleanup(connection.close)
        cursor = connection.execute("SELECT ?", (1,))
        self.addCleanup(cursor.close)
        self.assertEqual(cursor.fetchone(), (1,))
        self.assertEqual(connection.execute_calls, 1)
        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 1)

    def test_instrument_connection_idempotent(self) -> None:
        connection = self._connect("manual")
        self.assertIs(SQLite3Instrumentor.instrument_connection(connection), connection)
        cursor = connection.execute("SELECT 1")
        self.addCleanup(cursor.close)
        self.assertEqual(len(self.memory_exporter.get_finished_spans()), 1)

    def test_instrument_connection_preserves_existing_proxy(self) -> None:
        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        proxy = ObjectProxy(connection)
        self.assertIs(
            SQLite3Instrumentor.instrument_connection(proxy, tracer_provider=self.tracer_provider),
            proxy,
        )

    def test_connection_shortcuts_without_operation(self) -> None:
        connection = SQLite3Instrumentor.instrument_connection(
            sqlite3.connect(":memory:"),
            tracer_provider=trace_api.NoOpTracerProvider(),
        )
        self.addCleanup(connection.close)
        for query in ("", " ", "\n\t", "/* comment only */"):
            for method in ("execute", "executemany", "executescript"):
                with self.subTest(query=query, method=method):
                    args = (query, [()]) if method == "executemany" else (query,)
                    try:
                        native_cursor = getattr(connection.__wrapped__, method)(*args)
                    except sqlite3.Error as native_error:
                        with self.assertRaises(type(native_error)) as traced_error:
                            getattr(connection, method)(*args)
                        self.assertEqual(str(traced_error.exception), str(native_error))
                    else:
                        native_cursor.close()
                        cursor = getattr(connection, method)(*args)
                        self.addCleanup(cursor.close)
                        self.assertIsInstance(cursor, sqlite3.Cursor)
        self.assertEqual(self.memory_exporter.get_finished_spans(), ())

    def test_returned_cursor_without_operation(self) -> None:
        connection = SQLite3Instrumentor.instrument_connection(
            sqlite3.connect(":memory:"),
            tracer_provider=trace_api.NoOpTracerProvider(),
        )
        self.addCleanup(connection.close)
        cursor = connection.execute("SELECT 1")
        self.addCleanup(cursor.close)
        for query in ("", " ", "\n\t", "/* comment only */"):
            for method in ("execute", "executemany"):
                with self.subTest(query=query, method=method):
                    args = (query, [()]) if method == "executemany" else (query,)
                    try:
                        native_result = getattr(cursor.__wrapped__, method)(*args)
                    except sqlite3.Error as native_error:
                        with self.assertRaises(type(native_error)) as traced_error:
                            getattr(cursor, method)(*args)
                        self.assertEqual(str(traced_error.exception), str(native_error))
                    else:
                        self.assertIs(native_result, cursor.__wrapped__)
                        self.assertIsInstance(getattr(cursor, method)(*args), sqlite3.Cursor)
        self.assertEqual(self.memory_exporter.get_finished_spans(), ())
