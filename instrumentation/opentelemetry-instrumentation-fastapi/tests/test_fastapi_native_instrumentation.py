# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import Mock

import fastapi
import pytest
from fastapi.testclient import TestClient
from starlette.background import BackgroundTask

import opentelemetry.instrumentation.fastapi as otel_fastapi
from opentelemetry.sdk.metrics.export import Histogram
from opentelemetry.semconv.attributes.http_attributes import (
    HTTP_REQUEST_METHOD,
    HTTP_RESPONSE_STATUS_CODE,
    HTTP_ROUTE,
)
from opentelemetry.semconv.metrics.http_metrics import HTTP_SERVER_REQUEST_DURATION
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind

pytestmark = pytest.mark.skipif(
    otel_fastapi.telemetry is None,
    reason="FastAPI does not provide native OpenTelemetry instrumentation",
)


class TestNativeFastAPI(TestBase):
    def tearDown(self) -> None:
        with self.disable_logging():
            otel_fastapi.FastAPIInstrumentor().uninstrument()
        super().tearDown()

    def test_instrument_app_leaves_application_unchanged(self) -> None:
        app = fastapi.FastAPI()
        original_build = app.build_middleware_stack
        original_background_call = BackgroundTask.__call__

        with self.assertLogs(otel_fastapi.__name__, level="WARNING") as logs:
            otel_fastapi.FastAPIInstrumentor.instrument_app(app)
        self.assertIn("Configure telemetry directly in FastAPI", logs.output[0])

        otel_fastapi.FastAPIInstrumentor.uninstrument_app(app)
        otel_fastapi.FastAPIInstrumentor.uninstrument_app(app)

        self.assertEqual(app.build_middleware_stack, original_build)
        self.assertIsNone(app.middleware_stack)
        self.assertEqual(app.user_middleware, [])
        self.assertFalse(hasattr(app, "_is_instrumented_by_opentelemetry"))
        self.assertIs(BackgroundTask.__call__, original_background_call)

    def test_instrument_and_uninstrument_leave_fastapi_class_unchanged(self) -> None:
        original_fastapi = fastapi.FastAPI
        original_background_call = BackgroundTask.__call__
        instrumentor = otel_fastapi.FastAPIInstrumentor()

        for _ in range(2):
            with self.assertLogs(otel_fastapi.__name__, level="WARNING"):
                instrumentor.instrument()
            self.assertIs(fastapi.FastAPI, original_fastapi)
            instrumentor.uninstrument()
            self.assertIs(fastapi.FastAPI, original_fastapi)

        self.assertIs(BackgroundTask.__call__, original_background_call)

    def test_manual_instrumentation_preserves_native_spans_and_metrics(self) -> None:
        self._check_native_telemetry(automatic=False)

    def test_auto_instrumentation_preserves_native_spans_and_metrics(self) -> None:
        self._check_native_telemetry(automatic=True)

    def _check_native_telemetry(self, automatic: bool) -> None:
        instrumentor = otel_fastapi.FastAPIInstrumentor()
        request_hook = Mock()
        if automatic:
            with self.disable_logging():
                instrumentor.instrument(server_request_hook=request_hook)
        app = fastapi.FastAPI(telemetry={"auto_configure": False})
        if not automatic:
            with self.disable_logging():
                instrumentor.instrument_app(app, server_request_hook=request_hook)

        @app.get("/sync/{item_id}")
        def sync_endpoint(item_id: int) -> dict[str, int]:
            return {"item_id": item_id}

        @app.get("/async/{item_id}")
        async def async_endpoint(item_id: int) -> dict[str, int]:
            return {"item_id": item_id}

        # Cleanup must leave native telemetry working, even for a running app.
        with TestClient(app) as client:
            self.assertEqual(client.get("/sync/1").json(), {"item_id": 1})
            if automatic:
                instrumentor.uninstrument()
            else:
                instrumentor.uninstrument_app(app)
            self.assertEqual(client.get("/async/2").json(), {"item_id": 2})

        request_hook.assert_not_called()
        spans = self.memory_exporter.get_finished_spans()
        self.assertTrue(spans)
        self.assertTrue(all(span.instrumentation_scope.name == "fastapi" for span in spans))
        server_spans = [span for span in spans if span.kind == SpanKind.SERVER]
        self.assertEqual(len(server_spans), 2)
        for span, route in zip(server_spans, ("/sync/{item_id}", "/async/{item_id}")):
            self.assertSpanHasAttributes(
                span,
                {
                    HTTP_REQUEST_METHOD: "GET",
                    HTTP_RESPONSE_STATUS_CODE: 200,
                    HTTP_ROUTE: route,
                },
            )

        metrics_data = self.memory_metrics_reader.get_metrics_data()
        self.assertIsNotNone(metrics_data)
        self.assertEqual(len(metrics_data.resource_metrics), 1)
        scope_metrics = metrics_data.resource_metrics[0].scope_metrics
        self.assertEqual(len(scope_metrics), 1)
        self.assertEqual(scope_metrics[0].scope.name, "fastapi")
        duration = next(metric for metric in scope_metrics[0].metrics if metric.name == HTTP_SERVER_REQUEST_DURATION)
        self.assertIsInstance(duration.data, Histogram)
        self.assertEqual(sum(point.count for point in duration.data.data_points), 2)
        self.assertEqual(
            {point.attributes[HTTP_ROUTE] for point in duration.data.data_points},
            {"/sync/{item_id}", "/async/{item_id}"},
        )

    def test_instrumentation_respects_disabled_native_telemetry(self) -> None:
        app = fastapi.FastAPI(telemetry={"tracing": False, "metrics": False, "logs": False})
        with self.disable_logging():
            otel_fastapi.FastAPIInstrumentor.instrument_app(app)

        @app.get("/")
        async def endpoint() -> dict[str, str]:
            return {"message": "hello"}

        with TestClient(app) as client:
            self.assertEqual(client.get("/").status_code, 200)
        self.assertEqual(self.memory_exporter.get_finished_spans(), ())
        self.assertEqual(self.get_sorted_metrics(), [])
