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
import socket
import urllib
from unittest import mock
from unittest.mock import patch
from urllib import request
from urllib.error import HTTPError
from urllib.request import OpenerDirector

import httpretty

import opentelemetry.instrumentation.urllib  # pylint: disable=no-name-in-module,import-error
from opentelemetry import context, trace

# FIXME: fix the importing of this private attribute when the location of the _SUPPRESS_HTTP_INSTRUMENTATION_KEY is defined.
from opentelemetry.context import _SUPPRESS_HTTP_INSTRUMENTATION_KEY
from opentelemetry.instrumentation.urllib import (  # pylint: disable=no-name-in-module,import-error
    URLLibInstrumentor,
)
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
from opentelemetry.propagate import get_global_textmap, set_global_textmap
from opentelemetry.sdk import resources
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.mock_textmap import MockTextMapPropagator
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import StatusCode
from opentelemetry.util.http import get_excluded_urls

# pylint: disable=too-many-public-methods


class RequestsIntegrationTestBase(abc.ABC):
    # pylint: disable=no-member

    URL = "http://httpbin.org/status/200"
    URL_TIMEOUT = "http://httpbin.org/timeout/0"
    URL_EXCEPTION = "http://httpbin.org/exception/0"

    # pylint: disable=invalid-name
    def setUp(self):
        super().setUp()

        self.env_patch = mock.patch.dict(
            "os.environ",
            {
                "OTEL_PYTHON_URLLIB_EXCLUDED_URLS": "http://localhost/env_excluded_arg/123,env_excluded_noarg"
            },
        )
        self.env_patch.start()

        self.exclude_patch = mock.patch(
            "opentelemetry.instrumentation.urllib._excluded_urls_from_env",
            get_excluded_urls("URLLIB"),
        )
        self.exclude_patch.start()

        URLLibInstrumentor().instrument()
        httpretty.enable()
        httpretty.register_uri(httpretty.GET, self.URL, body=b"Hello!")
        httpretty.register_uri(
            httpretty.GET,
            self.URL_TIMEOUT,
            body=self.timeout_exception_callback,
        )
        httpretty.register_uri(
            httpretty.GET,
            self.URL_EXCEPTION,
            body=self.base_exception_callback,
        )
        httpretty.register_uri(
            httpretty.GET,
            "http://httpbin.org/status/500",
            status=500,
        )

    # pylint: disable=invalid-name
    def tearDown(self):
        super().tearDown()
        URLLibInstrumentor().uninstrument()
        httpretty.disable()

    @staticmethod
    def timeout_exception_callback(*_, **__):
        raise socket.timeout

    @staticmethod
    def base_exception_callback(*_, **__):
        raise Exception("test")

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
    def perform_request(url: str, opener: OpenerDirector = None):
        pass

    def test_basic(self):
        result = self.perform_request(self.URL)

        self.assertEqual(result.read(), b"Hello!")
        span = self.assert_span()

        self.assertIs(span.kind, trace.SpanKind.CLIENT)
        self.assertEqual(span.name, "HTTP GET")

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
            span, opentelemetry.instrumentation.urllib
        )

    def test_excluded_urls_explicit(self):
        url_201 = "http://httpbin.org/status/201"
        httpretty.register_uri(
            httpretty.GET,
            url_201,
            status=201,
        )

        URLLibInstrumentor().uninstrument()
        URLLibInstrumentor().instrument(excluded_urls=".*/201")
        self.perform_request(self.URL)
        self.perform_request(url_201)

        self.assert_span(num_spans=1)

    def test_excluded_urls_from_env(self):
        url = "http://localhost/env_excluded_arg/123"
        httpretty.register_uri(
            httpretty.GET,
            url,
            status=200,
        )

        URLLibInstrumentor().uninstrument()
        URLLibInstrumentor().instrument()
        self.perform_request(self.URL)
        self.perform_request(url)

        self.assert_span(num_spans=1)

    def test_not_foundbasic(self):
        url_404 = "http://httpbin.org/status/404/"
        httpretty.register_uri(
            httpretty.GET,
            url_404,
            status=404,
        )
        exception = None
        try:
            self.perform_request(url_404)
        except Exception as err:  # pylint: disable=broad-except
            exception = err
        code = exception.code
        self.assertEqual(code, 404)

        span = self.assert_span()

        self.assertEqual(
            span.attributes.get(SpanAttributes.HTTP_STATUS_CODE), 404
        )

        self.assertIs(
            span.status.status_code,
            trace.StatusCode.ERROR,
        )

    @staticmethod
    def mock_get_code(*args, **kwargs):
        return None

    @patch("http.client.HTTPResponse.getcode", new=mock_get_code)
    def test_response_code_none(self):
        result = self.perform_request(self.URL)

        self.assertEqual(result.read(), b"Hello!")
        span = self.assert_span()

        self.assertIs(span.kind, trace.SpanKind.CLIENT)
        self.assertEqual(span.name, "HTTP GET")

        self.assertEqual(
            span.attributes,
            {
                SpanAttributes.HTTP_METHOD: "GET",
                SpanAttributes.HTTP_URL: self.URL,
            },
        )

        self.assertIs(span.status.status_code, trace.StatusCode.UNSET)

        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.urllib
        )

    def test_uninstrument(self):
        URLLibInstrumentor().uninstrument()
        result = self.perform_request(self.URL)
        self.assertEqual(result.read(), b"Hello!")
        self.assert_span(num_spans=0)
        # instrument again to avoid annoying warning message
        URLLibInstrumentor().instrument()

    def test_uninstrument_session(self):
        clienr1 = urllib.request.build_opener()
        URLLibInstrumentor().uninstrument_opener(clienr1)

        result = self.perform_request(self.URL, clienr1)
        self.assertEqual(result.read(), b"Hello!")
        self.assert_span(num_spans=0)

        # Test that other sessions as well as global requests is still
        # instrumented
        opener2 = urllib.request.build_opener()
        result = self.perform_request(self.URL, opener2)
        self.assertEqual(result.read(), b"Hello!")
        self.assert_span()

        self.memory_exporter.clear()

        result = self.perform_request(self.URL)
        self.assertEqual(result.read(), b"Hello!")
        self.assert_span()

    def test_suppress_instrumentation(self):
        token = context.attach(
            context.set_value(_SUPPRESS_INSTRUMENTATION_KEY, True)
        )
        try:
            result = self.perform_request(self.URL)
            self.assertEqual(result.read(), b"Hello!")
        finally:
            context.detach(token)

        self.assert_span(num_spans=0)

    def test_suppress_http_instrumentation(self):
        token = context.attach(
            context.set_value(_SUPPRESS_HTTP_INSTRUMENTATION_KEY, True)
        )
        try:
            result = self.perform_request(self.URL)
            self.assertEqual(result.read(), b"Hello!")
        finally:
            context.detach(token)

        self.assert_span(num_spans=0)

    def test_not_recording(self):
        with mock.patch("opentelemetry.trace.INVALID_SPAN") as mock_span:
            URLLibInstrumentor().uninstrument()
            URLLibInstrumentor().instrument(
                tracer_provider=trace.NoOpTracerProvider()
            )
            mock_span.is_recording.return_value = False
            result = self.perform_request(self.URL)
            self.assertEqual(result.read(), b"Hello!")
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
            self.assertEqual(result.read(), b"Hello!")

            span = self.assert_span()

            headers_ = dict(httpretty.last_request().headers)
            headers = {}
            for k, v in headers_.items():
                headers[k.lower()] = v

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

    def test_custom_tracer_provider(self):
        resource = resources.Resource.create({})
        result = self.create_tracer_provider(resource=resource)
        tracer_provider, exporter = result
        URLLibInstrumentor().uninstrument()
        URLLibInstrumentor().instrument(tracer_provider=tracer_provider)

        result = self.perform_request(self.URL)
        self.assertEqual(result.read(), b"Hello!")

        span = self.assert_span(exporter=exporter)
        self.assertIs(span.resource, resource)

    def test_requests_exception_with_response(self, *_, **__):
        with self.assertRaises(HTTPError):
            self.perform_request("http://httpbin.org/status/500")

        span = self.assert_span()
        self.assertEqual(
            dict(span.attributes),
            {
                SpanAttributes.HTTP_METHOD: "GET",
                SpanAttributes.HTTP_URL: "http://httpbin.org/status/500",
                SpanAttributes.HTTP_STATUS_CODE: 500,
            },
        )
        self.assertEqual(span.status.status_code, StatusCode.ERROR)

    def test_requests_basic_exception(self, *_, **__):
        with self.assertRaises(Exception):
            self.perform_request(self.URL_EXCEPTION)

        span = self.assert_span()
        self.assertEqual(span.status.status_code, StatusCode.ERROR)

    def test_requests_timeout_exception(self, *_, **__):
        with self.assertRaises(Exception):
            opener = urllib.request.build_opener()
            opener.open(self.URL_TIMEOUT, timeout=0.0001)

        span = self.assert_span()
        self.assertEqual(span.status.status_code, StatusCode.ERROR)

    def test_credential_removal(self):
        url = "http://username:password@httpbin.org/status/200"

        with self.assertRaises(Exception):
            self.perform_request(url)

        span = self.assert_span()
        self.assertEqual(span.attributes[SpanAttributes.HTTP_URL], self.URL)

    def test_hooks(self):
        def request_hook(span, request_obj):
            span.update_name("name set from hook")

        def response_hook(span, request_obj, response):
            span.set_attribute("response_hook_attr", "value")

        URLLibInstrumentor().uninstrument()
        URLLibInstrumentor().instrument(
            request_hook=request_hook, response_hook=response_hook
        )
        result = self.perform_request(self.URL)

        self.assertEqual(result.read(), b"Hello!")
        span = self.assert_span()

        self.assertEqual(span.name, "name set from hook")
        self.assertIn("response_hook_attr", span.attributes)
        self.assertEqual(span.attributes["response_hook_attr"], "value")

    def test_no_op_tracer_provider(self):
        URLLibInstrumentor().uninstrument()
        tracer_provider = trace.NoOpTracerProvider()
        URLLibInstrumentor().instrument(tracer_provider=tracer_provider)

        result = self.perform_request(self.URL)
        self.assertEqual(result.read(), b"Hello!")
        self.assert_span(num_spans=0)


class TestRequestsIntegration(RequestsIntegrationTestBase, TestBase):
    @staticmethod
    def perform_request(url: str, opener: OpenerDirector = None):
        if not opener:
            opener = urllib.request.build_opener()
        return opener.open(fullurl=url)

    def test_invalid_url(self):
        url = "http://[::1/nope"

        with self.assertRaises(ValueError):
            request.Request(url, method="POST")

        self.assert_span(num_spans=0)

    def test_if_headers_equals_none(self):
        result = self.perform_request(self.URL)
        self.assertEqual(result.read(), b"Hello!")
        self.assert_span()
