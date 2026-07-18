# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import contextlib
import sqlite3
from sqlite3 import dbapi2
from unittest import mock

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
        self._connection3 = SQLite3Instrumentor.instrument_connection(
            dbapi2.connect(":memory:")
        )
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
        SQLite3Instrumentor().instrument(
            tracer_provider=trace_api.NoOpTracerProvider()
        )
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

    def test_semconv_stable(self):
        """database,http opt-in emits only stable attributes."""
        with use_semconv_opt_in("database,http"):
            SQLite3Instrumentor().instrument(
                tracer_provider=self.tracer_provider
            )
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
            SQLite3Instrumentor().instrument(
                tracer_provider=self.tracer_provider
            )
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
