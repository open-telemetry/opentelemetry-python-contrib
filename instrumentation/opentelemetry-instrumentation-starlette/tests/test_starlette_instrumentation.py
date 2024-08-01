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

import unittest
from timeit import default_timer
from unittest.mock import patch

from starlette import applications
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route
from starlette.testclient import TestClient
from starlette.websockets import WebSocket

import opentelemetry.instrumentation.starlette as otel_starlette
from opentelemetry.sdk.metrics.export import (
    HistogramDataPoint,
    NumberDataPoint,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.globals_test import reset_trace_globals
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import (
    NoOpTracerProvider,
    SpanKind,
    get_tracer,
    set_tracer_provider,
)
from opentelemetry.util.http import (
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE,
    _active_requests_count_attrs,
    _duration_attrs,
    get_excluded_urls,
)

_expected_metric_names = [
    "http.server.active_requests",
    "http.server.duration",
    "http.server.response.size",
    "http.server.request.size",
]
_recommended_attrs = {
    "http.server.active_requests": _active_requests_count_attrs,
    "http.server.duration": _duration_attrs,
    "http.server.response.size": _duration_attrs,
    "http.server.request.size": _duration_attrs,
}


class TestStarletteManualInstrumentation(TestBase):
    def _create_app(self):
        app = self._create_starlette_app()
        self._instrumentor.instrument_app(
            app=app,
            server_request_hook=getattr(self, "server_request_hook", None),
            client_request_hook=getattr(self, "client_request_hook", None),
            client_response_hook=getattr(self, "client_response_hook", None),
        )
        return app

    def setUp(self):
        super().setUp()
        self.env_patch = patch.dict(
            "os.environ",
            {"OTEL_PYTHON_STARLETTE_EXCLUDED_URLS": "/exclude/123,healthzz"},
        )
        self.env_patch.start()
        self.exclude_patch = patch(
            "opentelemetry.instrumentation.starlette._excluded_urls",
            get_excluded_urls("STARLETTE"),
        )
        self.exclude_patch.start()
        self._instrumentor = otel_starlette.StarletteInstrumentor()
        self._app = self._create_app()
        self._client = TestClient(self._app)

    def tearDown(self):
        super().tearDown()
        self.env_patch.stop()
        self.exclude_patch.stop()

    def test_basic_starlette_call(self):
        self._client.get("/foobar")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 3)
        for span in spans:
            self.assertIn("GET /foobar", span.name)
            self.assertEqual(
                span.instrumentation_scope.name,
                "opentelemetry.instrumentation.starlette",
            )

    def test_sub_app_starlette_call(self):
        """
        This test is to ensure that a span in case of a sub app targeted contains the correct server url
        """

        self._client.get("/sub/home")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 3)
        for span in spans:
            # As we are only looking to the "outer" app, we would see only the "GET /sub" spans
            self.assertIn("GET /sub", span.name)

        # We now want to specifically test all spans including the
        # - HTTP_TARGET
        # - HTTP_URL
        # attributes to be populated with the expected values
        spans_with_http_attributes = [
            span
            for span in spans
            if (
                SpanAttributes.HTTP_URL in span.attributes
                or SpanAttributes.HTTP_TARGET in span.attributes
            )
        ]

        # expect only one span to have the attributes
        self.assertEqual(1, len(spans_with_http_attributes))

        for span in spans_with_http_attributes:
            self.assertEqual(
                "/sub/home", span.attributes[SpanAttributes.HTTP_TARGET]
            )
            self.assertEqual(
                "http://testserver/sub/home",
                span.attributes[SpanAttributes.HTTP_URL],
            )

    def test_starlette_route_attribute_added(self):
        """Ensure that starlette routes are used as the span name."""
        self._client.get("/user/123")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 3)
        for span in spans:
            self.assertIn("GET /user/{username}", span.name)
        self.assertEqual(
            spans[-1].attributes[SpanAttributes.HTTP_ROUTE], "/user/{username}"
        )
        # ensure that at least one attribute that is populated by
        # the asgi instrumentation is successfully feeding though.
        self.assertEqual(
            spans[-1].attributes[SpanAttributes.HTTP_FLAVOR], "1.1"
        )

    def test_starlette_excluded_urls(self):
        """Ensure that given starlette routes are excluded."""
        self._client.get("/healthzz")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_starlette_metrics(self):
        self._client.get("/foobar")
        self._client.get("/foobar")
        self._client.get("/foobar")
        metrics_list = self.memory_metrics_reader.get_metrics_data()
        number_data_point_seen = False
        histogram_data_point_seen = False
        self.assertTrue(len(metrics_list.resource_metrics) == 1)
        for resource_metric in metrics_list.resource_metrics:
            self.assertTrue(len(resource_metric.scope_metrics) == 1)
            for scope_metric in resource_metric.scope_metrics:
                self.assertEqual(
                    scope_metric.scope.name,
                    "opentelemetry.instrumentation.starlette",
                )
                self.assertTrue(len(scope_metric.metrics) == 3)
                for metric in scope_metric.metrics:
                    self.assertIn(metric.name, _expected_metric_names)
                    data_points = list(metric.data.data_points)
                    self.assertEqual(len(data_points), 1)
                    for point in data_points:
                        if isinstance(point, HistogramDataPoint):
                            self.assertEqual(point.count, 3)
                            histogram_data_point_seen = True
                        if isinstance(point, NumberDataPoint):
                            number_data_point_seen = True
                        for attr in point.attributes:
                            self.assertIn(
                                attr, _recommended_attrs[metric.name]
                            )
        self.assertTrue(number_data_point_seen and histogram_data_point_seen)

    def test_basic_post_request_metric_success(self):
        start = default_timer()
        expected_duration_attributes = {
            "http.flavor": "1.1",
            "http.host": "testserver",
            "http.method": "POST",
            "http.scheme": "http",
            "http.server_name": "testserver",
            "http.status_code": 405,
            "net.host.port": 80,
        }
        expected_requests_count_attributes = {
            "http.flavor": "1.1",
            "http.host": "testserver",
            "http.method": "POST",
            "http.scheme": "http",
            "http.server_name": "testserver",
        }
        response = self._client.post(
            "/foobar",
            json={"foo": "bar"},
        )
        duration = max(round((default_timer() - start) * 1000), 0)
        response_size = int(response.headers.get("content-length"))
        request_size = int(response.request.headers.get("content-length"))
        metrics_list = self.memory_metrics_reader.get_metrics_data()
        for metric in (
            metrics_list.resource_metrics[0].scope_metrics[0].metrics
        ):
            for point in list(metric.data.data_points):
                if isinstance(point, HistogramDataPoint):
                    self.assertEqual(point.count, 1)
                    self.assertDictEqual(
                        dict(point.attributes), expected_duration_attributes
                    )
                    if metric.name == "http.server.duration":
                        self.assertAlmostEqual(duration, point.sum, delta=30)
                    elif metric.name == "http.server.response.size":
                        self.assertEqual(response_size, point.sum)
                    elif metric.name == "http.server.request.size":
                        self.assertEqual(request_size, point.sum)
                if isinstance(point, NumberDataPoint):
                    self.assertDictEqual(
                        expected_requests_count_attributes,
                        dict(point.attributes),
                    )
                    self.assertEqual(point.value, 0)

    def test_metric_for_uninstrment_app_method(self):
        self._client.get("/foobar")
        # uninstrumenting the existing client app
        self._instrumentor.uninstrument_app(self._app)
        self._client.get("/foobar")
        self._client.get("/foobar")
        metrics_list = self.memory_metrics_reader.get_metrics_data()
        for metric in (
            metrics_list.resource_metrics[0].scope_metrics[0].metrics
        ):
            for point in list(metric.data.data_points):
                if isinstance(point, HistogramDataPoint):
                    self.assertEqual(point.count, 1)
                if isinstance(point, NumberDataPoint):
                    self.assertEqual(point.value, 0)

    def test_metric_uninstrument_inherited_by_base(self):
        # instrumenting class and creating app to send request
        self._instrumentor.instrument()
        app = self._create_starlette_app()
        client = TestClient(app)
        client.get("/foobar")
        # calling uninstrument and checking for telemetry data
        self._instrumentor.uninstrument()
        client.get("/foobar")
        client.get("/foobar")
        client.get("/foobar")
        metrics_list = self.memory_metrics_reader.get_metrics_data()
        for metric in (
            metrics_list.resource_metrics[0].scope_metrics[0].metrics
        ):
            for point in list(metric.data.data_points):
                if isinstance(point, HistogramDataPoint):
                    self.assertEqual(point.count, 1)
                if isinstance(point, NumberDataPoint):
                    self.assertEqual(point.value, 0)

    @staticmethod
    def _create_starlette_app():
        def home(_):
            return PlainTextResponse("hi")

        def health(_):
            return PlainTextResponse("ok")

        def sub_home(_):
            return PlainTextResponse("sub hi")

        sub_app = applications.Starlette(routes=[Route("/home", sub_home)])

        app = applications.Starlette(
            routes=[
                Route("/foobar", home),
                Route("/user/{username}", home),
                Route("/healthzz", health),
                Mount("/sub", app=sub_app),
            ],
        )

        return app


