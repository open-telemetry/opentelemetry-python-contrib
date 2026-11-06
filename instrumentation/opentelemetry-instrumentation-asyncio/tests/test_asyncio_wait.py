# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
import asyncio
import sys
from unittest.mock import patch

# pylint: disable=no-name-in-module
from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
from opentelemetry.instrumentation.asyncio.environment_variables import (
    OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE,
    OTEL_PYTHON_ASYNCIO_FUTURE_TRACE_ENABLED,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import get_tracer

from .common_test_func import async_func


class TestAsyncioWait(TestBase):
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

    def test_asyncio_wait_with_create_task(self):
        async def main():
            if sys.version_info >= (3, 11):
                # In Python 3.11, you can't send coroutines directly to asyncio.wait().
                # Instead, you must wrap them in asyncio.create_task().
                tasks = [
                    asyncio.create_task(async_func()),
                    asyncio.create_task(async_func()),
                ]
                await asyncio.wait(tasks)
            else:
                await asyncio.wait([async_func(), async_func()])

        asyncio.run(main())
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)

    def test_asyncio_wait_for(self):
        async def main():
            await asyncio.wait_for(async_func(), 1)
            await asyncio.wait_for(async_func(), 1)

        asyncio.run(main())
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)

    def test_asyncio_wait_for_with_timeout(self):
        expected_timeout_error = None

        async def main():
            nonlocal expected_timeout_error
            try:
                await asyncio.wait_for(async_func(), 0.01)
            except asyncio.TimeoutError as timeout_error:
                expected_timeout_error = timeout_error

        asyncio.run(main())
        self.assertNotEqual(expected_timeout_error, None)

    def test_asyncio_as_completed(self):
        async def main():
            if sys.version_info >= (3, 11):
                # Mirror test_asyncio_wait_with_create_task; the coroutine
                # input path is covered by the tests below.
                tasks = [
                    asyncio.create_task(async_func()),
                    asyncio.create_task(async_func()),
                ]
                for task in asyncio.as_completed(tasks):
                    await task
            else:
                for task in asyncio.as_completed([async_func(), async_func()]):
                    await task

        asyncio.run(main())
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)

    def _assert_as_completed_traces_coroutines(self, make_container):
        """as_completed accepts coroutines directly, so this exercises the
        wrapper itself rather than the create_task instrumentation."""

        async def main():
            for item in asyncio.as_completed(make_container([async_func(), async_func()])):
                await item

        asyncio.run(main())
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        for span in spans:
            self.assertEqual(span.name, "asyncio coro-async_func")

    def test_asyncio_as_completed_with_list_of_coroutines(self):
        self._assert_as_completed_traces_coroutines(list)

    def test_asyncio_as_completed_with_set_of_coroutines(self):
        self._assert_as_completed_traces_coroutines(set)

    def test_asyncio_as_completed_with_tuple_of_coroutines(self):
        self._assert_as_completed_traces_coroutines(tuple)

    def test_asyncio_as_completed_with_generator_of_coroutines(self):
        self._assert_as_completed_traces_coroutines(lambda items: (item for item in items))


class TestAsyncioWaitWithFutures(TestBase):
    @patch.dict("os.environ", {OTEL_PYTHON_ASYNCIO_FUTURE_TRACE_ENABLED: "true"})
    def setUp(self):
        super().setUp()
        AsyncioInstrumentor().instrument()

    def tearDown(self):
        super().tearDown()
        AsyncioInstrumentor().uninstrument()

    def _assert_wait_traces_futures(self, make_container):
        """Bare futures are only instrumented through the wait wrapper."""

        async def main():
            loop = asyncio.get_running_loop()
            futs = [loop.create_future(), loop.create_future()]
            for fut in futs:
                fut.set_result(1)
            await asyncio.wait(make_container(futs))

        asyncio.run(main())
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        for span in spans:
            self.assertEqual(span.name, "asyncio future")

    def test_asyncio_wait_with_list_of_futures(self):
        self._assert_wait_traces_futures(list)

    def test_asyncio_wait_with_set_of_futures(self):
        self._assert_wait_traces_futures(set)

    def test_asyncio_wait_with_tuple_of_futures(self):
        self._assert_wait_traces_futures(tuple)

    def test_asyncio_wait_with_generator_of_futures(self):
        self._assert_wait_traces_futures(lambda items: (item for item in items))
