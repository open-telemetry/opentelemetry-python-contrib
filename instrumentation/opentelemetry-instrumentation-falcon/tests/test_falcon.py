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
#
from timeit import default_timer
from unittest.mock import Mock, patch

import pytest
from falcon import __version__ as _falcon_version
from falcon import testing
from packaging import version as package_version

from opentelemetry import trace
from opentelemetry.instrumentation._semconv import (
    HTTP_DURATION_HISTOGRAM_BUCKETS_NEW,
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
    _server_active_requests_count_attrs_new,
    _server_active_requests_count_attrs_old,
    _server_duration_attrs_new,
    _server_duration_attrs_old,
)
from opentelemetry.instrumentation.falcon import FalconInstrumentor
from opentelemetry.instrumentation.propagators import (
    TraceResponsePropagator,
    get_global_response_propagator,
    set_global_response_propagator,
)
from opentelemetry.sdk.metrics.export import (
    HistogramDataPoint,
    NumberDataPoint,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv._incubating.attributes.http_attributes import (
    HTTP_FLAVOR,
    HTTP_HOST,
    HTTP_METHOD,
    HTTP_SCHEME,
    HTTP_SERVER_NAME,
    HTTP_STATUS_CODE,
    HTTP_TARGET,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_HOST_PORT,
    NET_PEER_IP,
    NET_PEER_PORT,
)
from opentelemetry.semconv.attributes.client_attributes import (
    CLIENT_PORT,
)
from opentelemetry.semconv.attributes.http_attributes import (
    HTTP_REQUEST_METHOD,
    HTTP_RESPONSE_STATUS_CODE,
    HTTP_ROUTE,
)
from opentelemetry.semconv.attributes.network_attributes import (
    NETWORK_PROTOCOL_VERSION,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.semconv.attributes.url_attributes import (
    URL_PATH,
    URL_SCHEME,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.test.wsgitestutil import WsgiTestBase
from opentelemetry.trace import StatusCode
from opentelemetry.util.http import (
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE,
)

from .app import make_app

_expected_metric_names = [
    "http.server.active_requests",
    "http.server.duration",
]

_recommended_attrs = {
    "http.server.active_requests": _server_active_requests_count_attrs_new
    + _server_active_requests_count_attrs_old,
    "http.server.duration": _server_duration_attrs_new
    + _server_duration_attrs_old,
}

_recommended_metrics_attrs_old = {
    "http.server.active_requests": _server_active_requests_count_attrs_old,
    "http.server.duration": _server_duration_attrs_old,
}
_recommended_metrics_attrs_new = {
    "http.server.active_requests": _server_active_requests_count_attrs_new,
    "http.server.request.duration": _server_duration_attrs_new,
}
_server_active_requests_count_attrs_both = (
    _server_active_requests_count_attrs_old
)
_server_active_requests_count_attrs_both.extend(
    _server_active_requests_count_attrs_new
)
_recommended_metrics_attrs_both = {
    "http.server.active_requests": _server_active_requests_count_attrs_both,
    "http.server.duration": _server_duration_attrs_old,
    "http.server.request.duration": _server_duration_attrs_new,
}

_parsed_falcon_version = package_version.parse(_falcon_version)


class TestFalconBase(TestBase):
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
                "OTEL_PYTHON_FALCON_EXCLUDED_URLS": "ping",
                "OTEL_PYTHON_FALCON_TRACED_REQUEST_ATTRS": "query_string",
                OTEL_SEMCONV_STABILITY_OPT_IN: sem_conv_mode,
            },
        )

        _OpenTelemetrySemanticConventionStability._initialized = False
        self.env_patch.start()

        FalconInstrumentor().instrument(
            request_hook=getattr(self, "request_hook", None),
            response_hook=getattr(self, "response_hook", None),
        )
        self.app = make_app()

    @property
    def _has_fixed_http_target(self):
        # In falcon<3.1.2, HTTP_TARGET is always set to / in TestClient
        # In falcon>=3.1.2, HTTP_TARGET is set to unencoded path by default
        # https://github.com/falconry/falcon/blob/69cdcd6edd2ee33f4ac9f7793e1cc3c4f99da692/falcon/testing/helpers.py#L1153-1156 # noqa
        return _parsed_falcon_version < package_version.parse("3.1.2")

    def client(self):
        return testing.TestClient(self.app)

    def tearDown(self):
        super().tearDown()
        with self.disable_logging():
            FalconInstrumentor().uninstrument()
        self.env_patch.stop()


# pylint: disable=too-many-public-methods
class TestFalconInstrumentation(TestFalconBase, WsgiTestBase):
    def test_get(self):
        self._test_method("GET")

    def test_get_new_semconv(self):
        self._test_method("GET", old_semconv=False, new_semconv=True)

    def test_get_both_semconv(self):
        self._test_method("GET", old_semconv=True, new_semconv=True)

    def test_post(self):
        self._test_method("POST")

    def test_post_new_semconv(self):
        self._test_method("POST", old_semconv=False, new_semconv=True)

    def test_post_both_semconv(self):
        self._test_method("POST", old_semconv=True, new_semconv=True)

    def test_patch(self):
        self._test_method("PATCH")

    def test_patch_new_semconv(self):
        self._test_method("PATCH", old_semconv=False, new_semconv=True)

    def test_patch_both_semconv(self):
        self._test_method("PATCH", old_semconv=True, new_semconv=True)

    def test_put(self):
        self._test_method("PUT")

    def test_put_new_semconv(self):
        self._test_method("PUT", old_semconv=False, new_semconv=True)

    def test_put_both_semconv(self):
        self._test_method("PUT", old_semconv=True, new_semconv=True)

    def test_delete(self):
        self._test_method("DELETE")

    def test_delete_new_semconv(self):
        self._test_method("DELETE", old_semconv=False, new_semconv=True)

    def test_delete_both_semconv(self):
        self._test_method("DELETE", old_semconv=True, new_semconv=True)

    def test_head(self):
        self._test_method("HEAD")

    def test_head_new_semconv(self):
        self._test_method("HEAD", old_semconv=False, new_semconv=True)

    def test_head_both_semconv(self):
        self._test_method("HEAD", old_semconv=True, new_semconv=True)

    def _test_method(self, method, old_semconv=True, new_semconv=False):
        self.client().simulate_request(method=method, path="/hello")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, f"{method} /hello")
        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertEqual(
            span.status.description,
            None,
        )

        expected_attributes = {}
        expected_attributes_old = {
            HTTP_METHOD: method,
            HTTP_SERVER_NAME: "falconframework.org",
            HTTP_SCHEME: "http",
            NET_HOST_PORT: 80,
            HTTP_HOST: "falconframework.org",
            HTTP_TARGET: "/" if self._has_fixed_http_target else "/hello",
            NET_PEER_PORT: 65133,
            HTTP_FLAVOR: "1.1",
            "falcon.resource": "HelloWorldResource",
            HTTP_STATUS_CODE: 201,
            HTTP_ROUTE: "/hello",
        }
        expected_attributes_new = {
            HTTP_REQUEST_METHOD: method,
            SERVER_ADDRESS: "falconframework.org",
            URL_SCHEME: "http",
            SERVER_PORT: 80,
            URL_PATH: "/" if self._has_fixed_http_target else "/hello",
            CLIENT_PORT: 65133,
            NETWORK_PROTOCOL_VERSION: "1.1",
            "falcon.resource": "HelloWorldResource",
            HTTP_RESPONSE_STATUS_CODE: 201,
            HTTP_ROUTE: "/hello",
        }

        if old_semconv:
            expected_attributes.update(expected_attributes_old)
        if new_semconv:
            expected_attributes.update(expected_attributes_new)

        self.assertSpanHasAttributes(span, expected_attributes)
        # In falcon<3, NET_PEER_IP is always set by default to 127.0.0.1
        # In falcon>=3, NET_PEER_IP is not set to anything by default
        # https://github.com/falconry/falcon/blob/5233d0abed977d9dab78ebadf305f5abe2eef07c/falcon/testing/helpers.py#L1168-L1172 # noqa
        if NET_PEER_IP in span.attributes:
            self.assertEqual(span.attributes[NET_PEER_IP], "127.0.0.1")
        self.memory_exporter.clear()

    def test_404(self):
        self.client().simulate_get("/does-not-exist")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "GET")
        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertSpanHasAttributes(
            span,
            {
                HTTP_METHOD: "GET",
                HTTP_SERVER_NAME: "falconframework.org",
                HTTP_SCHEME: "http",
                NET_HOST_PORT: 80,
                HTTP_HOST: "falconframework.org",
                HTTP_TARGET: "/"
                if self._has_fixed_http_target
                else "/does-not-exist",
                NET_PEER_PORT: 65133,
                HTTP_FLAVOR: "1.1",
                HTTP_STATUS_CODE: 404,
            },
        )
        # In falcon<3, NET_PEER_IP is always set by default to 127.0.0.1
        # In falcon>=3, NET_PEER_IP is not set to anything by default
        # https://github.com/falconry/falcon/blob/5233d0abed977d9dab78ebadf305f5abe2eef07c/falcon/testing/helpers.py#L1168-L1172 # noqa
        if NET_PEER_IP in span.attributes:
            self.assertEqual(span.attributes[NET_PEER_IP], "127.0.0.1")

    def test_500(self):
        try:
            self.client().simulate_get("/error")
        except NameError:
            pass
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "GET /error")
        self.assertFalse(span.status.is_ok)
        self.assertEqual(span.status.status_code, StatusCode.ERROR)

        _parsed_falcon_version = package_version.parse(_falcon_version)
        if _parsed_falcon_version < package_version.parse("3.0.0"):
            self.assertEqual(
                span.status.description,
                "NameError: name 'non_existent_var' is not defined",
            )
        else:
            self.assertEqual(span.status.description, None)

        self.assertSpanHasAttributes(
            span,
            {
                HTTP_METHOD: "GET",
                HTTP_SERVER_NAME: "falconframework.org",
                HTTP_SCHEME: "http",
                NET_HOST_PORT: 80,
                HTTP_HOST: "falconframework.org",
                HTTP_TARGET: "/" if self._has_fixed_http_target else "/error",
                NET_PEER_PORT: 65133,
                HTTP_FLAVOR: "1.1",
                HTTP_STATUS_CODE: 500,
                HTTP_ROUTE: "/error",
            },
        )
        # In falcon<3, NET_PEER_IP is always set by default to 127.0.0.1
        # In falcon>=3, NET_PEER_IP is not set to anything by default
        # https://github.com/falconry/falcon/blob/5233d0abed977d9dab78ebadf305f5abe2eef07c/falcon/testing/helpers.py#L1168-L1172 # noqa
        if NET_PEER_IP in span.attributes:
            self.assertEqual(span.attributes[NET_PEER_IP], "127.0.0.1")

    def test_url_template_new_semconv(self):
        self.client().simulate_get("/user/123")
        spans = self.memory_exporter.get_finished_spans()
        metrics_list = self.memory_metrics_reader.get_metrics_data()

        self.assertEqual(len(spans), 1)
        self.assertTrue(len(metrics_list.resource_metrics) != 0)
        span = spans[0]
        self.assertEqual(span.name, "GET /user/{user_id}")
        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertEqual(
            span.status.description,
            None,
        )
        self.assertSpanHasAttributes(
            span,
            {
                HTTP_REQUEST_METHOD: "GET",
                SERVER_ADDRESS: "falconframework.org",
                URL_SCHEME: "http",
                SERVER_PORT: 80,
                URL_PATH: "/" if self._has_fixed_http_target else "/user/123",
                CLIENT_PORT: 65133,
                NETWORK_PROTOCOL_VERSION: "1.1",
                "falcon.resource": "UserResource",
                HTTP_RESPONSE_STATUS_CODE: 200,
                HTTP_ROUTE: "/user/{user_id}",
            },
        )

        for resource_metric in metrics_list.resource_metrics:
            for scope_metric in resource_metric.scope_metrics:
                for metric in scope_metric.metrics:
                    if metric.name == "http.server.request.duration":
                        data_points = list(metric.data.data_points)
                        for point in data_points:
                            self.assertIn(
                                "http.route",
                                point.attributes,
                            )

    def test_url_template(self):
        self.client().simulate_get("/user/123")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "GET /user/{user_id}")
        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertEqual(
            span.status.description,
            None,
        )
        self.assertSpanHasAttributes(
            span,
            {
                HTTP_METHOD: "GET",
                HTTP_SERVER_NAME: "falconframework.org",
                HTTP_SCHEME: "http",
                NET_HOST_PORT: 80,
                HTTP_HOST: "falconframework.org",
                HTTP_TARGET: "/"
                if self._has_fixed_http_target
                else "/user/123",
                NET_PEER_PORT: 65133,
                HTTP_FLAVOR: "1.1",
                "falcon.resource": "UserResource",
                HTTP_STATUS_CODE: 200,
                HTTP_ROUTE: "/user/{user_id}",
            },
        )

    def test_uninstrument(self):
        self.client().simulate_get(path="/hello")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        self.memory_exporter.clear()

        FalconInstrumentor().uninstrument()
        self.app = make_app()
        self.client().simulate_get(path="/hello")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_no_op_tracer_provider(self):
        FalconInstrumentor().uninstrument()

        FalconInstrumentor().instrument(
            tracer_provider=trace.NoOpTracerProvider()
        )

        self.memory_exporter.clear()

        self.client().simulate_get(path="/hello")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_exclude_lists(self):
        self.client().simulate_get(path="/ping")
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 0)

        self.client().simulate_get(path="/hello")
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

    def test_traced_request_attributes(self):
        self.client().simulate_get(path="/hello", query_string="q=abc")
        span = self.memory_exporter.get_finished_spans()[0]
        self.assertIn("query_string", span.attributes)
        self.assertEqual(span.attributes["query_string"], "q=abc")
        self.assertNotIn("not_available_attr", span.attributes)

    def test_trace_response(self):
        orig = get_global_response_propagator()
        set_global_response_propagator(TraceResponsePropagator())

        response = self.client().simulate_get(
            path="/hello", query_string="q=abc"
        )
        self.assertTraceResponseHeaderMatchesSpan(
            response.headers, self.memory_exporter.get_finished_spans()[0]
        )

        set_global_response_propagator(orig)

    def test_traced_not_recording(self):
        mock_tracer = Mock()
        mock_span = Mock()
        mock_span.is_recording.return_value = False
        mock_tracer.start_span.return_value = mock_span
        with patch("opentelemetry.trace.get_tracer") as tracer:
            tracer.return_value = mock_tracer
            self.client().simulate_get(path="/hello", query_string="q=abc")
            self.assertFalse(mock_span.is_recording())
            self.assertTrue(mock_span.is_recording.called)
            self.assertFalse(mock_span.set_attribute.called)
            self.assertFalse(mock_span.set_status.called)

            metrics = self.get_sorted_metrics()
            self.assertTrue(len(metrics) != 0)
            for metric in metrics:
                data_points = list(metric.data.data_points)
                self.assertEqual(len(data_points), 1)
                for point in list(metric.data.data_points):
                    if isinstance(point, HistogramDataPoint):
                        self.assertEqual(point.count, 1)
                    if isinstance(point, NumberDataPoint):
                        self.assertEqual(point.value, 0)
                    for attr in point.attributes:
                        self.assertIn(
                            attr,
                            _recommended_metrics_attrs_old[metric.name],
                        )

    def test_uninstrument_after_instrument(self):
        self.client().simulate_get(path="/hello")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        FalconInstrumentor().uninstrument()
        self.memory_exporter.clear()

        self.client().simulate_get(path="/hello")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_falcon_metrics(self):
        self.client().simulate_get("/hello/756")
        self.client().simulate_get("/hello/756")
        self.client().simulate_get("/hello/756")
        metrics = self.get_sorted_metrics()
        number_data_point_seen = False
        histogram_data_point_seen = False
        self.assertTrue(len(metrics) != 0)
        for metric in metrics:
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
                    self.assertIn(attr, _recommended_attrs[metric.name])
        self.assertTrue(number_data_point_seen and histogram_data_point_seen)

    def test_falcon_metric_values_new_semconv(self):
        number_data_point_seen = False
        histogram_data_point_seen = False

        start = default_timer()
        self.client().simulate_get("/hello/756")
        duration = max(default_timer() - start, 0)

        metrics = self.get_sorted_metrics()
        for metric in metrics:
            data_points = list(metric.data.data_points)
            self.assertEqual(len(data_points), 1)
            for point in data_points:
                if isinstance(point, HistogramDataPoint):
                    self.assertEqual(point.count, 1)
                    histogram_data_point_seen = True
                    self.assertAlmostEqual(duration, point.sum, delta=10)
                    self.assertEqual(
                        point.explicit_bounds,
                        HTTP_DURATION_HISTOGRAM_BUCKETS_NEW,
                    )
                if isinstance(point, NumberDataPoint):
                    self.assertEqual(point.value, 0)
                    number_data_point_seen = True
                for attr in point.attributes:
                    self.assertIn(
                        attr,
                        _recommended_metrics_attrs_new[metric.name],
                    )

        self.assertTrue(number_data_point_seen and histogram_data_point_seen)

    def test_falcon_metric_values_both_semconv(self):
        number_data_point_seen = False
        histogram_data_point_seen = False

        start = default_timer()
        self.client().simulate_get("/hello/756")
        duration_s = default_timer() - start

        metrics = self.get_sorted_metrics()

        # pylint: disable=too-many-nested-blocks
        for metric in metrics:
            if metric.unit == "ms":
                self.assertEqual(metric.name, "http.server.duration")
            elif metric.unit == "s":
                self.assertEqual(metric.name, "http.server.request.duration")
            else:
                self.assertEqual(metric.name, "http.server.active_requests")
            data_points = list(metric.data.data_points)
            self.assertEqual(len(data_points), 1)
            for point in data_points:
                if isinstance(point, HistogramDataPoint):
                    self.assertEqual(point.count, 1)
                    if metric.unit == "ms":
                        self.assertAlmostEqual(
                            max(round(duration_s * 1000), 0),
                            point.sum,
                            delta=10,
                        )
                    elif metric.unit == "s":
                        self.assertAlmostEqual(
                            max(duration_s, 0), point.sum, delta=10
                        )
                        self.assertEqual(
                            point.explicit_bounds,
                            HTTP_DURATION_HISTOGRAM_BUCKETS_NEW,
                        )

                    histogram_data_point_seen = True
                if isinstance(point, NumberDataPoint):
                    self.assertEqual(point.value, 0)
                    number_data_point_seen = True
                for attr in point.attributes:
                    self.assertIn(
                        attr,
                        _recommended_metrics_attrs_both[metric.name],
                    )
        self.assertTrue(number_data_point_seen and histogram_data_point_seen)

    def test_falcon_metric_values(self):
        number_data_point_seen = False
        histogram_data_point_seen = False

        start = default_timer()
        self.client().simulate_get("/hello/756")
        duration = max(round((default_timer() - start) * 1000), 0)

        metrics = self.get_sorted_metrics()
        for metric in metrics:
            data_points = list(metric.data.data_points)
            self.assertEqual(len(data_points), 1)
            for point in list(metric.data.data_points):
                if isinstance(point, HistogramDataPoint):
                    self.assertEqual(point.count, 1)
                    histogram_data_point_seen = True
                    self.assertAlmostEqual(duration, point.sum, delta=10)
                if isinstance(point, NumberDataPoint):
                    self.assertEqual(point.value, 0)
                    number_data_point_seen = True
                for attr in point.attributes:
                    self.assertIn(
                        attr,
                        _recommended_metrics_attrs_old[metric.name],
                    )

        self.assertTrue(number_data_point_seen and histogram_data_point_seen)

    def test_metric_uninstrument(self):
        self.client().simulate_request(method="POST", path="/hello/756")
        FalconInstrumentor().uninstrument()
        self.client().simulate_request(method="POST", path="/hello/756")
        metrics = self.get_sorted_metrics()
        for metric in metrics:
            for point in list(metric.data.data_points):
                if isinstance(point, HistogramDataPoint):
                    self.assertEqual(point.count, 1)


