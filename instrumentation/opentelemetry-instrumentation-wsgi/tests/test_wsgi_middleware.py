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

import sys
import unittest
import wsgiref.util as wsgiref_util
from unittest import mock
from urllib.parse import urlsplit

import opentelemetry.instrumentation.wsgi as otel_wsgi
from opentelemetry import trace as trace_api
from opentelemetry.instrumentation._semconv import (
    HTTP_DURATION_HISTOGRAM_BUCKETS_NEW,
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
    _server_active_requests_count_attrs_new,
    _server_active_requests_count_attrs_old,
    _server_duration_attrs_new,
    _server_duration_attrs_old,
    _StabilityMode,
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
    HTTP_URL,
    HTTP_USER_AGENT,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_HOST_NAME,
    NET_HOST_PORT,
)
from opentelemetry.semconv._incubating.attributes.user_agent_attributes import (
    USER_AGENT_SYNTHETIC_TYPE,
)
from opentelemetry.semconv.attributes.http_attributes import (
    HTTP_REQUEST_METHOD,
    HTTP_RESPONSE_STATUS_CODE,
)
from opentelemetry.semconv.attributes.network_attributes import (
    NETWORK_PROTOCOL_VERSION,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.semconv.attributes.url_attributes import (
    URL_FULL,
    URL_PATH,
    URL_QUERY,
    URL_SCHEME,
)
from opentelemetry.semconv.attributes.user_agent_attributes import (
    USER_AGENT_ORIGINAL,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.test.wsgitestutil import WsgiTestBase
from opentelemetry.trace import StatusCode
from opentelemetry.util.http import (
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE,
    OTEL_PYTHON_INSTRUMENTATION_HTTP_CAPTURE_ALL_METHODS,
)


class Response:
    def __init__(self):
        self.iter = iter([b"*"])
        self.close_calls = 0

    def __iter__(self):
        return self

    def __next__(self):
        return next(self.iter)

    def close(self):
        self.close_calls += 1


def simple_wsgi(environ, start_response):
    assert isinstance(environ, dict)
    start_response("200 OK", [("Content-Type", "text/plain")])
    return [b"*"]


def create_iter_wsgi(response):
    def iter_wsgi(environ, start_response):
        assert isinstance(environ, dict)
        start_response("200 OK", [("Content-Type", "text/plain")])
        return response

    return iter_wsgi


def create_gen_wsgi(response):
    def gen_wsgi(environ, start_response):
        result = create_iter_wsgi(response)(environ, start_response)
        yield from result
        getattr(result, "close", lambda: None)()

    return gen_wsgi


def error_wsgi(environ, start_response):
    assert isinstance(environ, dict)
    exc_info = None
    try:
        raise ValueError
    except ValueError:
        exc_info = sys.exc_info()
    start_response("200 OK", [("Content-Type", "text/plain")], exc_info)
    exc_info = None
    return [b"*"]


def error_wsgi_unhandled(environ, start_response):
    assert isinstance(environ, dict)
    raise ValueError


def wsgi_with_custom_response_headers(environ, start_response):
    assert isinstance(environ, dict)
    start_response(
        "200 OK",
        [
            ("content-type", "text/plain; charset=utf-8"),
            ("content-length", "100"),
            ("my-custom-header", "my-custom-value-1,my-custom-header-2"),
            (
                "my-custom-regex-header-1",
                "my-custom-regex-value-1,my-custom-regex-value-2",
            ),
            (
                "My-Custom-Regex-Header-2",
                "my-custom-regex-value-3,my-custom-regex-value-4",
            ),
            ("My-Secret-Header", "My Secret Value"),
        ],
    )
    return [b"*"]


def wsgi_with_repeat_custom_response_headers(environ, start_response):
    assert isinstance(environ, dict)
    start_response(
        "200 OK",
        [
            ("my-custom-header", "my-custom-value-1"),
            ("my-custom-header", "my-custom-value-2"),
        ],
    )
    return [b"*"]


_expected_metric_names_old = [
    "http.server.active_requests",
    "http.server.duration",
]
_expected_metric_names_new = [
    "http.server.active_requests",
    "http.server.request.duration",
]
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


class TestWsgiApplication(WsgiTestBase):
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
        self.env_patch = mock.patch.dict(
            "os.environ",
            {
                OTEL_SEMCONV_STABILITY_OPT_IN: sem_conv_mode,
            },
        )

        _OpenTelemetrySemanticConventionStability._initialized = False

        self.env_patch.start()

    def validate_response(
        self,
        response,
        error=None,
        span_name="GET /",
        http_method="GET",
        span_attributes=None,
        response_headers=None,
        old_sem_conv=True,
        new_sem_conv=False,
    ):
        while True:
            try:
                value = next(response)
                self.assertEqual(value, b"*")
            except StopIteration:
                break

        expected_headers = [("Content-Type", "text/plain")]
        if response_headers:
            expected_headers.extend(response_headers)

        self.assertEqual(self.status, "200 OK")
        self.assertEqual(self.response_headers, expected_headers)
        if error:
            self.assertIs(self.exc_info[0], error)
            self.assertIsInstance(self.exc_info[1], error)
            self.assertIsNotNone(self.exc_info[2])
        else:
            self.assertIsNone(self.exc_info)

        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)
        self.assertEqual(span_list[0].name, span_name)
        self.assertEqual(span_list[0].kind, trace_api.SpanKind.SERVER)
        expected_attributes = {}
        expected_attributes_old = {
            HTTP_SERVER_NAME: "127.0.0.1",
            HTTP_SCHEME: "http",
            NET_HOST_PORT: 80,
            HTTP_HOST: "127.0.0.1",
            HTTP_FLAVOR: "1.0",
            HTTP_URL: "http://127.0.0.1/",
            HTTP_STATUS_CODE: 200,
            NET_HOST_NAME: "127.0.0.1",
        }
        expected_attributes_new = {
            SERVER_PORT: 80,
            SERVER_ADDRESS: "127.0.0.1",
            NETWORK_PROTOCOL_VERSION: "1.0",
            HTTP_RESPONSE_STATUS_CODE: 200,
            URL_SCHEME: "http",
        }
        if old_sem_conv:
            expected_attributes.update(expected_attributes_old)
        if new_sem_conv:
            expected_attributes.update(expected_attributes_new)

        expected_attributes.update(span_attributes or {})
        if http_method is not None:
            if old_sem_conv:
                expected_attributes[HTTP_METHOD] = http_method
            if new_sem_conv:
                expected_attributes[HTTP_REQUEST_METHOD] = http_method
        self.assertEqual(span_list[0].attributes, expected_attributes)

    def test_basic_wsgi_call(self):
        app = otel_wsgi.OpenTelemetryMiddleware(simple_wsgi)
        response = app(self.environ, self.start_response)
        self.validate_response(response)

    def test_basic_wsgi_call_new_semconv(self):
        app = otel_wsgi.OpenTelemetryMiddleware(simple_wsgi)
        response = app(self.environ, self.start_response)
        self.validate_response(response, old_sem_conv=False, new_sem_conv=True)

    def test_basic_wsgi_call_both_semconv(self):
        app = otel_wsgi.OpenTelemetryMiddleware(simple_wsgi)
        response = app(self.environ, self.start_response)
        self.validate_response(response, old_sem_conv=True, new_sem_conv=True)

    def test_hooks(self):
        hook_headers = (
            "hook_attr",
            "hello otel",
        )

        def request_hook(span, environ):
            span.update_name("name from hook")

        def response_hook(span, environ, status_code, response_headers):
            span.set_attribute("hook_attr", "hello world")
            response_headers.append(hook_headers)

        app = otel_wsgi.OpenTelemetryMiddleware(
            simple_wsgi, request_hook, response_hook
        )
        response = app(self.environ, self.start_response)
        self.validate_response(
            response,
            span_name="name from hook",
            span_attributes={"hook_attr": "hello world"},
            response_headers=(hook_headers,),
        )

    def test_wsgi_not_recording(self):
        mock_tracer = mock.Mock()
        mock_span = mock.Mock()
        mock_span.is_recording.return_value = False
        mock_tracer.start_span.return_value = mock_span
        with mock.patch("opentelemetry.trace.get_tracer") as tracer:
            tracer.return_value = mock_tracer
            app = otel_wsgi.OpenTelemetryMiddleware(simple_wsgi)
            # pylint: disable=W0612
            response = app(self.environ, self.start_response)  # noqa: F841
            self.assertFalse(mock_span.is_recording())
            self.assertTrue(mock_span.is_recording.called)
            self.assertFalse(mock_span.set_attribute.called)
            self.assertFalse(mock_span.set_status.called)

    def test_wsgi_iterable(self):
        original_response = Response()
        iter_wsgi = create_iter_wsgi(original_response)
        app = otel_wsgi.OpenTelemetryMiddleware(iter_wsgi)
        response = app(self.environ, self.start_response)
        # Verify that start_response has been called
        self.assertTrue(self.status)
        self.validate_response(response)

        # Verify that close has been called exactly once
        self.assertEqual(1, original_response.close_calls)

    def test_wsgi_generator(self):
        original_response = Response()
        gen_wsgi = create_gen_wsgi(original_response)
        app = otel_wsgi.OpenTelemetryMiddleware(gen_wsgi)
        response = app(self.environ, self.start_response)
        # Verify that start_response has not been called
        self.assertIsNone(self.status)
        self.validate_response(response)

        # Verify that close has been called exactly once
        self.assertEqual(original_response.close_calls, 1)

    def test_wsgi_exc_info(self):
        app = otel_wsgi.OpenTelemetryMiddleware(error_wsgi)
        response = app(self.environ, self.start_response)
        self.validate_response(response, error=ValueError)

    def test_wsgi_internal_error(self):
        app = otel_wsgi.OpenTelemetryMiddleware(error_wsgi_unhandled)
        self.assertRaises(ValueError, app, self.environ, self.start_response)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)
        self.assertEqual(
            span_list[0].status.status_code,
            StatusCode.ERROR,
        )

    def test_wsgi_metrics(self):
        app = otel_wsgi.OpenTelemetryMiddleware(error_wsgi_unhandled)
        self.assertRaises(ValueError, app, self.environ, self.start_response)
        self.assertRaises(ValueError, app, self.environ, self.start_response)
        self.assertRaises(ValueError, app, self.environ, self.start_response)
        metrics_list = self.memory_metrics_reader.get_metrics_data()
        number_data_point_seen = False
        histogram_data_point_seen = False

        self.assertTrue(len(metrics_list.resource_metrics) != 0)
        for resource_metric in metrics_list.resource_metrics:
            self.assertTrue(len(resource_metric.scope_metrics) != 0)
            for scope_metric in resource_metric.scope_metrics:
                self.assertTrue(len(scope_metric.metrics) != 0)
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
                                attr,
                                _recommended_metrics_attrs_old[metric.name],
                            )
        self.assertTrue(number_data_point_seen and histogram_data_point_seen)

    def test_wsgi_metrics_new_semconv(self):
        # pylint: disable=too-many-nested-blocks
        app = otel_wsgi.OpenTelemetryMiddleware(error_wsgi_unhandled)
        self.assertRaises(ValueError, app, self.environ, self.start_response)
        self.assertRaises(ValueError, app, self.environ, self.start_response)
        self.assertRaises(ValueError, app, self.environ, self.start_response)
        metrics_list = self.memory_metrics_reader.get_metrics_data()
        number_data_point_seen = False
        histogram_data_point_seen = False

        self.assertTrue(len(metrics_list.resource_metrics) != 0)
        for resource_metric in metrics_list.resource_metrics:
            self.assertTrue(len(resource_metric.scope_metrics) != 0)
            for scope_metric in resource_metric.scope_metrics:
                self.assertTrue(len(scope_metric.metrics) != 0)
                for metric in scope_metric.metrics:
                    self.assertIn(metric.name, _expected_metric_names_new)
                    data_points = list(metric.data.data_points)
                    self.assertEqual(len(data_points), 1)
                    for point in data_points:
                        if isinstance(point, HistogramDataPoint):
                            self.assertEqual(point.count, 3)
                            if metric.name == "http.server.request.duration":
                                self.assertEqual(
                                    point.explicit_bounds,
                                    HTTP_DURATION_HISTOGRAM_BUCKETS_NEW,
                                )
                            histogram_data_point_seen = True
                        if isinstance(point, NumberDataPoint):
                            number_data_point_seen = True
                        for attr in point.attributes:
                            self.assertIn(
                                attr,
                                _recommended_metrics_attrs_new[metric.name],
                            )
        self.assertTrue(number_data_point_seen and histogram_data_point_seen)

    def test_wsgi_metrics_both_semconv(self):
        # pylint: disable=too-many-nested-blocks
        app = otel_wsgi.OpenTelemetryMiddleware(error_wsgi_unhandled)
        self.assertRaises(ValueError, app, self.environ, self.start_response)
        metrics_list = self.memory_metrics_reader.get_metrics_data()
        number_data_point_seen = False
        histogram_data_point_seen = False

        self.assertTrue(len(metrics_list.resource_metrics) != 0)
        for resource_metric in metrics_list.resource_metrics:
            self.assertTrue(len(resource_metric.scope_metrics) != 0)
            for scope_metric in resource_metric.scope_metrics:
                self.assertTrue(len(scope_metric.metrics) != 0)
                for metric in scope_metric.metrics:
                    if metric.unit == "ms":
                        self.assertEqual(metric.name, "http.server.duration")
                    elif metric.unit == "s":
                        self.assertEqual(
                            metric.name, "http.server.request.duration"
                        )
                    else:
                        self.assertEqual(
                            metric.name, "http.server.active_requests"
                        )
                    data_points = list(metric.data.data_points)
                    self.assertEqual(len(data_points), 1)
                    for point in data_points:
                        if isinstance(point, HistogramDataPoint):
                            self.assertEqual(point.count, 1)
                            if metric.name == "http.server.request.duration":
                                self.assertEqual(
                                    point.explicit_bounds,
                                    HTTP_DURATION_HISTOGRAM_BUCKETS_NEW,
                                )
                            histogram_data_point_seen = True
                        if isinstance(point, NumberDataPoint):
                            number_data_point_seen = True
                        for attr in point.attributes:
                            self.assertIn(
                                attr,
                                _recommended_metrics_attrs_both[metric.name],
                            )
        self.assertTrue(number_data_point_seen and histogram_data_point_seen)

    def test_nonstandard_http_method(self):
        self.environ["REQUEST_METHOD"] = "NONSTANDARD"
        app = otel_wsgi.OpenTelemetryMiddleware(simple_wsgi)
        response = app(self.environ, self.start_response)
        self.validate_response(
            response, span_name="HTTP", http_method="_OTHER"
        )

    @mock.patch.dict(
        "os.environ",
        {
            OTEL_PYTHON_INSTRUMENTATION_HTTP_CAPTURE_ALL_METHODS: "1",
        },
    )
    def test_nonstandard_http_method_allowed(self):
        self.environ["REQUEST_METHOD"] = "NONSTANDARD"
        app = otel_wsgi.OpenTelemetryMiddleware(simple_wsgi)
        response = app(self.environ, self.start_response)
        self.validate_response(
            response, span_name="NONSTANDARD /", http_method="NONSTANDARD"
        )

    def test_default_span_name_missing_path_info(self):
        """Test that default span_names with missing path info."""
        self.environ.pop("PATH_INFO")
        method = self.environ.get("REQUEST_METHOD", "").strip()
        app = otel_wsgi.OpenTelemetryMiddleware(simple_wsgi)
        response = app(self.environ, self.start_response)
        self.validate_response(response, span_name=method)


