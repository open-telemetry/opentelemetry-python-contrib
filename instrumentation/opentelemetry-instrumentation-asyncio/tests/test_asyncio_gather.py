# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