class TestFalconManualInstrumentation(TestFalconInstrumentation):
    def setUp(self):
        TestBase.setUp(self)
        self.env_patch = patch.dict(
            "os.environ",
            {
                "OTEL_PYTHON_FALCON_EXCLUDED_URLS": "ping",
                "OTEL_PYTHON_FALCON_TRACED_REQUEST_ATTRS": "query_string",
            },
        )
        self.env_patch.start()
        self.app = make_app()

        self.app = FalconInstrumentor.instrument_app(
            self.app,
            request_hook=getattr(self, "request_hook", None),
            response_hook=getattr(self, "response_hook", None),
        )

    def client(self):
        return testing.TestClient(self.app)

    def tearDown(self):
        TestBase.tearDown(self)
        with self.disable_logging():
            FalconInstrumentor.uninstrument_app(self.app)
        self.env_patch.stop()

    def test_uninstrument_after_instrument(self):
        self.client().simulate_get(path="/hello")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        FalconInstrumentor.uninstrument_app(self.app)
        self.memory_exporter.clear()

        self.client().simulate_get(path="/hello")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_metric_uninstrument(self):
        self.client().simulate_request(method="POST", path="/hello/756")
        FalconInstrumentor.uninstrument_app(self.app)
        self.client().simulate_request(method="POST", path="/hello/756")
        metrics_list = self.memory_metrics_reader.get_metrics_data()
        for resource_metric in metrics_list.resource_metrics:
            for scope_metric in resource_metric.scope_metrics:
                for metric in scope_metric.metrics:
                    for point in list(metric.data.data_points):
                        if isinstance(point, HistogramDataPoint):
                            self.assertEqual(point.count, 1)

    def test_falcon_attribute_validity(self):
        import falcon
        _parsed_falcon_version = package_version.parse(falcon.__version__)
        if _parsed_falcon_version < package_version.parse("3.0.0"):
            # Falcon 1 and Falcon 2

            class MyAPI(falcon.API):
                class_var = "class_var"

            self.app = MyAPI()
        else:
            # Falcon 3
            class MyAPP(falcon.App):
                class_var = "class_var"

            self.app = MyAPP()
        
        self.app = FalconInstrumentor.instrument_app(self.app)
        self.assertEqual(self.app.class_var, "class_var")


