# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
import asyncio
from unittest.mock import patch

from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
from opentelemetry.instrumentation.asyncio.environment_variables import (
    OTEL_PYTHON_ASYNCIO_FUTURE_TRACE_ENABLED,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import get_tracer

SCOPE = "opentelemetry.instrumentation.asyncio"
SLEEP_SECONDS = 0.02


class TestAsyncioFuturePending(TestBase):
    @patch.dict("os.environ", {OTEL_PYTHON_ASYNCIO_FUTURE_TRACE_ENABLED: "true"})
    def setUp(self):
        super().setUp()
        self._tracer = get_tracer(__name__)
        self.instrumentor = AsyncioInstrumentor()
        self.instrumentor.instrument()

    def tearDown(self):
        super().tearDown()
        self.instrumentor.uninstrument()

    def test_future_never_completed_does_not_start_span(self):
        pending = []

        async def main():
            with self._tracer.start_as_current_span("root"):
                future = asyncio.Future()
                asyncio.ensure_future(future)
                pending.append(future)
            await asyncio.sleep(0)

        with patch.object(
            self.instrumentor._tracer, "start_span", wraps=self.instrumentor._tracer.start_span
        ) as start_span:
            asyncio.run(main())

        self.assertFalse(pending[0].done())
        # no span is started for a future whose outcome is never known
        start_span.assert_not_called()
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual([span.name for span in spans], ["root"])
        # and no metric is recorded for it either
        self.assertEqual(self.get_sorted_metrics(SCOPE), [])

    def test_future_span_keeps_start_time_and_parent(self):
        async def main():
            with self._tracer.start_as_current_span("root"):
                future = asyncio.Future()
                task = asyncio.ensure_future(future)
            # root has ended, the future is still pending
            await asyncio.sleep(SLEEP_SECONDS)
            future.set_result(1)
            await task

        asyncio.run(main())

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        root = next(span for span in spans if span.name == "root")
        future_span = next(span for span in spans if span.name == "asyncio future")

        # parented to the span that was active when the future was registered
        self.assertEqual(future_span.parent.span_id, root.context.span_id)
        # started when the future was registered, not when it completed
        self.assertLessEqual(future_span.start_time, root.end_time)
        self.assertGreaterEqual(
            (future_span.end_time - future_span.start_time) / 10**9,
            SLEEP_SECONDS * 0.9,
        )

        metrics = self.get_sorted_metrics(SCOPE)
        self.assertEqual(len(metrics), 2)
        self.assertEqual(metrics[0].name, "asyncio.process.created")
        self.assertEqual(metrics[0].data.data_points[0].value, 1)
        self.assertEqual(metrics[0].data.data_points[0].attributes["state"], "finished")
        self.assertEqual(metrics[1].name, "asyncio.process.duration")
        self.assertGreaterEqual(metrics[1].data.data_points[0].sum, SLEEP_SECONDS * 0.9)
