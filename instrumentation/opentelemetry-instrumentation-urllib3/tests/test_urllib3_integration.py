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
import json
import typing
from unittest import mock

import httpretty
import httpretty.core
import httpretty.http
import urllib3
import urllib3.exceptions

from opentelemetry import trace
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _HTTPStabilityMode,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.urllib3 import (
    RequestInfo,
    URLLib3Instrumentor,
)
from opentelemetry.instrumentation.utils import (
    suppress_http_instrumentation,
    suppress_instrumentation,
)
from opentelemetry.propagate import get_global_textmap, set_global_textmap
from opentelemetry.test.mock_textmap import MockTextMapPropagator
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import Span
from opentelemetry.util.http import get_excluded_urls

# pylint: disable=too-many-public-methods


class TestURLLib3Instrumentor(TestBase):
    HTTP_URL = "http://mock/status/200"
    HTTPS_URL = "https://mock/status/200"

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
                "OTEL_PYTHON_URLLIB3_EXCLUDED_URLS": "http://localhost/env_excluded_arg/123,env_excluded_noarg",
                OTEL_SEMCONV_STABILITY_OPT_IN: sem_conv_mode,
            },
        )
        _OpenTelemetrySemanticConventionStability._initialized = False
        self.env_patch.start()

        self.exclude_patch = mock.patch(
            "opentelemetry.instrumentation.urllib3._excluded_urls_from_env",
            get_excluded_urls("URLLIB3"),
        )
        self.exclude_patch.start()

        URLLib3Instrumentor().instrument()

        httpretty.enable(allow_net_connect=False)
        httpretty.register_uri(httpretty.GET, self.HTTP_URL, body="Hello!")
        httpretty.register_uri(httpretty.GET, self.HTTPS_URL, body="Hello!")
        httpretty.register_uri(httpretty.POST, self.HTTP_URL, body="Hello!")

    def tearDown(self):
        super().tearDown()
        self.env_patch.stop()
        URLLib3Instrumentor().uninstrument()

        httpretty.disable()
        httpretty.reset()

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

    def assert_success_span(
        self,
        response: urllib3.response.HTTPResponse,
        url: str,
        sem_conv_opt_in_mode: _HTTPStabilityMode = _HTTPStabilityMode.DEFAULT,
    ):
        self.assertEqual(b"Hello!", response.data)

        span = self.assert_span()
        self.assertIs(trace.SpanKind.CLIENT, span.kind)
        self.assertEqual("GET", span.name)
        self.assertEqual(
            span.status.status_code, trace.status.StatusCode.UNSET
        )
        expected_attr_old = {
            "http.method": "GET",
            "http.url": url,
            "http.status_code": 200,
        }

        expected_attr_new = {
            "http.request.method": "GET",
            "url.full": url,
            "http.response.status_code": 200,
        }

        attributes = {
            _HTTPStabilityMode.DEFAULT: expected_attr_old,
            _HTTPStabilityMode.HTTP: expected_attr_new,
            _HTTPStabilityMode.HTTP_DUP: {
                **expected_attr_new,
                **expected_attr_old,
            },
        }
        self.assertDictEqual(
            dict(span.attributes), attributes.get(sem_conv_opt_in_mode)
        )

    def assert_exception_span(
        self,
        url: str,
        sem_conv_opt_in_mode: _HTTPStabilityMode = _HTTPStabilityMode.DEFAULT,
    ):
        span = self.assert_span()

        expected_attr_old = {
            "http.method": "GET",
            "http.url": url,
        }

        expected_attr_new = {
            "http.request.method": "GET",
            "url.full": url,
            # TODO: Add `error.type` attribute when supported
        }

        attributes = {
            _HTTPStabilityMode.DEFAULT: expected_attr_old,
            _HTTPStabilityMode.HTTP: expected_attr_new,
            _HTTPStabilityMode.HTTP_DUP: {
                **expected_attr_new,
                **expected_attr_old,
            },
        }

        self.assertDictEqual(
            dict(span.attributes), attributes.get(sem_conv_opt_in_mode)
        )
        self.assertEqual(
            trace.status.StatusCode.ERROR, span.status.status_code
        )

    @staticmethod
    def perform_request(
        url: str,
        headers: typing.Mapping = None,
        retries: urllib3.Retry = None,
        method: str = "GET",
    ) -> urllib3.response.HTTPResponse:
        if retries is None:
            retries = urllib3.Retry.from_int(0)

        pool = urllib3.PoolManager()
        return pool.request(method, url, headers=headers, retries=retries)

    def test_basic_http_success(self):
        response = self.perform_request(self.HTTP_URL)
        self.assert_success_span(
            response,
            self.HTTP_URL,
            sem_conv_opt_in_mode=_HTTPStabilityMode.DEFAULT,
        )

    def test_basic_http_success_new_semconv(self):
        response = self.perform_request(self.HTTP_URL)
        self.assert_success_span(
            response,
            self.HTTP_URL,
            sem_conv_opt_in_mode=_HTTPStabilityMode.HTTP,
        )

    def test_basic_http_success_both_semconv(self):
        response = self.perform_request(self.HTTP_URL)
        self.assert_success_span(
            response,
            self.HTTP_URL,
            sem_conv_opt_in_mode=_HTTPStabilityMode.HTTP_DUP,
        )

    def test_basic_http_success_using_connection_pool(self):
        pool = urllib3.HTTPConnectionPool("mock")
        response = pool.request("GET", "/status/200")

        self.assert_success_span(response, self.HTTP_URL)

    def test_basic_https_success(self):
        response = self.perform_request(self.HTTPS_URL)
        self.assert_success_span(response, self.HTTPS_URL)

    def test_basic_https_success_using_connection_pool(self):
        pool = urllib3.HTTPSConnectionPool("mock")
        response = pool.request("GET", "/status/200")

        self.assert_success_span(response, self.HTTPS_URL)

    def test_schema_url(self):
        pool = urllib3.HTTPSConnectionPool("mock")
        response = pool.request("GET", "/status/200")

        self.assertEqual(b"Hello!", response.data)
        span = self.assert_span()
        self.assertEqual(
            span.instrumentation_scope.schema_url,
            "https://opentelemetry.io/schemas/1.11.0",
        )

    def test_schema_url_new_semconv(self):
        pool = urllib3.HTTPSConnectionPool("mock")
        response = pool.request("GET", "/status/200")

        self.assertEqual(b"Hello!", response.data)
        span = self.assert_span()
        self.assertEqual(
            span.instrumentation_scope.schema_url,
            "https://opentelemetry.io/schemas/1.21.0",
        )

    def test_schema_url_both_semconv(self):
        pool = urllib3.HTTPSConnectionPool("mock")
        response = pool.request("GET", "/status/200")

        self.assertEqual(b"Hello!", response.data)
        span = self.assert_span()
        self.assertEqual(
            span.instrumentation_scope.schema_url,
            "https://opentelemetry.io/schemas/1.21.0",
        )

    def test_basic_not_found(self):
        url_404 = "http://mock/status/404"
        httpretty.register_uri(httpretty.GET, url_404, status=404)

        response = self.perform_request(url_404)
        self.assertEqual(404, response.status)

        span = self.assert_span()
        self.assertEqual(404, span.attributes.get("http.status_code"))
        self.assertIs(trace.status.StatusCode.ERROR, span.status.status_code)

    def test_basic_not_found_new_semconv(self):
        url_404 = "http://mock/status/404"
        httpretty.register_uri(httpretty.GET, url_404, status=404)

        response = self.perform_request(url_404)
        self.assertEqual(404, response.status)

        span = self.assert_span()
        self.assertEqual(404, span.attributes.get("http.response.status_code"))
        self.assertIs(trace.status.StatusCode.ERROR, span.status.status_code)

    def test_basic_not_found_both_semconv(self):
        url_404 = "http://mock/status/404"
        httpretty.register_uri(httpretty.GET, url_404, status=404)

        response = self.perform_request(url_404)
        self.assertEqual(404, response.status)

        span = self.assert_span()
        self.assertEqual(404, span.attributes.get("http.response.status_code"))
        self.assertEqual(404, span.attributes.get("http.status_code"))
        self.assertIs(trace.status.StatusCode.ERROR, span.status.status_code)

    @mock.patch("httpretty.http.HttpBaseClass.METHODS", ("NONSTANDARD",))
    def test_nonstandard_http_method(self):
        httpretty.register_uri(
            "NONSTANDARD", self.HTTP_URL, body="Hello!", status=405
        )
        self.perform_request(self.HTTP_URL, method="NONSTANDARD")
        span = self.assert_span()
        self.assertEqual("HTTP", span.name)
        self.assertEqual(span.attributes.get("http.method"), "_OTHER")
        self.assertEqual(span.attributes.get("http.status_code"), 405)

    @mock.patch("httpretty.http.HttpBaseClass.METHODS", ("NONSTANDARD",))
    def test_nonstandard_http_method_new_semconv(self):
        httpretty.register_uri(
            "NONSTANDARD", self.HTTP_URL, body="Hello!", status=405
        )
        self.perform_request(self.HTTP_URL, method="NONSTANDARD")
        span = self.assert_span()
        self.assertEqual("HTTP", span.name)
        self.assertEqual(span.attributes.get("http.request.method"), "_OTHER")
        self.assertEqual(
            span.attributes.get("http.request.method_original"), "NONSTANDARD"
        )
        self.assertEqual(span.attributes.get("http.response.status_code"), 405)

    @mock.patch("httpretty.http.HttpBaseClass.METHODS", ("NONSTANDARD",))
    def test_nonstandard_http_method_both_semconv(self):
        httpretty.register_uri(
            "NONSTANDARD", self.HTTP_URL, body="Hello!", status=405
        )
        self.perform_request(self.HTTP_URL, method="NONSTANDARD")
        span = self.assert_span()
        self.assertEqual("HTTP", span.name)
        self.assertEqual(span.attributes.get("http.method"), "_OTHER")
        self.assertEqual(span.attributes.get("http.status_code"), 405)
        self.assertEqual(span.attributes.get("http.request.method"), "_OTHER")
        self.assertEqual(
            span.attributes.get("http.request.method_original"), "NONSTANDARD"
        )
        self.assertEqual(span.attributes.get("http.response.status_code"), 405)

    def test_basic_http_non_default_port(self):
        url = "http://mock:666/status/200"
        httpretty.register_uri(httpretty.GET, url, body="Hello!")

        response = self.perform_request(url)
        self.assert_success_span(response, url)

    def test_basic_http_absolute_url(self):
        url = "http://mock:666/status/200"
        httpretty.register_uri(httpretty.GET, url, body="Hello!")
        pool = urllib3.HTTPConnectionPool("mock", port=666)
        response = pool.request("GET", url)

        self.assert_success_span(response, url)

    def test_url_open_explicit_arg_parameters(self):
        url = "http://mock:666/status/200"
        httpretty.register_uri(httpretty.GET, url, body="Hello!")
        pool = urllib3.HTTPConnectionPool("mock", port=666)
        response = pool.urlopen(method="GET", url="/status/200")

        self.assert_success_span(response, url)

    def test_excluded_urls_explicit(self):
        url_201 = "http://mock/status/201"
        httpretty.register_uri(
            httpretty.GET,
            url_201,
            status=201,
        )

        URLLib3Instrumentor().uninstrument()
        URLLib3Instrumentor().instrument(excluded_urls=".*/201")
        self.perform_request(self.HTTP_URL)
        self.perform_request(url_201)

        self.assert_span(num_spans=1)

    def test_excluded_urls_from_env(self):
        url = "http://localhost/env_excluded_arg/123"
        httpretty.register_uri(
            httpretty.GET,
            url,
            status=200,
        )

        URLLib3Instrumentor().uninstrument()
        URLLib3Instrumentor().instrument()
        self.perform_request(self.HTTP_URL)
        self.perform_request(url)

        self.assert_span(num_spans=1)

    def test_uninstrument(self):
        URLLib3Instrumentor().uninstrument()

        response = self.perform_request(self.HTTP_URL)
        self.assertEqual(b"Hello!", response.data)
        self.assert_span(num_spans=0)
        # instrument again to avoid warning message on tearDown
        URLLib3Instrumentor().instrument()

    def test_suppress_instrumentation(self):
        suppression_cms = (
            suppress_instrumentation,
            suppress_http_instrumentation,
        )
        for cm in suppression_cms:
            self.memory_exporter.clear()

            with self.subTest(cm=cm):
                with cm():
                    response = self.perform_request(self.HTTP_URL)
                    self.assertEqual(b"Hello!", response.data)

                self.assert_span(num_spans=0)

    def test_context_propagation(self):
        previous_propagator = get_global_textmap()
        try:
            set_global_textmap(MockTextMapPropagator())
            response = self.perform_request(self.HTTP_URL)
            self.assertEqual(b"Hello!", response.data)

            span = self.assert_span()
            headers = dict(httpretty.last_request().headers)

            self.assertIn(MockTextMapPropagator.TRACE_ID_KEY, headers)
            self.assertEqual(
                headers[MockTextMapPropagator.TRACE_ID_KEY],
                str(span.get_span_context().trace_id),
            )
            self.assertIn(MockTextMapPropagator.SPAN_ID_KEY, headers)
            self.assertEqual(
                headers[MockTextMapPropagator.SPAN_ID_KEY],
                str(span.get_span_context().span_id),
            )
        finally:
            set_global_textmap(previous_propagator)

    def test_custom_tracer_provider(self):
        tracer_provider, exporter = self.create_tracer_provider()
        tracer_provider = mock.Mock(wraps=tracer_provider)

        URLLib3Instrumentor().uninstrument()
        URLLib3Instrumentor().instrument(tracer_provider=tracer_provider)

        response = self.perform_request(self.HTTP_URL)
        self.assertEqual(b"Hello!", response.data)

        self.assert_span(exporter=exporter)
        self.assertEqual(1, tracer_provider.get_tracer.call_count)

    @mock.patch(
        "urllib3.connectionpool.HTTPConnectionPool._make_request",
        side_effect=urllib3.exceptions.ConnectTimeoutError,
    )
    def test_request_exception(self, _):
        with self.assertRaises(urllib3.exceptions.ConnectTimeoutError):
            self.perform_request(
                self.HTTP_URL, retries=urllib3.Retry(connect=False)
            )

        self.assert_exception_span(self.HTTP_URL)

    @mock.patch(
        "urllib3.connectionpool.HTTPConnectionPool._make_request",
        side_effect=urllib3.exceptions.ConnectTimeoutError,
    )
    def test_request_exception_new_semconv(self, _):
        with self.assertRaises(urllib3.exceptions.ConnectTimeoutError):
            self.perform_request(
                self.HTTP_URL, retries=urllib3.Retry(connect=False)
            )

        self.assert_exception_span(
            self.HTTP_URL, sem_conv_opt_in_mode=_HTTPStabilityMode.HTTP
        )

    @mock.patch(
        "urllib3.connectionpool.HTTPConnectionPool._make_request",
        side_effect=urllib3.exceptions.ConnectTimeoutError,
    )
    def test_request_exception_both_semconv(self, _):
        with self.assertRaises(urllib3.exceptions.ConnectTimeoutError):
            self.perform_request(
                self.HTTP_URL, retries=urllib3.Retry(connect=False)
            )

        self.assert_exception_span(
            self.HTTP_URL, sem_conv_opt_in_mode=_HTTPStabilityMode.HTTP_DUP
        )

    @mock.patch(
        "urllib3.connectionpool.HTTPConnectionPool._make_request",
        side_effect=urllib3.exceptions.ProtocolError,
    )
    def test_retries_do_not_create_spans(self, _):
        with self.assertRaises(urllib3.exceptions.MaxRetryError):
            self.perform_request(self.HTTP_URL, retries=urllib3.Retry(1))

        # expect only a single span (retries are ignored)
        self.assert_exception_span(self.HTTP_URL)

    def test_url_filter(self):
        def url_filter(url):
            return url.split("?")[0]

        URLLib3Instrumentor().uninstrument()
        URLLib3Instrumentor().instrument(url_filter=url_filter)

        response = self.perform_request(self.HTTP_URL + "?e=mcc")
        self.assert_success_span(response, self.HTTP_URL)

    def test_credential_removal(self):
        url = "http://username:password@mock/status/200"

        response = self.perform_request(url)
        self.assert_success_span(response, self.HTTP_URL)

    def test_hooks(self):
        def request_hook(span, pool, request_info):
            span.update_name("name set from hook")

        def response_hook(span, pool, response):
            span.set_attribute("response_hook_attr", "value")

        URLLib3Instrumentor().uninstrument()
        URLLib3Instrumentor().instrument(
            request_hook=request_hook, response_hook=response_hook
        )
        response = self.perform_request(self.HTTP_URL)
        self.assertEqual(b"Hello!", response.data)

        span = self.assert_span()

        self.assertEqual(span.name, "name set from hook")
        self.assertIn("response_hook_attr", span.attributes)
        self.assertEqual(span.attributes["response_hook_attr"], "value")

    def test_request_hook_params(self):
        def request_hook(
            span: Span,
            _pool: urllib3.connectionpool.ConnectionPool,
            request_info: RequestInfo,
        ) -> None:
            span.set_attribute("request_hook_method", request_info.method)
            span.set_attribute("request_hook_url", request_info.url)
            span.set_attribute(
                "request_hook_headers", json.dumps(dict(request_info.headers))
            )
            span.set_attribute("request_hook_body", request_info.body)

        URLLib3Instrumentor().uninstrument()
        URLLib3Instrumentor().instrument(
            request_hook=request_hook,
        )

        headers = {"header1": "value1", "header2": "value2"}
        body = "param1=1&param2=2"

        pool = urllib3.HTTPConnectionPool("mock")
        response = pool.request(
            "POST", "/status/200", body=body, headers=headers
        )

        self.assertEqual(b"Hello!", response.data)

        span = self.assert_span()

        self.assertEqual(span.attributes["request_hook_method"], "POST")
        self.assertEqual(
            span.attributes["request_hook_url"], "http://mock/status/200"
        )
        self.assertIn("request_hook_headers", span.attributes)
        self.assertEqual(
            span.attributes["request_hook_headers"], json.dumps(headers)
        )
        self.assertIn("request_hook_body", span.attributes)
        self.assertEqual(span.attributes["request_hook_body"], body)

    def test_request_positional_body(self):
        def request_hook(
            span: Span,
            _pool: urllib3.connectionpool.ConnectionPool,
            request_info: RequestInfo,
        ) -> None:
            span.set_attribute("request_hook_body", request_info.body)

        URLLib3Instrumentor().uninstrument()
        URLLib3Instrumentor().instrument(
            request_hook=request_hook,
        )

        body = "param1=1&param2=2"

        pool = urllib3.HTTPConnectionPool("mock")
        response = pool.urlopen("POST", "/status/200", body)

        self.assertEqual(b"Hello!", response.data)

        span = self.assert_span()

        self.assertIn("request_hook_body", span.attributes)
        self.assertEqual(span.attributes["request_hook_body"], body)

    def test_no_op_tracer_provider(self):
        URLLib3Instrumentor().uninstrument()
        tracer_provider = trace.NoOpTracerProvider()
        URLLib3Instrumentor().instrument(tracer_provider=tracer_provider)

        response = self.perform_request(self.HTTP_URL)
        self.assertEqual(b"Hello!", response.data)
        self.assert_span(num_spans=0)
