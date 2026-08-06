# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
import asyncio
import functools
import time
from unittest.mock import patch

# pylint: disable=no-name-in-module
from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
from opentelemetry.instrumentation.asyncio.environment_variables import (
    OTEL_PYTHON_ASYNCIO_TO_THREAD_FUNCTION_NAMES_TO_TRACE,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import StatusCode, get_tracer


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

    def test_to_thread_duration_covers_execution(self):
        def multiply(x, y):
            time.sleep(0.1)
            return x * y

        async def to_thread():
            result = await asyncio.to_thread(multiply, 2, 3)
            assert result == 6

        asyncio.run(to_thread())

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertGreaterEqual(span.end_time - span.start_time, 0.1 * 10**9)

        for metric in (
            self.memory_metrics_reader.get_metrics_data()
            .resource_metrics[0]
            .scope_metrics[0]
            .metrics
        ):
            if metric.name == "asyncio.process.duration":
                for point in metric.data.data_points:
                    self.assertGreaterEqual(point.sum, 0.1)

    def test_to_thread_exception(self):
        def multiply(x, y):
            raise ValueError("fail")

        async def to_thread():
            await asyncio.to_thread(multiply, 2, 3)

        with self.assertRaises(ValueError):
            asyncio.run(to_thread())

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "asyncio to_thread-multiply")
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(len(span.events), 1)
        self.assertEqual(span.events[0].name, "exception")

        for metric in (
            self.memory_metrics_reader.get_metrics_data()
            .resource_metrics[0]
            .scope_metrics[0]
            .metrics
        ):
            if metric.name == "asyncio.process.duration":
                for point in metric.data.data_points:
                    self.assertEqual(point.attributes["state"], "exception")

    def test_to_thread_repeated_calls(self):
        def multiply(x, y):
            return x * y

        async def to_thread():
            assert await asyncio.to_thread(multiply, 2, 3) == 6
            assert await asyncio.to_thread(multiply, 4, 5) == 20

        asyncio.run(to_thread())

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)

        for metric in (
            self.memory_metrics_reader.get_metrics_data()
            .resource_metrics[0]
            .scope_metrics[0]
            .metrics
        ):
            if metric.name == "asyncio.process.created":
                for point in metric.data.data_points:
                    self.assertEqual(point.value, 2)

    def test_to_thread_partial_func(self):
        def multiply(x, y):
            return x * y

        double = functools.partial(multiply, 2)

        async def to_thread():
            result = await asyncio.to_thread(double, 3)
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