class TestFalconInstrumentationWithTracerProvider(TestBase):
    def setUp(self):
        super().setUp()
        resource = Resource.create({"resource-key": "resource-value"})
        result = self.create_tracer_provider(resource=resource)
        tracer_provider, exporter = result
        self.exporter = exporter

        FalconInstrumentor().instrument(tracer_provider=tracer_provider)
        self.app = make_app()

    def client(self):
        return testing.TestClient(self.app)

    def tearDown(self):
        super().tearDown()
        with self.disable_logging():
            FalconInstrumentor().uninstrument()

    def test_traced_request(self):
        self.client().simulate_request(method="GET", path="/hello")
        spans = self.exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(
            span.resource.attributes["resource-key"], "resource-value"
        )
        self.exporter.clear()


class TestFalconManualInstrumentationWithTracerProvider(
    TestFalconInstrumentationWithTracerProvider
):
    def setUp(self):
        TestBase.setUp(self)
        resource = Resource.create({"resource-key": "resource-value"})
        result = self.create_tracer_provider(resource=resource)
        tracer_provider, exporter = result
        self.exporter = exporter
        self.app = make_app()
        self.app = FalconInstrumentor.instrument_app(
            self.app, tracer_provider=tracer_provider
        )

    def client(self):
        return testing.TestClient(self.app)

    def tearDown(self):
        TestBase.tearDown(self)
        with self.disable_logging():
            FalconInstrumentor.uninstrument_app(self.app)


