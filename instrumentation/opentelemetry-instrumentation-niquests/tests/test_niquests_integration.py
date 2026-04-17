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

import abc
import re
import ssl
from datetime import timedelta
from unittest import mock

import niquests
import responses
from niquests.adapters import BaseAdapter
from niquests.models import ConnectionInfo, Response

import opentelemetry.instrumentation.niquests
from opentelemetry import trace
from opentelemetry.instrumentation._semconv import (
    HTTP_DURATION_HISTOGRAM_BUCKETS_NEW,
    HTTP_DURATION_HISTOGRAM_BUCKETS_OLD,
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _get_schema_url,
    _OpenTelemetrySemanticConventionStability,
    _StabilityMode,
)
from opentelemetry.instrumentation.niquests import NiquestsInstrumentor
from opentelemetry.instrumentation.utils import (
    suppress_http_instrumentation,
    suppress_instrumentation,
)
from opentelemetry.propagate import get_global_textmap, set_global_textmap
from opentelemetry.sdk import resources
from opentelemetry.semconv._incubating.attributes.http_attributes import (
    HTTP_FLAVOR,
    HTTP_HOST,
    HTTP_METHOD,
    HTTP_SCHEME,
    HTTP_STATUS_CODE,
    HTTP_URL,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_PEER_NAME,
    NET_PEER_PORT,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.semconv.attributes.http_attributes import (
    HTTP_REQUEST_METHOD,
    HTTP_REQUEST_METHOD_ORIGINAL,
    HTTP_RESPONSE_STATUS_CODE,
)
from opentelemetry.semconv.attributes.network_attributes import (
    NETWORK_PEER_ADDRESS,
    NETWORK_PEER_PORT,
    NETWORK_PROTOCOL_VERSION,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.semconv.attributes.url_attributes import URL_FULL
from opentelemetry.semconv.attributes.user_agent_attributes import (
    USER_AGENT_ORIGINAL,
)
from opentelemetry.test.mock_textmap import MockTextMapPropagator
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import StatusCode
from opentelemetry.util.http import (
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_REQUEST,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_RESPONSE,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS,
    get_excluded_urls,
)

_NIQUESTS_USER_AGENT = f"niquests/{niquests.__version__}"


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


SCOPE = "opentelemetry.instrumentation.niquests"


class NiquestsIntegrationTestBase(abc.ABC):
    # pylint: disable=no-member
    # pylint: disable=too-many-public-methods

    URL = "http://mock/status/200"

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
                "OTEL_PYTHON_NIQUESTS_EXCLUDED_URLS": "http://localhost/env_excluded_arg/123,env_excluded_noarg",
                OTEL_SEMCONV_STABILITY_OPT_IN: sem_conv_mode,
            },
        )

        _OpenTelemetrySemanticConventionStability._initialized = False

        self.env_patch.start()

        self.exclude_patch = mock.patch(
            "opentelemetry.instrumentation.niquests._excluded_urls_from_env",
            get_excluded_urls("NIQUESTS"),
        )
        self.exclude_patch.start()

        NiquestsInstrumentor().instrument()
        responses.start()
        responses.add(responses.GET, self.URL, body="Hello!", status=200)

    # pylint: disable=invalid-name
    def tearDown(self):
        super().tearDown()
        self.env_patch.stop()
        self.exclude_patch.stop()
        _OpenTelemetrySemanticConventionStability._initialized = False
        NiquestsInstrumentor().uninstrument()
        responses.stop()
        responses.reset()

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
    def perform_request(url: str, session: niquests.Session = None):
        pass

    def test_basic(self):
        result = self.perform_request(self.URL)
        self.assertEqual(result.text, "Hello!")
        span = self.assert_span()

        self.assertIs(span.kind, trace.SpanKind.CLIENT)
        self.assertEqual(span.name, "GET")

        self.assertEqual(
            span.instrumentation_scope.schema_url,
            _get_schema_url(_StabilityMode.DEFAULT),
        )

        self.assertEqual(
            span.attributes,
            {
                HTTP_METHOD: "GET",
                HTTP_URL: self.URL,
                HTTP_STATUS_CODE: 200,
                USER_AGENT_ORIGINAL: _NIQUESTS_USER_AGENT,
            },
        )

        self.assertIs(span.status.status_code, trace.StatusCode.UNSET)

        self.assertEqualSpanInstrumentationScope(
            span, opentelemetry.instrumentation.niquests
        )

    def test_basic_new_semconv(self):
        url_with_port = "http://mock:80/status/200"
        responses.add(responses.GET, url_with_port, status=200, body="Hello!")
        result = self.perform_request(url_with_port)
        self.assertEqual(result.text, "Hello!")
        span = self.assert_span()

        self.assertIs(span.kind, trace.SpanKind.CLIENT)
        self.assertEqual(span.name, "GET")

        self.assertEqual(
            span.instrumentation_scope.schema_url,
            _get_schema_url(_StabilityMode.HTTP),
        )
        expected = {
            HTTP_REQUEST_METHOD: "GET",
            URL_FULL: url_with_port,
            SERVER_ADDRESS: "mock",
            NETWORK_PEER_ADDRESS: "mock",
            HTTP_RESPONSE_STATUS_CODE: 200,
            SERVER_PORT: 80,
            NETWORK_PEER_PORT: 80,
            USER_AGENT_ORIGINAL: _NIQUESTS_USER_AGENT,
        }
        # responses mock does not provide raw.version, so
        # NETWORK_PROTOCOL_VERSION is only present on real connections.
        if NETWORK_PROTOCOL_VERSION in span.attributes:
            expected[NETWORK_PROTOCOL_VERSION] = span.attributes[
                NETWORK_PROTOCOL_VERSION
            ]
        self.assertEqual(span.attributes, expected)

        self.assertIs(span.status.status_code, trace.StatusCode.UNSET)

        self.assertEqualSpanInstrumentationScope(
            span, opentelemetry.instrumentation.niquests
        )

    def test_basic_both_semconv(self):
        url_with_port = "http://mock:80/status/200"
        responses.add(responses.GET, url_with_port, status=200, body="Hello!")
        result = self.perform_request(url_with_port)
        self.assertEqual(result.text, "Hello!")
        span = self.assert_span()

        self.assertIs(span.kind, trace.SpanKind.CLIENT)
        self.assertEqual(span.name, "GET")

        self.assertEqual(
            span.instrumentation_scope.schema_url,
            _get_schema_url(_StabilityMode.HTTP),
        )
        expected = {
            HTTP_METHOD: "GET",
            HTTP_REQUEST_METHOD: "GET",
            HTTP_URL: url_with_port,
            URL_FULL: url_with_port,
            HTTP_HOST: "mock",
            SERVER_ADDRESS: "mock",
            NETWORK_PEER_ADDRESS: "mock",
            NET_PEER_PORT: 80,
            HTTP_STATUS_CODE: 200,
            HTTP_RESPONSE_STATUS_CODE: 200,
            SERVER_PORT: 80,
            NETWORK_PEER_PORT: 80,
            USER_AGENT_ORIGINAL: _NIQUESTS_USER_AGENT,
        }
        # responses mock does not provide raw.version, so
        # protocol version attributes are only present on real connections.
        if HTTP_FLAVOR in span.attributes:
            expected[HTTP_FLAVOR] = span.attributes[HTTP_FLAVOR]
        if NETWORK_PROTOCOL_VERSION in span.attributes:
            expected[NETWORK_PROTOCOL_VERSION] = span.attributes[
                NETWORK_PROTOCOL_VERSION
            ]
        self.assertEqual(span.attributes, expected)

        self.assertIs(span.status.status_code, trace.StatusCode.UNSET)

        self.assertEqualSpanInstrumentationScope(
            span, opentelemetry.instrumentation.niquests
        )

    def test_nonstandard_http_method(self):
        responses.add("NONSTANDARD", self.URL, status=405)
        session = niquests.Session()
        session.request("NONSTANDARD", self.URL)
        span = self.assert_span()
        self.assertIs(span.kind, trace.SpanKind.CLIENT)
        self.assertEqual(span.name, "HTTP")
        self.assertEqual(
            span.attributes,
            {
                HTTP_METHOD: "_OTHER",
                HTTP_URL: self.URL,
                HTTP_STATUS_CODE: 405,
                USER_AGENT_ORIGINAL: _NIQUESTS_USER_AGENT,
            },
        )

        self.assertIs(span.status.status_code, trace.StatusCode.ERROR)

    def test_nonstandard_http_method_new_semconv(self):
        responses.add("NONSTANDARD", self.URL, status=405)
        session = niquests.Session()
        session.request("NONSTANDARD", self.URL)
        span = self.assert_span()
        self.assertIs(span.kind, trace.SpanKind.CLIENT)
        self.assertEqual(span.name, "HTTP")
        expected = {
            HTTP_REQUEST_METHOD: "_OTHER",
            URL_FULL: self.URL,
            SERVER_ADDRESS: "mock",
            NETWORK_PEER_ADDRESS: "mock",
            HTTP_RESPONSE_STATUS_CODE: 405,
            ERROR_TYPE: "405",
            HTTP_REQUEST_METHOD_ORIGINAL: "NONSTANDARD",
            USER_AGENT_ORIGINAL: _NIQUESTS_USER_AGENT,
        }
        if NETWORK_PROTOCOL_VERSION in span.attributes:
            expected[NETWORK_PROTOCOL_VERSION] = span.attributes[
                NETWORK_PROTOCOL_VERSION
            ]
        self.assertEqual(span.attributes, expected)
        self.assertIs(span.status.status_code, trace.StatusCode.ERROR)

    def test_hooks(self):
        def request_hook(span, request_obj):
            span.update_name("name set from hook")

        def response_hook(span, request_obj, response):
            span.set_attribute("response_hook_attr", "value")

        NiquestsInstrumentor().uninstrument()
        NiquestsInstrumentor().instrument(
            request_hook=request_hook, response_hook=response_hook
        )
        result = self.perform_request(self.URL)
        self.assertEqual(result.text, "Hello!")
        span = self.assert_span()

        self.assertEqual(span.name, "name set from hook")
        self.assertEqual(span.attributes["response_hook_attr"], "value")

    def test_excluded_urls_explicit(self):
        url_404 = "http://mock/status/404"
        responses.add(responses.GET, url_404, status=404)

        NiquestsInstrumentor().uninstrument()
        NiquestsInstrumentor().instrument(excluded_urls=".*/404")
        self.perform_request(self.URL)
        self.perform_request(url_404)

        self.assert_span(num_spans=1)

    def test_excluded_urls_from_env(self):
        url = "http://localhost/env_excluded_arg/123"
        responses.add(responses.GET, url, status=200)

        NiquestsInstrumentor().uninstrument()
        NiquestsInstrumentor().instrument()
        self.perform_request(self.URL)
        self.perform_request(url)

        self.assert_span(num_spans=1)

    def test_name_callback_default(self):
        def name_callback(method, url):
            return 123

        NiquestsInstrumentor().uninstrument()
        NiquestsInstrumentor().instrument(name_callback=name_callback)
        result = self.perform_request(self.URL)
        self.assertEqual(result.text, "Hello!")
        span = self.assert_span()

        self.assertEqual(span.name, "GET")

    def test_not_found_basic(self):
        url_404 = "http://mock/status/404"
        responses.add(responses.GET, url_404, status=404)
        result = self.perform_request(url_404)
        self.assertEqual(result.status_code, 404)

        span = self.assert_span()

        self.assertEqual(span.attributes.get(HTTP_STATUS_CODE), 404)

        self.assertIs(
            span.status.status_code,
            trace.StatusCode.ERROR,
        )

    def test_not_found_basic_new_semconv(self):
        url_404 = "http://mock/status/404"
        responses.add(responses.GET, url_404, status=404)
        result = self.perform_request(url_404)
        self.assertEqual(result.status_code, 404)

        span = self.assert_span()

        self.assertEqual(span.attributes.get(HTTP_RESPONSE_STATUS_CODE), 404)
        self.assertEqual(span.attributes.get(ERROR_TYPE), "404")

        self.assertIs(
            span.status.status_code,
            trace.StatusCode.ERROR,
        )

    def test_not_found_basic_both_semconv(self):
        url_404 = "http://mock/status/404"
        responses.add(responses.GET, url_404, status=404)
        result = self.perform_request(url_404)
        self.assertEqual(result.status_code, 404)

        span = self.assert_span()

        self.assertEqual(span.attributes.get(HTTP_STATUS_CODE), 404)
        self.assertEqual(span.attributes.get(HTTP_RESPONSE_STATUS_CODE), 404)
        self.assertEqual(span.attributes.get(ERROR_TYPE), "404")

        self.assertIs(
            span.status.status_code,
            trace.StatusCode.ERROR,
        )

    def test_uninstrument(self):
        NiquestsInstrumentor().uninstrument()
        result = self.perform_request(self.URL)
        self.assertEqual(result.text, "Hello!")
        self.assert_span(num_spans=0)
        # instrument again to avoid annoying warning message
        NiquestsInstrumentor().instrument()

    def test_uninstrument_session(self):
        session1 = niquests.Session()
        NiquestsInstrumentor().uninstrument_session(session1)

        result = self.perform_request(self.URL, session1)
        self.assertEqual(result.text, "Hello!")
        self.assert_span(num_spans=0)

        # Test that other sessions as well as global niquests is still
        # instrumented
        session2 = niquests.Session()
        result = self.perform_request(self.URL, session2)
        self.assertEqual(result.text, "Hello!")
        self.assert_span()

        self.memory_exporter.clear()

        result = self.perform_request(self.URL)
        self.assertEqual(result.text, "Hello!")
        self.assert_span()

    def test_suppress_instrumentation(self):
        with suppress_instrumentation():
            result = self.perform_request(self.URL)
            self.assertEqual(result.text, "Hello!")

        self.assert_span(num_spans=0)

    def test_suppress_http_instrumentation(self):
        with suppress_http_instrumentation():
            result = self.perform_request(self.URL)
            self.assertEqual(result.text, "Hello!")

        self.assert_span(num_spans=0)

    def test_not_recording(self):
        with mock.patch("opentelemetry.trace.INVALID_SPAN") as mock_span:
            NiquestsInstrumentor().uninstrument()
            NiquestsInstrumentor().instrument(
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

            headers = dict(responses.calls[-1].request.headers)
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
        NiquestsInstrumentor().uninstrument()

        def response_hook(
            span,
            request: niquests.PreparedRequest,
            response: niquests.Response,
        ):
            span.set_attribute(
                "http.response.body", response.content.decode("utf-8")
            )

        NiquestsInstrumentor().instrument(
            tracer_provider=self.tracer_provider,
            response_hook=response_hook,
        )

        result = self.perform_request(self.URL)
        self.assertEqual(result.text, "Hello!")

        span = self.assert_span()
        self.assertEqual(
            span.attributes,
            {
                HTTP_METHOD: "GET",
                HTTP_URL: self.URL,
                HTTP_STATUS_CODE: 200,
                "http.response.body": "Hello!",
                USER_AGENT_ORIGINAL: _NIQUESTS_USER_AGENT,
            },
        )

    def test_custom_tracer_provider(self):
        resource = resources.Resource.create({})
        result = self.create_tracer_provider(resource=resource)
        tracer_provider, exporter = result
        NiquestsInstrumentor().uninstrument()
        NiquestsInstrumentor().instrument(tracer_provider=tracer_provider)

        result = self.perform_request(self.URL)
        self.assertEqual(result.text, "Hello!")

        span = self.assert_span(exporter=exporter)
        self.assertIs(span.resource, resource)

    @mock.patch(
        "niquests.adapters.HTTPAdapter.send",
        side_effect=niquests.RequestException,
    )
    def test_requests_exception_without_response(self, *_, **__):
        with self.assertRaises(niquests.RequestException):
            self.perform_request(self.URL)

        span = self.assert_span()
        self.assertEqual(
            span.attributes,
            {
                HTTP_METHOD: "GET",
                HTTP_URL: self.URL,
                USER_AGENT_ORIGINAL: _NIQUESTS_USER_AGENT,
            },
        )
        self.assertEqual(span.status.status_code, StatusCode.ERROR)

    @mock.patch(
        "niquests.adapters.HTTPAdapter.send",
        side_effect=niquests.RequestException,
    )
    def test_requests_exception_new_semconv(self, *_, **__):
        url_with_port = "http://mock:80/status/200"
        responses.add(responses.GET, url_with_port, status=200, body="Hello!")
        with self.assertRaises(niquests.RequestException):
            self.perform_request(url_with_port)

        span = self.assert_span()
        self.assertEqual(
            span.attributes,
            {
                HTTP_REQUEST_METHOD: "GET",
                URL_FULL: url_with_port,
                SERVER_ADDRESS: "mock",
                SERVER_PORT: 80,
                NETWORK_PEER_PORT: 80,
                NETWORK_PEER_ADDRESS: "mock",
                ERROR_TYPE: "RequestException",
                USER_AGENT_ORIGINAL: _NIQUESTS_USER_AGENT,
            },
        )
        self.assertEqual(span.status.status_code, StatusCode.ERROR)

    @mock.patch(
        "niquests.adapters.HTTPAdapter.send",
        side_effect=InvalidResponseObjectException,
    )
    def test_requests_exception_without_proper_response_type(self, *_, **__):
        with self.assertRaises(InvalidResponseObjectException):
            self.perform_request(self.URL)

        span = self.assert_span()
        self.assertEqual(
            span.attributes,
            {
                HTTP_METHOD: "GET",
                HTTP_URL: self.URL,
                USER_AGENT_ORIGINAL: _NIQUESTS_USER_AGENT,
            },
        )
        self.assertEqual(span.status.status_code, StatusCode.ERROR)

    mocked_response = niquests.Response()
    mocked_response.status_code = 500
    mocked_response.reason = "Internal Server Error"

    @mock.patch(
        "niquests.adapters.HTTPAdapter.send",
        side_effect=niquests.RequestException(response=mocked_response),
    )
    def test_requests_exception_with_response(self, *_, **__):
        with self.assertRaises(niquests.RequestException):
            self.perform_request(self.URL)

        span = self.assert_span()
        self.assertEqual(
            span.attributes,
            {
                HTTP_METHOD: "GET",
                HTTP_URL: self.URL,
                HTTP_STATUS_CODE: 500,
                USER_AGENT_ORIGINAL: _NIQUESTS_USER_AGENT,
            },
        )
        self.assertEqual(span.status.status_code, StatusCode.ERROR)

    @mock.patch("niquests.adapters.HTTPAdapter.send", side_effect=Exception)
    def test_requests_basic_exception(self, *_, **__):
        with self.assertRaises(Exception):
            self.perform_request(self.URL)

        span = self.assert_span()
        self.assertEqual(span.status.status_code, StatusCode.ERROR)

    @mock.patch(
        "niquests.adapters.HTTPAdapter.send", side_effect=niquests.Timeout
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

        session = niquests.Session()
        session.mount(self.URL, MyAdapter(response))

        self.perform_request(self.URL, session)
        span = self.assert_span()
        self.assertEqual(
            span.attributes,
            {
                "http.method": "GET",
                "http.url": self.URL,
                "http.status_code": 210,
                USER_AGENT_ORIGINAL: _NIQUESTS_USER_AGENT,
            },
        )


class TestNiquestsIntegration(NiquestsIntegrationTestBase, TestBase):
    @staticmethod
    def perform_request(url: str, session: niquests.Session = None):
        if session is None:
            return niquests.get(url, timeout=5)
        return session.get(url)

    def test_remove_sensitive_params(self):
        new_url = (
            "http://username:password@mock/status/200?AWSAccessKeyId=secret"
        )
        responses.add(
            responses.GET,
            re.compile(r"http://.*mock/status/200"),
            body="Hello!",
            status=200,
        )
        self.perform_request(new_url)
        span = self.assert_span()

        self.assertEqual(
            span.attributes[HTTP_URL],
            "http://REDACTED:REDACTED@mock/status/200?AWSAccessKeyId=REDACTED",
        )

    def test_if_headers_equals_none(self):
        result = niquests.get(self.URL, headers=None, timeout=5)
        self.assertEqual(result.text, "Hello!")
        self.assert_span()

    @mock.patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_REQUEST: "X-Custom-Header,X-Another-Header",
        },
    )
    def test_custom_request_headers_captured(self):
        """Test that specified request headers are captured as span attributes."""
        NiquestsInstrumentor().uninstrument()
        NiquestsInstrumentor().instrument()

        headers = {
            "X-Custom-Header": "custom-value",
            "X-Another-Header": "another-value",
            "X-Excluded-Header": "excluded-value",
        }
        responses.add(responses.GET, self.URL, body="Hello!")
        result = niquests.get(self.URL, headers=headers, timeout=5)
        self.assertEqual(result.text, "Hello!")

        span = self.assert_span()
        self.assertEqual(
            span.attributes["http.request.header.x_custom_header"],
            ("custom-value",),
        )
        self.assertEqual(
            span.attributes["http.request.header.x_another_header"],
            ("another-value",),
        )
        self.assertNotIn("http.request.x_excluded_header", span.attributes)

    @mock.patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_RESPONSE: "X-Custom-Header,X-Another-Header",
        },
    )
    def test_custom_response_headers_captured(self):
        """Test that specified response headers are captured as span attributes."""
        NiquestsInstrumentor().uninstrument()
        NiquestsInstrumentor().instrument()

        resp_headers = {
            "X-Custom-Header": "custom-value",
            "X-Another-Header": "another-value",
            "X-Excluded-Header": "excluded-value",
        }
        responses.replace(
            responses.GET, self.URL, body="Hello!", headers=resp_headers
        )
        result = niquests.get(self.URL, timeout=5)
        self.assertEqual(result.text, "Hello!")

        span = self.assert_span()
        self.assertEqual(
            span.attributes["http.response.header.x_custom_header"],
            ("custom-value",),
        )
        self.assertEqual(
            span.attributes["http.response.header.x_another_header"],
            ("another-value",),
        )
        self.assertNotIn("http.response.x_excluded_header", span.attributes)

    @mock.patch.dict("os.environ", {})
    def test_custom_headers_not_captured_when_not_configured(self):
        """Test that headers are not captured when env vars are not set."""
        NiquestsInstrumentor().uninstrument()
        NiquestsInstrumentor().instrument()
        headers = {"X-Request-Header": "request-value"}
        responses.replace(
            responses.GET,
            self.URL,
            body="Hello!",
            headers={"X-Response-Header": "response-value"},
        )
        result = niquests.get(self.URL, headers=headers, timeout=5)
        self.assertEqual(result.text, "Hello!")

        span = self.assert_span()
        self.assertNotIn(
            "http.request.header.x_request_header", span.attributes
        )
        self.assertNotIn(
            "http.response.header.x_response_header", span.attributes
        )

    @mock.patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_RESPONSE: "Set-Cookie,X-Secret",
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_REQUEST: "Authorization,X-Api-Key",
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS: "Authorization,X-Api-Key,Set-Cookie,X-Secret",
        },
    )
    def test_sensitive_headers_sanitized(self):
        """Test that sensitive header values are redacted."""
        NiquestsInstrumentor().uninstrument()
        NiquestsInstrumentor().instrument()

        request_headers = {
            "Authorization": "Bearer secret-token",
            "X-Api-Key": "secret-key",
        }
        response_headers = {
            "Set-Cookie": "session=abc123",
            "X-Secret": "secret",
        }
        responses.replace(
            responses.GET,
            self.URL,
            body="Hello!",
            headers=response_headers,
        )
        result = niquests.get(self.URL, headers=request_headers, timeout=5)
        self.assertEqual(result.text, "Hello!")

        span = self.assert_span()
        self.assertEqual(
            span.attributes["http.request.header.authorization"],
            ("[REDACTED]",),
        )
        self.assertEqual(
            span.attributes["http.request.header.x_api_key"],
            ("[REDACTED]",),
        )
        self.assertEqual(
            span.attributes["http.response.header.set_cookie"],
            ("[REDACTED]",),
        )
        self.assertEqual(
            span.attributes["http.response.header.x_secret"],
            ("[REDACTED]",),
        )

    @mock.patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_RESPONSE: "X-Custom-Response-.*",
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_REQUEST: "X-Custom-Request-.*",
        },
    )
    def test_custom_headers_with_regex(self):
        """Test that header capture works with regex patterns."""
        NiquestsInstrumentor().uninstrument()
        NiquestsInstrumentor().instrument()
        request_headers = {
            "X-Custom-Request-One": "value-one",
            "X-Custom-Request-Two": "value-two",
            "X-Other-Request-Header": "other-value",
        }
        response_headers = {
            "X-Custom-Response-A": "value-A",
            "X-Custom-Response-B": "value-B",
            "X-Other-Response-Header": "other-value",
        }
        responses.replace(
            responses.GET,
            self.URL,
            body="Hello!",
            headers=response_headers,
        )
        result = niquests.get(self.URL, headers=request_headers, timeout=5)
        self.assertEqual(result.text, "Hello!")

        span = self.assert_span()
        self.assertEqual(
            span.attributes["http.request.header.x_custom_request_one"],
            ("value-one",),
        )
        self.assertEqual(
            span.attributes["http.request.header.x_custom_request_two"],
            ("value-two",),
        )
        self.assertNotIn(
            "http.request.header.x_other_request_header", span.attributes
        )
        self.assertEqual(
            span.attributes["http.response.header.x_custom_response_a"],
            ("value-A",),
        )
        self.assertEqual(
            span.attributes["http.response.header.x_custom_response_b"],
            ("value-B",),
        )
        self.assertNotIn(
            "http.response.header.x_other_response_header", span.attributes
        )

    @mock.patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_RESPONSE: "x-response-header",
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_REQUEST: "x-request-header",
        },
    )
    def test_custom_headers_case_insensitive(self):
        """Test that header capture is case-insensitive."""
        NiquestsInstrumentor().uninstrument()
        NiquestsInstrumentor().instrument()
        request_headers = {"X-ReQuESt-HeaDER": "custom-value"}
        response_headers = {"X-ReSPoNse-HeaDER": "custom-value"}
        responses.replace(
            responses.GET,
            self.URL,
            body="Hello!",
            headers=response_headers,
        )
        result = niquests.get(self.URL, headers=request_headers, timeout=5)
        self.assertEqual(result.text, "Hello!")

        span = self.assert_span()
        self.assertEqual(
            span.attributes["http.request.header.x_request_header"],
            ("custom-value",),
        )
        self.assertEqual(
            span.attributes["http.response.header.x_response_header"],
            ("custom-value",),
        )


