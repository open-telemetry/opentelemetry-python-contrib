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

# pylint: disable=too-many-lines

import unittest
from timeit import default_timer
from unittest.mock import patch

import fastapi
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import opentelemetry.instrumentation.fastapi as otel_fastapi
from opentelemetry import trace
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
    _server_active_requests_count_attrs_new,
    _server_active_requests_count_attrs_old,
    _server_duration_attrs_new,
    _server_duration_attrs_old,
)
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.sdk.metrics.export import (
    HistogramDataPoint,
    NumberDataPoint,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.attributes.http_attributes import (
    HTTP_REQUEST_METHOD,
    HTTP_RESPONSE_STATUS_CODE,
    HTTP_ROUTE,
)
from opentelemetry.semconv.attributes.network_attributes import (
    NETWORK_PROTOCOL_VERSION,
)
from opentelemetry.semconv.attributes.url_attributes import URL_SCHEME
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.globals_test import reset_trace_globals
from opentelemetry.test.test_base import TestBase
from opentelemetry.util.http import (
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE,
    get_excluded_urls,
)

_expected_metric_names_old = [
    "http.server.active_requests",
    "http.server.duration",
    "http.server.response.size",
    "http.server.request.size",
]
_expected_metric_names_new = [
    "http.server.active_requests",
    "http.server.request.duration",
    "http.server.response.body.size",
    "http.server.request.body.size",
]
_expected_metric_names_both = _expected_metric_names_old
_expected_metric_names_both.extend(_expected_metric_names_new)

_recommended_attrs_old = {
    "http.server.active_requests": _server_active_requests_count_attrs_old,
    "http.server.duration": {
        *_server_duration_attrs_old,
        SpanAttributes.HTTP_TARGET,
    },
    "http.server.response.size": {
        *_server_duration_attrs_old,
        SpanAttributes.HTTP_TARGET,
    },
    "http.server.request.size": {
        *_server_duration_attrs_old,
        SpanAttributes.HTTP_TARGET,
    },
}

_recommended_attrs_new = {
    "http.server.active_requests": _server_active_requests_count_attrs_new,
    "http.server.request.duration": _server_duration_attrs_new,
    "http.server.response.body.size": _server_duration_attrs_new,
    "http.server.request.body.size": _server_duration_attrs_new,
}

_recommended_attrs_both = _recommended_attrs_old.copy()
_recommended_attrs_both.update(_recommended_attrs_new)
_recommended_attrs_both["http.server.active_requests"].extend(
    _server_active_requests_count_attrs_old
)


class TestBaseFastAPI(TestBase):
    def _create_app(self):
        app = self._create_fastapi_app()
        self._instrumentor.instrument_app(
            app=app,
            server_request_hook=getattr(self, "server_request_hook", None),
            client_request_hook=getattr(self, "client_request_hook", None),
            client_response_hook=getattr(self, "client_response_hook", None),
        )
        return app

    def _create_app_explicit_excluded_urls(self):
        app = self._create_fastapi_app()
        to_exclude = "/user/123,/foobar"
        self._instrumentor.instrument_app(
            app,
            excluded_urls=to_exclude,
            server_request_hook=getattr(self, "server_request_hook", None),
            client_request_hook=getattr(self, "client_request_hook", None),
            client_response_hook=getattr(self, "client_response_hook", None),
        )
        return app

    @classmethod
    def setUpClass(cls):
        if cls is TestBaseFastAPI:
            raise unittest.SkipTest(
                f"{cls.__name__} is an abstract base class"
            )

        super(TestBaseFastAPI, cls).setUpClass()

    def setUp(self):
        super().setUp()

        test_name = ""
        if hasattr(self, "_testMethodName"):
            test_name = self._testMethodName
        sem_conv_mode = "default"
        if "new_semconv" in test_name:
            sem_conv_mode = "http"
        elif "both_semconv" in test_name:
            sem_conv_mode = "http/dup"
        self.env_patch = patch.dict(
            "os.environ",
            {
                "OTEL_PYTHON_FASTAPI_EXCLUDED_URLS": "/exclude/123,healthzz",
                OTEL_SEMCONV_STABILITY_OPT_IN: sem_conv_mode,
            },
        )
        _OpenTelemetrySemanticConventionStability._initialized = False
        self.env_patch.start()
        self.exclude_patch = patch(
            "opentelemetry.instrumentation.fastapi._excluded_urls_from_env",
            get_excluded_urls("FASTAPI"),
        )
        self.exclude_patch.start()
        self._instrumentor = otel_fastapi.FastAPIInstrumentor()
        self._app = self._create_app()
        self._app.add_middleware(HTTPSRedirectMiddleware)
        self._client = TestClient(self._app)

    def tearDown(self):
        super().tearDown()
        self.env_patch.stop()
        self.exclude_patch.stop()
        with self.disable_logging():
            self._instrumentor.uninstrument()
            self._instrumentor.uninstrument_app(self._app)

    @staticmethod
    def _create_fastapi_app():
        app = fastapi.FastAPI()
        sub_app = fastapi.FastAPI()

        @sub_app.get("/home")
        async def _():
            return {"message": "sub hi"}

        @app.get("/foobar")
        async def _():
            return {"message": "hello world"}

        @app.get("/user/{username}")
        async def _(username: str):
            return {"message": username}

        @app.get("/exclude/{param}")
        async def _(param: str):
            return {"message": param}

        @app.get("/healthzz")
        async def _():
            return {"message": "ok"}

        app.mount("/sub", app=sub_app)

        return app


class TestBaseManualFastAPI(TestBaseFastAPI):
    @classmethod
    def setUpClass(cls):
        if cls is TestBaseManualFastAPI:
            raise unittest.SkipTest(
                f"{cls.__name__} is an abstract base class"
            )

        super(TestBaseManualFastAPI, cls).setUpClass()

    def test_sub_app_fastapi_call(self):
        """
        This test is to ensure that a span in case of a sub app targeted contains the correct server url

        As this test case covers manual instrumentation, we won't see any additional spans for the sub app.
        In this case all generated spans might suffice the requirements for the attributes already
        (as the testcase is not setting a root_path for the outer app here)
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

        # We expect only one span to have the HTTP attributes set (the SERVER span from the app itself)
        # the sub app is not instrumented with manual instrumentation tests.
        self.assertEqual(1, len(spans_with_http_attributes))

        for span in spans_with_http_attributes:
            self.assertEqual(
                "/sub/home", span.attributes[SpanAttributes.HTTP_TARGET]
            )
        self.assertEqual(
            "https://testserver:443/sub/home",
            span.attributes[SpanAttributes.HTTP_URL],
        )


class TestBaseAutoFastAPI(TestBaseFastAPI):
    @classmethod
    def setUpClass(cls):
        if cls is TestBaseAutoFastAPI:
            raise unittest.SkipTest(
                f"{cls.__name__} is an abstract base class"
            )

        super(TestBaseAutoFastAPI, cls).setUpClass()

    def test_sub_app_fastapi_call(self):
        """
        This test is to ensure that a span in case of a sub app targeted contains the correct server url

        As this test case covers auto instrumentation, we will see additional spans for the sub app.
        In this case all generated spans might suffice the requirements for the attributes already
        (as the testcase is not setting a root_path for the outer app here)
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

        for span in spans_with_http_attributes:
            self.assertEqual(
                "/sub/home", span.attributes[SpanAttributes.HTTP_TARGET]
            )
        self.assertEqual(
            "https://testserver:443/sub/home",
            span.attributes[SpanAttributes.HTTP_URL],
        )


# pylint: disable=too-many-public-methods
class TestFastAPIManualInstrumentation(TestBaseManualFastAPI):
    def test_instrument_app_with_instrument(self):
        if not isinstance(self, TestAutoInstrumentation):
            self._instrumentor.instrument()
        self._client.get("/foobar")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 3)
        for span in spans:
            self.assertIn("GET /foobar", span.name)
            self.assertEqual(
                span.instrumentation_scope.name,
                "opentelemetry.instrumentation.fastapi",
            )

    def test_uninstrument_app(self):
        self._client.get("/foobar")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 3)

        self._instrumentor.uninstrument_app(self._app)
        self.assertFalse(
            isinstance(
                self._app.user_middleware[0].cls, OpenTelemetryMiddleware
            )
        )
        self._client = TestClient(self._app)
        resp = self._client.get("/foobar")
        self.assertEqual(200, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 3)

    def test_uninstrument_app_after_instrument(self):
        if not isinstance(self, TestAutoInstrumentation):
            self._instrumentor.instrument()
        self._instrumentor.uninstrument_app(self._app)
        self._client.get("/foobar")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_basic_fastapi_call(self):
        self._client.get("/foobar")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 3)
        for span in spans:
            self.assertIn("GET /foobar", span.name)

    def test_fastapi_route_attribute_added(self):
        """Ensure that fastapi routes are used as the span name."""
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

    def test_fastapi_excluded_urls(self):
        """Ensure that given fastapi routes are excluded."""
        self._client.get("/exclude/123")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)
        self._client.get("/healthzz")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_fastapi_excluded_urls_not_env(self):
        """Ensure that given fastapi routes are excluded when passed explicitly (not in the environment)"""
        app = self._create_app_explicit_excluded_urls()
        client = TestClient(app)
        client.get("/user/123")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)
        client.get("/foobar")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_fastapi_metrics(self):
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
                    "opentelemetry.instrumentation.fastapi",
                )
                self.assertTrue(len(scope_metric.metrics) == 3)
                for metric in scope_metric.metrics:
                    self.assertIn(metric.name, _expected_metric_names_old)
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
                                attr, _recommended_attrs_old[metric.name]
                            )
        self.assertTrue(number_data_point_seen and histogram_data_point_seen)

    def test_fastapi_metrics_new_semconv(self):
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
                    "opentelemetry.instrumentation.fastapi",
                )
                self.assertTrue(len(scope_metric.metrics) == 3)
                for metric in scope_metric.metrics:
                    self.assertIn(metric.name, _expected_metric_names_new)
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
                                attr, _recommended_attrs_new[metric.name]
                            )
        self.assertTrue(number_data_point_seen and histogram_data_point_seen)

    def test_fastapi_metrics_both_semconv(self):
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
                    "opentelemetry.instrumentation.fastapi",
                )
                self.assertTrue(len(scope_metric.metrics) == 5)
                for metric in scope_metric.metrics:
                    self.assertIn(metric.name, _expected_metric_names_both)
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
                                attr, _recommended_attrs_both[metric.name]
                            )
        self.assertTrue(number_data_point_seen and histogram_data_point_seen)

    def test_basic_metric_success(self):
        start = default_timer()
        self._client.get("/foobar")
        duration = max(round((default_timer() - start) * 1000), 0)
        expected_duration_attributes = {
            SpanAttributes.HTTP_METHOD: "GET",
            SpanAttributes.HTTP_HOST: "testserver:443",
            SpanAttributes.HTTP_SCHEME: "https",
            SpanAttributes.HTTP_FLAVOR: "1.1",
            SpanAttributes.HTTP_SERVER_NAME: "testserver",
            SpanAttributes.NET_HOST_PORT: 443,
            SpanAttributes.HTTP_STATUS_CODE: 200,
            SpanAttributes.HTTP_TARGET: "/foobar",
        }
        expected_requests_count_attributes = {
            SpanAttributes.HTTP_METHOD: "GET",
            SpanAttributes.HTTP_HOST: "testserver:443",
            SpanAttributes.HTTP_SCHEME: "https",
            SpanAttributes.HTTP_FLAVOR: "1.1",
            SpanAttributes.HTTP_SERVER_NAME: "testserver",
        }
        metrics_list = self.memory_metrics_reader.get_metrics_data()
        for metric in (
            metrics_list.resource_metrics[0].scope_metrics[0].metrics
        ):
            for point in list(metric.data.data_points):
                if isinstance(point, HistogramDataPoint):
                    self.assertDictEqual(
                        expected_duration_attributes,
                        dict(point.attributes),
                    )
                    self.assertEqual(point.count, 1)
                    self.assertAlmostEqual(duration, point.sum, delta=350)
                if isinstance(point, NumberDataPoint):
                    self.assertDictEqual(
                        expected_requests_count_attributes,
                        dict(point.attributes),
                    )
                    self.assertEqual(point.value, 0)

    def test_basic_metric_success_new_semconv(self):
        start = default_timer()
        self._client.get("/foobar")
        duration_s = max(default_timer() - start, 0)
        expected_duration_attributes = {
            HTTP_REQUEST_METHOD: "GET",
            URL_SCHEME: "https",
            NETWORK_PROTOCOL_VERSION: "1.1",
            HTTP_RESPONSE_STATUS_CODE: 200,
            HTTP_ROUTE: "/foobar",
        }
        expected_requests_count_attributes = {
            HTTP_REQUEST_METHOD: "GET",
            URL_SCHEME: "https",
        }
        metrics_list = self.memory_metrics_reader.get_metrics_data()
        for metric in (
            metrics_list.resource_metrics[0].scope_metrics[0].metrics
        ):
            for point in list(metric.data.data_points):
                if isinstance(point, HistogramDataPoint):
                    self.assertDictEqual(
                        expected_duration_attributes,
                        dict(point.attributes),
                    )
                    self.assertEqual(point.count, 1)
                    if metric.name == "http.server.request.duration":
                        self.assertAlmostEqual(
                            duration_s * 0.1, point.sum, places=1
                        )
                    elif metric.name == "http.server.response.body.size":
                        self.assertEqual(25, point.sum)
                    elif metric.name == "http.server.request.body.size":
                        self.assertEqual(25, point.sum)
                if isinstance(point, NumberDataPoint):
                    self.assertDictEqual(
                        expected_requests_count_attributes,
                        dict(point.attributes),
                    )
                    self.assertEqual(point.value, 0)

    def test_basic_metric_success_both_semconv(self):
        start = default_timer()
        self._client.get("/foobar")
        duration = max(round((default_timer() - start) * 1000), 0)
        duration_s = max(default_timer() - start, 0)
        expected_duration_attributes_old = {
            SpanAttributes.HTTP_METHOD: "GET",
            SpanAttributes.HTTP_HOST: "testserver:443",
            SpanAttributes.HTTP_SCHEME: "https",
            SpanAttributes.HTTP_FLAVOR: "1.1",
            SpanAttributes.HTTP_SERVER_NAME: "testserver",
            SpanAttributes.NET_HOST_PORT: 443,
            SpanAttributes.HTTP_STATUS_CODE: 200,
            SpanAttributes.HTTP_TARGET: "/foobar",
        }
        expected_duration_attributes_new = {
            HTTP_REQUEST_METHOD: "GET",
            URL_SCHEME: "https",
            NETWORK_PROTOCOL_VERSION: "1.1",
            HTTP_RESPONSE_STATUS_CODE: 200,
            HTTP_ROUTE: "/foobar",
        }
        expected_requests_count_attributes = {
            SpanAttributes.HTTP_METHOD: "GET",
            SpanAttributes.HTTP_HOST: "testserver:443",
            SpanAttributes.HTTP_SCHEME: "https",
            SpanAttributes.HTTP_FLAVOR: "1.1",
            SpanAttributes.HTTP_SERVER_NAME: "testserver",
            HTTP_REQUEST_METHOD: "GET",
            URL_SCHEME: "https",
        }
        metrics_list = self.memory_metrics_reader.get_metrics_data()
        for metric in (
            metrics_list.resource_metrics[0].scope_metrics[0].metrics
        ):
            for point in list(metric.data.data_points):
                if isinstance(point, HistogramDataPoint):
                    self.assertEqual(point.count, 1)
                    self.assertAlmostEqual(duration, point.sum, delta=350)
                    if metric.name == "http.server.request.duration":
                        self.assertAlmostEqual(
                            duration_s * 0.1, point.sum, places=1
                        )
                        self.assertDictEqual(
                            expected_duration_attributes_new,
                            dict(point.attributes),
                        )
                    elif metric.name == "http.server.response.body.size":
                        self.assertEqual(25, point.sum)
                        self.assertDictEqual(
                            expected_duration_attributes_new,
                            dict(point.attributes),
                        )
                    elif metric.name == "http.server.request.body.size":
                        self.assertEqual(25, point.sum)
                        self.assertDictEqual(
                            expected_duration_attributes_new,
                            dict(point.attributes),
                        )
                    elif metric.name == "http.server.duration":
                        self.assertAlmostEqual(duration, point.sum, delta=350)
                        self.assertDictEqual(
                            expected_duration_attributes_old,
                            dict(point.attributes),
                        )
                    elif metric.name == "http.server.response.size":
                        self.assertEqual(25, point.sum)
                        self.assertDictEqual(
                            expected_duration_attributes_old,
                            dict(point.attributes),
                        )
                    elif metric.name == "http.server.request.size":
                        self.assertEqual(25, point.sum)
                        self.assertDictEqual(
                            expected_duration_attributes_old,
                            dict(point.attributes),
                        )
                if isinstance(point, NumberDataPoint):
                    self.assertDictEqual(
                        expected_requests_count_attributes,
                        dict(point.attributes),
                    )
                    self.assertEqual(point.value, 0)

    def test_basic_metric_nonstandard_http_method_success(self):
        start = default_timer()
        self._client.request("NONSTANDARD", "/foobar")
        duration = max(round((default_timer() - start) * 1000), 0)
        expected_duration_attributes = {
            SpanAttributes.HTTP_METHOD: "_OTHER",
            SpanAttributes.HTTP_HOST: "testserver:443",
            SpanAttributes.HTTP_SCHEME: "https",
            SpanAttributes.HTTP_FLAVOR: "1.1",
            SpanAttributes.HTTP_SERVER_NAME: "testserver",
            SpanAttributes.NET_HOST_PORT: 443,
            SpanAttributes.HTTP_STATUS_CODE: 405,
            SpanAttributes.HTTP_TARGET: "/foobar",
        }
        expected_requests_count_attributes = {
            SpanAttributes.HTTP_METHOD: "_OTHER",
            SpanAttributes.HTTP_HOST: "testserver:443",
            SpanAttributes.HTTP_SCHEME: "https",
            SpanAttributes.HTTP_FLAVOR: "1.1",
            SpanAttributes.HTTP_SERVER_NAME: "testserver",
        }
        metrics_list = self.memory_metrics_reader.get_metrics_data()
        for metric in (
            metrics_list.resource_metrics[0].scope_metrics[0].metrics
        ):
            for point in list(metric.data.data_points):
                if isinstance(point, HistogramDataPoint):
                    self.assertDictEqual(
                        expected_duration_attributes,
                        dict(point.attributes),
                    )
                    self.assertEqual(point.count, 1)
                    self.assertAlmostEqual(duration, point.sum, delta=350)
                if isinstance(point, NumberDataPoint):
                    self.assertDictEqual(
                        expected_requests_count_attributes,
                        dict(point.attributes),
                    )
                    self.assertEqual(point.value, 0)

    def test_basic_metric_nonstandard_http_method_success_new_semconv(self):
        start = default_timer()
        self._client.request("NONSTANDARD", "/foobar")
        duration_s = max(default_timer() - start, 0)
        expected_duration_attributes = {
            HTTP_REQUEST_METHOD: "_OTHER",
            URL_SCHEME: "https",
            NETWORK_PROTOCOL_VERSION: "1.1",
            HTTP_RESPONSE_STATUS_CODE: 405,
            HTTP_ROUTE: "/foobar",
        }
        expected_requests_count_attributes = {
            HTTP_REQUEST_METHOD: "_OTHER",
            URL_SCHEME: "https",
        }
        metrics_list = self.memory_metrics_reader.get_metrics_data()
        for metric in (
            metrics_list.resource_metrics[0].scope_metrics[0].metrics
        ):
            for point in list(metric.data.data_points):
                if isinstance(point, HistogramDataPoint):
                    self.assertDictEqual(
                        expected_duration_attributes,
                        dict(point.attributes),
                    )
                    self.assertEqual(point.count, 1)
                    if metric.name == "http.server.request.duration":
                        self.assertAlmostEqual(
                            duration_s * 0.1, point.sum, places=1
                        )
                    elif metric.name == "http.server.response.body.size":
                        self.assertEqual(31, point.sum)
                    elif metric.name == "http.server.request.body.size":
                        self.assertEqual(25, point.sum)
                if isinstance(point, NumberDataPoint):
                    self.assertDictEqual(
                        expected_requests_count_attributes,
                        dict(point.attributes),
                    )
                    self.assertEqual(point.value, 0)

    def test_basic_metric_nonstandard_http_method_success_both_semconv(self):
        start = default_timer()
        self._client.request("NONSTANDARD", "/foobar")
        duration = max(round((default_timer() - start) * 1000), 0)
        duration_s = max(default_timer() - start, 0)
        expected_duration_attributes_old = {
            SpanAttributes.HTTP_METHOD: "_OTHER",
            SpanAttributes.HTTP_HOST: "testserver:443",
            SpanAttributes.HTTP_SCHEME: "https",
            SpanAttributes.HTTP_FLAVOR: "1.1",
            SpanAttributes.HTTP_SERVER_NAME: "testserver",
            SpanAttributes.NET_HOST_PORT: 443,
            SpanAttributes.HTTP_STATUS_CODE: 405,
            SpanAttributes.HTTP_TARGET: "/foobar",
        }
        expected_duration_attributes_new = {
            HTTP_REQUEST_METHOD: "_OTHER",
            URL_SCHEME: "https",
            NETWORK_PROTOCOL_VERSION: "1.1",
            HTTP_RESPONSE_STATUS_CODE: 405,
            HTTP_ROUTE: "/foobar",
        }
        expected_requests_count_attributes = {
            SpanAttributes.HTTP_METHOD: "_OTHER",
            SpanAttributes.HTTP_HOST: "testserver:443",
            SpanAttributes.HTTP_SCHEME: "https",
            SpanAttributes.HTTP_FLAVOR: "1.1",
            SpanAttributes.HTTP_SERVER_NAME: "testserver",
            HTTP_REQUEST_METHOD: "_OTHER",
            URL_SCHEME: "https",
        }
        metrics_list = self.memory_metrics_reader.get_metrics_data()
        for metric in (
            metrics_list.resource_metrics[0].scope_metrics[0].metrics
        ):
            for point in list(metric.data.data_points):
                if isinstance(point, HistogramDataPoint):
                    self.assertEqual(point.count, 1)
                    if metric.name == "http.server.request.duration":
                        self.assertAlmostEqual(
                            duration_s * 0.1, point.sum, places=1
                        )
                        self.assertDictEqual(
                            expected_duration_attributes_new,
                            dict(point.attributes),
                        )
                    elif metric.name == "http.server.response.body.size":
                        self.assertEqual(31, point.sum)
                        self.assertDictEqual(
                            expected_duration_attributes_new,
                            dict(point.attributes),
                        )
                    elif metric.name == "http.server.request.body.size":
                        self.assertEqual(25, point.sum)
                        self.assertDictEqual(
                            expected_duration_attributes_new,
                            dict(point.attributes),
                        )
                    elif metric.name == "http.server.duration":
                        self.assertAlmostEqual(duration, point.sum, delta=350)
                        self.assertDictEqual(
                            expected_duration_attributes_old,
                            dict(point.attributes),
                        )
                    elif metric.name == "http.server.response.size":
                        self.assertEqual(31, point.sum)
                        self.assertDictEqual(
                            expected_duration_attributes_old,
                            dict(point.attributes),
                        )
                    elif metric.name == "http.server.request.size":
                        self.assertEqual(25, point.sum)
                        self.assertDictEqual(
                            expected_duration_attributes_old,
                            dict(point.attributes),
                        )
                if isinstance(point, NumberDataPoint):
                    self.assertDictEqual(
                        expected_requests_count_attributes,
                        dict(point.attributes),
                    )
                    self.assertEqual(point.value, 0)

    def test_basic_post_request_metric_success(self):
        start = default_timer()
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
                    if metric.name == "http.server.duration":
                        self.assertAlmostEqual(duration, point.sum, delta=350)
                    elif metric.name == "http.server.response.size":
                        self.assertEqual(response_size, point.sum)
                    elif metric.name == "http.server.request.size":
                        self.assertEqual(request_size, point.sum)
                if isinstance(point, NumberDataPoint):
                    self.assertEqual(point.value, 0)

    def test_basic_post_request_metric_success_new_semconv(self):
        start = default_timer()
        response = self._client.post(
            "/foobar",
            json={"foo": "bar"},
        )
        duration_s = max(default_timer() - start, 0)
        response_size = int(response.headers.get("content-length"))
        request_size = int(response.request.headers.get("content-length"))
        metrics_list = self.memory_metrics_reader.get_metrics_data()
        for metric in (
            metrics_list.resource_metrics[0].scope_metrics[0].metrics
        ):
            for point in list(metric.data.data_points):
                if isinstance(point, HistogramDataPoint):
                    self.assertEqual(point.count, 1)
                    if metric.name == "http.server.request.duration":
                        self.assertAlmostEqual(
                            duration_s * 0.1, point.sum, places=1
                        )
                    elif metric.name == "http.server.response.body.size":
                        self.assertEqual(response_size, point.sum)
                    elif metric.name == "http.server.request.body.size":
                        self.assertEqual(request_size, point.sum)
                if isinstance(point, NumberDataPoint):
                    self.assertEqual(point.value, 0)

    def test_basic_post_request_metric_success_both_semconv(self):
        start = default_timer()
        response = self._client.post(
            "/foobar",
            json={"foo": "bar"},
        )
        duration = max(round((default_timer() - start) * 1000), 0)
        duration_s = max(default_timer() - start, 0)
        response_size = int(response.headers.get("content-length"))
        request_size = int(response.request.headers.get("content-length"))
        metrics_list = self.memory_metrics_reader.get_metrics_data()
        for metric in (
            metrics_list.resource_metrics[0].scope_metrics[0].metrics
        ):
            for point in list(metric.data.data_points):
                if isinstance(point, HistogramDataPoint):
                    self.assertEqual(point.count, 1)
                    if metric.name == "http.server.request.duration":
                        self.assertAlmostEqual(
                            duration_s * 0.1, point.sum, places=1
                        )
                    elif metric.name == "http.server.response.body.size":
                        self.assertEqual(response_size, point.sum)
                    elif metric.name == "http.server.request.body.size":
                        self.assertEqual(request_size, point.sum)
                    elif metric.name == "http.server.duration":
                        self.assertAlmostEqual(duration, point.sum, delta=350)
                    elif metric.name == "http.server.response.size":
                        self.assertEqual(response_size, point.sum)
                    elif metric.name == "http.server.request.size":
                        self.assertEqual(request_size, point.sum)
                if isinstance(point, NumberDataPoint):
                    self.assertEqual(point.value, 0)

    def test_metric_uninstrument_app(self):
        self._client.get("/foobar")
        self._instrumentor.uninstrument_app(self._app)
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

    def test_metric_uninstrument(self):
        if not isinstance(self, TestAutoInstrumentation):
            self._instrumentor.instrument()
        self._client.get("/foobar")
        self._instrumentor.uninstrument()
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

    @staticmethod
    def _create_fastapi_app():
        app = fastapi.FastAPI()
        sub_app = fastapi.FastAPI()

        @sub_app.get("/home")
        async def _():
            return {"message": "sub hi"}

        @app.get("/foobar")
        async def _():
            return {"message": "hello world"}

        @app.get("/user/{username}")
        async def _(username: str):
            return {"message": username}

        @app.get("/exclude/{param}")
        async def _(param: str):
            return {"message": param}

        @app.get("/healthzz")
        async def _():
            return {"message": "ok"}

        app.mount("/sub", app=sub_app)

        return app


