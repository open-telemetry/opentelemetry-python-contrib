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
import sys

from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import get_tracer

from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
from .common_test_func import async_func

py11 = False
if sys.version_info >= (3, 11):
    py11 = True


class TestAsyncioTaskgroup(TestBase):
    def setUp(self):
        super().setUp()
        AsyncioInstrumentor().instrument()
        self._tracer = get_tracer(
            __name__,
        )

    def tearDown(self):
        super().tearDown()
        AsyncioInstrumentor().uninstrument()

    def test_task_group_create_task(self):
        async def main():
            if py11:
                async with asyncio.TaskGroup() as tg:
                    for _ in range(10):
                        tg.create_task(async_func())

        asyncio.run(main())
        spans = self.memory_exporter.get_finished_spans()
        assert spans
        if py11:
            self.assertEqual(len(spans), 10)