class TestFalconInstrumentationHooks(TestFalconBase):
    # pylint: disable=no-self-use
    def request_hook(self, span, req):
        span.set_attribute("request_hook_attr", "value from hook")

    def response_hook(self, span, req, resp):
        span.update_name("set from hook")

    def test_hooks(self):
        self.client().simulate_get(path="/hello", query_string="q=abc")
        span = self.memory_exporter.get_finished_spans()[0]

        self.assertEqual(span.name, "set from hook")
        self.assertIn("request_hook_attr", span.attributes)
        self.assertEqual(
            span.attributes["request_hook_attr"], "value from hook"
        )


class TestFalconManualInstrumentationHooks(TestFalconInstrumentationHooks):
    def setUp(self):
        TestBase.setUp(self)
        self.env_patch = patch.dict(
            "os.environ",
            {
                "OTEL_PYTHON_FALCON_EXCLUDED_URLS": "ping",
                "OTEL_PYTHON_FALCON_TRACED_REQUEST_ATTRS": "query_string",
            },
        )
        self.env_patch.start()
        self.app = make_app()

        self.app = FalconInstrumentor.instrument_app(
            self.app,
            request_hook=getattr(self, "request_hook", None),
            response_hook=getattr(self, "response_hook", None),
        )

    def client(self):
        return testing.TestClient(self.app)

    def tearDown(self):
        TestBase.tearDown(self)
        with self.disable_logging():
            FalconInstrumentor.uninstrument_app(self.app)
        self.env_patch.stop()


