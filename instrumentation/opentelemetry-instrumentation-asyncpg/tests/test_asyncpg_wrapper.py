from unittest import mock
import asyncio

from asyncpg import Connection, cursor
from wrapt import ObjectProxy
import pytest

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
                (cursor.CursorIterator, ("__anext__", ))
            ]:
                for method_name in methods:
                    method = getattr(cls, method_name, None)
                    assert_fnc(isinstance(method, ObjectProxy), f"{method} isinstance {type(method)}")


        assert_wrapped(self.assertFalse)
        AsyncPGInstrumentor().instrument()
        assert_wrapped(self.assertTrue)
        AsyncPGInstrumentor().uninstrument()
        assert_wrapped(self.assertFalse)

    def test_cursor_span_creation(self):
        """ Test the cursor wrapper if it creates spans correctly.
        """
        async def mock_fn(*args, **kwargs):
            pass

        async def mock_fn_stop(*args, **kwargs):
            raise StopAsyncIteration()

        cursor_mock = mock.Mock()
        cursor_mock._query = "SELECT * FROM test"

        apg = AsyncPGInstrumentor()
        apg.instrument(tracer_provider=self.tracer_provider)

        # Call the wrapper function directly. They only way to be able to do this on the real classes is to mock all of the
        # methods. In that case we are only testing the instrumentation of mocked functions. This makes it explicit.
        asyncio.run(apg._do_cursor_execute(mock_fn, cursor_mock, [], {}))

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "CURSOR: SELECT")
        self.assertTrue(spans[0].status.is_ok)

        # Now test that the StopAsyncIteration of the cursor does not get recorded as an ERROR
        with pytest.raises(StopAsyncIteration):
            asyncio.run(apg._do_cursor_execute(mock_fn_stop, cursor_mock, [], {}))

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        self.assertEqual([span.status.is_ok for span in spans], [True, True])