class TestFastAPIManualInstrumentationHooks(TestBaseManualFastAPI):
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


class TestAutoInstrumentation(TestBaseAutoFastAPI):
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
        return self._create_fastapi_app()

    def _create_app_explicit_excluded_urls(self):
        resource = Resource.create({"key1": "value1", "key2": "value2"})
        tracer_provider, exporter = self.create_tracer_provider(
            resource=resource
        )
        self.memory_exporter = exporter

        to_exclude = "/user/123,/foobar"
        self._instrumentor.uninstrument()  # Disable previous instrumentation (setUp)
        self._instrumentor.instrument(
            tracer_provider=tracer_provider,
            excluded_urls=to_exclude,
        )
        return self._create_fastapi_app()

    def test_request(self):
        self._client.get("/foobar")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 3)
        for span in spans:
            self.assertEqual(span.resource.attributes["key1"], "value1")
            self.assertEqual(span.resource.attributes["key2"], "value2")

    def test_mulitple_way_instrumentation(self):
        self._instrumentor.instrument_app(self._app)
        count = 0
        for middleware in self._app.user_middleware:
            if middleware.cls is OpenTelemetryMiddleware:
                count += 1
        self.assertEqual(count, 1)

    def test_uninstrument_after_instrument(self):
        app = self._create_fastapi_app()
        client = TestClient(app)
        client.get("/foobar")
        self._instrumentor.uninstrument()
        client.get("/foobar")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 3)

    def test_no_op_tracer_provider(self):
        self._instrumentor.uninstrument()
        self._instrumentor.instrument(
            tracer_provider=trace.NoOpTracerProvider()
        )

        app = self._create_fastapi_app()
        client = TestClient(app)
        client.get("/foobar")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def tearDown(self):
        self._instrumentor.uninstrument()
        super().tearDown()

    def test_sub_app_fastapi_call(self):
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

        for span in spans_with_http_attributes:
            self.assertEqual(
                "/sub/home", span.attributes[SpanAttributes.HTTP_TARGET]
            )
        self.assertEqual(
            "https://testserver:443/sub/home",
            span.attributes[SpanAttributes.HTTP_URL],
        )


