# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
import asyncio
from unittest.mock import patch

# pylint: disable=no-name-in-module
from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
from opentelemetry.instrumentation.asyncio.environment_variables import (
    OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind, get_tracer

from .common_test_func import cancellation_create_task


class TestAsyncioCancel(TestBase):
    @patch.dict(
        "os.environ",
        {
            OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE: "cancellation_coro, cancellable_coroutine"
        },
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

    def test_cancel(self):
        with self._tracer.start_as_current_span("root", kind=SpanKind.SERVER):
            try:
                asyncio.run(cancellation_create_task())
            except asyncio.CancelledError:
                pass
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 3)
        self.assertEqual(spans[0].context.trace_id, spans[1].context.trace_id)
        self.assertEqual(spans[2].context.trace_id, spans[1].context.trace_id)

        self.assertEqual(spans[0].name, "asyncio coro-cancellable_coroutine")
        self.assertEqual(spans[1].name, "asyncio coro-cancellation_coro")
        for metric in (
            self.memory_metrics_reader.get_metrics_data()
            .resource_metrics[0]
            .scope_metrics[0]
            .metrics
        ):
            if metric.name == "asyncio.process.duration":
                for point in metric.data.data_points:
                    self.assertEqual(point.attributes["type"], "coroutine")
                    self.assertIn(
                        point.attributes["name"],
                        ["cancellation_coro", "cancellable_coroutine"],
                    )
            if metric.name == "asyncio.process.created":
                for point in metric.data.data_points:
                    self.assertEqual(point.attributes["type"], "coroutine")
                    self.assertIn(
                        point.attributes["name"],
                        ["cancellation_coro", "cancellable_coroutine"],
                    )
                    self.assertIn(
                        point.attributes["state"], ["finished", "cancelled"]
                    )