class TestStarletteManualInstrumentationHooks(
    TestStarletteManualInstrumentation
):
    _server_request_hook = None
    _client_request_hook = None
    _client_response_hook = None

    def server_request_hook(self, span, scope):
        if self._server_request_hook is not None:
            self._server_request_hook(span, scope)

    def client_request_hook(self, receive_span, scope, message):
        if self._client_request_hook is not None:
            self._client_request_hook(receive_span, scope, message)

    def client_response_hook(self, send_span, scope, message):
        if self._client_response_hook is not None:
            self._client_response_hook(send_span, scope, message)

    def test_hooks(self):
        def server_request_hook(span, scope):
            span.update_name("name from server hook")

        def client_request_hook(receive_span, scope, message):
            receive_span.update_name("name from client hook")
            receive_span.set_attribute("attr-from-request-hook", "set")

        def client_response_hook(send_span, scope, message):
            send_span.update_name("name from response hook")
            send_span.set_attribute("attr-from-response-hook", "value")

        self._server_request_hook = server_request_hook
        self._client_request_hook = client_request_hook
        self._client_response_hook = client_response_hook

        self._client.get("/foobar")
        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(
            len(spans), 3
        )  # 1 server span and 2 response spans (response start and body)

        server_span = spans[2]
        self.assertEqual(server_span.name, "name from server hook")

        response_spans = spans[:2]
        for span in response_spans:
            self.assertEqual(span.name, "name from response hook")
            self.assertSpanHasAttributes(
                span, {"attr-from-response-hook": "value"}
            )