class TestAutoInstrumentationHooks(TestBaseAutoFastAPI):
    """
    Test the auto-instrumented variant for request and response hooks

    Extending the manual instrumentation to inherit defined hooks and since most test cases apply
    to both.
    """

    def _create_app(self):
        # instrumentation is handled by the instrument call
        self._instrumentor.instrument(
            server_request_hook=getattr(self, "server_request_hook", None),
            client_request_hook=getattr(self, "client_request_hook", None),
            client_response_hook=getattr(self, "client_response_hook", None),
        )

        return self._create_fastapi_app()

    def _create_app_explicit_excluded_urls(self):
        resource = Resource.create({"key1": "value1", "key2": "value2"})
        tracer_provider, exporter = self.create_tracer_provider(
            resource=resource
        )
        self.memory_exporter = exporter

        to_exclude = "/user/123,/foobar"
        self._instrumentor.uninstrument()  # Disable previous instrumentation (setUp)
        self._instrumentor.instrument(
            tracer_provider=tracer_provider,
            excluded_urls=to_exclude,
            server_request_hook=getattr(self, "server_request_hook", None),
            client_request_hook=getattr(self, "client_request_hook", None),
            client_response_hook=getattr(self, "client_response_hook", None),
        )
        return self._create_fastapi_app()

    def tearDown(self):
        self._instrumentor.uninstrument()
        super().tearDown()

    def test_sub_app_fastapi_call(self):
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

        for span in spans_with_http_attributes:
            self.assertEqual(
                "/sub/home", span.attributes[SpanAttributes.HTTP_TARGET]
            )
        self.assertEqual(
            "https://testserver:443/sub/home",
            span.attributes[SpanAttributes.HTTP_URL],
        )