class TestNiquestsIntegrationPreparedRequest(
    NiquestsIntegrationTestBase, TestBase
):
    @staticmethod
    def perform_request(url: str, session: niquests.Session = None):
        if session is None:
            session = niquests.Session()
        request = niquests.Request("GET", url)
        prepared_request = session.prepare_request(request)
        return session.send(prepared_request)


class TestNiquestsIntegrationMetric(TestBase):
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
                OTEL_SEMCONV_STABILITY_OPT_IN: sem_conv_mode,
            },
        )
        self.env_patch.start()
        _OpenTelemetrySemanticConventionStability._initialized = False
        NiquestsInstrumentor().instrument(meter_provider=self.meter_provider)

        responses.start()
        responses.add(responses.GET, self.URL, body="Hello!")

    def tearDown(self):
        super().tearDown()
        self.env_patch.stop()
        _OpenTelemetrySemanticConventionStability._initialized = False
        NiquestsInstrumentor().uninstrument()
        responses.stop()
        responses.reset()

    @staticmethod
    def perform_request(url: str) -> niquests.Response:
        return niquests.get(url, timeout=5)

    def test_basic_metric_success(self):
        self.perform_request(self.URL)

        expected_attributes = {
            HTTP_STATUS_CODE: 200,
            HTTP_HOST: "examplehost",
            NET_PEER_PORT: 8000,
            NET_PEER_NAME: "examplehost",
            HTTP_METHOD: "GET",
            HTTP_SCHEME: "http",
        }

        metrics = self.get_sorted_metrics(SCOPE)
        self.assertEqual(len(metrics), 1)
        for metric in metrics:
            self.assertEqual(metric.unit, "ms")
            self.assertEqual(
                metric.description,
                "measures the duration of the outbound HTTP request",
            )
            for data_point in metric.data.data_points:
                self.assertEqual(
                    data_point.explicit_bounds,
                    HTTP_DURATION_HISTOGRAM_BUCKETS_OLD,
                )
                actual = dict(data_point.attributes)
                # responses mock does not provide raw.version
                actual.pop(HTTP_FLAVOR, None)
                self.assertDictEqual(expected_attributes, actual)
                self.assertEqual(data_point.count, 1)

    def test_basic_metric_new_semconv(self):
        self.perform_request(self.URL)

        expected_attributes = {
            HTTP_RESPONSE_STATUS_CODE: 200,
            SERVER_ADDRESS: "examplehost",
            SERVER_PORT: 8000,
            HTTP_REQUEST_METHOD: "GET",
        }
        metrics = self.get_sorted_metrics(SCOPE)
        self.assertEqual(len(metrics), 1)
        for metric in metrics:
            self.assertEqual(metric.unit, "s")
            self.assertEqual(
                metric.description, "Duration of HTTP client requests."
            )
            for data_point in metric.data.data_points:
                self.assertEqual(
                    data_point.explicit_bounds,
                    HTTP_DURATION_HISTOGRAM_BUCKETS_NEW,
                )
                actual = dict(data_point.attributes)
                # responses mock does not provide raw.version
                actual.pop(NETWORK_PROTOCOL_VERSION, None)
                self.assertDictEqual(expected_attributes, actual)
                self.assertEqual(data_point.count, 1)

    def test_basic_metric_both_semconv(self):
        self.perform_request(self.URL)

        expected_attributes_old = {
            HTTP_STATUS_CODE: 200,
            HTTP_HOST: "examplehost",
            NET_PEER_PORT: 8000,
            NET_PEER_NAME: "examplehost",
            HTTP_METHOD: "GET",
            HTTP_SCHEME: "http",
        }

        expected_attributes_new = {
            HTTP_RESPONSE_STATUS_CODE: 200,
            SERVER_ADDRESS: "examplehost",
            SERVER_PORT: 8000,
            HTTP_REQUEST_METHOD: "GET",
        }

        metrics = self.get_sorted_metrics(SCOPE)
        self.assertEqual(len(metrics), 2)
        for metric in metrics:
            for data_point in metric.data.data_points:
                actual = dict(data_point.attributes)
                if metric.unit == "ms":
                    # responses mock does not provide raw.version
                    actual.pop(HTTP_FLAVOR, None)
                    self.assertDictEqual(
                        expected_attributes_old,
                        actual,
                    )
                else:
                    actual.pop(NETWORK_PROTOCOL_VERSION, None)
                    self.assertDictEqual(
                        expected_attributes_new,
                        actual,
                    )
                self.assertEqual(data_point.count, 1)

    def test_custom_histogram_boundaries(self):
        NiquestsInstrumentor().uninstrument()
        custom_boundaries = (0.0, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0)
        meter_provider, memory_reader = self.create_meter_provider()
        NiquestsInstrumentor().instrument(
            meter_provider=meter_provider,
            duration_histogram_boundaries=custom_boundaries,
        )

        self.perform_request(self.URL)
        metrics = memory_reader.get_metrics_data().resource_metrics[0]
        self.assertEqual(len(metrics.scope_metrics), 1)
        data_point = metrics.scope_metrics[0].metrics[0].data.data_points[0]
        self.assertEqual(data_point.explicit_bounds, custom_boundaries)
        self.assertEqual(data_point.count, 1)

    def test_custom_histogram_boundaries_new_semconv(self):
        NiquestsInstrumentor().uninstrument()
        custom_boundaries = (0.0, 5.0, 10.0, 25.0, 50.0, 100.0)
        meter_provider, memory_reader = self.create_meter_provider()
        NiquestsInstrumentor().instrument(
            meter_provider=meter_provider,
            duration_histogram_boundaries=custom_boundaries,
        )

        self.perform_request(self.URL)
        metrics = memory_reader.get_metrics_data().resource_metrics[0]
        self.assertEqual(len(metrics.scope_metrics), 1)
        data_point = metrics.scope_metrics[0].metrics[0].data.data_points[0]
        self.assertEqual(data_point.explicit_bounds, custom_boundaries)
        self.assertEqual(data_point.count, 1)

    def test_basic_metric_non_recording_span(self):
        expected_attributes = {
            HTTP_STATUS_CODE: 200,
            HTTP_HOST: "examplehost",
            NET_PEER_PORT: 8000,
            NET_PEER_NAME: "examplehost",
            HTTP_METHOD: "GET",
            HTTP_SCHEME: "http",
        }

        with mock.patch("opentelemetry.trace.INVALID_SPAN") as mock_span:
            NiquestsInstrumentor().uninstrument()
            NiquestsInstrumentor().instrument(
                tracer_provider=trace.NoOpTracerProvider()
            )
            mock_span.is_recording.return_value = False
            result = self.perform_request(self.URL)
            self.assertEqual(result.text, "Hello!")
            self.assertFalse(mock_span.is_recording())
            self.assertTrue(mock_span.is_recording.called)
            self.assertFalse(mock_span.set_attribute.called)
            self.assertFalse(mock_span.set_status.called)
            metrics = self.get_sorted_metrics(SCOPE)
            self.assertEqual(len(metrics), 1)
            duration_data_point = metrics[0].data.data_points[0]
            actual = dict(duration_data_point.attributes)
            # responses mock does not provide raw.version
            actual.pop(HTTP_FLAVOR, None)
            self.assertDictEqual(expected_attributes, actual)
            self.assertEqual(duration_data_point.count, 1)


