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

import abc
from unittest import mock

import httpretty
import requests
from requests.adapters import BaseAdapter
from requests.models import Response

import opentelemetry.instrumentation.requests
from opentelemetry import context, trace

# FIXME: fix the importing of this private attribute when the location of the _SUPPRESS_HTTP_INSTRUMENTATION_KEY is defined.
from opentelemetry.context import _SUPPRESS_HTTP_INSTRUMENTATION_KEY
from opentelemetry.instrumentation._semconv import (
    _SPAN_ATTRIBUTES_ERROR_TYPE,
    _SPAN_ATTRIBUTES_NETWORK_PEER_ADDRESS,
    _OTEL_SEMCONV_STABILITY_OPT_IN_KEY,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
from opentelemetry.propagate import get_global_textmap, set_global_textmap
from opentelemetry.sdk import resources
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.mock_textmap import MockTextMapPropagator
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import StatusCode
from opentelemetry.util.http import get_excluded_urls


class TransportMock:
    def read(self, *args, **kwargs):
        pass


class MyAdapter(BaseAdapter):
    def __init__(self, response):
        super().__init__()
        self._response = response

    def send(self, *args, **kwargs):  # pylint:disable=signature-differs
        return self._response

    def close(self):
        pass


class InvalidResponseObjectException(Exception):
    def __init__(self):
        super().__init__()
        self.response = {}


class RequestsIntegrationTestBase(abc.ABC):
    # pylint: disable=no-member
    # pylint: disable=too-many-public-methods

    URL = "http://mock/status/200"
    HOST = "mock"

    # pylint: disable=invalid-name
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
                "OTEL_PYTHON_REQUESTS_EXCLUDED_URLS": "http://localhost/env_excluded_arg/123,env_excluded_noarg",
                _OTEL_SEMCONV_STABILITY_OPT_IN_KEY: sem_conv_mode,
            },
        )

        _OpenTelemetrySemanticConventionStability._initialized = False

        self.env_patch.start()

        self.exclude_patch = mock.patch(
            "opentelemetry.instrumentation.requests._excluded_urls_from_env",
            get_excluded_urls("REQUESTS"),
        )
        self.exclude_patch.start()

        RequestsInstrumentor().instrument()
        httpretty.enable()
        httpretty.register_uri(httpretty.GET, self.URL, body="Hello!")

    # pylint: disable=invalid-name
    def tearDown(self):
        super().tearDown()
        self.env_patch.stop()
        RequestsInstrumentor().uninstrument()
        httpretty.disable()

    def assert_span(self, exporter=None, num_spans=1):
        if exporter is None:
            exporter = self.memory_exporter
        span_list = exporter.get_finished_spans()
        self.assertEqual(num_spans, len(span_list))
        if num_spans == 0:
            return None
        if num_spans == 1:
            return span_list[0]
        return span_list

    @staticmethod
    @abc.abstractmethod
    def perform_request(url: str, session: requests.Session = None):
        pass

    def test_basic(self):
        result = self.perform_request(self.URL)
        self.assertEqual(result.text, "Hello!")
        span = self.assert_span()

        self.assertIs(span.kind, trace.SpanKind.CLIENT)
        self.assertEqual(span.name, "GET")

        self.assertEqual(
            span.attributes,
            {
                SpanAttributes.HTTP_METHOD: "GET",
                SpanAttributes.HTTP_URL: self.URL,
                SpanAttributes.HTTP_STATUS_CODE: 200,
            },
        )

        self.assertIs(span.status.status_code, trace.StatusCode.UNSET)

        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.requests
        )

    def test_basic_new_semconv(self):
        result = self.perform_request(self.URL)
        self.assertEqual(result.text, "Hello!")
        span = self.assert_span()

        self.assertIs(span.kind, trace.SpanKind.CLIENT)
        self.assertEqual(span.name, "GET")

        self.assertEqual(
            span.attributes,
            {
                SpanAttributes.HTTP_REQUEST_METHOD: "GET",
                SpanAttributes.URL_FULL: self.URL,
                SpanAttributes.SERVER_ADDRESS: self.HOST,
                _SPAN_ATTRIBUTES_NETWORK_PEER_ADDRESS: "mock",
                SpanAttributes.HTTP_RESPONSE_STATUS_CODE: 200,
                SpanAttributes.NET_PROTOCOL_VERSION: "1.1",
            },
        )

        self.assertIs(span.status.status_code, trace.StatusCode.UNSET)

        self.assertEqualSpanInstrumentationScope(
            span, opentelemetry.instrumentation.requests
        )

    def test_basic_both_semconv(self):
        result = self.perform_request(self.URL)
        self.assertEqual(result.text, "Hello!")
        span = self.assert_span()

        self.assertIs(span.kind, trace.SpanKind.CLIENT)
        self.assertEqual(span.name, "GET")

        self.assertEqual(
            span.attributes,
            {
                SpanAttributes.HTTP_METHOD: "GET",
                SpanAttributes.HTTP_REQUEST_METHOD: "GET",
                SpanAttributes.HTTP_URL: self.URL,
                SpanAttributes.URL_FULL: self.URL,
                SpanAttributes.HTTP_HOST: self.HOST,
                SpanAttributes.SERVER_ADDRESS: self.HOST,
                _SPAN_ATTRIBUTES_NETWORK_PEER_ADDRESS: "mock",
                SpanAttributes.HTTP_STATUS_CODE: 200,
                SpanAttributes.HTTP_RESPONSE_STATUS_CODE: 200,
                SpanAttributes.HTTP_FLAVOR: "1.1",
                SpanAttributes.NET_PROTOCOL_VERSION: "1.1",
            },
        )

        self.assertIs(span.status.status_code, trace.StatusCode.UNSET)

        self.assertEqualSpanInstrumentationScope(
            span, opentelemetry.instrumentation.requests
        )

    def test_hooks(self):
        def request_hook(span, request_obj):
            span.update_name("name set from hook")

        def response_hook(span, request_obj, response):
            span.set_attribute("response_hook_attr", "value")

        RequestsInstrumentor().uninstrument()
        RequestsInstrumentor().instrument(
            request_hook=request_hook, response_hook=response_hook
        )
        result = self.perform_request(self.URL)
        self.assertEqual(result.text, "Hello!")
        span = self.assert_span()

        self.assertEqual(span.name, "name set from hook")
        self.assertEqual(span.attributes["response_hook_attr"], "value")

    def test_excluded_urls_explicit(self):
        url_404 = "http://mock/status/404"
        httpretty.register_uri(
            httpretty.GET,
            url_404,
            status=404,
        )

        RequestsInstrumentor().uninstrument()
        RequestsInstrumentor().instrument(excluded_urls=".*/404")
        self.perform_request(self.URL)
        self.perform_request(url_404)

        self.assert_span(num_spans=1)

    def test_excluded_urls_from_env(self):
        url = "http://localhost/env_excluded_arg/123"
        httpretty.register_uri(
            httpretty.GET,
            url,
            status=200,
        )

        RequestsInstrumentor().uninstrument()
        RequestsInstrumentor().instrument()
        self.perform_request(self.URL)
        self.perform_request(url)

        self.assert_span(num_spans=1)

    def test_name_callback_default(self):
        def name_callback(method, url):
            return 123

        RequestsInstrumentor().uninstrument()
        RequestsInstrumentor().instrument(name_callback=name_callback)
        result = self.perform_request(self.URL)
        self.assertEqual(result.text, "Hello!")
        span = self.assert_span()

        self.assertEqual(span.name, "GET")

    def test_not_foundbasic(self):
        url_404 = "http://mock/status/404"
        httpretty.register_uri(
            httpretty.GET,
            url_404,
            status=404,
        )
        result = self.perform_request(url_404)
        self.assertEqual(result.status_code, 404)

        span = self.assert_span()

        self.assertEqual(
            span.attributes.get(SpanAttributes.HTTP_STATUS_CODE), 404
        )

        self.assertIs(
            span.status.status_code,
            trace.StatusCode.ERROR,
        )

    def test_not_foundbasic_new_semconv(self):
        url_404 = "http://mock/status/404"
        httpretty.register_uri(
            httpretty.GET,
            url_404,
            status=404,
        )
        result = self.perform_request(url_404)
        self.assertEqual(result.status_code, 404)

        span = self.assert_span()

        self.assertEqual(
            span.attributes.get(SpanAttributes.HTTP_RESPONSE_STATUS_CODE), 404
        )

        self.assertIs(
            span.status.status_code,
            trace.StatusCode.ERROR,
        )

    def test_not_foundbasic_both_semconv(self):
        url_404 = "http://mock/status/404"
        httpretty.register_uri(
            httpretty.GET,
            url_404,
            status=404,
        )
        result = self.perform_request(url_404)
        self.assertEqual(result.status_code, 404)

        span = self.assert_span()

        self.assertEqual(
            span.attributes.get(SpanAttributes.HTTP_STATUS_CODE), 404
        )
        self.assertEqual(
            span.attributes.get(SpanAttributes.HTTP_RESPONSE_STATUS_CODE), 404
        )

        self.assertIs(
            span.status.status_code,
            trace.StatusCode.ERROR,
        )

    def test_uninstrument(self):
        RequestsInstrumentor().uninstrument()
        result = self.perform_request(self.URL)
        self.assertEqual(result.text, "Hello!")
        self.assert_span(num_spans=0)
        # instrument again to avoid annoying warning message
        RequestsInstrumentor().instrument()

    def test_uninstrument_session(self):
        session1 = requests.Session()
        RequestsInstrumentor().uninstrument_session(session1)

        result = self.perform_request(self.URL, session1)
        self.assertEqual(result.text, "Hello!")
        self.assert_span(num_spans=0)

        # Test that other sessions as well as global requests is still
        # instrumented
        session2 = requests.Session()
        result = self.perform_request(self.URL, session2)
        self.assertEqual(result.text, "Hello!")
        self.assert_span()

        self.memory_exporter.clear()

        result = self.perform_request(self.URL)
        self.assertEqual(result.text, "Hello!")
        self.assert_span()

    def test_suppress_instrumentation(self):
        token = context.attach(
            context.set_value(_SUPPRESS_INSTRUMENTATION_KEY, True)
        )
        try:
            result = self.perform_request(self.URL)
            self.assertEqual(result.text, "Hello!")
        finally:
            context.detach(token)

        self.assert_span(num_spans=0)

    def test_suppress_http_instrumentation(self):
        token = context.attach(
            context.set_value(_SUPPRESS_HTTP_INSTRUMENTATION_KEY, True)
        )
        try:
            result = self.perform_request(self.URL)
            self.assertEqual(result.text, "Hello!")
        finally:
            context.detach(token)

        self.assert_span(num_spans=0)

    def test_not_recording(self):
        with mock.patch("opentelemetry.trace.INVALID_SPAN") as mock_span:
            RequestsInstrumentor().uninstrument()
            RequestsInstrumentor().instrument(
                tracer_provider=trace.NoOpTracerProvider()
            )
            mock_span.is_recording.return_value = False
            result = self.perform_request(self.URL)
            self.assertEqual(result.text, "Hello!")
            self.assert_span(None, 0)
            self.assertFalse(mock_span.is_recording())
            self.assertTrue(mock_span.is_recording.called)
            self.assertFalse(mock_span.set_attribute.called)
            self.assertFalse(mock_span.set_status.called)

    def test_distributed_context(self):
        previous_propagator = get_global_textmap()
        try:
            set_global_textmap(MockTextMapPropagator())
            result = self.perform_request(self.URL)
            self.assertEqual(result.text, "Hello!")

            span = self.assert_span()

            headers = dict(httpretty.last_request().headers)
            self.assertIn(MockTextMapPropagator.TRACE_ID_KEY, headers)
            self.assertEqual(
                str(span.get_span_context().trace_id),
                headers[MockTextMapPropagator.TRACE_ID_KEY],
            )
            self.assertIn(MockTextMapPropagator.SPAN_ID_KEY, headers)
            self.assertEqual(
                str(span.get_span_context().span_id),
                headers[MockTextMapPropagator.SPAN_ID_KEY],
            )

        finally:
            set_global_textmap(previous_propagator)

    def test_response_hook(self):
        RequestsInstrumentor().uninstrument()

        def response_hook(
            span,
            request: requests.PreparedRequest,
            response: requests.Response,
        ):
            span.set_attribute(
                "http.response.body", response.content.decode("utf-8")
            )

        RequestsInstrumentor().instrument(
            tracer_provider=self.tracer_provider,
            response_hook=response_hook,
        )

        result = self.perform_request(self.URL)
        self.assertEqual(result.text, "Hello!")

        span = self.assert_span()
        self.assertEqual(
            span.attributes,
            {
                SpanAttributes.HTTP_METHOD: "GET",
                SpanAttributes.HTTP_URL: self.URL,
                SpanAttributes.HTTP_STATUS_CODE: 200,
                "http.response.body": "Hello!",
            },
        )

    def test_custom_tracer_provider(self):
        resource = resources.Resource.create({})
        result = self.create_tracer_provider(resource=resource)
        tracer_provider, exporter = result
        RequestsInstrumentor().uninstrument()
        RequestsInstrumentor().instrument(tracer_provider=tracer_provider)

        result = self.perform_request(self.URL)
        self.assertEqual(result.text, "Hello!")

        span = self.assert_span(exporter=exporter)
        self.assertIs(span.resource, resource)

    @mock.patch(
        "requests.adapters.HTTPAdapter.send",
        side_effect=requests.RequestException,
    )
    def test_requests_exception_without_response(self, *_, **__):
        with self.assertRaises(requests.RequestException):
            self.perform_request(self.URL)

        span = self.assert_span()
        self.assertEqual(
            span.attributes,
            {
                SpanAttributes.HTTP_METHOD: "GET",
                SpanAttributes.HTTP_URL: self.URL,
            },
        )
        self.assertEqual(span.status.status_code, StatusCode.ERROR)

    @mock.patch(
        "requests.adapters.HTTPAdapter.send",
        side_effect=requests.RequestException,
    )
    def test_requests_exception_new_semconv(self, *_, **__):
        with self.assertRaises(requests.RequestException):
            self.perform_request(self.URL)

        span = self.assert_span()
        self.assertEqual(
            span.attributes,
            {
                SpanAttributes.HTTP_REQUEST_METHOD: "GET",
                SpanAttributes.URL_FULL: self.URL,
                SpanAttributes.SERVER_ADDRESS: self.HOST,
                _SPAN_ATTRIBUTES_NETWORK_PEER_ADDRESS: "mock",
                _SPAN_ATTRIBUTES_ERROR_TYPE: "RequestException",
            },
        )
        self.assertEqual(span.status.status_code, StatusCode.ERROR)

    mocked_response = requests.Response()
    mocked_response.status_code = 500
    mocked_response.reason = "Internal Server Error"

    @mock.patch(
        "requests.adapters.HTTPAdapter.send",
        side_effect=InvalidResponseObjectException,
    )
    def test_requests_exception_without_proper_response_type(self, *_, **__):
        with self.assertRaises(InvalidResponseObjectException):
            self.perform_request(self.URL)

        span = self.assert_span()
        self.assertEqual(
            span.attributes,
            {
                SpanAttributes.HTTP_METHOD: "GET",
                SpanAttributes.HTTP_URL: self.URL,
            },
        )
        self.assertEqual(span.status.status_code, StatusCode.ERROR)

    mocked_response = requests.Response()
    mocked_response.status_code = 500
    mocked_response.reason = "Internal Server Error"

    @mock.patch(
        "requests.adapters.HTTPAdapter.send",
        side_effect=requests.RequestException(response=mocked_response),
    )
    def test_requests_exception_with_response(self, *_, **__):
        with self.assertRaises(requests.RequestException):
            self.perform_request(self.URL)

        span = self.assert_span()
        self.assertEqual(
            span.attributes,
            {
                SpanAttributes.HTTP_METHOD: "GET",
                SpanAttributes.HTTP_URL: self.URL,
                SpanAttributes.HTTP_STATUS_CODE: 500,
            },
        )
        self.assertEqual(span.status.status_code, StatusCode.ERROR)

    @mock.patch("requests.adapters.HTTPAdapter.send", side_effect=Exception)
    def test_requests_basic_exception(self, *_, **__):
        with self.assertRaises(Exception):
            self.perform_request(self.URL)

        span = self.assert_span()
        self.assertEqual(span.status.status_code, StatusCode.ERROR)

    @mock.patch(
        "requests.adapters.HTTPAdapter.send", side_effect=requests.Timeout
    )
    def test_requests_timeout_exception(self, *_, **__):
        with self.assertRaises(Exception):
            self.perform_request(self.URL)

        span = self.assert_span()
        self.assertEqual(span.status.status_code, StatusCode.ERROR)

    def test_adapter_with_custom_response(self):
        response = Response()
        response.status_code = 210
        response.reason = "hello adapter"
        response.raw = TransportMock()

        session = requests.Session()
        session.mount(self.URL, MyAdapter(response))

        self.perform_request(self.URL, session)
        span = self.assert_span()
        self.assertEqual(
            span.attributes,
            {
                "http.method": "GET",
                "http.url": self.URL,
                "http.status_code": 210,
            },
        )