class TestAutoInstrumentationLogic(unittest.TestCase):
    def test_instrumentation(self):
        """Verify that instrumentation methods are instrumenting and
        removing as expected.
        """
        instrumentor = otel_fastapi.FastAPIInstrumentor()
        original = fastapi.FastAPI
        instrumentor.instrument()
        try:
            instrumented = fastapi.FastAPI
            self.assertIsNot(original, instrumented)
        finally:
            instrumentor.uninstrument()

        should_be_original = fastapi.FastAPI
        self.assertIs(original, should_be_original)


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


@patch.dict(
    "os.environ",
    {
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS: ".*my-secret.*",
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3,Regex-Test-Header-.*,Regex-Invalid-Test-Header-.*,.*my-secret.*",
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3,my-custom-regex-header-.*,invalid-regex-header-.*,.*my-secret.*",
    },
)
class TestHTTPAppWithCustomHeaders(TestBase):
    def setUp(self):
        super().setUp()
        self.app = self._create_app()
        otel_fastapi.FastAPIInstrumentor().instrument_app(self.app)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        super().tearDown()
        with self.disable_logging():
            otel_fastapi.FastAPIInstrumentor().uninstrument_app(self.app)

    @staticmethod
    def _create_app():
        app = fastapi.FastAPI()

        @app.get("/foobar")
        async def _():
            headers = {
                "custom-test-header-1": "test-header-value-1",
                "custom-test-header-2": "test-header-value-2",
                "my-custom-regex-header-1": "my-custom-regex-value-1,my-custom-regex-value-2",
                "My-Custom-Regex-Header-2": "my-custom-regex-value-3,my-custom-regex-value-4",
                "My-Secret-Header": "My Secret Value",
            }
            content = {"message": "hello world"}
            return JSONResponse(content=content, headers=headers)

        return app

    def test_http_custom_request_headers_in_span_attributes(self):
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
        resp = self.client.get(
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
            span for span in span_list if span.kind == trace.SpanKind.SERVER
        ][0]

        self.assertSpanHasAttributes(server_span, expected)

    def test_http_custom_request_headers_not_in_span_attributes(self):
        not_expected = {
            "http.request.header.custom_test_header_3": (
                "test-header-value-3",
            ),
        }
        resp = self.client.get(
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
            span for span in span_list if span.kind == trace.SpanKind.SERVER
        ][0]

        for key, _ in not_expected.items():
            self.assertNotIn(key, server_span.attributes)

    def test_http_custom_response_headers_in_span_attributes(self):
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
        resp = self.client.get("/foobar")
        self.assertEqual(200, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 3)

        server_span = [
            span for span in span_list if span.kind == trace.SpanKind.SERVER
        ][0]
        self.assertSpanHasAttributes(server_span, expected)

    def test_http_custom_response_headers_not_in_span_attributes(self):
        not_expected = {
            "http.response.header.custom_test_header_3": (
                "test-header-value-3",
            ),
        }
        resp = self.client.get("/foobar")
        self.assertEqual(200, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 3)

        server_span = [
            span for span in span_list if span.kind == trace.SpanKind.SERVER
        ][0]

        for key, _ in not_expected.items():
            self.assertNotIn(key, server_span.attributes)