class TestNiquestsConnInfoAttributes(TestBase):
    """Tests for niquests-specific span attributes derived from conn_info.

    Uses a custom adapter so we can inject a Response with realistic
    ``conn_info`` fields that the ``responses`` mock library does not provide.
    """

    URL = "http://examplehost:8000/status/200"

    def setUp(self):
        super().setUp()
        self.env_patch = mock.patch.dict(
            "os.environ",
            {
                OTEL_SEMCONV_STABILITY_OPT_IN: "default",
            },
        )
        self.env_patch.start()
        _OpenTelemetrySemanticConventionStability._initialized = False
        NiquestsInstrumentor().instrument()

    def tearDown(self):
        super().tearDown()
        self.env_patch.stop()
        _OpenTelemetrySemanticConventionStability._initialized = False
        NiquestsInstrumentor().uninstrument()

    @staticmethod
    def perform_request(url: str, session: niquests.Session = None):
        if session is None:
            return niquests.get(url, timeout=5)
        return session.get(url)

    def assert_span(self, num_spans=1):
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(num_spans, len(span_list))
        if num_spans == 0:
            return None
        if num_spans == 1:
            return span_list[0]
        return span_list

    @staticmethod
    def _make_response_with_conn_info(ocsp_verified=None, **conn_kwargs):
        """Build a Response with a mocked conn_info.

        The niquests Response.conn_info property delegates to
        ``self.request.conn_info``, and Response.ocsp_verified delegates to
        ``self.request.ocsp_verified``.  We therefore attach these to a
        stub request object.
        """
        response = Response()
        response.status_code = 200
        response.reason = "OK"
        response.raw = TransportMock()

        ci = ConnectionInfo()
        for key, val in conn_kwargs.items():
            setattr(ci, key, val)

        # Attach conn_info and ocsp_verified via a stub request.
        stub_request = type(
            "StubRequest",
            (),
            {
                "conn_info": ci,
                "ocsp_verified": ocsp_verified,
            },
        )()
        response.request = stub_request
        return response

    def test_tls_attributes_on_span(self):
        """tls.protocol.version and tls.cipher are set on the span when
        conn_info has tls_version and cipher."""
        resp = self._make_response_with_conn_info(
            tls_version=ssl.TLSVersion.TLSv1_3,
            cipher="TLS_AES_256_GCM_SHA384",
        )
        session = niquests.Session()
        session.mount(self.URL, MyAdapter(resp))
        self.perform_request(self.URL, session)

        span = self.assert_span()
        self.assertEqual(span.attributes.get("tls.protocol.version"), "1.3")
        self.assertEqual(
            span.attributes.get("tls.cipher"), "TLS_AES_256_GCM_SHA384"
        )

    def test_tls_version_1_2(self):
        """tls.protocol.version is correctly formatted for TLS 1.2."""
        resp = self._make_response_with_conn_info(
            tls_version=ssl.TLSVersion.TLSv1_2,
            cipher="ECDHE-RSA-AES128-GCM-SHA256",
        )
        session = niquests.Session()
        session.mount(self.URL, MyAdapter(resp))
        self.perform_request(self.URL, session)

        span = self.assert_span()
        self.assertEqual(span.attributes.get("tls.protocol.version"), "1.2")

    def test_no_tls_attributes_for_plain_http(self):
        """When conn_info has no TLS fields, no tls.* attributes are set."""
        resp = self._make_response_with_conn_info(
            destination_address=("127.0.0.1", 8000),
        )
        session = niquests.Session()
        session.mount(self.URL, MyAdapter(resp))
        self.perform_request(self.URL, session)

        span = self.assert_span()
        self.assertIsNone(span.attributes.get("tls.protocol.version"))
        self.assertIsNone(span.attributes.get("tls.cipher"))

    def test_revocation_verified_true(self):
        """revocation_verified is set on the span when response.ocsp_verified is True."""
        resp = self._make_response_with_conn_info(ocsp_verified=True)
        session = niquests.Session()
        session.mount(self.URL, MyAdapter(resp))
        self.perform_request(self.URL, session)

        span = self.assert_span()
        self.assertTrue(span.attributes.get("tls.revocation.verified"))

    def test_revocation_verified_false(self):
        """revocation_verified is set on the span when response.ocsp_verified is False."""
        resp = self._make_response_with_conn_info(ocsp_verified=False)
        session = niquests.Session()
        session.mount(self.URL, MyAdapter(resp))
        self.perform_request(self.URL, session)

        span = self.assert_span()
        self.assertFalse(span.attributes.get("tls.revocation.verified"))

    def test_revocation_verified_not_set_when_none(self):
        """revocation_verified is NOT set on the span when response.ocsp_verified is None."""
        resp = self._make_response_with_conn_info(ocsp_verified=None)
        session = niquests.Session()
        session.mount(self.URL, MyAdapter(resp))
        self.perform_request(self.URL, session)

        span = self.assert_span()
        self.assertNotIn("tls.revocation.verified", span.attributes)


