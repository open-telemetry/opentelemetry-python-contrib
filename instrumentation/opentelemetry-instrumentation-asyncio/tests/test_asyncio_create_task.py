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

from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import get_tracer

from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor


class TestAsyncioCreateTask(TestBase):
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

        asyncio.run(async_func())
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
