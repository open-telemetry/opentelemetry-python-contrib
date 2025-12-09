import asyncio
import os
import unittest
from collections import namedtuple
from unittest.mock import patch

import asyncpg

from opentelemetry import trace
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import StatusCode

POSTGRES_HOST = os.getenv("POSTGRESQL_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRESQL_PORT", "5432"))
POSTGRES_DB_NAME = os.getenv("POSTGRESQL_DB_NAME", "opentelemetry-tests")
POSTGRES_PASSWORD = os.getenv("POSTGRESQL_PASSWORD", "testpassword")
POSTGRES_USER = os.getenv("POSTGRESQL_USER", "testuser")


def async_call(coro):
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


class CheckSpanMixin:
    def check_span(self, span, expected_db_name=POSTGRES_DB_NAME):
        self.assertEqual(
            span.attributes[SpanAttributes.DB_SYSTEM], "postgresql"
        )
        self.assertEqual(
            span.attributes[SpanAttributes.DB_NAME], expected_db_name
        )
        self.assertEqual(
            span.attributes[SpanAttributes.DB_USER], POSTGRES_USER
        )
        self.assertEqual(
            span.attributes[SpanAttributes.NET_PEER_NAME], POSTGRES_HOST
        )
        self.assertEqual(
            span.attributes[SpanAttributes.NET_PEER_PORT], POSTGRES_PORT
        )


