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

        @self.app.get("/user/{username}")
        async def _(username: str):
            return {"username": username}

        otel_fastapi.FastAPIInstrumentor().instrument_app(
            self.app, render_path_parameters=True
        )
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

    def test_render_path_parameters(self):
        """Test that path parameters are rendered correctly in spans."""

        # Make sure non-path parameters are not affected
        resp = self.client.get("/foobar")
        self.assertEqual(resp.status_code, 200)
        spans = self.memory_exporter.get_finished_spans()
        expected_span_name = "GET /foobar http send"
        self.assertEqual(
            spans[0].name,
            expected_span_name,
            f"Expected span name to be '{expected_span_name}', but got '{spans[0].name}'",
        )

        # Make a request to the endpoint with a path parameter
        resp = self.client.get("/user/johndoe")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"username": "johndoe"})

        # Retrieve the spans generated
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 3)  # Adjust based on expected spans

        # Check that the span for the request contains the expected attributes
        server_span = [
            span for span in spans if span.kind == trace.SpanKind.SERVER
        ][0]

        # Verify that the path parameter is rendered correctly
        self.assertIn("http.route", server_span.attributes)
        self.assertEqual(
            server_span.attributes["http.route"], "/user/{username}"
        )

        # Optionally, check if the username is also included in the span attributes
        self.assertIn("http.path_parameters.username", server_span.attributes)
        self.assertEqual(
            server_span.attributes["http.path_parameters.username"], "johndoe"
        )

        # Retrieve the spans generated
        spans = self.memory_exporter.get_finished_spans()

        # Assert that at least one span was created
        self.assertGreater(len(spans), 0, "No spans were generated.")

        # Assert that the span name is as expected
        expected_span_name = (
            "GET /user/johndoe"  # Adjust this based on your implementation
        )
        self.assertEqual(
            spans[0].name,
            expected_span_name,
            f"Expected span name to be '{expected_span_name}', but got '{spans[0].name}'",
        )
