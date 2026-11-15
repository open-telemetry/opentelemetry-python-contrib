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

from .common_test_func import factorial


class TestAsyncioGather(TestBase):
    @patch.dict(
        "os.environ",
        {OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE: "factorial"},
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

    def test_asyncio_gather(self):
        async def gather_factorial():
            await asyncio.gather(factorial(2), factorial(3), factorial(4))

        asyncio.run(gather_factorial())
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 3)
        self.assertEqual(spans[0].name, "asyncio coro-factorial")
        self.assertEqual(spans[1].name, "asyncio coro-factorial")
        self.assertEqual(spans[2].name, "asyncio coro-factorial")

    def test_asyncio_gather_duplicate_coroutines(self) -> None:
        async def gather_factorial() -> list[int]:
            immediate = factorial(1)
            yielding = factorial(3)
            return await asyncio.gather(immediate, yielding, immediate, yielding)

        self.assertEqual(asyncio.run(gather_factorial()), [1, 6, 1, 6])
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        self.assertTrue(all(span.name == "asyncio coro-factorial" for span in spans))

    def test_asyncio_gather_duplicate_coroutine_exception(self) -> None:
        error = ValueError("failed operation")

        async def fail() -> None:
            await asyncio.sleep(0)
            raise error

        async def gather_errors() -> None:
            coro = fail()
            results = await asyncio.gather(coro, coro, return_exceptions=True)
            self.assertEqual(results, [error, error])

            coro = fail()
            with self.assertRaises(ValueError) as raised:
                await asyncio.gather(coro, coro)
            self.assertIs(raised.exception, error)

        asyncio.run(gather_errors())

    def test_asyncio_gather_duplicate_tasks_and_futures(self) -> None:
        async def gather_results() -> list[int]:
            task = asyncio.create_task(factorial(3))
            future = asyncio.get_running_loop().create_future()
            future.set_result(42)
            return await asyncio.gather(task, future, task, future)

        self.assertEqual(asyncio.run(gather_results()), [6, 42, 6, 42])
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "asyncio coro-factorial")