class TestFunctionalAsyncPG(TestBase, CheckSpanMixin):
    def setUp(self):
        super().setUp()
        self._tracer = self.tracer_provider.get_tracer(__name__)
        AsyncPGInstrumentor().instrument(tracer_provider=self.tracer_provider)
        self._connection = async_call(
            asyncpg.connect(
                database=POSTGRES_DB_NAME,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
            )
        )

    def tearDown(self):
        AsyncPGInstrumentor().uninstrument()
        super().tearDown()

    def test_instrumented_execute_method_without_arguments(self, *_, **__):
        """Should create a span for execute()."""
        async_call(self._connection.execute("SELECT 42;"))
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertIs(StatusCode.UNSET, spans[0].status.status_code)
        self.check_span(spans[0])
        self.assertEqual(spans[0].name, "SELECT")
        self.assertEqual(
            spans[0].attributes[SpanAttributes.DB_STATEMENT], "SELECT 42;"
        )

    def test_instrumented_execute_method_error(self, *_, **__):
        """Should create an error span for execute() with the database name as the span name."""
        with self.assertRaises(AttributeError):
            async_call(self._connection.execute(""))
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertIs(StatusCode.ERROR, spans[0].status.status_code)
        self.check_span(spans[0])
        self.assertEqual(spans[0].name, POSTGRES_DB_NAME)
        self.assertEqual(spans[0].attributes[SpanAttributes.DB_STATEMENT], "")

    def test_instrumented_fetch_method_without_arguments(self, *_, **__):
        """Should create a span from fetch()."""
        async_call(self._connection.fetch("SELECT 42;"))
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertIs(StatusCode.UNSET, spans[0].status.status_code)
        self.check_span(spans[0])
        self.assertEqual(spans[0].name, "SELECT")
        self.assertEqual(
            spans[0].attributes[SpanAttributes.DB_STATEMENT], "SELECT 42;"
        )

    def test_instrumented_fetch_method_empty_query(self, *_, **__):
        """Should create an error span for fetch() with the database name as the span name."""
        async_call(self._connection.fetch(""))
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertIs(StatusCode.UNSET, spans[0].status.status_code)
        self.check_span(spans[0])
        self.assertEqual(spans[0].name, POSTGRES_DB_NAME)
        self.assertEqual(spans[0].attributes[SpanAttributes.DB_STATEMENT], "")

    def test_instrumented_fetchval_method_without_arguments(self, *_, **__):
        """Should create a span for fetchval()."""
        async_call(self._connection.fetchval("SELECT 42;"))
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertIs(StatusCode.UNSET, spans[0].status.status_code)
        self.check_span(spans[0])
        self.assertEqual(spans[0].name, "SELECT")
        self.assertEqual(
            spans[0].attributes[SpanAttributes.DB_STATEMENT], "SELECT 42;"
        )

    def test_instrumented_fetchval_method_empty_query(self, *_, **__):
        """Should create an error span for fetchval() with the database name as the span name."""
        async_call(self._connection.fetchval(""))
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertIs(StatusCode.UNSET, spans[0].status.status_code)
        self.check_span(spans[0])
        self.assertEqual(spans[0].name, POSTGRES_DB_NAME)
        self.assertEqual(spans[0].attributes[SpanAttributes.DB_STATEMENT], "")

    def test_instrumented_fetchrow_method_without_arguments(self, *_, **__):
        """Should create a span for fetchrow()."""
        async_call(self._connection.fetchrow("SELECT 42;"))
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertIs(StatusCode.UNSET, spans[0].status.status_code)
        self.check_span(spans[0])
        self.assertEqual(spans[0].name, "SELECT")
        self.assertEqual(
            spans[0].attributes[SpanAttributes.DB_STATEMENT], "SELECT 42;"
        )

    def test_instrumented_fetchrow_method_empty_query(self, *_, **__):
        """Should create an error span for fetchrow() with the database name as the span name."""
        async_call(self._connection.fetchrow(""))
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertIs(StatusCode.UNSET, spans[0].status.status_code)
        self.check_span(spans[0])
        self.assertEqual(spans[0].name, POSTGRES_DB_NAME)
        self.assertEqual(spans[0].attributes[SpanAttributes.DB_STATEMENT], "")

    def test_instrumented_cursor_execute_method_without_arguments(
        self, *_, **__
    ):
        """Should create spans for the transaction as well as the cursor fetches."""

        async def _cursor_execute():
            async with self._connection.transaction():
                async for record in self._connection.cursor(
                    "SELECT generate_series(0, 5);"
                ):
                    pass

        async_call(_cursor_execute())
        spans = self.memory_exporter.get_finished_spans()

        self.check_span(spans[0])
        self.assertEqual(spans[0].name, "BEGIN;")
        self.assertEqual(
            spans[0].attributes[SpanAttributes.DB_STATEMENT], "BEGIN;"
        )
        self.assertIs(StatusCode.UNSET, spans[0].status.status_code)

        for span in spans[1:-1]:
            self.check_span(span)
            self.assertEqual(span.name, "CURSOR: SELECT")
            self.assertEqual(
                span.attributes[SpanAttributes.DB_STATEMENT],
                "SELECT generate_series(0, 5);",
            )
            self.assertIs(StatusCode.UNSET, span.status.status_code)

        self.check_span(spans[-1])
        self.assertEqual(spans[-1].name, "COMMIT;")
        self.assertEqual(
            spans[-1].attributes[SpanAttributes.DB_STATEMENT], "COMMIT;"
        )

    def test_instrumented_cursor_execute_method_empty_query(self, *_, **__):
        """Should create spans for the transaction and cursor fetches with the database name as the span name."""

        async def _cursor_execute():
            async with self._connection.transaction():
                async for record in self._connection.cursor(""):
                    pass

        async_call(_cursor_execute())
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 3)

        self.check_span(spans[0])
        self.assertEqual(
            spans[0].attributes[SpanAttributes.DB_STATEMENT], "BEGIN;"
        )
        self.assertIs(StatusCode.UNSET, spans[0].status.status_code)

        self.check_span(spans[1])
        self.assertEqual(spans[1].name, f"CURSOR: {POSTGRES_DB_NAME}")
        self.assertEqual(spans[1].attributes[SpanAttributes.DB_STATEMENT], "")
        self.assertIs(StatusCode.UNSET, spans[1].status.status_code)

        self.check_span(spans[2])
        self.assertEqual(
            spans[2].attributes[SpanAttributes.DB_STATEMENT], "COMMIT;"
        )

    def test_instrumented_remove_comments(self, *_, **__):
        """Should remove comments from the query and set the span name correctly."""
        async_call(self._connection.fetch("/* leading comment */ SELECT 42;"))
        async_call(
            self._connection.fetch(
                "/* leading comment */ SELECT 42; /* trailing comment */"
            )
        )
        async_call(self._connection.fetch("SELECT 42; /* trailing comment */"))
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 3)
        self.check_span(spans[0])
        self.assertIs(StatusCode.UNSET, spans[0].status.status_code)
        self.assertEqual(spans[0].name, "SELECT")
        self.assertEqual(
            spans[0].attributes[SpanAttributes.DB_STATEMENT],
            "/* leading comment */ SELECT 42;",
        )
        self.check_span(spans[1])
        self.assertIs(StatusCode.UNSET, spans[1].status.status_code)
        self.assertEqual(spans[1].name, "SELECT")
        self.assertEqual(
            spans[1].attributes[SpanAttributes.DB_STATEMENT],
            "/* leading comment */ SELECT 42; /* trailing comment */",
        )
        self.check_span(spans[2])
        self.assertIs(StatusCode.UNSET, spans[2].status.status_code)
        self.assertEqual(spans[2].name, "SELECT")
        self.assertEqual(
            spans[2].attributes[SpanAttributes.DB_STATEMENT],
            "SELECT 42; /* trailing comment */",
        )

    def test_instrumented_transaction_method(self, *_, **__):
        """Should create spans for the transaction and the inner execute()."""

        async def _transaction_execute():
            async with self._connection.transaction():
                await self._connection.execute("SELECT 42;")

        async_call(_transaction_execute())

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(3, len(spans))
        self.check_span(spans[0])
        self.assertEqual(
            spans[0].attributes[SpanAttributes.DB_STATEMENT], "BEGIN;"
        )
        self.assertIs(StatusCode.UNSET, spans[0].status.status_code)

        self.check_span(spans[1])
        self.assertEqual(
            spans[1].attributes[SpanAttributes.DB_STATEMENT], "SELECT 42;"
        )
        self.assertIs(StatusCode.UNSET, spans[1].status.status_code)

        self.check_span(spans[2])
        self.assertEqual(
            spans[2].attributes[SpanAttributes.DB_STATEMENT], "COMMIT;"
        )
        self.assertIs(StatusCode.UNSET, spans[2].status.status_code)

    def test_instrumented_failed_transaction_method(self, *_, **__):
        """Should create spans for the transaction as well as an error span for execute()."""

        async def _transaction_execute():
            async with self._connection.transaction():
                await self._connection.execute("SELECT 42::uuid;")

        with self.assertRaises(asyncpg.CannotCoerceError):
            async_call(_transaction_execute())

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(3, len(spans))

        self.check_span(spans[0])
        self.assertEqual(
            spans[0].attributes[SpanAttributes.DB_STATEMENT], "BEGIN;"
        )
        self.assertIs(StatusCode.UNSET, spans[0].status.status_code)

        self.check_span(spans[1])
        self.assertEqual(
            spans[1].attributes[SpanAttributes.DB_STATEMENT],
            "SELECT 42::uuid;",
        )
        self.assertEqual(StatusCode.ERROR, spans[1].status.status_code)

        self.check_span(spans[2])
        self.assertEqual(
            spans[2].attributes[SpanAttributes.DB_STATEMENT], "ROLLBACK;"
        )
        self.assertIs(StatusCode.UNSET, spans[2].status.status_code)

    def test_instrumented_method_doesnt_capture_parameters(self, *_, **__):
        """Should not capture parameters when capture_parameters is False."""
        async_call(self._connection.execute("SELECT $1;", "1"))
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertIs(StatusCode.UNSET, spans[0].status.status_code)
        self.check_span(spans[0])
        self.assertEqual(
            spans[0].attributes[SpanAttributes.DB_STATEMENT], "SELECT $1;"
        )


