import asyncio
from unittest.mock import patch

import pytest

from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
from opentelemetry.instrumentation.asyncio.environment_variables import (
    OTEL_PYTHON_ASYNCIO_FUTURE_TRACE_ENABLED,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import get_tracer


class TestTraceFuture(TestBase):
    @patch.dict(
        "os.environ", {OTEL_PYTHON_ASYNCIO_FUTURE_TRACE_ENABLED: "true"}
    )
    def setUp(self):
        super().setUp()
        self._tracer = get_tracer(
            __name__,
        )
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.instrumentor = AsyncioInstrumentor()
        self.instrumentor.instrument()

    def tearDown(self):
        super().tearDown()
        self.instrumentor.uninstrument()
        self.loop.close()

    @pytest.mark.asyncio
    def test_trace_future_cancelled(self):
        with self._tracer.start_as_current_span("root"):
            future = asyncio.Future()
            future = self.instrumentor.trace_future(future)
            future.cancel()
        try:
            self.loop.run_until_complete(future)
        except asyncio.CancelledError as exc:
            self.assertEqual(isinstance(exc, asyncio.CancelledError), True)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        self.assertEqual(spans[0].name, "root")
        self.assertEqual(spans[1].name, "asyncio future")
        for metric in (
            self.memory_metrics_reader.get_metrics_data()
            .resource_metrics[0]
            .scope_metrics[0]
            .metrics
        ):
            for point in metric.data.data_points:
                self.assertEqual(point.attributes["type"], "future")
                self.assertEqual(point.attributes["state"], "cancelled")