# pylint: disable=too-many-public-methods
class TestWsgiAttributes(unittest.TestCase):
    def setUp(self):
        self.environ = {}
        wsgiref_util.setup_testing_defaults(self.environ)
        self.span = mock.create_autospec(trace_api.Span, spec_set=True)

    def test_request_attributes(self):
        self.environ["QUERY_STRING"] = "foo=bar"

        attrs = otel_wsgi.collect_request_attributes(self.environ)
        self.assertDictEqual(
            attrs,
            {
                HTTP_METHOD: "GET",
                HTTP_HOST: "127.0.0.1",
                HTTP_URL: "http://127.0.0.1/?foo=bar",
                NET_HOST_PORT: 80,
                HTTP_SCHEME: "http",
                HTTP_SERVER_NAME: "127.0.0.1",
                HTTP_FLAVOR: "1.0",
                NET_HOST_NAME: "127.0.0.1",
            },
        )

    def test_request_attributes_new_semconv(self):
        self.environ["QUERY_STRING"] = "foo=bar"
        self.environ["REQUEST_URI"] = "http://127.0.0.1/?foo=bar"

        attrs = otel_wsgi.collect_request_attributes(
            self.environ,
            _StabilityMode.HTTP,
        )
        self.assertDictEqual(
            attrs,
            {
                HTTP_REQUEST_METHOD: "GET",
                SERVER_ADDRESS: "127.0.0.1",
                SERVER_PORT: 80,
                NETWORK_PROTOCOL_VERSION: "1.0",
                URL_PATH: "/",
                URL_QUERY: "foo=bar",
                URL_SCHEME: "http",
            },
        )

    def validate_url(
        self,
        expected_url,
        raw=False,
        has_host=True,
        old_semconv=True,
        new_semconv=False,
    ):
        parts = urlsplit(expected_url)
        expected_old = {
            HTTP_SCHEME: parts.scheme,
            NET_HOST_PORT: parts.port
            or (80 if parts.scheme == "http" else 443),
            HTTP_SERVER_NAME: parts.hostname,  # Not true in the general case, but for all tests.
        }
        expected_new = {
            SERVER_PORT: parts.port or (80 if parts.scheme == "http" else 443),
            SERVER_ADDRESS: parts.hostname,
            URL_PATH: parts.path,
            URL_QUERY: parts.query,
        }
        if old_semconv:
            if raw:
                expected_old[HTTP_TARGET] = expected_url.split(
                    parts.netloc, 1
                )[1]
            else:
                expected_old[HTTP_URL] = expected_url
            if has_host:
                expected_old[HTTP_HOST] = parts.hostname
        if new_semconv:
            if raw:
                expected_new[URL_PATH] = expected_url.split(parts.path, 1)[1]
                if parts.query:
                    expected_new[URL_QUERY] = expected_url.split(
                        parts.query, 1
                    )[1]
            else:
                expected_new[URL_FULL] = expected_url
            if has_host:
                expected_new[SERVER_ADDRESS] = parts.hostname

        attrs = otel_wsgi.collect_request_attributes(self.environ)
        self.assertGreaterEqual(
            attrs.items(), expected_old.items(), expected_url + " expected."
        )

    def test_request_attributes_with_partial_raw_uri(self):
        self.environ["RAW_URI"] = "/?foo=bar/#top"
        self.validate_url("http://127.0.0.1/?foo=bar/#top", raw=True)
        self.validate_url(
            "http://127.0.0.1/?foo=bar/#top",
            raw=True,
            old_semconv=False,
            new_semconv=True,
        )
        self.validate_url(
            "http://127.0.0.1/?foo=bar/#top",
            raw=True,
            old_semconv=True,
            new_semconv=True,
        )

    def test_request_attributes_with_partial_raw_uri_and_nonstandard_port(
        self,
    ):
        self.environ["RAW_URI"] = "/?"
        del self.environ["HTTP_HOST"]
        self.environ["SERVER_PORT"] = "8080"
        self.validate_url("http://127.0.0.1:8080/?", raw=True, has_host=False)
        self.validate_url(
            "http://127.0.0.1:8080/?",
            raw=True,
            has_host=False,
            old_semconv=False,
            new_semconv=True,
        )
        self.validate_url(
            "http://127.0.0.1:8080/?",
            raw=True,
            has_host=False,
            old_semconv=True,
            new_semconv=True,
        )

    def test_https_uri_port(self):
        del self.environ["HTTP_HOST"]
        self.environ["SERVER_PORT"] = "443"
        self.environ["wsgi.url_scheme"] = "https"
        self.validate_url("https://127.0.0.1/", has_host=False)
        self.validate_url(
            "https://127.0.0.1/",
            has_host=False,
            old_semconv=False,
            new_semconv=True,
        )
        self.validate_url(
            "https://127.0.0.1/",
            has_host=False,
            old_semconv=True,
            new_semconv=True,
        )

        self.environ["SERVER_PORT"] = "8080"
        self.validate_url("https://127.0.0.1:8080/", has_host=False)
        self.validate_url(
            "https://127.0.0.1:8080/",
            has_host=False,
            old_semconv=False,
            new_semconv=True,
        )
        self.validate_url(
            "https://127.0.0.1:8080/",
            has_host=False,
            old_semconv=True,
            new_semconv=True,
        )

        self.environ["SERVER_PORT"] = "80"
        self.validate_url("https://127.0.0.1:80/", has_host=False)
        self.validate_url(
            "https://127.0.0.1:80/",
            has_host=False,
            old_semconv=False,
            new_semconv=True,
        )
        self.validate_url(
            "https://127.0.0.1:80/",
            has_host=False,
            old_semconv=True,
            new_semconv=True,
        )

    def test_http_uri_port(self):
        del self.environ["HTTP_HOST"]
        self.environ["SERVER_PORT"] = "80"
        self.environ["wsgi.url_scheme"] = "http"
        self.validate_url("http://127.0.0.1/", has_host=False)

        self.environ["SERVER_PORT"] = "8080"
        self.validate_url("http://127.0.0.1:8080/", has_host=False)

        self.environ["SERVER_PORT"] = "443"
        self.validate_url("http://127.0.0.1:443/", has_host=False)

    def test_request_attributes_with_nonstandard_port_and_no_host(self):
        del self.environ["HTTP_HOST"]
        self.environ["SERVER_PORT"] = "8080"
        self.validate_url("http://127.0.0.1:8080/", has_host=False)

        self.environ["SERVER_PORT"] = "443"
        self.validate_url("http://127.0.0.1:443/", has_host=False)

    def test_request_attributes_with_conflicting_nonstandard_port(self):
        self.environ["HTTP_HOST"] += (
            ":8080"  # Note that we do not correct SERVER_PORT
        )
        expected = {
            HTTP_HOST: "127.0.0.1:8080",
            HTTP_URL: "http://127.0.0.1:8080/",
            NET_HOST_PORT: 80,
        }
        self.assertGreaterEqual(
            otel_wsgi.collect_request_attributes(self.environ).items(),
            expected.items(),
        )

    def test_request_attributes_with_faux_scheme_relative_raw_uri(self):
        self.environ["RAW_URI"] = "//127.0.0.1/?"
        self.validate_url("http://127.0.0.1//127.0.0.1/?", raw=True)

    def test_request_attributes_pathless(self):
        self.environ["RAW_URI"] = ""
        self.assertIsNone(
            otel_wsgi.collect_request_attributes(self.environ).get(HTTP_TARGET)
        )

    def test_request_attributes_with_full_request_uri(self):
        self.environ["HTTP_HOST"] = "127.0.0.1:8080"
        self.environ["REQUEST_METHOD"] = "CONNECT"
        self.environ["REQUEST_URI"] = (
            "http://docs.python.org:80/3/library/urllib.parse.html?highlight=params#url-parsing"  # Might happen in a CONNECT request
        )
        expected_old = {
            HTTP_HOST: "127.0.0.1:8080",
            HTTP_TARGET: "http://docs.python.org:80/3/library/urllib.parse.html?highlight=params#url-parsing",
        }
        expected_new = {
            URL_PATH: "/3/library/urllib.parse.html",
            URL_QUERY: "highlight=params",
        }
        self.assertGreaterEqual(
            otel_wsgi.collect_request_attributes(self.environ).items(),
            expected_old.items(),
        )
        self.assertGreaterEqual(
            otel_wsgi.collect_request_attributes(
                self.environ,
                _StabilityMode.HTTP,
            ).items(),
            expected_new.items(),
        )

    def test_http_user_agent_attribute(self):
        self.environ["HTTP_USER_AGENT"] = "test-useragent"
        expected = {HTTP_USER_AGENT: "test-useragent"}
        expected_new = {USER_AGENT_ORIGINAL: "test-useragent"}
        self.assertGreaterEqual(
            otel_wsgi.collect_request_attributes(self.environ).items(),
            expected.items(),
        )
        self.assertGreaterEqual(
            otel_wsgi.collect_request_attributes(
                self.environ,
                _StabilityMode.HTTP,
            ).items(),
            expected_new.items(),
        )

    def test_http_user_agent_bytes_like_attribute(self):
        self.environ["HTTP_USER_AGENT"] = b"AlwaysOn-Monitor/1.0"
        attributes = otel_wsgi.collect_request_attributes(self.environ)

        self.assertEqual(attributes[HTTP_USER_AGENT], "AlwaysOn-Monitor/1.0")
        self.assertEqual(attributes[USER_AGENT_SYNTHETIC_TYPE], "test")

    def test_http_user_agent_synthetic_bot_detection(self):
        """Test that bot user agents are detected as synthetic with type 'bot'"""
        test_cases = [
            "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
            "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
            "googlebot/1.0",
            "bingbot/1.0",
        ]

        for user_agent in test_cases:
            with self.subTest(user_agent=user_agent):
                self.environ["HTTP_USER_AGENT"] = user_agent
                attributes = otel_wsgi.collect_request_attributes(self.environ)

                # Should have both the original user agent and synthetic type
                self.assertIn(HTTP_USER_AGENT, attributes)
                self.assertEqual(attributes[HTTP_USER_AGENT], user_agent)
                self.assertIn(USER_AGENT_SYNTHETIC_TYPE, attributes)
                self.assertEqual(attributes[USER_AGENT_SYNTHETIC_TYPE], "bot")

    def test_http_user_agent_synthetic_test_detection(self):
        """Test that test user agents are detected as synthetic with type 'test'"""
        test_cases = [
            "alwayson/1.0",
            "AlwaysOn/2.0",
            "test-alwayson-client",
        ]

        for user_agent in test_cases:
            with self.subTest(user_agent=user_agent):
                self.environ["HTTP_USER_AGENT"] = user_agent
                attributes = otel_wsgi.collect_request_attributes(self.environ)

                # Should have both the original user agent and synthetic type
                self.assertIn(HTTP_USER_AGENT, attributes)
                self.assertEqual(attributes[HTTP_USER_AGENT], user_agent)
                self.assertIn(USER_AGENT_SYNTHETIC_TYPE, attributes)
                self.assertEqual(attributes[USER_AGENT_SYNTHETIC_TYPE], "test")

    def test_http_user_agent_non_synthetic(self):
        """Test that normal user agents are not marked as synthetic"""
        test_cases = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
            "PostmanRuntime/7.28.4",
            "curl/7.68.0",
        ]

        for user_agent in test_cases:
            with self.subTest(user_agent=user_agent):
                self.environ["HTTP_USER_AGENT"] = user_agent
                attributes = otel_wsgi.collect_request_attributes(self.environ)

                # Should have the original user agent but no synthetic type
                self.assertIn(HTTP_USER_AGENT, attributes)
                self.assertEqual(attributes[HTTP_USER_AGENT], user_agent)
                self.assertNotIn(USER_AGENT_SYNTHETIC_TYPE, attributes)

    def test_http_user_agent_synthetic_new_semconv(self):
        """Test synthetic user agent detection with new semantic conventions"""
        self.environ["HTTP_USER_AGENT"] = (
            "Mozilla/5.0 (compatible; Googlebot/2.1)"
        )
        attributes = otel_wsgi.collect_request_attributes(
            self.environ,
            _StabilityMode.HTTP,
        )

        # Should have both the new semconv user agent and synthetic type
        self.assertIn(USER_AGENT_ORIGINAL, attributes)
        self.assertEqual(
            attributes[USER_AGENT_ORIGINAL],
            "Mozilla/5.0 (compatible; Googlebot/2.1)",
        )
        self.assertIn(USER_AGENT_SYNTHETIC_TYPE, attributes)
        self.assertEqual(attributes[USER_AGENT_SYNTHETIC_TYPE], "bot")

    def test_response_attributes(self):
        otel_wsgi.add_response_attributes(self.span, "404 Not Found", {})
        otel_wsgi.add_response_attributes(
            self.span,
            "404 Not Found",
            {},
            sem_conv_opt_in_mode=_StabilityMode.HTTP,
        )
        expected = (mock.call(HTTP_STATUS_CODE, 404),)
        expected_new = (mock.call(HTTP_RESPONSE_STATUS_CODE, 404),)
        self.assertEqual(self.span.set_attribute.call_count, 2)
        self.span.set_attribute.assert_has_calls(expected, any_order=True)
        self.span.set_attribute.assert_has_calls(expected_new, any_order=True)

    def test_response_attributes_noop(self):
        mock_span = mock.Mock()
        mock_span.is_recording.return_value = False

        attrs = {}
        otel_wsgi.add_response_attributes(
            mock_span, "404 Not Found", {}, duration_attrs=attrs
        )

        self.assertEqual(mock_span.set_attribute.call_count, 0)
        self.assertEqual(mock_span.is_recording.call_count, 2)
        self.assertEqual(attrs[HTTP_STATUS_CODE], 404)

    def test_remove_sensitive_params(self):
        self.environ["HTTP_HOST"] = "username:password@mock"
        self.environ["PATH_INFO"] = "/status/200"
        self.environ["QUERY_STRING"] = "sig=secret"
        expected = {
            HTTP_URL: "http://REDACTED:REDACTED@mock/status/200?sig=REDACTED",
            NET_HOST_PORT: 80,
        }
        self.assertGreaterEqual(
            otel_wsgi.collect_request_attributes(self.environ).items(),
            expected.items(),
        )


