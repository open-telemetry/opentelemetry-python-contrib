# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import contextlib
import os
from unittest import mock

import psycopg2
from psycopg2 import sql

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_NAME,
    DB_QUERY_PARAMETER_TEMPLATE,
    DB_STATEMENT,
    DB_SYSTEM,
    DB_USER,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_PEER_NAME,
    NET_PEER_PORT,
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


POSTGRES_HOST = os.getenv("POSTGRESQL_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRESQL_PORT", "5432"))
POSTGRES_DB_NAME = os.getenv("POSTGRESQL_DB_NAME", "opentelemetry-tests")
POSTGRES_PASSWORD = os.getenv("POSTGRESQL_PASSWORD", "testpassword")
POSTGRES_USER = os.getenv("POSTGRESQL_USER", "testuser")


class TestFunctionalPsycopg(TestBase):
    def setUp(self):
        super().setUp()
        self._tracer = self.tracer_provider.get_tracer(__name__)
        Psycopg2Instrumentor().instrument(tracer_provider=self.tracer_provider)
        self._connection = psycopg2.connect(
            dbname=POSTGRES_DB_NAME,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
        )
        self._connection.set_session(autocommit=True)
        self._cursor = self._connection.cursor()

    def tearDown(self):
        self._cursor.close()
        self._connection.close()
        Psycopg2Instrumentor().uninstrument()
        super().tearDown()

    def validate_spans(self, span_name):
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
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
        self.assertEqual(child_span.attributes[DB_SYSTEM], "postgresql")
        self.assertEqual(child_span.attributes[DB_NAME], POSTGRES_DB_NAME)
        self.assertEqual(child_span.attributes[DB_USER], POSTGRES_USER)
        self.assertEqual(child_span.attributes[NET_PEER_NAME], POSTGRES_HOST)
        self.assertEqual(child_span.attributes[NET_PEER_PORT], POSTGRES_PORT)

    def test_execute(self):
        """Should create a child span for execute method"""
        stmt = "CREATE TABLE IF NOT EXISTS test (id integer)"
        with self._tracer.start_as_current_span("rootSpan"):
            self._cursor.execute(stmt)
        self.validate_spans("CREATE")

    def test_execute_with_connection_context_manager(self):
        """Should create a child span for execute with connection context"""
        stmt = "CREATE TABLE IF NOT EXISTS test (id INT)"
        with self._tracer.start_as_current_span("rootSpan"):
            with self._connection as conn:
                cursor = conn.cursor()
                cursor.execute(stmt)
        self.validate_spans("CREATE")

    def test_execute_with_cursor_context_manager(self):
        """Should create a child span for execute with cursor context"""
        stmt = "CREATE TABLE IF NOT EXISTS test (id INT)"
        with self._tracer.start_as_current_span("rootSpan"):
            with self._connection.cursor() as cursor:
                cursor.execute(stmt)
        self.validate_spans("CREATE")
        self.assertTrue(cursor.closed)

    def test_executemany(self):
        """Should create a child span for executemany"""
        stmt = "INSERT INTO test (id) VALUES (%s)"
        with self._tracer.start_as_current_span("rootSpan"):
            data = (("1",), ("2",), ("3",))
            self._cursor.executemany(stmt, data)
        self.validate_spans("INSERT")

    def test_callproc(self):
        """Should create a child span for callproc"""
        with (
            self._tracer.start_as_current_span("rootSpan"),
            self.assertRaises(Exception),
        ):
            self._cursor.callproc("test", ())
            self.validate_spans("test")

    def test_register_types(self):
        psycopg2.extras.register_default_jsonb(
            conn_or_curs=self._cursor, loads=lambda x: x
        )

    def test_composed_queries(self):
        stmt = "CREATE TABLE IF NOT EXISTS users (id integer, name varchar)"
        with self._tracer.start_as_current_span("rootSpan"):
            self._cursor.execute(stmt)
        self.validate_spans("CREATE")

        self._cursor.execute(
            sql.SQL("SELECT FROM {table} where {field}='{value}'").format(
                table=sql.Identifier("users"),
                field=sql.Identifier("name"),
                value=sql.Identifier("abc"),
            )
        )

        spans = self.memory_exporter.get_finished_spans()
        span = spans[2]
        self.assertEqual(span.name, "SELECT")
        self.assertEqual(
            span.attributes[DB_STATEMENT],
            'SELECT FROM "users" where "name"=\'"abc"\'',
        )

    def test_commenter_enabled(self):
        stmt = "CREATE TABLE IF NOT EXISTS users (id integer, name varchar)"
        with self._tracer.start_as_current_span("rootSpan"):
            self._cursor.execute(stmt)
        self.validate_spans("CREATE")
        Psycopg2Instrumentor().uninstrument()
        Psycopg2Instrumentor().instrument(enable_commenter=True)

        self._cursor.execute(
            sql.SQL("SELECT FROM {table} where {field}='{value}'").format(
                table=sql.Identifier("users"),
                field=sql.Identifier("name"),
                value=sql.Identifier("abc"),
            )
        )

        spans = self.memory_exporter.get_finished_spans()
        span = spans[2]
        self.assertEqual(span.name, "SELECT")
        self.assertEqual(
            span.attributes[DB_STATEMENT],
            'SELECT FROM "users" where "name"=\'"abc"\'',
        )


