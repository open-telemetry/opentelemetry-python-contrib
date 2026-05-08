# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
import asyncio
import sys
from unittest.mock import patch

# pylint: disable=no-name-in-module
from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
from opentelemetry.instrumentation.asyncio.environment_variables import (
    OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE,
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
                # In Python 3.11, you can't send coroutines directly to asyncio.as_completed().
                # Instead, you must wrap them in asyncio.create_task().
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