class TestFalconInstrumentationWrappedWithOtherFramework(TestFalconBase):
    def test_mark_span_internal_in_presence_of_span_from_other_framework(self):
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span(
            "test", kind=trace.SpanKind.SERVER
        ) as parent_span:
            self.client().simulate_request(method="GET", path="/hello")
            span = self.memory_exporter.get_finished_spans()[0]
            assert span.status.is_ok
            self.assertEqual(trace.SpanKind.INTERNAL, span.kind)
            self.assertEqual(
                span.parent.span_id, parent_span.get_span_context().span_id
            )


class TestFalconManualInstrumentationWrappedWithOtherFramework(
    TestFalconInstrumentationWrappedWithOtherFramework
):
    def setUp(self):
        TestBase.setUp(self)
        self.env_patch = patch.dict(
            "os.environ",
            {
                "OTEL_PYTHON_FALCON_EXCLUDED_URLS": "ping",
                "OTEL_PYTHON_FALCON_TRACED_REQUEST_ATTRS": "query_string",
            },
        )
        self.env_patch.start()
        self.app = make_app()

        self.app = FalconInstrumentor.instrument_app(
            self.app,
            request_hook=getattr(self, "request_hook", None),
            response_hook=getattr(self, "response_hook", None),
        )

    def client(self):
        return testing.TestClient(self.app)

    def tearDown(self):
        TestBase.tearDown(self)
        with self.disable_logging():
            FalconInstrumentor.uninstrument_app(self.app)