class TestWsgiMiddlewareWithTracerProvider(WsgiTestBase):
    def validate_response(
        self,
        response,
        exporter,
        error=None,
        span_name="GET /",
        http_method="GET",
    ):
        while True:
            try:
                value = next(response)
                self.assertEqual(value, b"*")
            except StopIteration:
                break

        span_list = exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)
        self.assertEqual(span_list[0].name, span_name)
        self.assertEqual(span_list[0].kind, trace_api.SpanKind.SERVER)
        self.assertEqual(
            span_list[0].resource.attributes["service-key"], "service-value"
        )

    def test_basic_wsgi_call(self):
        resource = Resource.create({"service-key": "service-value"})
        result = TestBase.create_tracer_provider(resource=resource)
        tracer_provider, exporter = result

        app = otel_wsgi.OpenTelemetryMiddleware(
            simple_wsgi, tracer_provider=tracer_provider
        )
        response = app(self.environ, self.start_response)
        self.validate_response(response, exporter)

    def test_no_op_tracer_provider(self):
        app = otel_wsgi.OpenTelemetryMiddleware(
            simple_wsgi, tracer_provider=trace_api.NoOpTracerProvider()
        )

        response = app(self.environ, self.start_response)
        while True:
            try:
                value = next(response)
                self.assertEqual(value, b"*")
            except StopIteration:
                break
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 0)