class TestNiquestsConnectionMetrics(TestBase):
    """Tests for niquests-specific connection sub-duration histogram metrics.

    Uses ``MyAdapter`` to inject a Response with realistic ``conn_info``
    latency fields, then asserts the histograms are recorded correctly.
    """

    URL = "http://examplehost:8000/status/200"

    def setUp(self):
        super().setUp()
        self.env_patch = mock.patch.dict(
            "os.environ",
            {
                OTEL_SEMCONV_STABILITY_OPT_IN: "http",
            },
        )
        self.env_patch.start()
        _OpenTelemetrySemanticConventionStability._initialized = False
        NiquestsInstrumentor().instrument(meter_provider=self.meter_provider)

    def tearDown(self):
        super().tearDown()
        self.env_patch.stop()
        _OpenTelemetrySemanticConventionStability._initialized = False
        NiquestsInstrumentor().uninstrument()

    @staticmethod
    def perform_request(url: str, session: niquests.Session = None):
        if session is None:
            return niquests.get(url, timeout=5)
        return session.get(url)

    def test_connection_latency_metrics(self):
        """All four connection sub-duration histograms are recorded from conn_info."""
        ci = ConnectionInfo()
        ci.resolution_latency = timedelta(milliseconds=5)
        ci.established_latency = timedelta(milliseconds=10)
        ci.tls_handshake_latency = timedelta(milliseconds=15)
        ci.request_sent_latency = timedelta(milliseconds=2)

        response = Response()
        response.status_code = 200
        response.reason = "OK"
        response.raw = TransportMock()
        response.request = type(
            "StubRequest",
            (),
            {
                "conn_info": ci,
                "ocsp_verified": None,
            },
        )()

        session = niquests.Session()
        session.mount(self.URL, MyAdapter(response))
        self.perform_request(self.URL, session)

        metrics = self.get_sorted_metrics(SCOPE)
        metric_names = {m.name for m in metrics}

        expected_metrics = {
            "http.client.connection.dns.duration",
            "http.client.connection.tcp.duration",
            "http.client.connection.tls.duration",
            "http.client.request.send.duration",
        }
        # The main HTTP duration histogram is also present.
        self.assertTrue(
            expected_metrics.issubset(metric_names),
            f"Missing metrics: {expected_metrics - metric_names}",
        )

        # Verify each connection metric was recorded once with correct value.
        expected_values = {
            "http.client.connection.dns.duration": 0.005,
            "http.client.connection.tcp.duration": 0.010,
            "http.client.connection.tls.duration": 0.015,
            "http.client.request.send.duration": 0.002,
        }
        for metric in metrics:
            if metric.name in expected_values:
                self.assertEqual(metric.unit, "s")
                dp = metric.data.data_points[0]
                self.assertEqual(dp.count, 1)
                self.assertAlmostEqual(
                    dp.sum, expected_values[metric.name], places=6
                )

    def test_connection_metrics_missing_latencies(self):
        """When conn_info latencies are None, no connection metrics are recorded."""
        ci = ConnectionInfo()
        # All latency fields default to None

        response = Response()
        response.status_code = 200
        response.reason = "OK"
        response.raw = TransportMock()
        response.request = type(
            "StubRequest",
            (),
            {
                "conn_info": ci,
                "ocsp_verified": None,
            },
        )()

        session = niquests.Session()
        session.mount(self.URL, MyAdapter(response))
        self.perform_request(self.URL, session)

        metrics = self.get_sorted_metrics(SCOPE)
        conn_metrics = [
            metric
            for metric in metrics
            if metric.name.startswith("http.client.connection.")
            or metric.name == "http.client.request.send.duration"
        ]

        # Connection metrics should exist (histograms are created) but have
        # zero data points since no latencies were available.
        for metric in conn_metrics:
            for dp in metric.data.data_points:
                self.assertEqual(dp.count, 0)

    def test_connection_metrics_zero_latencies_skipped(self):
        """Zero-duration latencies (e.g. DNS on a reused connection) must not
        be recorded so they don't pollute the histogram."""
        ci = ConnectionInfo()
        ci.resolution_latency = timedelta(0)  # no DNS (reused conn)
        ci.established_latency = timedelta(0)  # no TCP (reused conn)
        ci.tls_handshake_latency = timedelta(0)  # no TLS (reused conn)
        ci.request_sent_latency = timedelta(milliseconds=3)  # always > 0

        response = Response()
        response.status_code = 200
        response.reason = "OK"
        response.raw = TransportMock()
        response.request = type(
            "StubRequest",
            (),
            {
                "conn_info": ci,
                "ocsp_verified": None,
            },
        )()

        session = niquests.Session()
        session.mount(self.URL, MyAdapter(response))
        self.perform_request(self.URL, session)

        metrics = self.get_sorted_metrics(SCOPE)
        metrics_by_name = {m.name: m for m in metrics}

        # The three zero-duration phases must NOT have been recorded.
        for name in [
            "http.client.connection.dns.duration",
            "http.client.connection.tcp.duration",
            "http.client.connection.tls.duration",
        ]:
            metric = metrics_by_name.get(name)
            if metric is not None:
                for dp in metric.data.data_points:
                    self.assertEqual(
                        dp.count,
                        0,
                        f"{name} should not record zero-duration latencies",
                    )

        # request_sent_latency was > 0, so it SHOULD have been recorded.
        send_metric = metrics_by_name.get("http.client.request.send.duration")
        self.assertIsNotNone(send_metric)
        dp = send_metric.data.data_points[0]
        self.assertEqual(dp.count, 1)
        self.assertAlmostEqual(dp.sum, 0.003, places=6)

    def test_connection_metrics_no_conn_info(self):
        """When conn_info is None, no connection metrics are recorded."""
        response = Response()
        response.status_code = 200
        response.reason = "OK"
        response.raw = TransportMock()
        # response.request left as None => conn_info returns None

        session = niquests.Session()
        session.mount(self.URL, MyAdapter(response))
        self.perform_request(self.URL, session)