class TestAutoInstrumentation(TestStarletteManualInstrumentation):
    """Test the auto-instrumented variant

    Extending the manual instrumentation as most test cases apply
    to both.
    """

    def _create_app(self):
        # instrumentation is handled by the instrument call
        resource = Resource.create({"key1": "value1", "key2": "value2"})
        result = self.create_tracer_provider(resource=resource)
        tracer_provider, exporter = result
        self.memory_exporter = exporter

        self._instrumentor.instrument(tracer_provider=tracer_provider)

        return self._create_starlette_app()

    def tearDown(self):
        self._instrumentor.uninstrument()
        super().tearDown()

    def test_request(self):
        self._client.get("/foobar")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 3)
        for span in spans:
            self.assertEqual(span.resource.attributes["key1"], "value1")
            self.assertEqual(span.resource.attributes["key2"], "value2")

    def test_uninstrument(self):
        self._client.get("/foobar")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 3)

        self.memory_exporter.clear()
        self._instrumentor.uninstrument()

        self._client.get("/foobar")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_no_op_tracer_provider(self):
        self._client.get("/foobar")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 3)

        self.memory_exporter.clear()
        self._instrumentor.uninstrument()

        tracer_provider = NoOpTracerProvider()
        self._instrumentor.instrument(tracer_provider=tracer_provider)

        self._client.get("/foobar")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_sub_app_starlette_call(self):
        """
        !!! Attention: we need to override this testcase for the auto-instrumented variant
            The reason is, that with auto instrumentation, the sub app is instrumented as well
            and therefore we would see the spans for the sub app as well

        This test is to ensure that a span in case of a sub app targeted contains the correct server url
        """

        self._client.get("/sub/home")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 6)

        for span in spans:
            # As we are only looking to the "outer" app, we would see only the "GET /sub" spans
            #   -> the outer app is not aware of the sub_apps internal routes
            sub_in = "GET /sub" in span.name
            # The sub app spans are named GET /home as from the sub app perspective the request targets /home
            #   -> the sub app is technically not aware of the /sub prefix
            home_in = "GET /home" in span.name

            # We expect the spans to be either from the outer app or the sub app
            self.assertTrue(
                sub_in or home_in,
                f"Span {span.name} does not have /sub or /home in its name",
            )

        # We now want to specifically test all spans including the
        # - HTTP_TARGET
        # - HTTP_URL
        # attributes to be populated with the expected values
        spans_with_http_attributes = [
            span
            for span in spans
            if (
                SpanAttributes.HTTP_URL in span.attributes
                or SpanAttributes.HTTP_TARGET in span.attributes
            )
        ]

        # We now expect spans with attributes from both the app and its sub app
        self.assertEqual(2, len(spans_with_http_attributes))

        # Due to a potential bug in starlettes handling of sub app mounts, we can
        # check only the server kind spans for the correct attributes
        # The internal one generated by the sub app is not yet producing the correct attributes
        server_span = next(
            (
                span
                for span in spans_with_http_attributes
                if span.kind == SpanKind.SERVER
            ),
            None,
        )

        self.assertIsNotNone(server_span)
        # As soon as the bug is fixed for starlette, we can iterate over spans_with_http_attributes here
        # to verify the correctness of the attributes for the internal span as well
        self.assertEqual(
            "/sub/home", server_span.attributes[SpanAttributes.HTTP_TARGET]
        )
        self.assertEqual(
            "http://testserver/sub/home",
            server_span.attributes[SpanAttributes.HTTP_URL],
        )