@patch.dict(
    "os.environ",
    {
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS: ".*my-secret.*",
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST: "Custom-Test-Header-1,Custom-Test-Header-2,invalid-header,Regex-Test-Header-.*,Regex-Invalid-Test-Header-.*,.*my-secret.*",
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE: "content-type,content-length,my-custom-header,invalid-header,my-custom-regex-header-.*,invalid-regex-header-.*,.*my-secret.*",
    },
)
class TestCustomRequestResponseHeaders(TestFalconBase):
    def test_custom_request_header_added_in_server_span(self):
        headers = {
            "Custom-Test-Header-1": "Test Value 1",
            "Custom-Test-Header-2": "TestValue2,TestValue3",
            "Custom-Test-Header-3": "TestValue4",
            "Regex-Test-Header-1": "Regex Test Value 1",
            "regex-test-header-2": "RegexTestValue2,RegexTestValue3",
            "My-Secret-Header": "My Secret Value",
        }
        self.client().simulate_request(
            method="GET", path="/hello", headers=headers
        )
        span = self.memory_exporter.get_finished_spans()[0]
        assert span.status.is_ok

        expected = {
            "http.request.header.custom_test_header_1": ("Test Value 1",),
            "http.request.header.custom_test_header_2": (
                "TestValue2,TestValue3",
            ),
            "http.request.header.regex_test_header_1": ("Regex Test Value 1",),
            "http.request.header.regex_test_header_2": (
                "RegexTestValue2,RegexTestValue3",
            ),
            "http.request.header.my_secret_header": ("[REDACTED]",),
        }
        not_expected = {
            "http.request.header.custom_test_header_3": ("TestValue4",),
        }

        self.assertEqual(span.kind, trace.SpanKind.SERVER)
        self.assertSpanHasAttributes(span, expected)
        for key, _ in not_expected.items():
            self.assertNotIn(key, span.attributes)

    def test_custom_request_header_not_added_in_internal_span(self):
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("test", kind=trace.SpanKind.SERVER):
            headers = {
                "Custom-Test-Header-1": "Test Value 1",
                "Custom-Test-Header-2": "TestValue2,TestValue3",
                "Regex-Test-Header-1": "Regex Test Value 1",
                "regex-test-header-2": "RegexTestValue2,RegexTestValue3",
                "My-Secret-Header": "My Secret Value",
            }
            self.client().simulate_request(
                method="GET", path="/hello", headers=headers
            )
            span = self.memory_exporter.get_finished_spans()[0]
            assert span.status.is_ok
            not_expected = {
                "http.request.header.custom_test_header_1": ("Test Value 1",),
                "http.request.header.custom_test_header_2": (
                    "TestValue2,TestValue3",
                ),
                "http.request.header.regex_test_header_1": (
                    "Regex Test Value 1",
                ),
                "http.request.header.regex_test_header_2": (
                    "RegexTestValue2,RegexTestValue3",
                ),
                "http.request.header.my_secret_header": ("[REDACTED]",),
            }
            self.assertEqual(span.kind, trace.SpanKind.INTERNAL)
            for key, _ in not_expected.items():
                self.assertNotIn(key, span.attributes)

    @pytest.mark.skipif(
        condition=_parsed_falcon_version < package_version.parse("2.0.0"),
        reason="falcon<2 does not implement custom response headers",
    )
    def test_custom_response_header_added_in_server_span(self):
        self.client().simulate_request(
            method="GET", path="/test_custom_response_headers"
        )
        span = self.memory_exporter.get_finished_spans()[0]
        assert span.status.is_ok
        expected = {
            "http.response.header.content_type": (
                "text/plain; charset=utf-8",
            ),
            "http.response.header.content_length": ("0",),
            "http.response.header.my_custom_header": (
                "my-custom-value-1,my-custom-header-2",
            ),
            "http.response.header.my_custom_regex_header_1": (
                "my-custom-regex-value-1,my-custom-regex-value-2",
            ),
            "http.response.header.my_custom_regex_header_2": (
                "my-custom-regex-value-3,my-custom-regex-value-4",
            ),
            "http.response.header.my_secret_header": ("[REDACTED]",),
        }
        not_expected = {
            "http.response.header.dont_capture_me": ("test-value",)
        }
        self.assertEqual(span.kind, trace.SpanKind.SERVER)
        self.assertSpanHasAttributes(span, expected)
        for key, _ in not_expected.items():
            self.assertNotIn(key, span.attributes)

    @pytest.mark.skipif(
        condition=_parsed_falcon_version < package_version.parse("2.0.0"),
        reason="falcon<2 does not implement custom response headers",
    )
    def test_custom_response_header_not_added_in_internal_span(self):
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("test", kind=trace.SpanKind.SERVER):
            self.client().simulate_request(
                method="GET", path="/test_custom_response_headers"
            )
            span = self.memory_exporter.get_finished_spans()[0]
            assert span.status.is_ok
            not_expected = {
                "http.response.header.content_type": (
                    "text/plain; charset=utf-8",
                ),
                "http.response.header.content_length": ("0",),
                "http.response.header.my_custom_header": (
                    "my-custom-value-1,my-custom-header-2",
                ),
                "http.response.header.my_custom_regex_header_1": (
                    "my-custom-regex-value-1,my-custom-regex-value-2",
                ),
                "http.response.header.my_custom_regex_header_2": (
                    "my-custom-regex-value-3,my-custom-regex-value-4",
                ),
                "http.response.header.my_secret_header": ("[REDACTED]",),
            }
            self.assertEqual(span.kind, trace.SpanKind.INTERNAL)
            for key, _ in not_expected.items():
                self.assertNotIn(key, span.attributes)


class TestCustomRequestResponseHeadersManualInstrumentation(
    TestCustomRequestResponseHeaders
):
    def setUp(self):
        TestBase.setUp(self)
        self.env_patch = patch.dict(
            "os.environ",
            {
                "OTEL_PYTHON_FALCON_EXCLUDED_URLS": "ping",
                "OTEL_PYTHON_FALCON_TRACED_REQUEST_ATTRS": "query_string",
            },
        )
        self.env_patch.start()
        self.app = make_app()

        self.app = FalconInstrumentor.instrument_app(
            self.app,
            request_hook=getattr(self, "request_hook", None),
            response_hook=getattr(self, "response_hook", None),
        )

    def client(self):
        return testing.TestClient(self.app)

    def tearDown(self):
        TestBase.tearDown(self)
        with self.disable_logging():
            FalconInstrumentor.uninstrument_app(self.app)
