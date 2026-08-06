# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
import fastapi
from starlette.testclient import TestClient

import opentelemetry.instrumentation.fastapi as otel_fastapi
from opentelemetry import trace
from opentelemetry.test.test_base import TestBase


class TestWrappedApplication(TestBase):
    def setUp(self):
        super().setUp()

        self.app = fastapi.FastAPI()

        @self.app.get("/foobar")
        async def _():
            return {"message": "hello world"}

        otel_fastapi.FastAPIInstrumentor().instrument_app(self.app)
        self.client = TestClient(self.app)
        self.tracer = self.tracer_provider.get_tracer(__name__)

    def tearDown(self) -> None:
        super().tearDown()
        with self.disable_logging():
            otel_fastapi.FastAPIInstrumentor().uninstrument_app(self.app)

    def test_mark_span_internal_in_presence_of_span_from_other_framework(self):
        with self.tracer.start_as_current_span(
            "test", kind=trace.SpanKind.SERVER
        ) as parent_span:
            resp = self.client.get("/foobar")
            self.assertEqual(200, resp.status_code)

        span_list = self.memory_exporter.get_finished_spans()
        for span in span_list:
            print(str(span.__class__) + ": " + str(span.__dict__))

        # there should be 4 spans - single SERVER "test" and three INTERNAL "FastAPI"
        self.assertEqual(trace.SpanKind.INTERNAL, span_list[0].kind)
        self.assertEqual(trace.SpanKind.INTERNAL, span_list[1].kind)
        # main INTERNAL span - child of test
        self.assertEqual(trace.SpanKind.INTERNAL, span_list[2].kind)
        self.assertEqual(
            parent_span.context.span_id, span_list[2].parent.span_id
        )
        # SERVER "test"
        self.assertEqual(trace.SpanKind.SERVER, span_list[3].kind)
        self.assertEqual(
            parent_span.context.span_id, span_list[3].context.span_id
        )