class TestAutoInstrumentationHooks(TestStarletteManualInstrumentationHooks):
    """
    Test the auto-instrumented variant for request and response hooks
    """

    def _create_app(self):
        # instrumentation is handled by the instrument call
        self._instrumentor.instrument(
            server_request_hook=getattr(self, "server_request_hook", None),
            client_request_hook=getattr(self, "client_request_hook", None),
            client_response_hook=getattr(self, "client_response_hook", None),
        )

        return self._create_starlette_app()

    def tearDown(self):
        self._instrumentor.uninstrument()
        super().tearDown()

    def test_sub_app_starlette_call(self):
        """
        !!! Attention: we need to override this testcase for the auto-instrumented variant
            The reason is, that with auto instrumentation, the sub app is instrumented as well
            and therefore we would see the spans for the sub app as well

        This test is to ensure that a span in case of a sub app targeted contains the correct server url
        """

        self._client.get("/sub/home")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 6)

        for span in spans:
            # As we are only looking to the "outer" app, we would see only the "GET /sub" spans
            #   -> the outer app is not aware of the sub_apps internal routes
            sub_in = "GET /sub" in span.name
            # The sub app spans are named GET /home as from the sub app perspective the request targets /home
            #   -> the sub app is technically not aware of the /sub prefix
            home_in = "GET /home" in span.name

            # We expect the spans to be either from the outer app or the sub app
            self.assertTrue(
                sub_in or home_in,
                f"Span {span.name} does not have /sub or /home in its name",
            )

        # We now want to specifically test all spans including the
        # - HTTP_TARGET
        # - HTTP_URL
        # attributes to be populated with the expected values
        spans_with_http_attributes = [
            span
            for span in spans
            if (
                SpanAttributes.HTTP_URL in span.attributes
                or SpanAttributes.HTTP_TARGET in span.attributes
            )
        ]

        # We now expect spans with attributes from both the app and its sub app
        self.assertEqual(2, len(spans_with_http_attributes))

        # Due to a potential bug in starlettes handling of sub app mounts, we can
        # check only the server kind spans for the correct attributes
        # The internal one generated by the sub app is not yet producing the correct attributes
        server_span = next(
            (
                span
                for span in spans_with_http_attributes
                if span.kind == SpanKind.SERVER
            ),
            None,
        )

        self.assertIsNotNone(server_span)
        # As soon as the bug is fixed for starlette, we can iterate over spans_with_http_attributes here
        # to verify the correctness of the attributes for the internal span as well
        self.assertEqual(
            "/sub/home", server_span.attributes[SpanAttributes.HTTP_TARGET]
        )
        self.assertEqual(
            "http://testserver/sub/home",
            server_span.attributes[SpanAttributes.HTTP_URL],
        )


