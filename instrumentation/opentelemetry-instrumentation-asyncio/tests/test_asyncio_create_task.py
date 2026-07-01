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


class TestAsyncioCreateTask(TestBase):
    @patch.dict(
        "os.environ", {OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE: "sleep"}
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

    def test_asyncio_create_task(self):
        async def async_func():
            await asyncio.create_task(asyncio.sleep(0))
            await asyncio.create_task(factorial(3))

        asyncio.run(async_func())
        spans = self.memory_exporter.get_finished_spans()

        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "asyncio coro-sleep")
