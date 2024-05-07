from asyncpg import Connection, cursor

from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.test.test_base import TestBase

from wrapt import ObjectProxy


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