class TestAutoInstrumentationLogic(unittest.TestCase):
    def test_instrumentation(self):
        """Verify that instrumentation methods are instrumenting and
        removing as expected.
        """
        instrumentor = otel_starlette.StarletteInstrumentor()
        original = applications.Starlette
        instrumentor.instrument()
        try:
            instrumented = applications.Starlette
            self.assertIsNot(original, instrumented)
        finally:
            instrumentor.uninstrument()

        should_be_original = applications.Starlette
        self.assertIs(original, should_be_original)


class TestConditonalServerSpanCreation(TestStarletteManualInstrumentation):
    def test_mark_span_internal_in_presence_of_another_span(self):
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span(
            "test", kind=SpanKind.SERVER
        ) as parent_span:
            self._client.get("/foobar")
            spans = self.sorted_spans(
                self.memory_exporter.get_finished_spans()
            )
            starlette_span = spans[2]
            self.assertEqual(SpanKind.INTERNAL, starlette_span.kind)
            self.assertEqual(SpanKind.SERVER, parent_span.kind)
            self.assertEqual(
                parent_span.context.span_id, starlette_span.parent.span_id
            )


class TestBaseWithCustomHeaders(TestBase):
    def create_app(self):
        app = self.create_starlette_app()
        self._instrumentor.instrument_app(app=app)
        return app

    def setUp(self):
        super().setUp()
        self._instrumentor = otel_starlette.StarletteInstrumentor()
        self._app = self.create_app()
        self._client = TestClient(self._app)

    def tearDown(self) -> None:
        super().tearDown()
        with self.disable_logging():
            self._instrumentor.uninstrument()

    @staticmethod
    def create_starlette_app():
        app = applications.Starlette()

        @app.route("/foobar")
        def _(request):
            return PlainTextResponse(
                content="hi",
                headers={
                    "custom-test-header-1": "test-header-value-1",
                    "custom-test-header-2": "test-header-value-2",
                    "my-custom-regex-header-1": "my-custom-regex-value-1,my-custom-regex-value-2",
                    "My-Custom-Regex-Header-2": "my-custom-regex-value-3,my-custom-regex-value-4",
                    "my-secret-header": "my-secret-value",
                },
            )

        @app.websocket_route("/foobar_web")
        async def _(websocket: WebSocket) -> None:
            message = await websocket.receive()
            if message.get("type") == "websocket.connect":
                await websocket.send(
                    {
                        "type": "websocket.accept",
                        "headers": [
                            (b"custom-test-header-1", b"test-header-value-1"),
                            (b"custom-test-header-2", b"test-header-value-2"),
                            (
                                b"my-custom-regex-header-1",
                                b"my-custom-regex-value-1,my-custom-regex-value-2",
                            ),
                            (
                                b"My-Custom-Regex-Header-2",
                                b"my-custom-regex-value-3,my-custom-regex-value-4",
                            ),
                            (b"my-secret-header", b"my-secret-value"),
                        ],
                    }
                )
                await websocket.send_json({"message": "hello world"})
                await websocket.close()
            if message.get("type") == "websocket.disconnect":
                pass

        return app


