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

# pylint: disable=no-name-in-module
from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
from opentelemetry.instrumentation.asyncio.environment_variables import (
    OTEL_PYTHON_ASYNCIO_FUTURE_TRACE_ENABLED,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import get_tracer

from .common_test_func import async_func


class TestAsyncioEnsureFuture(TestBase):
    @patch.dict(
        "os.environ", {OTEL_PYTHON_ASYNCIO_FUTURE_TRACE_ENABLED: "true"}
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
            with self._tracer.start_as_current_span("root"):
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
            if span.name == "asyncio future":
                self.assertNotEqual(span.parent.trace_id, 0)

        for metric in (
            self.memory_metrics_reader.get_metrics_data()
            .resource_metrics[0]
            .scope_metrics[0]
            .metrics
        ):
            if metric.name == "asyncio.process.duration":
                for point in metric.data.data_points:
                    self.assertEqual(point.attributes["type"], "future")
            if metric.name == "asyncio.process.created":
                for point in metric.data.data_points:
                    self.assertEqual(point.attributes["type"], "future")
                    self.assertEqual(point.attributes["state"], "finished")
