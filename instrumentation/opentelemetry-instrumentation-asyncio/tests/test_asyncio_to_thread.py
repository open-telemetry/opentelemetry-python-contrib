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
    OTEL_PYTHON_ASYNCIO_TO_THREAD_FUNCTION_NAMES_TO_TRACE,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import get_tracer


class TestAsyncioToThread(TestBase):
    @patch.dict(
        "os.environ",
        {OTEL_PYTHON_ASYNCIO_TO_THREAD_FUNCTION_NAMES_TO_TRACE: "multiply"},
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
        sys.version_info < (3, 9), "to_thread is only available in Python 3.9+"
    )
    def test_to_thread(self):
        def multiply(x, y):
            return x * y

        async def to_thread():
            result = await asyncio.to_thread(multiply, 2, 3)
            assert result == 6

        with self._tracer.start_as_current_span("root"):
            asyncio.run(to_thread())
        spans = self.memory_exporter.get_finished_spans()

        self.assertEqual(len(spans), 2)
        assert spans[0].name == "asyncio to_thread-multiply"
        for metric in (
            self.memory_metrics_reader.get_metrics_data()
            .resource_metrics[0]
            .scope_metrics[0]
            .metrics
        ):
            if metric.name == "asyncio.process.duration":
                for point in metric.data.data_points:
                    self.assertEqual(point.attributes["type"], "to_thread")
                    self.assertEqual(point.attributes["name"], "multiply")
            if metric.name == "asyncio.process.created":
                for point in metric.data.data_points:
                    self.assertEqual(point.attributes["type"], "to_thread")
                    self.assertEqual(point.attributes["name"], "multiply")
