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

import pytest
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import get_tracer

from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor, ASYNCIO_FUTURES_DURATION, \
    ASYNCIO_FUTURES_CANCELLED, ASYNCIO_FUTURES_CREATED, ASYNCIO_FUTURES_ACTIVE, ASYNCIO_FUTURES_EXCEPTIONS, \
    ASYNCIO_FUTURES_FINISHED, ASYNCIO_FUTURES_TIMEOUTS
from opentelemetry.instrumentation.asyncio.environment_variables import OTEL_PYTHON_ASYNCIO_FUTURE_TRACE_ENABLED
from .common_test_func import async_func

_expected_metric_names = [
    ASYNCIO_FUTURES_DURATION,
    ASYNCIO_FUTURES_EXCEPTIONS,
    ASYNCIO_FUTURES_CANCELLED,
    ASYNCIO_FUTURES_CREATED,
    ASYNCIO_FUTURES_ACTIVE,
    ASYNCIO_FUTURES_FINISHED,
    ASYNCIO_FUTURES_TIMEOUTS
]


class TestAsyncioEnsureFuture(TestBase):
    @patch.dict(
        "os.environ", {
            OTEL_PYTHON_ASYNCIO_FUTURE_TRACE_ENABLED: "true"
        }
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

    @pytest.mark.asyncio
    def test_asyncio_loop_ensure_future(self):
        """
        async_func is not traced because it is not set in the environment variable
        """

        async def test():
            task = asyncio.ensure_future(async_func())
            await task

        asyncio.run(test())

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    @pytest.mark.asyncio
    def test_asyncio_ensure_future_with_future(self):
        async def test():
            with self._tracer.start_as_current_span("root") as root:
                future = asyncio.Future()
                future.set_result(1)
                task = asyncio.ensure_future(future)
                await task

        asyncio.run(test())

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        for span in spans:
            if span.name == "root":
                self.assertEqual(span.parent, None)
            if span.name == "asyncio.future":
                self.assertNotEquals(span.parent.trace_id, 0)

        for metric in self.memory_metrics_reader.get_metrics_data().resource_metrics[0].scope_metrics[0].metrics:
            if metric.name == ASYNCIO_FUTURES_DURATION:
                self.assertEquals(metric.data.data_points[0].count, 1)
            elif metric.name == ASYNCIO_FUTURES_ACTIVE:
                self.assertEqual(metric.data.data_points[0].value, 0)
            elif metric.name == ASYNCIO_FUTURES_CREATED:
                self.assertEqual(metric.data.data_points[0].value, 1)
            elif metric.name == ASYNCIO_FUTURES_FINISHED:
                self.assertEqual(metric.data.data_points[0].value, 1)
            elif metric.name == ASYNCIO_FUTURES_EXCEPTIONS:
                self.assertEqual(metric.data.data_points[0].value, 0)
            elif metric.name == ASYNCIO_FUTURES_CANCELLED:
                self.assertEqual(metric.data.data_points[0].value, 0)
            elif metric.name == ASYNCIO_FUTURES_TIMEOUTS:
                self.assertEqual(metric.data.data_points[0].value, 0)
