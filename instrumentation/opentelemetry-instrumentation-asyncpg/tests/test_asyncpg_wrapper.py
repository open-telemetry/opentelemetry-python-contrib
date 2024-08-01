import asyncio
from unittest import mock

import pytest
from asyncpg import Connection, Record, cursor
from wrapt import ObjectProxy

from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.test.test_base import TestBase


class TestAsyncPGInstrumentation(TestBase):
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
                        isinstance(method, ObjectProxy),
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
            asyncio.run(crs_iter.__anext__())

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        self.assertEqual([span.status.is_ok for span in spans], [True, True])
