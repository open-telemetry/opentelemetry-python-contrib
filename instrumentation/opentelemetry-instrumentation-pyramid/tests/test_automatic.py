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

from timeit import default_timer
from unittest.mock import patch

from pyramid.config import Configurator

from opentelemetry import trace
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
    _server_active_requests_count_attrs_old,
    _server_duration_attrs_old,
    _StabilityMode,
)
from opentelemetry.instrumentation.pyramid import PyramidInstrumentor
from opentelemetry.sdk.metrics.export import (
    HistogramDataPoint,
    NumberDataPoint,
)
from opentelemetry.semconv._incubating.attributes.http_attributes import (
    HTTP_ROUTE,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.semconv.attributes.url_attributes import URL_SCHEME
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.globals_test import reset_trace_globals
from opentelemetry.test.wsgitestutil import WsgiTestBase
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import StatusCode
from opentelemetry.util.http import (
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE,
)

# pylint: disable=import-error
from .pyramid_base_test import InstrumentationTest

_expected_metric_names = [
    "http.server.active_requests",
    "http.server.duration",
]
_recommended_attrs = {
    "http.server.active_requests": _server_active_requests_count_attrs_old,
    "http.server.duration": _server_duration_attrs_old,
}


class TestAutomatic(InstrumentationTest, WsgiTestBase):
    def setUp(self):
        super().setUp()

        PyramidInstrumentor().instrument()

        self.config = Configurator()

        self._common_initialization(self.config)

    def tearDown(self):
        super().tearDown()
        with self.disable_logging():
            PyramidInstrumentor().uninstrument()

    def test_uninstrument(self):
        # pylint: disable=access-member-before-definition
        resp = self.client.get("/hello/123")
        self.assertEqual(200, resp.status_code)
        self.assertEqual([b"Hello: 123"], list(resp.response))
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

        PyramidInstrumentor().uninstrument()
        self.config = Configurator()

        self._common_initialization(self.config)

        resp = self.client.get("/hello/123")
        self.assertEqual(200, resp.status_code)
        self.assertEqual([b"Hello: 123"], list(resp.response))
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

    def test_tween_list(self):
        tween_list = "pyramid.tweens.excview_tween_factory"
        config = Configurator(settings={"pyramid.tweens": tween_list})
        self._common_initialization(config)
        resp = self.client.get("/hello/123")
        self.assertEqual(200, resp.status_code)
        self.assertEqual([b"Hello: 123"], list(resp.response))
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

        PyramidInstrumentor().uninstrument()

        self.config = Configurator()

        self._common_initialization(self.config)

        resp = self.client.get("/hello/123")
        self.assertEqual(200, resp.status_code)
        self.assertEqual([b"Hello: 123"], list(resp.response))
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

    def test_registry_name_is_this_module(self):
        config = Configurator()
        self.assertEqual(
            config.registry.__name__, __name__.rsplit(".", maxsplit=1)[0]
        )

    def test_redirect_response_is_not_an_error(self):
        tween_list = "pyramid.tweens.excview_tween_factory"
        config = Configurator(settings={"pyramid.tweens": tween_list})
        self._common_initialization(config)
        resp = self.client.get("/hello/302")
        self.assertEqual(302, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)
        self.assertEqual(span_list[0].status.status_code, StatusCode.UNSET)
        self.assertEqual(len(span_list[0].events), 0)

        PyramidInstrumentor().uninstrument()

        self.config = Configurator()

        self._common_initialization(self.config)

        resp = self.client.get("/hello/302")
        self.assertEqual(302, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

    def test_204_empty_response_is_not_an_error(self):
        tween_list = "pyramid.tweens.excview_tween_factory"
        config = Configurator(settings={"pyramid.tweens": tween_list})
        self._common_initialization(config)
        resp = self.client.get("/hello/204")
        self.assertEqual(204, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)
        self.assertEqual(span_list[0].status.status_code, StatusCode.UNSET)

        PyramidInstrumentor().uninstrument()

        self.config = Configurator()

        self._common_initialization(self.config)

        resp = self.client.get("/hello/204")
        self.assertEqual(204, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

    def test_400s_response_is_not_an_error(self):
        tween_list = "pyramid.tweens.excview_tween_factory"
        config = Configurator(settings={"pyramid.tweens": tween_list})
        self._common_initialization(config)
        resp = self.client.get("/hello/404")
        self.assertEqual(404, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)
        self.assertEqual(span_list[0].status.status_code, StatusCode.UNSET)

        PyramidInstrumentor().uninstrument()

        self.config = Configurator()

        self._common_initialization(self.config)

        resp = self.client.get("/hello/404")
        self.assertEqual(404, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)

    def test_pyramid_metric(self):
        self.client.get("/hello/756")
        self.client.get("/hello/756")
        self.client.get("/hello/756")
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
        self.client.get("/hello/756")
        duration = max(round((default_timer() - start) * 1000), 0)
        expected_duration_attributes = {
            "http.method": "GET",
            "http.host": "localhost",
            "http.scheme": "http",
            "http.flavor": "1.1",
            "http.server_name": "localhost",
            "net.host.port": 80,
            "http.status_code": 200,
            "net.host.name": "localhost",
        }
        expected_requests_count_attributes = {
            "http.method": "GET",
            "http.host": "localhost",
            "http.scheme": "http",
            "http.flavor": "1.1",
            "http.server_name": "localhost",
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
                    self.assertAlmostEqual(duration, point.sum, delta=20)
                if isinstance(point, NumberDataPoint):
                    self.assertDictEqual(
                        expected_requests_count_attributes,
                        dict(point.attributes),
                    )
                    self.assertEqual(point.value, 0)

    def test_metric_uninstrument(self):
        self.client.get("/hello/756")
        PyramidInstrumentor().uninstrument()
        self.config = Configurator()
        self._common_initialization(self.config)
        self.client.get("/hello/756")
        metrics_list = self.memory_metrics_reader.get_metrics_data()
        for metric in (
            metrics_list.resource_metrics[0].scope_metrics[0].metrics
        ):
            for point in list(metric.data.data_points):
                if isinstance(point, HistogramDataPoint):
                    self.assertEqual(point.count, 1)
                if isinstance(point, NumberDataPoint):
                    self.assertEqual(point.value, 0)


class TestWrappedWithOtherFramework(InstrumentationTest, WsgiTestBase):
    def setUp(self):
        super().setUp()
        PyramidInstrumentor().instrument()
        self.config = Configurator()
        self._common_initialization(self.config)

    def tearDown(self) -> None:
        super().tearDown()
        with self.disable_logging():
            PyramidInstrumentor().uninstrument()

    def test_with_existing_span(self):
        tracer_provider, _ = self.create_tracer_provider()
        tracer = tracer_provider.get_tracer(__name__)

        with tracer.start_as_current_span(
            "test", kind=SpanKind.SERVER
        ) as parent_span:
            resp = self.client.get("/hello/123")
            self.assertEqual(200, resp.status_code)
            span_list = self.memory_exporter.get_finished_spans()
            self.assertEqual(SpanKind.INTERNAL, span_list[0].kind)
            self.assertEqual(
                parent_span.get_span_context().span_id,
                span_list[0].parent.span_id,
            )


@patch.dict(
    "os.environ",
    {
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS: ".*my-secret.*",
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST: "Custom-Test-Header-1,Custom-Test-Header-2,invalid-header,Regex-Test-Header-.*,Regex-Invalid-Test-Header-.*,.*my-secret.*",
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE: "content-type,content-length,my-custom-header,invalid-header,my-custom-regex-header-.*,invalid-regex-header-.*,.*my-secret.*",
    },
)
class TestCustomRequestResponseHeaders(InstrumentationTest, WsgiTestBase):
    def setUp(self):
        super().setUp()
        PyramidInstrumentor().instrument()
        self.config = Configurator()
        self._common_initialization(self.config)

    def tearDown(self) -> None:
        super().tearDown()
        with self.disable_logging():
            PyramidInstrumentor().uninstrument()

    def test_custom_request_header_added_in_server_span(self):
        headers = {
            "Custom-Test-Header-1": "Test Value 1",
            "Custom-Test-Header-2": "TestValue2,TestValue3",
            "Custom-Test-Header-3": "TestValue4",
            "Regex-Test-Header-1": "Regex Test Value 1",
            "regex-test-header-2": "RegexTestValue2,RegexTestValue3",
            "My-Secret-Header": "My Secret Value",
        }
        resp = self.client.get("/hello/123", headers=headers)
        self.assertEqual(200, resp.status_code)
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
        not_expected = {
            "http.request.header.custom_test_header_3": ("TestValue4",),
        }
        self.assertEqual(span.kind, SpanKind.SERVER)
        self.assertSpanHasAttributes(span, expected)
        for key, _ in not_expected.items():
            self.assertNotIn(key, span.attributes)

    def test_custom_request_header_not_added_in_internal_span(self):
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("test", kind=SpanKind.SERVER):
            headers = {
                "Custom-Test-Header-1": "Test Value 1",
                "Custom-Test-Header-2": "TestValue2,TestValue3",
            }
            resp = self.client.get("/hello/123", headers=headers)
            self.assertEqual(200, resp.status_code)
            span = self.memory_exporter.get_finished_spans()[0]
            not_expected = {
                "http.request.header.custom_test_header_1": ("Test Value 1",),
                "http.request.header.custom_test_header_2": (
                    "TestValue2,TestValue3",
                ),
            }
            self.assertEqual(span.kind, SpanKind.INTERNAL)
            for key, _ in not_expected.items():
                self.assertNotIn(key, span.attributes)

    def test_custom_response_header_added_in_server_span(self):
        resp = self.client.get("/test_custom_response_headers")
        self.assertEqual(200, resp.status_code)
        span = self.memory_exporter.get_finished_spans()[0]
        expected = {
            "http.response.header.content_type": (
                "text/plain; charset=utf-8",
            ),
            "http.response.header.content_length": ("7",),
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
        self.assertEqual(span.kind, SpanKind.SERVER)
        self.assertSpanHasAttributes(span, expected)
        for key, _ in not_expected.items():
            self.assertNotIn(key, span.attributes)

    def test_custom_response_header_not_added_in_internal_span(self):
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("test", kind=SpanKind.SERVER):
            resp = self.client.get("/test_custom_response_headers")
            self.assertEqual(200, resp.status_code)
            span = self.memory_exporter.get_finished_spans()[0]
            not_expected = {
                "http.response.header.content_type": (
                    "text/plain; charset=utf-8",
                ),
                "http.response.header.content_length": ("7",),
                "http.response.header.my_custom_header": (
                    "my-custom-value-1,my-custom-header-2",
                ),
            }
            self.assertEqual(span.kind, SpanKind.INTERNAL)
            for key, _ in not_expected.items():
                self.assertNotIn(key, span.attributes)


class _SemConvTestBase(InstrumentationTest, WsgiTestBase):
    semconv_mode = _StabilityMode.DEFAULT

    def setUp(self):
        super().setUp()
        self.env_patch = patch.dict(
            "os.environ",
            {OTEL_SEMCONV_STABILITY_OPT_IN: self.semconv_mode.value},
        )
        _OpenTelemetrySemanticConventionStability._initialized = False
        self.env_patch.start()

        PyramidInstrumentor().instrument()
        self.config = Configurator()
        self._common_initialization(self.config)

    def tearDown(self):
        super().tearDown()
        self.env_patch.stop()
        with self.disable_logging():
            PyramidInstrumentor().uninstrument()

    def _verify_metric_names(
        self, metrics_list, expected_names, not_expected_names=None
    ):
        metric_names = []
        for resource_metric in metrics_list.resource_metrics:
            for scope_metric in resource_metric.scope_metrics:
                for metric in scope_metric.metrics:
                    metric_names.append(metric.name)
                    if expected_names:
                        self.assertIn(metric.name, expected_names)
                    if not_expected_names:
                        self.assertNotIn(metric.name, not_expected_names)
        return metric_names

    def _verify_duration_point(self, point):
        self.assertIn("http.request.method", point.attributes)
        self.assertIn("url.scheme", point.attributes)
        self.assertNotIn("http.method", point.attributes)
        self.assertNotIn("http.scheme", point.attributes)

    def _verify_metric_duration(self, metric):
        if "duration" in metric.name:
            for point in metric.data.data_points:
                if isinstance(point, HistogramDataPoint):
                    self._verify_duration_point(point)

    def _verify_duration_attributes(self, metrics_list):
        for resource_metric in metrics_list.resource_metrics:
            for scope_metric in resource_metric.scope_metrics:
                for metric in scope_metric.metrics:
                    self._verify_metric_duration(metric)


class TestSemConvDefault(_SemConvTestBase):
    semconv_mode = _StabilityMode.DEFAULT

    def test_basic_old_semconv(self):
        resp = self.client.get("/hello/123")
        self.assertEqual(200, resp.status_code)

        span = self.memory_exporter.get_finished_spans()[0]

        old_attrs = {
            SpanAttributes.HTTP_METHOD: "GET",
            SpanAttributes.HTTP_SCHEME: "http",
            SpanAttributes.HTTP_HOST: "localhost",
            SpanAttributes.HTTP_TARGET: "/hello/123",
            SpanAttributes.NET_HOST_PORT: 80,
            SpanAttributes.HTTP_STATUS_CODE: 200,
            SpanAttributes.HTTP_FLAVOR: "1.1",
            HTTP_ROUTE: "/hello/{helloid}",
        }
        for attr, value in old_attrs.items():
            self.assertEqual(span.attributes[attr], value)

        for attr in [SERVER_ADDRESS, SERVER_PORT, URL_SCHEME]:
            self.assertNotIn(attr, span.attributes)

    def test_metrics_old_semconv(self):
        self.client.get("/hello/123")

        metrics_list = self.memory_metrics_reader.get_metrics_data()
        self.assertTrue(len(metrics_list.resource_metrics) == 1)

        expected_metrics = [
            "http.server.active_requests",
            "http.server.duration",
        ]
        self._verify_metric_names(
            metrics_list, expected_metrics, ["http.server.request.duration"]
        )

        for resource_metric in metrics_list.resource_metrics:
            for scope_metric in resource_metric.scope_metrics:
                for metric in scope_metric.metrics:
                    for point in metric.data.data_points:
                        if isinstance(point, HistogramDataPoint):
                            self.assertIn("http.method", point.attributes)
                            self.assertIn("http.scheme", point.attributes)
                            self.assertNotIn(
                                "http.request.method", point.attributes
                            )


class TestSemConvNew(_SemConvTestBase):
    semconv_mode = _StabilityMode.HTTP

    def test_basic_new_semconv(self):
        resp = self.client.get("/hello/456")
        self.assertEqual(200, resp.status_code)

        span = self.memory_exporter.get_finished_spans()[0]

        new_attrs = {
            "http.request.method": "GET",
            URL_SCHEME: "http",
            SERVER_ADDRESS: "localhost",
            SERVER_PORT: 80,
            "http.response.status_code": 200,
            "network.protocol.version": "1.1",
            HTTP_ROUTE: "/hello/{helloid}",
        }
        for attr, value in new_attrs.items():
            self.assertEqual(span.attributes[attr], value)

        old_attrs = [
            SpanAttributes.HTTP_METHOD,
            SpanAttributes.HTTP_HOST,
            SpanAttributes.HTTP_TARGET,
            SpanAttributes.HTTP_URL,
        ]
        for attr in old_attrs:
            self.assertNotIn(attr, span.attributes)

    def test_metrics_new_semconv(self):
        self.client.get("/hello/456")
        metrics_list = self.memory_metrics_reader.get_metrics_data()
        self.assertTrue(len(metrics_list.resource_metrics) == 1)

        expected_metrics = [
            "http.server.request.duration",
            "http.server.active_requests",
        ]
        metric_names = self._verify_metric_names(
            metrics_list, expected_metrics
        )

        self.assertIn("http.server.request.duration", metric_names)
        self.assertIn("http.server.active_requests", metric_names)

        self._verify_duration_attributes(metrics_list)


class TestSemConvDup(_SemConvTestBase):
    semconv_mode = _StabilityMode.HTTP_DUP

    def test_basic_both_semconv(self):
        resp = self.client.get("/hello/789")
        self.assertEqual(200, resp.status_code)

        span = self.memory_exporter.get_finished_spans()[0]

        expected_attrs = {
            SpanAttributes.HTTP_METHOD: "GET",
            SpanAttributes.HTTP_SCHEME: "http",
            SpanAttributes.HTTP_HOST: "localhost",
            SpanAttributes.HTTP_STATUS_CODE: 200,
            "http.request.method": "GET",
            URL_SCHEME: "http",
            SERVER_ADDRESS: "localhost",
            "http.response.status_code": 200,
            HTTP_ROUTE: "/hello/{helloid}",
        }
        for attr, value in expected_attrs.items():
            self.assertEqual(span.attributes[attr], value)

    def test_metrics_both_semconv(self):
        self.client.get("/hello/789")

        metrics_list = self.memory_metrics_reader.get_metrics_data()
        self.assertTrue(len(metrics_list.resource_metrics) == 1)

        expected_metrics = [
            "http.server.duration",
            "http.server.request.duration",
            "http.server.active_requests",
        ]
        metric_names = self._verify_metric_names(metrics_list, None)

        for metric_name in expected_metrics:
            self.assertIn(metric_name, metric_names)


@patch.dict(
    "os.environ",
    {
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS: ".*my-secret.*",
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST: "Custom-Test-Header-1,Custom-Test-Header-2,invalid-header,Regex-Test-Header-.*,Regex-Invalid-Test-Header-.*,.*my-secret.*",
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE: "content-type,content-length,my-custom-header,invalid-header,my-custom-regex-header-.*,invalid-regex-header-.*,.*my-secret.*",
    },
)
class TestCustomHeadersNonRecordingSpan(InstrumentationTest, WsgiTestBase):
    def setUp(self):
        super().setUp()
        # This is done because set_tracer_provider cannot override the
        # current tracer provider.
        reset_trace_globals()
        tracer_provider = trace.NoOpTracerProvider()
        trace.set_tracer_provider(tracer_provider)
        PyramidInstrumentor().instrument()
        self.config = Configurator()
        self._common_initialization(self.config)

    def tearDown(self) -> None:
        super().tearDown()
        with self.disable_logging():
            PyramidInstrumentor().uninstrument()

    def test_custom_header_non_recording_span(self):
        try:
            resp = self.client.get("/hello/123")
            self.assertEqual(200, resp.status_code)
        except Exception as exc:  # pylint: disable=W0703
            self.fail(f"Exception raised with NonRecordingSpan {exc}")
