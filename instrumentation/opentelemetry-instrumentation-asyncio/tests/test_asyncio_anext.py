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
from unittest import skipIf
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
    @skipIf(
        sys.version_info < (3, 10), "anext is only available in Python 3.10+"
    )
    def test_asyncio_anext(self):
        async def main():
            async def async_gen():
                # nothing special about this range other than to avoid returning a zero
                # from a function named 'main' (which might cause confusion about intent)
                for it in range(2, 4):
                    yield it

            async_gen_instance = async_gen()
            agen = anext(async_gen_instance)
            return await asyncio.create_task(agen)

        ret = asyncio.run(main())
        self.assertEqual(ret, 2)  # first iteration from range()
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)