class TestHTTPAppWithCustomHeadersParameters(TestBase):
    """Minimal tests here since the behavior of this logic is tested above and in the ASGI tests."""

    def setUp(self):
        super().setUp()
        self.instrumentor = otel_fastapi.FastAPIInstrumentor()
        self.kwargs = {
            "http_capture_headers_server_request": ["a.*", "b.*"],
            "http_capture_headers_server_response": ["c.*", "d.*"],
            "http_capture_headers_sanitize_fields": [".*secret.*"],
        }
        self.app = None

    def tearDown(self) -> None:
        super().tearDown()
        with self.disable_logging():
            if self.app:
                self.instrumentor.uninstrument_app(self.app)
            else:
                self.instrumentor.uninstrument()

    @staticmethod
    def _create_app():
        app = fastapi.FastAPI()

        @app.get("/foobar")
        async def _():
            headers = {
                "carrot": "bar",
                "date-secret": "yellow",
                "egg": "ham",
            }
            content = {"message": "hello world"}
            return JSONResponse(content=content, headers=headers)

        return app

    def test_http_custom_request_headers_in_span_attributes_app(self):
        self.app = self._create_app()
        self.instrumentor.instrument_app(self.app, **self.kwargs)

        resp = TestClient(self.app).get(
            "/foobar",
            headers={
                "apple": "red",
                "banana-secret": "yellow",
                "fig": "green",
            },
        )
        self.assertEqual(200, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 3)

        server_span = [
            span for span in span_list if span.kind == trace.SpanKind.SERVER
        ][0]

        expected = {
            # apple should be included because it starts with a
            "http.request.header.apple": ("red",),
            # same with banana because it starts with b,
            # redacted because it contains "secret"
            "http.request.header.banana_secret": ("[REDACTED]",),
        }
        self.assertSpanHasAttributes(server_span, expected)
        self.assertNotIn("http.request.header.fig", server_span.attributes)

    def test_http_custom_request_headers_in_span_attributes_instr(self):
        """As above, but use instrument(), not instrument_app()."""
        self.instrumentor.instrument(**self.kwargs)

        resp = TestClient(self._create_app()).get(
            "/foobar",
            headers={
                "apple": "red",
                "banana-secret": "yellow",
                "fig": "green",
            },
        )
        self.assertEqual(200, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 3)

        server_span = [
            span for span in span_list if span.kind == trace.SpanKind.SERVER
        ][0]

        expected = {
            # apple should be included because it starts with a
            "http.request.header.apple": ("red",),
            # same with banana because it starts with b,
            # redacted because it contains "secret"
            "http.request.header.banana_secret": ("[REDACTED]",),
        }
        self.assertSpanHasAttributes(server_span, expected)
        self.assertNotIn("http.request.header.fig", server_span.attributes)

    def test_http_custom_response_headers_in_span_attributes_app(self):
        self.app = self._create_app()
        self.instrumentor.instrument_app(self.app, **self.kwargs)
        resp = TestClient(self.app).get("/foobar")
        self.assertEqual(200, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 3)

        server_span = [
            span for span in span_list if span.kind == trace.SpanKind.SERVER
        ][0]

        expected = {
            "http.response.header.carrot": ("bar",),
            "http.response.header.date_secret": ("[REDACTED]",),
        }
        self.assertSpanHasAttributes(server_span, expected)
        self.assertNotIn("http.response.header.egg", server_span.attributes)

    def test_http_custom_response_headers_in_span_attributes_inst(self):
        """As above, but use instrument(), not instrument_app()."""
        self.instrumentor.instrument(**self.kwargs)

        resp = TestClient(self._create_app()).get("/foobar")
        self.assertEqual(200, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 3)

        server_span = [
            span for span in span_list if span.kind == trace.SpanKind.SERVER
        ][0]

        expected = {
            "http.response.header.carrot": ("bar",),
            "http.response.header.date_secret": ("[REDACTED]",),
        }
        self.assertSpanHasAttributes(server_span, expected)
        self.assertNotIn("http.response.header.egg", server_span.attributes)