class TestRequestsIntegration(RequestsIntegrationTestBase, TestBase):
    @staticmethod
    def perform_request(url: str, session: requests.Session = None):
        if session is None:
            return requests.get(url, timeout=5)
        return session.get(url)

    def test_credential_removal(self):
        new_url = "http://username:password@mock/status/200"
        self.perform_request(new_url)
        span = self.assert_span()

        self.assertEqual(span.attributes[SpanAttributes.HTTP_URL], self.URL)

    def test_if_headers_equals_none(self):
        result = requests.get(self.URL, headers=None, timeout=5)
        self.assertEqual(result.text, "Hello!")
        self.assert_span()


class TestRequestsIntegrationPreparedRequest(
    RequestsIntegrationTestBase, TestBase
):
    @staticmethod
    def perform_request(url: str, session: requests.Session = None):
        if session is None:
            session = requests.Session()
        request = requests.Request("GET", url)
        prepared_request = session.prepare_request(request)
        return session.send(prepared_request)


class TestRequestsIntergrationMetric(TestBase):
    URL = "http://examplehost:8000/status/200"

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
                _OTEL_SEMCONV_STABILITY_OPT_IN_KEY: sem_conv_mode,
            },
        )
        self.env_patch.start()
        _OpenTelemetrySemanticConventionStability._initialized = False
        RequestsInstrumentor().instrument(meter_provider=self.meter_provider)

        httpretty.enable()
        httpretty.register_uri(httpretty.GET, self.URL, body="Hello!")

    def tearDown(self):
        super().tearDown()
        self.env_patch.stop()
        RequestsInstrumentor().uninstrument()
        httpretty.disable()

    @staticmethod
    def perform_request(url: str) -> requests.Response:
        return requests.get(url, timeout=5)

    def test_basic_metric_success(self):
        self.perform_request(self.URL)

        expected_attributes = {
            SpanAttributes.HTTP_STATUS_CODE: 200,
            SpanAttributes.HTTP_HOST: "examplehost",
            SpanAttributes.NET_PEER_PORT: 8000,
            SpanAttributes.NET_PEER_NAME: "examplehost",
            SpanAttributes.HTTP_METHOD: "GET",
            SpanAttributes.HTTP_FLAVOR: "1.1",
            SpanAttributes.HTTP_SCHEME: "http",
        }

        for (
            resource_metrics
        ) in self.memory_metrics_reader.get_metrics_data().resource_metrics:
            for scope_metrics in resource_metrics.scope_metrics:
                self.assertEqual(len(scope_metrics.metrics), 1)
                for metric in scope_metrics.metrics:
                    self.assertEqual(metric.unit, "ms")
                    self.assertEqual(
                        metric.description,
                        "measures the duration of the outbound HTTP request",
                    )
                    for data_point in metric.data.data_points:
                        self.assertDictEqual(
                            expected_attributes, dict(data_point.attributes)
                        )
                        self.assertEqual(data_point.count, 1)

    def test_basic_metric_new_semconv(self):
        self.perform_request(self.URL)

        expected_attributes = {
            SpanAttributes.HTTP_RESPONSE_STATUS_CODE: 200,
            SpanAttributes.SERVER_ADDRESS: "examplehost",
            SpanAttributes.SERVER_PORT: 8000,
            SpanAttributes.SERVER_ADDRESS: "examplehost",
            SpanAttributes.HTTP_REQUEST_METHOD: "GET",
            SpanAttributes.NET_PROTOCOL_VERSION: "1.1",
        }

        for (
            resource_metrics
        ) in self.memory_metrics_reader.get_metrics_data().resource_metrics:
            for scope_metrics in resource_metrics.scope_metrics:
                self.assertEqual(len(scope_metrics.metrics), 1)
                for metric in scope_metrics.metrics:
                    self.assertEqual(metric.unit, "s")
                    self.assertEqual(
                        metric.description, "Duration of HTTP client requests."
                    )
                    for data_point in metric.data.data_points:
                        self.assertDictEqual(
                            expected_attributes, dict(data_point.attributes)
                        )
                        self.assertEqual(data_point.count, 1)

    def test_basic_metric_both_semconv(self):
        self.perform_request(self.URL)

        expected_attributes_old = {
            SpanAttributes.HTTP_STATUS_CODE: 200,
            SpanAttributes.HTTP_HOST: "examplehost",
            SpanAttributes.NET_PEER_PORT: 8000,
            SpanAttributes.NET_PEER_NAME: "examplehost",
            SpanAttributes.HTTP_METHOD: "GET",
            SpanAttributes.HTTP_FLAVOR: "1.1",
            SpanAttributes.HTTP_SCHEME: "http",
        }

        expected_attributes_new = {
            SpanAttributes.HTTP_RESPONSE_STATUS_CODE: 200,
            SpanAttributes.SERVER_ADDRESS: "examplehost",
            SpanAttributes.SERVER_PORT: 8000,
            SpanAttributes.SERVER_ADDRESS: "examplehost",
            SpanAttributes.HTTP_REQUEST_METHOD: "GET",
            SpanAttributes.NET_PROTOCOL_VERSION: "1.1",
        }

        for (
            resource_metrics
        ) in self.memory_metrics_reader.get_metrics_data().resource_metrics:
            for scope_metrics in resource_metrics.scope_metrics:
                self.assertEqual(len(scope_metrics.metrics), 2)
                for metric in scope_metrics.metrics:
                    for data_point in metric.data.data_points:
                        if metric.unit == "ms":
                            self.assertDictEqual(
                                expected_attributes_old,
                                dict(data_point.attributes),
                            )
                        else:
                            self.assertDictEqual(
                                expected_attributes_new,
                                dict(data_point.attributes),
                            )
                        self.assertEqual(data_point.count, 1)
