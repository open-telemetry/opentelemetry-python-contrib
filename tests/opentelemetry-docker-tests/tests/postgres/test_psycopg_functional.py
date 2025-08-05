# Copyright 2020, OpenTelemetry Authors
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

import os

import psycopg2
from psycopg2 import sql

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.test_base import TestBase

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
        self.assertEqual(
            child_span.attributes[SpanAttributes.DB_SYSTEM], "postgresql"
        )
        self.assertEqual(
            child_span.attributes[SpanAttributes.DB_NAME], POSTGRES_DB_NAME
        )
        self.assertEqual(
            child_span.attributes[SpanAttributes.DB_USER], POSTGRES_USER
        )
        self.assertEqual(
            child_span.attributes[SpanAttributes.NET_PEER_NAME], POSTGRES_HOST
        )
        self.assertEqual(
            child_span.attributes[SpanAttributes.NET_PEER_PORT], POSTGRES_PORT
        )

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
            span.attributes[SpanAttributes.DB_STATEMENT],
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
            span.attributes[SpanAttributes.DB_STATEMENT],
            'SELECT FROM "users" where "name"=\'"abc"\'',
        )