class TestFunctionalAsyncPG_CaptureParameters(TestBase, CheckSpanMixin):
    def setUp(self):
        super().setUp()
        self._tracer = self.tracer_provider.get_tracer(__name__)
        AsyncPGInstrumentor(capture_parameters=True).instrument(
            tracer_provider=self.tracer_provider
        )
        self._connection = async_call(
            asyncpg.connect(
                database=POSTGRES_DB_NAME,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
            )
        )

    def tearDown(self):
        AsyncPGInstrumentor().uninstrument()
        super().tearDown()

    def test_instrumented_execute_method_with_arguments(self, *_, **__):
        """Should create a span for execute() with captured parameters."""
        async_call(self._connection.execute("SELECT $1;", "1"))
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertIs(StatusCode.UNSET, spans[0].status.status_code)

        self.check_span(spans[0])
        self.assertEqual(spans[0].name, "SELECT")
        self.assertEqual(
            spans[0].attributes[SpanAttributes.DB_STATEMENT], "SELECT $1;"
        )
        self.assertEqual(
            spans[0].attributes["db.statement.parameters"], "('1',)"
        )

    def test_instrumented_fetch_method_with_arguments(self, *_, **__):
        """Should create a span for fetch() with captured parameters."""
        async_call(self._connection.fetch("SELECT $1;", "1"))
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        self.check_span(spans[0])
        self.assertEqual(spans[0].name, "SELECT")
        self.assertEqual(
            spans[0].attributes[SpanAttributes.DB_STATEMENT], "SELECT $1;"
        )
        self.assertEqual(
            spans[0].attributes["db.statement.parameters"], "('1',)"
        )

    def test_instrumented_executemany_method_with_arguments(self, *_, **__):
        """Should create a span for executemany with captured parameters."""
        async_call(self._connection.executemany("SELECT $1;", [["1"], ["2"]]))
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertIs(StatusCode.UNSET, spans[0].status.status_code)
        self.check_span(spans[0])
        self.assertEqual(
            spans[0].attributes[SpanAttributes.DB_STATEMENT], "SELECT $1;"
        )
        self.assertEqual(
            spans[0].attributes["db.statement.parameters"], "([['1'], ['2']],)"
        )

    def test_instrumented_execute_interface_error_method(self, *_, **__):
        """Should create an error span for execute() with captured parameters."""
        with self.assertRaises(asyncpg.InterfaceError):
            async_call(self._connection.execute("SELECT 42;", 1, 2, 3))
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertIs(StatusCode.ERROR, spans[0].status.status_code)
        self.check_span(spans[0])
        self.assertEqual(
            spans[0].attributes[SpanAttributes.DB_STATEMENT], "SELECT 42;"
        )
        self.assertEqual(
            spans[0].attributes["db.statement.parameters"], "(1, 2, 3)"
        )

    def test_instrumented_executemany_method_empty_query(self, *_, **__):
        """Should create a span for executemany() with captured parameters."""
        async_call(self._connection.executemany("", []))
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertIs(StatusCode.UNSET, spans[0].status.status_code)
        self.check_span(spans[0])
        self.assertEqual(spans[0].name, POSTGRES_DB_NAME)
        self.assertEqual(spans[0].attributes[SpanAttributes.DB_STATEMENT], "")
        self.assertEqual(
            spans[0].attributes["db.statement.parameters"], "([],)"
        )

    def test_instrumented_fetch_method_broken_asyncpg(self, *_, **__):
        """Should create a span for fetch() with "postgresql" as the span name."""
        with patch.object(
            self._connection, "_params", namedtuple("ConnectionParams", [])
        ):
            async_call(self._connection.fetch(""))
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertIs(StatusCode.UNSET, spans[0].status.status_code)
        self.assertEqual(spans[0].name, "postgresql")
        self.assertEqual(spans[0].attributes[SpanAttributes.DB_STATEMENT], "")