class TestHTTPAppWithCustomHeaders(TestBaseWithCustomHeaders):
    @patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS: ".*my-secret.*",
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3,Regex-Test-Header-.*,Regex-Invalid-Test-Header-.*,.*my-secret.*",
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3,my-custom-regex-header-.*,invalid-regex-header-.*,.*my-secret.*",
        },
    )
    def setUp(self) -> None:
        super().setUp()

    def test_custom_request_headers_in_span_attributes(self):
        expected = {
            "http.request.header.custom_test_header_1": (
                "test-header-value-1",
            ),
            "http.request.header.custom_test_header_2": (
                "test-header-value-2",
            ),
            "http.request.header.regex_test_header_1": ("Regex Test Value 1",),
            "http.request.header.regex_test_header_2": (
                "RegexTestValue2,RegexTestValue3",
            ),
            "http.request.header.my_secret_header": ("[REDACTED]",),
        }
        resp = self._client.get(
            "/foobar",
            headers={
                "custom-test-header-1": "test-header-value-1",
                "custom-test-header-2": "test-header-value-2",
                "Regex-Test-Header-1": "Regex Test Value 1",
                "regex-test-header-2": "RegexTestValue2,RegexTestValue3",
                "My-Secret-Header": "My Secret Value",
            },
        )
        self.assertEqual(200, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 3)

        server_span = [
            span for span in span_list if span.kind == SpanKind.SERVER
        ][0]

        self.assertSpanHasAttributes(server_span, expected)

    @patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS: ".*my-secret.*",
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3,Regex-Test-Header-.*,Regex-Invalid-Test-Header-.*,.*my-secret.*",
        },
    )
    def test_custom_request_headers_not_in_span_attributes(self):
        not_expected = {
            "http.request.header.custom_test_header_3": (
                "test-header-value-3",
            ),
        }
        resp = self._client.get(
            "/foobar",
            headers={
                "custom-test-header-1": "test-header-value-1",
                "custom-test-header-2": "test-header-value-2",
                "Regex-Test-Header-1": "Regex Test Value 1",
                "regex-test-header-2": "RegexTestValue2,RegexTestValue3",
                "My-Secret-Header": "My Secret Value",
            },
        )
        self.assertEqual(200, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 3)

        server_span = [
            span for span in span_list if span.kind == SpanKind.SERVER
        ][0]

        for key in not_expected:
            self.assertNotIn(key, server_span.attributes)

    def test_custom_response_headers_in_span_attributes(self):
        expected = {
            "http.response.header.custom_test_header_1": (
                "test-header-value-1",
            ),
            "http.response.header.custom_test_header_2": (
                "test-header-value-2",
            ),
            "http.response.header.my_custom_regex_header_1": (
                "my-custom-regex-value-1,my-custom-regex-value-2",
            ),
            "http.response.header.my_custom_regex_header_2": (
                "my-custom-regex-value-3,my-custom-regex-value-4",
            ),
            "http.response.header.my_secret_header": ("[REDACTED]",),
        }
        resp = self._client.get("/foobar")
        self.assertEqual(200, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 3)

        server_span = [
            span for span in span_list if span.kind == SpanKind.SERVER
        ][0]

        self.assertSpanHasAttributes(server_span, expected)

    def test_custom_response_headers_not_in_span_attributes(self):
        not_expected = {
            "http.response.header.custom_test_header_3": (
                "test-header-value-3",
            ),
        }
        resp = self._client.get("/foobar")
        self.assertEqual(200, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 3)

        server_span = [
            span for span in span_list if span.kind == SpanKind.SERVER
        ][0]

        for key in not_expected:
            self.assertNotIn(key, server_span.attributes)


