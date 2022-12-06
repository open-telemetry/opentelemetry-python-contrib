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
import unittest

import pytest
import os
from cherrypy import __version__ as _cherrypy_verison
import cherrypy
from cherrypy.test import helper
from packaging import version as package_version

from opentelemetry import trace
from opentelemetry.test.globals_test import reset_trace_globals
from opentelemetry.instrumentation.cherrypy import CherryPyInstrumentor
from opentelemetry.instrumentation.propagators import (
    TraceResponsePropagator,
    get_global_response_propagator,
    set_global_response_propagator,
)
from opentelemetry.instrumentation.wsgi import (
    _active_requests_count_attrs,
    _duration_attrs,
)
from opentelemetry.sdk.metrics.export import (
    HistogramDataPoint,
    NumberDataPoint,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.test_base import TestBase
from opentelemetry.test.wsgitestutil import WsgiTestBase
from opentelemetry.trace import StatusCode
from opentelemetry.util.http import (
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE,
    _active_requests_count_attrs,
    _duration_attrs,
    get_excluded_urls,
)


_expected_metric_names = [
    "http.server.active_requests",
    "http.server.duration",
]
_recommended_attrs = {
    "http.server.active_requests": _active_requests_count_attrs,
    "http.server.duration": _duration_attrs,
}

class TestCherryPyBase(TestBase, helper.CPWebCase):
    def setUp(self):
        super().setUp()
        self.env_patch = patch.dict(
            "os.environ",
            {
                "OTEL_PYTHON_CHERRYPY_EXCLUDED_URLS": "exclude,healthzz",
                "OTEL_PYTHON_CHERRYPY_TRACED_REQUEST_ATTRS": "query_string",
            },
        )
        self.env_patch.start()
        self.exclude_patch = patch(
            "opentelemetry.instrumentation.cherrypy._excluded_urls_from_env",
            get_excluded_urls("CHERRYPY"),
        )
        self.exclude_patch.start()

        CherryPyInstrumentor().instrument(
            request_hook=getattr(self, "request_hook", None),
            response_hook=getattr(self, "response_hook", None),
        )

    
    def call(self, *args, **kwargs):
        self.setup_server()
        return self.getPage(*args, **kwargs)
        
    @staticmethod
    def setup_server():
        class CherryPyApp(object):
            @cherrypy.expose
            def hello(self):
                return {"message": "hello world"}
            
            @cherrypy.expose
            def user(self, username):
                return {"user": username}
            
            @cherrypy.expose
            def exclude(self):
                return "excluded route"
            
            @cherrypy.expose
            def healthzz(self):
                return {"message": "ok"}
            
            @cherrypy.expose
            def error(self):
                raise cherrypy.HTTPError(500, 'error')
            
            @cherrypy.expose
            def check_header(self):
                cherrypy.response.headers["custom-test-header-1"]="test-header-value-1"
                cherrypy.response.headers["custom-test-header-2"]="test-header-value-2"
                content = {"message": "hello world"}
                return content

        return cherrypy.tree.mount(CherryPyApp())

    def tearDown(self):
        super().tearDown()
        self.exclude_patch.stop()
        with self.disable_logging():
            CherryPyInstrumentor().uninstrument()
        self.env_patch.stop()
    

class TestCherryPyAutoInstrumentation(TestCherryPyBase, WsgiTestBase):
    def test_get(self):
        self._test_method("GET")

    def test_post(self):
        self._test_method("POST")

    def test_patch(self):
        self._test_method("PATCH")

    def test_put(self):
        self._test_method("PUT")

    def test_delete(self):
        self._test_method("DELETE")

    def test_head(self):
        self._test_method("HEAD")

    def _test_method(self, method):
        res = self.call(method=method, url="/hello")
        self.assertEqual(res[0],'200 OK')

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, f"HTTP {method.upper()}")
        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertEqual(
            span.status.description,
            None,
        )
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.HTTP_METHOD: method,
                SpanAttributes.HTTP_SERVER_NAME: "127.0.0.1",
                SpanAttributes.HTTP_SCHEME: "http",
                SpanAttributes.NET_HOST_PORT: 54583,
                SpanAttributes.HTTP_HOST: "127.0.0.1:54583",
                SpanAttributes.HTTP_TARGET: "/hello",
                SpanAttributes.HTTP_FLAVOR: "1.1",
                SpanAttributes.HTTP_STATUS_CODE: 200,
            },
        )
        self.memory_exporter.clear()

    def test_404(self):
        res = self.call(method="GET", url="/does-not-exit")
        self.assertEqual(res[0],'404 Not Found')
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, f"HTTP GET")
        self.assertEqual(span.status.status_code, StatusCode.UNSET)
        self.assertEqual(
            span.status.description,
            None,
        )
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.HTTP_METHOD: "GET",
                SpanAttributes.HTTP_SERVER_NAME: "127.0.0.1",
                SpanAttributes.HTTP_SCHEME: "http",
                SpanAttributes.NET_HOST_PORT: 54583,
                SpanAttributes.HTTP_HOST: "127.0.0.1:54583",
                SpanAttributes.HTTP_TARGET: "/does-not-exit",
                SpanAttributes.HTTP_FLAVOR: "1.1",
                SpanAttributes.HTTP_STATUS_CODE: 404,
            },
        )
        self.memory_exporter.clear()
    
    def test_500(self):
        res = self.call(method="GET", url="/error")
        self.assertEqual(res[0],'500 Internal Server Error')
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, f"HTTP GET")
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            None,
        )
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.HTTP_METHOD: "GET",
                SpanAttributes.HTTP_SERVER_NAME: "127.0.0.1",
                SpanAttributes.HTTP_SCHEME: "http",
                SpanAttributes.NET_HOST_PORT: 54583,
                SpanAttributes.HTTP_HOST: "127.0.0.1:54583",
                SpanAttributes.HTTP_TARGET: "/error",
                SpanAttributes.HTTP_FLAVOR: "1.1",
                SpanAttributes.HTTP_STATUS_CODE: 500,
            },
        )
        self.memory_exporter.clear()

    def test_uninstrument(self):
        self.call(method="GET", url="/hello")
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        self.memory_exporter.clear()

        CherryPyInstrumentor().uninstrument()
        self.setup_server()
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)
    
    def test_exclude_lists(self):
        self.call(method="GET", url="/exclude")
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 0)
        self.call(method="GET", url="/healthzz")
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 0)

    def test_cherrypy_metrics(self):
        self.setup_server()
        self.call(url="/hello")
        self.call(url="/hello")
        self.call(url="/hello")
        metrics_list = self.memory_metrics_reader.get_metrics_data()
        number_data_point_seen = False
        histogram_data_point_seen = False
        self.assertTrue(len(metrics_list.resource_metrics) == 1)
        for resource_metric in metrics_list.resource_metrics:
            self.assertTrue(len(resource_metric.scope_metrics) == 1)
            for scope_metric in resource_metric.scope_metrics:
                self.assertTrue(len(scope_metric.metrics) == 2)
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

    def test_basic_metric_success(self):
        start = default_timer()
        self.setup_server()
        self.call(url="/hello")
        duration = max(round((default_timer() - start) * 1000), 0)
        expected_duration_attributes = {
            "http.method": "GET",
            "http.host": "127.0.0.1:54583",
            "http.scheme": "http",
            "http.flavor": "1.1",
            "http.server_name": "127.0.0.1",
            "net.host.port": 54583,
            "http.status_code": 200,
        }
        expected_requests_count_attributes = {
            "http.method": "GET",
            "http.host": "127.0.0.1:54583",
            "http.scheme": "http",
            "http.flavor": "1.1",
            "http.server_name": "127.0.0.1",
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
                    self.assertAlmostEqual(duration, point.sum, delta=30)
                if isinstance(point, NumberDataPoint):
                    self.assertDictEqual(
                        expected_requests_count_attributes,
                        dict(point.attributes),
                    )
                    self.assertEqual(point.value, 0)

    def test_basic_post_request_metric_success(self):
        start = default_timer()
        self.setup_server()
        self.call(url="/hello")
        duration = max(round((default_timer() - start) * 1000), 0)
        metrics_list = self.memory_metrics_reader.get_metrics_data()
        for metric in (
            metrics_list.resource_metrics[0].scope_metrics[0].metrics
        ):
            for point in list(metric.data.data_points):
                if isinstance(point, HistogramDataPoint):
                    self.assertEqual(point.count, 1)
                    self.assertAlmostEqual(duration, point.sum, delta=30)
                if isinstance(point, NumberDataPoint):
                    self.assertEqual(point.value, 0)


class TestCherryPyCustomHeaders(TestBase, helper.CPWebCase):

    def setUp(self):
        super().setUp()
        self.env_patch = patch.dict(
            "os.environ",
            {
                OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3",
                OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3",
            },
        )
        self.env_patch.start()
        CherryPyInstrumentor().instrument()

    
    def call(self, *args, **kwargs):
        self.setup_server()
        return self.getPage(*args, **kwargs)
    
    @staticmethod
    def setup_server():
        class CherryPyApp(object):
            
            @cherrypy.expose
            def check_header(self):
                cherrypy.response.headers["custom-test-header-1"]="test-header-value-1"
                cherrypy.response.headers["custom-test-header-2"]="test-header-value-2"
                content = {"message": "hello world"}
                return content

        return cherrypy.tree.mount(CherryPyApp())

    def tearDown(self):
        super().tearDown()
        with self.disable_logging():
            CherryPyInstrumentor().uninstrument()
        self.env_patch.stop()

    def test_http_custom_request_headers_in_span_attributes(self):
        expected = {
            "http.request.header.custom_test_header_1": (
                "test-header-value-1",
            ),
            "http.request.header.custom_test_header_2": (
                "test-header-value-2",
            ),
        }
        resp = self.call(
            url="/check_header",
            headers=[
                ("custom-test-header-1","test-header-value-1"),
                ("custom-test-header-2","test-header-value-2"),
            ],
        )
        self.assertEqual('200 OK', resp[0])
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

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
        resp = self.call(
            url="/check_header",
            headers=[
                ("custom-test-header-1","test-header-value-1"),
                ("custom-test-header-2","test-header-value-2"),
            ],
        )
        self.assertEqual('200 OK', resp[0])
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

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
        }
        resp = self.call(url="/check_header")
        self.assertEqual('200 OK', resp[0])
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

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
        resp = self.call(url="/check_header")
        self.assertEqual('200 OK', resp[0])
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

        server_span = [
            span for span in span_list if span.kind == trace.SpanKind.SERVER
        ][0]

        for key, _ in not_expected.items():
            self.assertNotIn(key, server_span.attributes)

class TestNonRecordingSpanWithCustomHeaders(TestBase, helper.CPWebCase):
    def setUp(self):
        super().setUp()
        self.env_patch = patch.dict(
            "os.environ",
            {
                OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3",
            },
        )
        self.env_patch.start()

        reset_trace_globals()
        tracer_provider = trace.NoOpTracerProvider()
        trace.set_tracer_provider(tracer_provider=tracer_provider)

        self._instrumentor = CherryPyInstrumentor()
        self._instrumentor.instrument()

    def call(self, *args, **kwargs):
        self.setup_server()
        return self.getPage(*args, **kwargs)
    
    @staticmethod
    def setup_server():
        class CherryPyApp(object):

            @cherrypy.expose
            def check_header(self):
                content = {"message": "hello world"}
                return content

        return cherrypy.tree.mount(CherryPyApp())

    def tearDown(self):
        super().tearDown()
        with self.disable_logging():
            CherryPyInstrumentor().uninstrument()
        self.env_patch.stop()

    def test_custom_header_not_present_in_non_recording_span(self):
        resp = self.call(
            url="/check_header",
            headers=[
                ("custom-test-header-1","test-header-value-1"),
            ],
        )
        self.assertEqual('200 OK', resp[0])
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 0)