class _NonRecordingSpan:
    def __init__(self, recording=False):
        self._recording = recording
        self.set_status_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def is_recording(self):
        return self._recording

    def set_status(self, status):
        self.set_status_calls += 1
        self.status = status


class _CapturingTracer:
    def __init__(self, span):
        self.span = span
        self.started_spans = []

    def start_as_current_span(self, name, kind=None, attributes=None):
        self.started_spans.append(
            {"name": name, "kind": kind, "attributes": attributes}
        )
        return self.span


class _FakeParams:
    def __init__(self, database="testdb", user="dbuser"):
        self.database = database
        self.user = user


class _FakeConnection:
    def __init__(self):
        self._params = _FakeParams()
        self._addr = ("db.example.com", 5432)


class _FakeCursor:
    def __init__(self, connection, query, args):
        self._connection = connection
        self._query = query
        self._args = args


class TestAsyncPGSamplingAttributes(unittest.TestCase):
    def setUp(self):
        self.connection = _FakeConnection()
        self.span = _NonRecordingSpan(recording=False)
        self.tracer = _CapturingTracer(self.span)
        self.instrumentor = AsyncPGInstrumentor(capture_parameters=True)
        self.instrumentor._tracer = self.tracer

    def test_attributes_available_when_span_not_recording(self):
        async def _fake_execute(*args, **kwargs):
            return "ok"

        async_call(
            self.instrumentor._do_execute(
                _fake_execute,
                self.connection,
                ("SELECT $1", "42"),
                {},
            )
        )

        self.assertEqual(len(self.tracer.started_spans), 1)
        span_info = self.tracer.started_spans[0]
        self.assertEqual(
            span_info["attributes"],
            {
                SpanAttributes.DB_SYSTEM: "postgresql",
                SpanAttributes.DB_NAME: "testdb",
                SpanAttributes.DB_USER: "dbuser",
                SpanAttributes.NET_PEER_NAME: "db.example.com",
                SpanAttributes.NET_PEER_PORT: 5432,
                SpanAttributes.NET_TRANSPORT: "ip_tcp",
                SpanAttributes.DB_STATEMENT: "SELECT $1",
                "db.statement.parameters": "('42',)",
            },
        )
        self.assertEqual(span_info["kind"], trace.SpanKind.CLIENT)
        self.assertEqual(span_info["name"], "SELECT")

    def test_cursor_attributes_available_when_span_not_recording(self):
        async def _fake_cursor_execute(*args, **kwargs):
            return "ok"

        cursor = _FakeCursor(self.connection, "SELECT $1", ("99",))

        async_call(
            self.instrumentor._do_cursor_execute(
                _fake_cursor_execute,
                cursor,
                (),
                {},
            )
        )

        self.assertEqual(len(self.tracer.started_spans), 1)
        span_info = self.tracer.started_spans[0]
        self.assertEqual(
            span_info["attributes"],
            {
                SpanAttributes.DB_SYSTEM: "postgresql",
                SpanAttributes.DB_NAME: "testdb",
                SpanAttributes.DB_USER: "dbuser",
                SpanAttributes.NET_PEER_NAME: "db.example.com",
                SpanAttributes.NET_PEER_PORT: 5432,
                SpanAttributes.NET_TRANSPORT: "ip_tcp",
                SpanAttributes.DB_STATEMENT: "SELECT $1",
                "db.statement.parameters": "('99',)",
            },
        )
        self.assertEqual(span_info["kind"], trace.SpanKind.CLIENT)
        self.assertEqual(span_info["name"], "CURSOR: SELECT")
