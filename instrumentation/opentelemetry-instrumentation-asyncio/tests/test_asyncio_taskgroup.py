# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
import asyncio
import sys
from unittest import skipIf
from unittest.mock import patch

# pylint: disable=no-name-in-module
from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
from opentelemetry.instrumentation.asyncio.environment_variables import (
    OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import get_tracer

from .common_test_func import async_func


class TestAsyncioTaskgroup(TestBase):
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

    @skipIf(
        sys.version_info < (3, 11),
        "TaskGroup is only available in Python 3.11+",
    )
    def test_task_group_create_task(self):
        async def main():
            async with asyncio.TaskGroup() as tg:  # pylint: disable=no-member
                for _ in range(10):
                    tg.create_task(async_func())

        with self._tracer.start_as_current_span("root"):
            asyncio.run(main())
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 11)
        self.assertEqual(spans[4].context.trace_id, spans[5].context.trace_id)