class TestWsgiMiddlewareWrappedWithAnotherFramework(WsgiTestBase):
    def test_mark_span_internal_in_presence_of_span_from_other_framework(self):
        tracer_provider, exporter = TestBase.create_tracer_provider()
        tracer = tracer_provider.get_tracer(__name__)

        with tracer.start_as_current_span(
            "test", kind=trace_api.SpanKind.SERVER
        ) as parent_span:
            app = otel_wsgi.OpenTelemetryMiddleware(
                simple_wsgi, tracer_provider=tracer_provider
            )
            response = app(self.environ, self.start_response)
            while True:
                try:
                    value = next(response)
                    self.assertEqual(value, b"*")
                except StopIteration:
                    break

            span_list = exporter.get_finished_spans()

            self.assertEqual(trace_api.SpanKind.INTERNAL, span_list[0].kind)
            self.assertEqual(trace_api.SpanKind.SERVER, parent_span.kind)

            # internal span should be child of the parent span we have provided
            self.assertEqual(
                parent_span.context.span_id, span_list[0].parent.span_id
            )


class TestAdditionOfCustomRequestResponseHeaders(WsgiTestBase):
    def setUp(self):
        super().setUp()
        self.tracer = self.tracer_provider.get_tracer(__name__)

    def iterate_response(self, response):
        while True:
            try:
                value = next(response)
                self.assertEqual(value, b"*")
            except StopIteration:
                break

    @mock.patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS: ".*my-secret.*",
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3,Regex-Test-Header-.*,Regex-Invalid-Test-Header-.*,.*my-secret.*",
        },
    )
    def test_custom_request_headers_non_recording_span(self):
        try:
            tracer_provider = trace_api.NoOpTracerProvider()
            self.environ.update(
                {
                    "HTTP_CUSTOM_TEST_HEADER_1": "Test Value 2",
                    "HTTP_CUSTOM_TEST_HEADER_2": "TestValue2,TestValue3",
                    "HTTP_REGEX_TEST_HEADER_1": "Regex Test Value 1",
                    "HTTP_REGEX_TEST_HEADER_2": "RegexTestValue2,RegexTestValue3",
                    "HTTP_MY_SECRET_HEADER": "My Secret Value",
                }
            )
            app = otel_wsgi.OpenTelemetryMiddleware(
                simple_wsgi, tracer_provider=tracer_provider
            )
            response = app(self.environ, self.start_response)
            self.iterate_response(response)
        except Exception as exc:  # pylint: disable=W0703
            self.fail(f"Exception raised with NonRecordingSpan {exc}")

    @mock.patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS: ".*my-secret.*",
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3,Regex-Test-Header-.*,Regex-Invalid-Test-Header-.*,.*my-secret.*",
        },
    )
    def test_custom_request_headers_added_in_server_span(self):
        self.environ.update(
            {
                "HTTP_CUSTOM_TEST_HEADER_1": "Test Value 1",
                "HTTP_CUSTOM_TEST_HEADER_2": "TestValue2,TestValue3",
                "HTTP_REGEX_TEST_HEADER_1": "Regex Test Value 1",
                "HTTP_REGEX_TEST_HEADER_2": "RegexTestValue2,RegexTestValue3",
                "HTTP_MY_SECRET_HEADER": "My Secret Value",
            }
        )
        app = otel_wsgi.OpenTelemetryMiddleware(simple_wsgi)
        response = app(self.environ, self.start_response)
        self.iterate_response(response)
        span = self.memory_exporter.get_finished_spans()[0]
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
        self.assertSpanHasAttributes(span, expected)

    @mock.patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST: "Custom-Test-Header-1"
        },
    )
    def test_custom_request_headers_not_added_in_internal_span(self):
        self.environ.update(
            {
                "HTTP_CUSTOM_TEST_HEADER_1": "Test Value 1",
            }
        )

        with self.tracer.start_as_current_span(
            "test", kind=trace_api.SpanKind.SERVER
        ):
            app = otel_wsgi.OpenTelemetryMiddleware(simple_wsgi)
            response = app(self.environ, self.start_response)
            self.iterate_response(response)
            span = self.memory_exporter.get_finished_spans()[0]
            not_expected = {
                "http.request.header.custom_test_header_1": ("Test Value 1",),
            }
            for key, _ in not_expected.items():
                self.assertNotIn(key, span.attributes)

    @mock.patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS: ".*my-secret.*",
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE: "content-type,content-length,my-custom-header,invalid-header,my-custom-regex-header-.*,invalid-regex-header-.*,.*my-secret.*",
        },
    )
    def test_custom_response_headers_added_in_server_span(self):
        app = otel_wsgi.OpenTelemetryMiddleware(
            wsgi_with_custom_response_headers
        )
        response = app(self.environ, self.start_response)
        self.iterate_response(response)
        span = self.memory_exporter.get_finished_spans()[0]
        expected = {
            "http.response.header.content_type": (
                "text/plain; charset=utf-8",
            ),
            "http.response.header.content_length": ("100",),
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
        self.assertSpanHasAttributes(span, expected)

    @mock.patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE: "my-custom-header"
        },
    )
    def test_custom_response_headers_not_added_in_internal_span(self):
        with self.tracer.start_as_current_span(
            "test", kind=trace_api.SpanKind.INTERNAL
        ):
            app = otel_wsgi.OpenTelemetryMiddleware(
                wsgi_with_custom_response_headers
            )
            response = app(self.environ, self.start_response)
            self.iterate_response(response)
            span = self.memory_exporter.get_finished_spans()[0]
            not_expected = {
                "http.response.header.my_custom_header": (
                    "my-custom-value-1,my-custom-header-2",
                ),
            }
            for key, _ in not_expected.items():
                self.assertNotIn(key, span.attributes)

    @mock.patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE: "my-custom-header",
        },
    )
    def test_repeat_custom_response_headers_added_in_server_span(self):
        app = otel_wsgi.OpenTelemetryMiddleware(
            wsgi_with_repeat_custom_response_headers
        )
        response = app(self.environ, self.start_response)
        self.iterate_response(response)
        span = self.memory_exporter.get_finished_spans()[0]
        expected = {
            "http.response.header.my_custom_header": (
                "my-custom-value-1,my-custom-value-2",
            ),
        }
        self.assertSpanHasAttributes(span, expected)


if __name__ == "__main__":
    unittest.main()
