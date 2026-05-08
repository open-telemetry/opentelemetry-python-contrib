# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
import asyncio
from unittest.mock import patch

# pylint: disable=no-name-in-module
from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
from opentelemetry.instrumentation.asyncio.environment_variables import (
    OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import get_tracer


class TestAsyncioAnext(TestBase):
    @patch.dict(
        "os.environ",
        {OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE: "async_func"},
    )
    def setUp(self):
        super().setUp()
        AsyncioInstrumentor().instrument()
        self._tracer = get_tracer(
            __name__,
        )

    def tearDown(self):
        super().tearDown()
        AsyncioInstrumentor().uninstrument()

    # Asyncio anext() does not have __name__ attribute, which is used to determine if the coroutine should be traced.
    # This test is to ensure that the instrumentation does not break when the coroutine does not have __name__ attribute.
    # Additionally, ensure the coroutine is actually awaited.
    def test_asyncio_anext(self):
        async def main():
            async def async_gen():
                # nothing special about this range other than to avoid returning a zero
                # from a function named 'main' (which might cause confusion about intent)
                for it in range(2, 4):
                    yield it

            async_gen_instance = async_gen()
            agen = anext(async_gen_instance)  # noqa: F821
            return await asyncio.create_task(agen)

        ret = asyncio.run(main())
        self.assertEqual(ret, 2)  # first iteration from range()
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)