class TestFunctionalPsycopgQueryParameters(TestBase):
    """db.query.parameter.<key> capture through the dbapi base against a real
    PostgreSQL server."""

    def setUp(self):
        super().setUp()
        self._tracer = self.tracer_provider.get_tracer(__name__)

    def _client_spans_for(self, sem_conv_mode, operation):
        # The dbapi base reads the semconv opt-in mode and capture_parameters
        # when the connection is wrapped, so both must be set before connecting.
        with use_semconv_opt_in(sem_conv_mode):
            Psycopg2Instrumentor().instrument(
                tracer_provider=self.tracer_provider,
                capture_parameters=True,
            )
            connection = psycopg2.connect(
                dbname=POSTGRES_DB_NAME,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
            )
            connection.set_session(autocommit=True)
            try:
                with (
                    connection.cursor() as cursor,
                    self._tracer.start_as_current_span("rootSpan"),
                ):
                    operation(cursor)
            finally:
                connection.close()
                Psycopg2Instrumentor().uninstrument()
        return [
            span
            for span in self.memory_exporter.get_finished_spans()
            if span.kind is trace_api.SpanKind.CLIENT
        ]

    def test_positional_query_parameters_captured(self):
        spans = self._client_spans_for(
            "database",
            lambda cursor: cursor.execute("SELECT %s, %s", ("jdoe", 42)),
        )
        self.assertEqual(len(spans), 1)
        attributes = spans[0].attributes
        # Positional parameters are keyed by their 0-based index and stringified.
        self.assertEqual(
            attributes[f"{DB_QUERY_PARAMETER_TEMPLATE}.0"], "jdoe"
        )
        self.assertEqual(attributes[f"{DB_QUERY_PARAMETER_TEMPLATE}.1"], "42")
        self.assertIsInstance(
            attributes[f"{DB_QUERY_PARAMETER_TEMPLATE}.0"], str
        )
        self.assertIsInstance(
            attributes[f"{DB_QUERY_PARAMETER_TEMPLATE}.1"], str
        )

    def test_named_query_parameters_captured(self):
        spans = self._client_spans_for(
            "database",
            lambda cursor: cursor.execute(
                "SELECT %(userName)s", {"userName": "jdoe"}
            ),
        )
        self.assertEqual(len(spans), 1)
        attributes = spans[0].attributes
        # Named parameters are keyed by their name.
        self.assertEqual(
            attributes[f"{DB_QUERY_PARAMETER_TEMPLATE}.userName"], "jdoe"
        )
        self.assertIsInstance(
            attributes[f"{DB_QUERY_PARAMETER_TEMPLATE}.userName"], str
        )

    def test_query_parameters_not_captured_for_batch_operations(self):
        def operation(cursor):
            cursor.execute("CREATE TEMPORARY TABLE batch_test (id varchar)")
            cursor.executemany(
                "INSERT INTO batch_test (id) VALUES (%s)",
                (("param1Value",), ("param2Value",)),
            )

        spans = self._client_spans_for("database/dup", operation)
        insert_spans = [span for span in spans if span.name == "INSERT"]
        self.assertEqual(len(insert_spans), 1)
        attributes = insert_spans[0].attributes
        # db.query.parameter.<key> SHOULD NOT be captured on batch operations,
        # but the legacy db.statement.parameters blob still is under the old
        # semconv.
        self.assertFalse(
            any(
                key.startswith(DB_QUERY_PARAMETER_TEMPLATE)
                for key in attributes
            )
        )
        self.assertEqual(
            attributes["db.statement.parameters"],
            "(('param1Value',), ('param2Value',))",
        )