class TestWebSocketAppWithCustomHeaders(TestBaseWithCustomHeaders):
    @patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS: ".*my-secret.*",
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3,Regex-Test-Header-.*,Regex-Invalid-Test-Header-.*,.*my-secret.*",
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3,my-custom-regex-header-.*,invalid-regex-header-.*,.*my-secret.*",
        },
    )
    def setUp(self) -> None:
        super().setUp()

    def test_custom_request_headers_in_span_attributes(self):
        expected = {
            "http.request.header.custom_test_header_1": (
                "test-header-value-1",
            ),
            "http.request.header.custom_test_header_2": (
                "test-header-value-2",
            ),
            "http.request.header.regex_test_header_1": ("Regex Test Value 1",),
            "http.request.header.regex_test_header_2": (
                "RegexTestValue2,RegexTestValue3",
            ),
            "http.request.header.my_secret_header": ("[REDACTED]",),
        }
        with self._client.websocket_connect(
            "/foobar_web",
            headers={
                "custom-test-header-1": "test-header-value-1",
                "custom-test-header-2": "test-header-value-2",
                "Regex-Test-Header-1": "Regex Test Value 1",
                "regex-test-header-2": "RegexTestValue2,RegexTestValue3",
                "My-Secret-Header": "My Secret Value",
            },
        ) as websocket:
            data = websocket.receive_json()
            self.assertEqual(data, {"message": "hello world"})

        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 5)

        server_span = [
            span for span in span_list if span.kind == SpanKind.SERVER
        ][0]
        self.assertSpanHasAttributes(server_span, expected)

    def test_custom_request_headers_not_in_span_attributes(self):
        not_expected = {
            "http.request.header.custom_test_header_3": (
                "test-header-value-3",
            ),
        }
        with self._client.websocket_connect(
            "/foobar_web",
            headers={
                "custom-test-header-1": "test-header-value-1",
                "custom-test-header-2": "test-header-value-2",
                "Regex-Test-Header-1": "Regex Test Value 1",
                "regex-test-header-2": "RegexTestValue2,RegexTestValue3",
                "My-Secret-Header": "My Secret Value",
            },
        ) as websocket:
            data = websocket.receive_json()
            self.assertEqual(data, {"message": "hello world"})

        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 5)

        server_span = [
            span for span in span_list if span.kind == SpanKind.SERVER
        ][0]

        for key, _ in not_expected.items():
            self.assertNotIn(key, server_span.attributes)

    def test_custom_response_headers_in_span_attributes(self):
        expected = {
            "http.response.header.custom_test_header_1": (
                "test-header-value-1",
            ),
            "http.response.header.custom_test_header_2": (
                "test-header-value-2",
            ),
            "http.response.header.my_custom_regex_header_1": (
                "my-custom-regex-value-1,my-custom-regex-value-2",
            ),
            "http.response.header.my_custom_regex_header_2": (
                "my-custom-regex-value-3,my-custom-regex-value-4",
            ),
            "http.response.header.my_secret_header": ("[REDACTED]",),
        }
        with self._client.websocket_connect("/foobar_web") as websocket:
            data = websocket.receive_json()
            self.assertEqual(data, {"message": "hello world"})

        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 5)

        server_span = [
            span for span in span_list if span.kind == SpanKind.SERVER
        ][0]

        self.assertSpanHasAttributes(server_span, expected)

    def test_custom_response_headers_not_in_span_attributes(self):
        not_expected = {
            "http.response.header.custom_test_header_3": (
                "test-header-value-3",
            ),
        }
        with self._client.websocket_connect("/foobar_web") as websocket:
            data = websocket.receive_json()
            self.assertEqual(data, {"message": "hello world"})

        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 5)

        server_span = [
            span for span in span_list if span.kind == SpanKind.SERVER
        ][0]

        for key, _ in not_expected.items():
            self.assertNotIn(key, server_span.attributes)


@patch.dict(
    "os.environ",
    {
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS: ".*my-secret.*",
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3,Regex-Test-Header-.*,Regex-Invalid-Test-Header-.*,.*my-secret.*",
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3,my-custom-regex-header-.*,invalid-regex-header-.*,.*my-secret.*",
    },
)
class TestNonRecordingSpanWithCustomHeaders(TestBaseWithCustomHeaders):
    def setUp(self):
        super().setUp()
        reset_trace_globals()
        set_tracer_provider(tracer_provider=NoOpTracerProvider())

        self._app = self.create_app()
        self._client = TestClient(self._app)

    def test_custom_header_not_present_in_non_recording_span(self):
        resp = self._client.get(
            "/foobar",
            headers={
                "custom-test-header-1": "test-header-value-1",
            },
        )
        self.assertEqual(200, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 0)