@patch.dict(
    "os.environ",
    {
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS: ".*my-secret.*",
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3,Regex-Test-Header-.*,Regex-Invalid-Test-Header-.*,.*my-secret.*",
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3,my-custom-regex-header-.*,invalid-regex-header-.*,.*my-secret.*",
    },
)
class TestWebSocketAppWithCustomHeaders(TestBase):
    def setUp(self):
        super().setUp()
        self.app = self._create_app()
        otel_fastapi.FastAPIInstrumentor().instrument_app(self.app)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        super().tearDown()
        with self.disable_logging():
            otel_fastapi.FastAPIInstrumentor().uninstrument_app(self.app)

    @staticmethod
    def _create_app():
        app = fastapi.FastAPI()

        @app.websocket("/foobar_web")
        async def _(websocket: fastapi.WebSocket):
            message = await websocket.receive()
            if message.get("type") == "websocket.connect":
                await websocket.send(
                    {
                        "type": "websocket.accept",
                        "headers": [
                            (b"custom-test-header-1", b"test-header-value-1"),
                            (b"custom-test-header-2", b"test-header-value-2"),
                            (b"Regex-Test-Header-1", b"Regex Test Value 1"),
                            (
                                b"regex-test-header-2",
                                b"RegexTestValue2,RegexTestValue3",
                            ),
                            (b"My-Secret-Header", b"My Secret Value"),
                        ],
                    }
                )
                await websocket.send_json({"message": "hello world"})
                await websocket.close()
            if message.get("type") == "websocket.disconnect":
                pass

        return app

    def test_web_socket_custom_request_headers_in_span_attributes(self):
        expected = {
            "http.request.header.custom_test_header_1": (
                "test-header-value-1",
            ),
            "http.request.header.custom_test_header_2": (
                "test-header-value-2",
            ),
        }

        with self.client.websocket_connect(
            "/foobar_web",
            headers={
                "custom-test-header-1": "test-header-value-1",
                "custom-test-header-2": "test-header-value-2",
            },
        ) as websocket:
            data = websocket.receive_json()
            self.assertEqual(data, {"message": "hello world"})

        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 5)

        server_span = [
            span for span in span_list if span.kind == trace.SpanKind.SERVER
        ][0]

        self.assertSpanHasAttributes(server_span, expected)

    @patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS: ".*my-secret.*",
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3,Regex-Test-Header-.*,Regex-Invalid-Test-Header-.*,.*my-secret.*",
        },
    )
    def test_web_socket_custom_request_headers_not_in_span_attributes(self):
        not_expected = {
            "http.request.header.custom_test_header_3": (
                "test-header-value-3",
            ),
        }

        with self.client.websocket_connect(
            "/foobar_web",
            headers={
                "custom-test-header-1": "test-header-value-1",
                "custom-test-header-2": "test-header-value-2",
            },
        ) as websocket:
            data = websocket.receive_json()
            self.assertEqual(data, {"message": "hello world"})

        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 5)

        server_span = [
            span for span in span_list if span.kind == trace.SpanKind.SERVER
        ][0]

        for key, _ in not_expected.items():
            self.assertNotIn(key, server_span.attributes)

    def test_web_socket_custom_response_headers_in_span_attributes(self):
        expected = {
            "http.response.header.custom_test_header_1": (
                "test-header-value-1",
            ),
            "http.response.header.custom_test_header_2": (
                "test-header-value-2",
            ),
        }

        with self.client.websocket_connect("/foobar_web") as websocket:
            data = websocket.receive_json()
            self.assertEqual(data, {"message": "hello world"})

        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 5)

        server_span = [
            span for span in span_list if span.kind == trace.SpanKind.SERVER
        ][0]

        self.assertSpanHasAttributes(server_span, expected)

    def test_web_socket_custom_response_headers_not_in_span_attributes(self):
        not_expected = {
            "http.response.header.custom_test_header_3": (
                "test-header-value-3",
            ),
        }

        with self.client.websocket_connect("/foobar_web") as websocket:
            data = websocket.receive_json()
            self.assertEqual(data, {"message": "hello world"})

        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 5)

        server_span = [
            span for span in span_list if span.kind == trace.SpanKind.SERVER
        ][0]

        for key, _ in not_expected.items():
            self.assertNotIn(key, server_span.attributes)


@patch.dict(
    "os.environ",
    {
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3",
    },
)
class TestNonRecordingSpanWithCustomHeaders(TestBase):
    def setUp(self):
        super().setUp()
        self.app = fastapi.FastAPI()

        @self.app.get("/foobar")
        async def _():
            return {"message": "hello world"}

        reset_trace_globals()
        tracer_provider = trace.NoOpTracerProvider()
        trace.set_tracer_provider(tracer_provider=tracer_provider)

        self._instrumentor = otel_fastapi.FastAPIInstrumentor()
        self._instrumentor.instrument_app(self.app)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        super().tearDown()
        with self.disable_logging():
            self._instrumentor.uninstrument_app(self.app)

    def test_custom_header_not_present_in_non_recording_span(self):
        resp = self.client.get(
            "/foobar",
            headers={
                "custom-test-header-1": "test-header-value-1",
            },
        )
        self.assertEqual(200, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 0)
