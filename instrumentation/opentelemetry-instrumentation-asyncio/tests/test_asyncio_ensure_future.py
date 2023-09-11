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

import pytest
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import get_tracer

from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
from .common_test_func import async_func


class TestAsyncioEnsureFuture(TestBase):
    def setUp(self):
        super().setUp()
        AsyncioInstrumentor().instrument()
        self._tracer = get_tracer(
            __name__,
        )

    def tearDown(self):
        super().tearDown()
        AsyncioInstrumentor().uninstrument()

    @pytest.mark.asyncio
    def test_asyncio_loop_ensure_future(self):
        loop = asyncio.get_event_loop()
        task = asyncio.ensure_future(async_func())
        loop.run_until_complete(task)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "asyncio.coro-async_func")

    @pytest.mark.asyncio
    def test_asyncio_ensure_future_with_future(self):
        loop = asyncio.get_event_loop()

        future = asyncio.Future()
        future.set_result(1)
        task = asyncio.ensure_future(future)
        loop.run_until_complete(task)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "asyncio.Future")
