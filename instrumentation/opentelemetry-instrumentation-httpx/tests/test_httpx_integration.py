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
import asyncio
import typing
from unittest import mock

import httpx
import respx

import opentelemetry.instrumentation.httpx
from opentelemetry import trace
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.httpx import (
    AsyncOpenTelemetryTransport,
    HTTPXClientInstrumentor,
    SyncOpenTelemetryTransport,
)
from opentelemetry.instrumentation.utils import suppress_http_instrumentation
from opentelemetry.propagate import get_global_textmap, set_global_textmap
from opentelemetry.sdk import resources
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
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.mock_textmap import MockTextMapPropagator
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import StatusCode

if typing.TYPE_CHECKING:
    from opentelemetry.instrumentation.httpx import (
        AsyncRequestHook,
        AsyncResponseHook,
        RequestHook,
        RequestInfo,
        ResponseHook,
        ResponseInfo,
    )
    from opentelemetry.sdk.trace.export import SpanExporter
    from opentelemetry.trace import TracerProvider
    from opentelemetry.trace.span import Span


HTTP_RESPONSE_BODY = "http.response.body"


def _is_url_tuple(request: "RequestInfo"):
    """Determine if request url format is for httpx versions < 0.20.0."""
    return isinstance(request[1], tuple) and len(request[1]) == 4


def _async_call(coro: typing.Coroutine) -> asyncio.Task:
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


def _response_hook(span, request: "RequestInfo", response: "ResponseInfo"):
    assert _is_url_tuple(request) or isinstance(request.url, httpx.URL)
    span.set_attribute(
        HTTP_RESPONSE_BODY,
        b"".join(response[2]),
    )


async def _async_response_hook(
    span: "Span", request: "RequestInfo", response: "ResponseInfo"
):
    assert _is_url_tuple(request) or isinstance(request.url, httpx.URL)
    span.set_attribute(
        HTTP_RESPONSE_BODY,
        b"".join([part async for part in response[2]]),
    )


def _request_hook(span: "Span", request: "RequestInfo"):
    assert _is_url_tuple(request) or isinstance(request.url, httpx.URL)
    url = httpx.URL(request[1])
    span.update_name("GET" + str(url))


async def _async_request_hook(span: "Span", request: "RequestInfo"):
    assert _is_url_tuple(request) or isinstance(request.url, httpx.URL)
    url = httpx.URL(request[1])
    span.update_name("GET" + str(url))


def _no_update_request_hook(span: "Span", request: "RequestInfo"):
    return 123


async def _async_no_update_request_hook(span: "Span", request: "RequestInfo"):
    return 123


# pylint: disable=too-many-public-methods


# Using this wrapper class to have a base class for the tests while also not
# angering pylint or mypy when calling methods not in the class when only
# subclassing abc.ABC.
class BaseTestCases:
    class BaseTest(TestBase, metaclass=abc.ABCMeta):
        # pylint: disable=no-member

        URL = "http://mock/status/200"
        response_hook = staticmethod(_response_hook)
        request_hook = staticmethod(_request_hook)
        no_update_request_hook = staticmethod(_no_update_request_hook)

        # TODO: make this more explicit to tests
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
                    OTEL_SEMCONV_STABILITY_OPT_IN: sem_conv_mode,
                },
            )
            self.env_patch.start()
            _OpenTelemetrySemanticConventionStability._initialized = False
            respx.start()
            respx.get(self.URL).mock(
                httpx.Response(
                    200,
                    text="Hello!",
                    extensions={"http_version": b"HTTP/1.1"},
                )
            )

        # pylint: disable=invalid-name
        def tearDown(self):
            super().tearDown()
            self.env_patch.stop()
            respx.stop()

        def assert_span(
            self, exporter: "SpanExporter" = None, num_spans: int = 1
        ):
            if exporter is None:
                exporter = self.memory_exporter
            span_list = exporter.get_finished_spans()
            self.assertEqual(num_spans, len(span_list))
            if num_spans == 0:
                return None
            if num_spans == 1:
                return span_list[0]
            return span_list

        @abc.abstractmethod
        def perform_request(
            self,
            url: str,
            method: str = "GET",
            headers: typing.Dict[str, str] = None,
            client: typing.Union[httpx.Client, httpx.AsyncClient, None] = None,
        ):
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
                span, opentelemetry.instrumentation.httpx
            )

        def test_nonstandard_http_method(self):
            respx.route(method="NONSTANDARD").mock(
                return_value=httpx.Response(405)
            )
            self.perform_request(self.URL, method="NONSTANDARD")
            span = self.assert_span()

            self.assertIs(span.kind, trace.SpanKind.CLIENT)
            self.assertEqual(span.name, "HTTP")
            self.assertEqual(
                span.attributes,
                {
                    SpanAttributes.HTTP_METHOD: "_OTHER",
                    SpanAttributes.HTTP_URL: self.URL,
                    SpanAttributes.HTTP_STATUS_CODE: 405,
                },
            )

            self.assertIs(span.status.status_code, trace.StatusCode.ERROR)

            self.assertEqualSpanInstrumentationInfo(
                span, opentelemetry.instrumentation.httpx
            )

        def test_nonstandard_http_method_new_semconv(self):
            respx.route(method="NONSTANDARD").mock(
                return_value=httpx.Response(405)
            )
            self.perform_request(self.URL, method="NONSTANDARD")
            span = self.assert_span()

            self.assertIs(span.kind, trace.SpanKind.CLIENT)
            self.assertEqual(span.name, "HTTP")
            self.assertEqual(
                span.attributes,
                {
                    HTTP_REQUEST_METHOD: "_OTHER",
                    URL_FULL: self.URL,
                    SERVER_ADDRESS: "mock",
                    NETWORK_PEER_ADDRESS: "mock",
                    HTTP_RESPONSE_STATUS_CODE: 405,
                    NETWORK_PROTOCOL_VERSION: "1.1",
                    ERROR_TYPE: "405",
                    HTTP_REQUEST_METHOD_ORIGINAL: "NONSTANDARD",
                },
            )

            self.assertIs(span.status.status_code, trace.StatusCode.ERROR)

            self.assertEqualSpanInstrumentationInfo(
                span, opentelemetry.instrumentation.httpx
            )

        def test_basic_new_semconv(self):
            url = "http://mock:8080/status/200"
            respx.get(url).mock(
                httpx.Response(
                    200,
                    text="Hello!",
                    extensions={"http_version": b"HTTP/1.1"},
                )
            )
            result = self.perform_request(url)
            self.assertEqual(result.text, "Hello!")
            span = self.assert_span()

            self.assertIs(span.kind, trace.SpanKind.CLIENT)
            self.assertEqual(span.name, "GET")

            self.assertEqual(
                span.instrumentation_scope.schema_url,
                SpanAttributes.SCHEMA_URL,
            )
            self.assertEqual(
                span.attributes,
                {
                    HTTP_REQUEST_METHOD: "GET",
                    URL_FULL: url,
                    SERVER_ADDRESS: "mock",
                    NETWORK_PEER_ADDRESS: "mock",
                    HTTP_RESPONSE_STATUS_CODE: 200,
                    NETWORK_PROTOCOL_VERSION: "1.1",
                    SERVER_PORT: 8080,
                    NETWORK_PEER_PORT: 8080,
                },
            )

            self.assertIs(span.status.status_code, trace.StatusCode.UNSET)

            self.assertEqualSpanInstrumentationInfo(
                span, opentelemetry.instrumentation.httpx
            )

        def test_basic_both_semconv(self):
            url = "http://mock:8080/status/200"  # 8080 because httpx returns None for common ports (http, https, wss)
            respx.get(url).mock(httpx.Response(200, text="Hello!"))
            result = self.perform_request(url)
            self.assertEqual(result.text, "Hello!")
            span = self.assert_span()

            self.assertIs(span.kind, trace.SpanKind.CLIENT)
            self.assertEqual(span.name, "GET")

            self.assertEqual(
                span.instrumentation_scope.schema_url,
                SpanAttributes.SCHEMA_URL,
            )

            self.assertEqual(
                span.attributes,
                {
                    SpanAttributes.HTTP_METHOD: "GET",
                    HTTP_REQUEST_METHOD: "GET",
                    SpanAttributes.HTTP_URL: url,
                    URL_FULL: url,
                    SpanAttributes.HTTP_HOST: "mock",
                    SERVER_ADDRESS: "mock",
                    NETWORK_PEER_ADDRESS: "mock",
                    SpanAttributes.NET_PEER_PORT: 8080,
                    SpanAttributes.HTTP_STATUS_CODE: 200,
                    HTTP_RESPONSE_STATUS_CODE: 200,
                    SpanAttributes.HTTP_FLAVOR: "1.1",
                    NETWORK_PROTOCOL_VERSION: "1.1",
                    SERVER_PORT: 8080,
                    NETWORK_PEER_PORT: 8080,
                },
            )

            self.assertIs(span.status.status_code, trace.StatusCode.UNSET)

            self.assertEqualSpanInstrumentationInfo(
                span, opentelemetry.instrumentation.httpx
            )

        def test_basic_multiple(self):
            self.perform_request(self.URL)
            self.perform_request(self.URL)
            self.assert_span(num_spans=2)

        def test_not_foundbasic(self):
            url_404 = "http://mock/status/404"

            with respx.mock:
                respx.get(url_404).mock(httpx.Response(404))
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

            with respx.mock:
                respx.get(url_404).mock(httpx.Response(404))
                result = self.perform_request(url_404)

            self.assertEqual(result.status_code, 404)
            span = self.assert_span()
            self.assertEqual(
                span.attributes.get(HTTP_RESPONSE_STATUS_CODE), 404
            )
            # new in semconv
            self.assertEqual(span.attributes.get(ERROR_TYPE), "404")

            self.assertIs(
                span.status.status_code,
                trace.StatusCode.ERROR,
            )

        def test_not_foundbasic_both_semconv(self):
            url_404 = "http://mock/status/404"

            with respx.mock:
                respx.get(url_404).mock(httpx.Response(404))
                result = self.perform_request(url_404)

            self.assertEqual(result.status_code, 404)
            span = self.assert_span()
            self.assertEqual(
                span.attributes.get(SpanAttributes.HTTP_STATUS_CODE), 404
            )
            self.assertEqual(
                span.attributes.get(HTTP_RESPONSE_STATUS_CODE), 404
            )
            self.assertEqual(span.attributes.get(ERROR_TYPE), "404")

            self.assertIs(
                span.status.status_code,
                trace.StatusCode.ERROR,
            )

        def test_suppress_instrumentation(self):
            with suppress_http_instrumentation():
                result = self.perform_request(self.URL)
                self.assertEqual(result.text, "Hello!")

            self.assert_span(num_spans=0)

        def test_distributed_context(self):
            previous_propagator = get_global_textmap()
            try:
                set_global_textmap(MockTextMapPropagator())
                result = self.perform_request(self.URL)
                self.assertEqual(result.text, "Hello!")

                span = self.assert_span()

                headers = dict(respx.calls.last.request.headers)
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

        def test_requests_500_error(self):
            respx.get(self.URL).mock(httpx.Response(500))

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

        def test_requests_basic_exception(self):
            with respx.mock, self.assertRaises(Exception):
                respx.get(self.URL).mock(side_effect=Exception)
                self.perform_request(self.URL)

            span = self.assert_span()
            self.assertEqual(span.status.status_code, StatusCode.ERROR)
            self.assertIn("Exception", span.status.description)
            self.assertEqual(
                span.events[0].attributes["exception.type"], "Exception"
            )
            self.assertIsNone(span.attributes.get(ERROR_TYPE))

        def test_requests_basic_exception_new_semconv(self):
            with respx.mock, self.assertRaises(Exception):
                respx.get(self.URL).mock(side_effect=Exception)
                self.perform_request(self.URL)

            span = self.assert_span()
            self.assertEqual(span.status.status_code, StatusCode.ERROR)
            self.assertIn("Exception", span.status.description)
            self.assertEqual(
                span.events[0].attributes["exception.type"], "Exception"
            )
            self.assertEqual(span.attributes.get(ERROR_TYPE), "Exception")

        def test_requests_basic_exception_both_semconv(self):
            with respx.mock, self.assertRaises(Exception):
                respx.get(self.URL).mock(side_effect=Exception)
                self.perform_request(self.URL)

            span = self.assert_span()
            self.assertEqual(span.status.status_code, StatusCode.ERROR)
            self.assertIn("Exception", span.status.description)
            self.assertEqual(
                span.events[0].attributes["exception.type"], "Exception"
            )
            self.assertEqual(span.attributes.get(ERROR_TYPE), "Exception")

        def test_requests_timeout_exception_new_semconv(self):
            url = "http://mock:8080/exception"
            with respx.mock, self.assertRaises(httpx.TimeoutException):
                respx.get(url).mock(side_effect=httpx.TimeoutException)
                self.perform_request(url)

            span = self.assert_span()
            self.assertEqual(
                span.attributes,
                {
                    HTTP_REQUEST_METHOD: "GET",
                    URL_FULL: url,
                    SERVER_ADDRESS: "mock",
                    SERVER_PORT: 8080,
                    NETWORK_PEER_PORT: 8080,
                    NETWORK_PEER_ADDRESS: "mock",
                    ERROR_TYPE: "TimeoutException",
                },
            )
            self.assertEqual(span.status.status_code, StatusCode.ERROR)

        def test_requests_timeout_exception_both_semconv(self):
            url = "http://mock:8080/exception"
            with respx.mock, self.assertRaises(httpx.TimeoutException):
                respx.get(url).mock(side_effect=httpx.TimeoutException)
                self.perform_request(url)

            span = self.assert_span()
            self.assertEqual(
                span.attributes,
                {
                    SpanAttributes.HTTP_METHOD: "GET",
                    HTTP_REQUEST_METHOD: "GET",
                    SpanAttributes.HTTP_URL: url,
                    URL_FULL: url,
                    SpanAttributes.HTTP_HOST: "mock",
                    SERVER_ADDRESS: "mock",
                    NETWORK_PEER_ADDRESS: "mock",
                    SpanAttributes.NET_PEER_PORT: 8080,
                    SERVER_PORT: 8080,
                    NETWORK_PEER_PORT: 8080,
                    ERROR_TYPE: "TimeoutException",
                },
            )
            self.assertEqual(span.status.status_code, StatusCode.ERROR)

        def test_requests_timeout_exception(self):
            with respx.mock, self.assertRaises(httpx.TimeoutException):
                respx.get(self.URL).mock(side_effect=httpx.TimeoutException)
                self.perform_request(self.URL)

            span = self.assert_span()
            self.assertEqual(span.status.status_code, StatusCode.ERROR)

        def test_invalid_url(self):
            url = "invalid://nope/"

            with respx.mock, self.assertRaises(httpx.UnsupportedProtocol):
                respx.post("invalid://nope").pass_through()
                self.perform_request(url, method="POST")

            span = self.assert_span()

            self.assertEqual(span.name, "POST")
            self.assertEqual(
                span.attributes[SpanAttributes.HTTP_METHOD], "POST"
            )
            self.assertEqual(span.attributes[SpanAttributes.HTTP_URL], url)
            self.assertEqual(span.status.status_code, StatusCode.ERROR)

        def test_if_headers_equals_none(self):
            result = self.perform_request(self.URL)
            self.assertEqual(result.text, "Hello!")
            self.assert_span()

    class BaseManualTest(BaseTest, metaclass=abc.ABCMeta):
        @abc.abstractmethod
        def create_transport(
            self,
            tracer_provider: typing.Optional["TracerProvider"] = None,
            request_hook: typing.Optional["RequestHook"] = None,
            response_hook: typing.Optional["ResponseHook"] = None,
            **kwargs,
        ):
            pass

        @abc.abstractmethod
        def create_client(
            self,
            transport: typing.Union[
                SyncOpenTelemetryTransport, AsyncOpenTelemetryTransport, None
            ] = None,
            **kwargs,
        ):
            pass

        def test_default_client(self):
            client = self.create_client(transport=None)
            result = self.perform_request(self.URL, client=client)
            self.assertEqual(result.text, "Hello!")
            self.assert_span(num_spans=0)

            result = self.perform_request(self.URL)
            self.assertEqual(result.text, "Hello!")
            self.assert_span()

        def test_custom_tracer_provider(self):
            resource = resources.Resource.create({})
            result = self.create_tracer_provider(resource=resource)
            tracer_provider, exporter = result

            transport = self.create_transport(tracer_provider=tracer_provider)
            client = self.create_client(transport)
            result = self.perform_request(self.URL, client=client)

            self.assertEqual(result.text, "Hello!")
            span = self.assert_span(exporter=exporter)
            self.assertIs(span.resource, resource)

        def test_response_hook(self):
            transport = self.create_transport(
                tracer_provider=self.tracer_provider,
                response_hook=self.response_hook,
            )
            client = self.create_client(transport)
            result = self.perform_request(self.URL, client=client)

            self.assertEqual(result.text, "Hello!")
            span = self.assert_span()
            self.assertEqual(
                span.attributes,
                {
                    SpanAttributes.HTTP_METHOD: "GET",
                    SpanAttributes.HTTP_URL: self.URL,
                    SpanAttributes.HTTP_STATUS_CODE: 200,
                    HTTP_RESPONSE_BODY: "Hello!",
                },
            )

        def test_request_hook(self):
            transport = self.create_transport(request_hook=self.request_hook)
            client = self.create_client(transport)
            result = self.perform_request(self.URL, client=client)

            self.assertEqual(result.text, "Hello!")
            span = self.assert_span()
            self.assertEqual(span.name, "GET" + self.URL)

        def test_request_hook_no_span_change(self):
            transport = self.create_transport(
                request_hook=self.no_update_request_hook
            )
            client = self.create_client(transport)
            result = self.perform_request(self.URL, client=client)

            self.assertEqual(result.text, "Hello!")
            span = self.assert_span()
            self.assertEqual(span.name, "GET")

        def test_not_recording(self):
            with mock.patch("opentelemetry.trace.INVALID_SPAN") as mock_span:
                transport = self.create_transport(
                    tracer_provider=trace.NoOpTracerProvider()
                )
                client = self.create_client(transport)
                mock_span.is_recording.return_value = False
                result = self.perform_request(self.URL, client=client)

                self.assertEqual(result.text, "Hello!")
                self.assert_span(None, 0)
                self.assertFalse(mock_span.is_recording())
                self.assertTrue(mock_span.is_recording.called)
                self.assertFalse(mock_span.set_attribute.called)
                self.assertFalse(mock_span.set_status.called)

        @respx.mock
        def test_not_recording_not_set_attribute_in_exception_new_semconv(
            self,
        ):
            respx.get(self.URL).mock(side_effect=httpx.TimeoutException)
            with mock.patch("opentelemetry.trace.INVALID_SPAN") as mock_span:
                transport = self.create_transport(
                    tracer_provider=trace.NoOpTracerProvider()
                )
                client = self.create_client(transport)
                mock_span.is_recording.return_value = False
                try:
                    self.perform_request(self.URL, client=client)
                except httpx.TimeoutException:
                    pass

                self.assert_span(None, 0)
                self.assertFalse(mock_span.is_recording())
                self.assertTrue(mock_span.is_recording.called)
                self.assertFalse(mock_span.set_attribute.called)
                self.assertFalse(mock_span.set_status.called)

        @respx.mock
        def test_client_mounts_with_instrumented_transport(self):
            https_url = "https://mock/status/200"
            respx.get(https_url).mock(httpx.Response(200))
            proxy_mounts = {
                "http://": self.create_transport(
                    proxy=httpx.Proxy("http://localhost:8080")
                ),
                "https://": self.create_transport(
                    proxy=httpx.Proxy("http://localhost:8443")
                ),
            }
            client1 = self.create_client(mounts=proxy_mounts)
            client2 = self.create_client(mounts=proxy_mounts)
            self.perform_request(self.URL, client=client1)
            self.perform_request(https_url, client=client2)
            spans = self.assert_span(num_spans=2)
            self.assertEqual(
                spans[0].attributes[SpanAttributes.HTTP_URL], self.URL
            )
            self.assertEqual(
                spans[1].attributes[SpanAttributes.HTTP_URL], https_url
            )

    @mock.patch.dict("os.environ", {"NO_PROXY": ""}, clear=True)
    class BaseInstrumentorTest(BaseTest, metaclass=abc.ABCMeta):
        @abc.abstractmethod
        def create_client(
            self,
            transport: typing.Union[
                SyncOpenTelemetryTransport, AsyncOpenTelemetryTransport, None
            ] = None,
            **kwargs,
        ):
            pass

        @abc.abstractmethod
        def create_proxy_transport(self, url: str):
            pass

        def setUp(self):
            super().setUp()
            HTTPXClientInstrumentor().instrument()
            self.client = self.create_client()
            HTTPXClientInstrumentor().uninstrument()

        def create_proxy_mounts(self):
            return {
                "http://": self.create_proxy_transport(
                    "http://localhost:8080"
                ),
                "https://": self.create_proxy_transport(
                    "http://localhost:8080"
                ),
            }

        def assert_proxy_mounts(self, mounts, num_mounts, transport_type):
            self.assertEqual(len(mounts), num_mounts)
            for transport in mounts:
                with self.subTest(transport):
                    self.assertIsInstance(
                        transport,
                        transport_type,
                    )

        def test_custom_tracer_provider(self):
            resource = resources.Resource.create({})
            result = self.create_tracer_provider(resource=resource)
            tracer_provider, exporter = result

            HTTPXClientInstrumentor().instrument(
                tracer_provider=tracer_provider
            )
            client = self.create_client()
            result = self.perform_request(self.URL, client=client)

            self.assertEqual(result.text, "Hello!")
            span = self.assert_span(exporter=exporter)
            self.assertIs(span.resource, resource)
            HTTPXClientInstrumentor().uninstrument()

        def test_response_hook(self):
            response_hook_key = (
                "async_response_hook"
                if asyncio.iscoroutinefunction(self.response_hook)
                else "response_hook"
            )
            response_hook_kwargs = {response_hook_key: self.response_hook}
            HTTPXClientInstrumentor().instrument(
                tracer_provider=self.tracer_provider,
                **response_hook_kwargs,
            )
            client = self.create_client()
            result = self.perform_request(self.URL, client=client)

            self.assertEqual(result.text, "Hello!")
            span = self.assert_span()
            self.assertEqual(
                span.attributes,
                {
                    SpanAttributes.HTTP_METHOD: "GET",
                    SpanAttributes.HTTP_URL: self.URL,
                    SpanAttributes.HTTP_STATUS_CODE: 200,
                    HTTP_RESPONSE_BODY: "Hello!",
                },
            )
            HTTPXClientInstrumentor().uninstrument()

        def test_response_hook_sync_async_kwargs(self):
            HTTPXClientInstrumentor().instrument(
                tracer_provider=self.tracer_provider,
                response_hook=_response_hook,
                async_response_hook=_async_response_hook,
            )
            client = self.create_client()
            result = self.perform_request(self.URL, client=client)

            self.assertEqual(result.text, "Hello!")
            span = self.assert_span()
            self.assertEqual(
                span.attributes,
                {
                    SpanAttributes.HTTP_METHOD: "GET",
                    SpanAttributes.HTTP_URL: self.URL,
                    SpanAttributes.HTTP_STATUS_CODE: 200,
                    HTTP_RESPONSE_BODY: "Hello!",
                },
            )
            HTTPXClientInstrumentor().uninstrument()

        def test_request_hook(self):
            request_hook_key = (
                "async_request_hook"
                if asyncio.iscoroutinefunction(self.request_hook)
                else "request_hook"
            )
            request_hook_kwargs = {request_hook_key: self.request_hook}
            HTTPXClientInstrumentor().instrument(
                tracer_provider=self.tracer_provider,
                **request_hook_kwargs,
            )
            client = self.create_client()
            result = self.perform_request(self.URL, client=client)

            self.assertEqual(result.text, "Hello!")
            span = self.assert_span()
            self.assertEqual(span.name, "GET" + self.URL)
            HTTPXClientInstrumentor().uninstrument()

        def test_request_hook_sync_async_kwargs(self):
            HTTPXClientInstrumentor().instrument(
                tracer_provider=self.tracer_provider,
                request_hook=_request_hook,
                async_request_hook=_async_request_hook,
            )
            client = self.create_client()
            result = self.perform_request(self.URL, client=client)

            self.assertEqual(result.text, "Hello!")
            span = self.assert_span()
            self.assertEqual(span.name, "GET" + self.URL)
            HTTPXClientInstrumentor().uninstrument()

        def test_request_hook_no_span_update(self):
            HTTPXClientInstrumentor().instrument(
                tracer_provider=self.tracer_provider,
                request_hook=self.no_update_request_hook,
            )
            client = self.create_client()
            result = self.perform_request(self.URL, client=client)

            self.assertEqual(result.text, "Hello!")
            span = self.assert_span()
            self.assertEqual(span.name, "GET")
            HTTPXClientInstrumentor().uninstrument()

        def test_not_recording(self):
            with mock.patch("opentelemetry.trace.INVALID_SPAN") as mock_span:
                HTTPXClientInstrumentor().instrument(
                    tracer_provider=trace.NoOpTracerProvider()
                )
                client = self.create_client()

                mock_span.is_recording.return_value = False
                result = self.perform_request(self.URL, client=client)

                self.assertEqual(result.text, "Hello!")
                self.assert_span(None, 0)
                self.assertFalse(mock_span.is_recording())
                self.assertTrue(mock_span.is_recording.called)
                self.assertFalse(mock_span.set_attribute.called)
                self.assertFalse(mock_span.set_status.called)
                HTTPXClientInstrumentor().uninstrument()

        def test_suppress_instrumentation_new_client(self):
            HTTPXClientInstrumentor().instrument()
            with suppress_http_instrumentation():
                client = self.create_client()
                result = self.perform_request(self.URL, client=client)
                self.assertEqual(result.text, "Hello!")

            self.assert_span(num_spans=0)
            HTTPXClientInstrumentor().uninstrument()

        def test_instrument_client(self):
            client = self.create_client()
            HTTPXClientInstrumentor().instrument_client(client)
            result = self.perform_request(self.URL, client=client)
            self.assertEqual(result.text, "Hello!")
            self.assert_span(num_spans=1)

        def test_instrumentation_without_client(self):

            HTTPXClientInstrumentor().instrument()
            results = [
                httpx.get(self.URL),
                httpx.request("GET", self.URL),
            ]
            with httpx.stream("GET", self.URL) as stream:
                stream.read()
                results.append(stream)

            spans = self.assert_span(num_spans=len(results))
            for idx, res in enumerate(results):
                with self.subTest(idx=idx, res=res):
                    self.assertEqual(res.text, "Hello!")
                    self.assertEqual(
                        spans[idx].attributes[SpanAttributes.HTTP_URL],
                        self.URL,
                    )

            HTTPXClientInstrumentor().uninstrument()

        def test_uninstrument(self):
            HTTPXClientInstrumentor().instrument()
            HTTPXClientInstrumentor().uninstrument()
            client = self.create_client()
            result = self.perform_request(self.URL, client=client)
            result_no_client = httpx.get(self.URL)
            self.assertEqual(result.text, "Hello!")
            self.assertEqual(result_no_client.text, "Hello!")
            self.assert_span(num_spans=0)

        def test_uninstrument_client(self):
            HTTPXClientInstrumentor().uninstrument_client(self.client)

            result = self.perform_request(self.URL)

            self.assertEqual(result.text, "Hello!")
            self.assert_span(num_spans=0)

        def test_uninstrument_new_client(self):
            HTTPXClientInstrumentor().instrument()
            client1 = self.create_client()
            HTTPXClientInstrumentor().uninstrument_client(client1)

            result = self.perform_request(self.URL, client=client1)
            self.assertEqual(result.text, "Hello!")
            self.assert_span(num_spans=0)

            # Test that other clients as well as instance client is still
            # instrumented
            client2 = self.create_client()
            result = self.perform_request(self.URL, client=client2)
            self.assertEqual(result.text, "Hello!")
            self.assert_span()

            self.memory_exporter.clear()

            result = self.perform_request(self.URL)
            self.assertEqual(result.text, "Hello!")
            self.assert_span()

        def test_instrument_proxy(self):
            proxy_mounts = self.create_proxy_mounts()
            HTTPXClientInstrumentor().instrument()
            client = self.create_client(mounts=proxy_mounts)
            self.perform_request(self.URL, client=client)
            self.assert_span(num_spans=1)
            self.assert_proxy_mounts(
                client._mounts.values(),
                2,
                (SyncOpenTelemetryTransport, AsyncOpenTelemetryTransport),
            )
            HTTPXClientInstrumentor().uninstrument()

        def test_instrument_client_with_proxy(self):
            proxy_mounts = self.create_proxy_mounts()
            client = self.create_client(mounts=proxy_mounts)
            self.assert_proxy_mounts(
                client._mounts.values(),
                2,
                (httpx.HTTPTransport, httpx.AsyncHTTPTransport),
            )
            HTTPXClientInstrumentor().instrument_client(client)
            result = self.perform_request(self.URL, client=client)
            self.assertEqual(result.text, "Hello!")
            self.assert_span(num_spans=1)
            self.assert_proxy_mounts(
                client._mounts.values(),
                2,
                (SyncOpenTelemetryTransport, AsyncOpenTelemetryTransport),
            )
            HTTPXClientInstrumentor().uninstrument_client(client)

        def test_uninstrument_client_with_proxy(self):
            proxy_mounts = self.create_proxy_mounts()
            HTTPXClientInstrumentor().instrument()
            client = self.create_client(mounts=proxy_mounts)
            self.assert_proxy_mounts(
                client._mounts.values(),
                2,
                (SyncOpenTelemetryTransport, AsyncOpenTelemetryTransport),
            )

            HTTPXClientInstrumentor().uninstrument_client(client)
            result = self.perform_request(self.URL, client=client)

            self.assertEqual(result.text, "Hello!")
            self.assert_span(num_spans=0)
            self.assert_proxy_mounts(
                client._mounts.values(),
                2,
                (httpx.HTTPTransport, httpx.AsyncHTTPTransport),
            )
            # Test that other clients as well as instance client is still
            # instrumented
            client2 = self.create_client()
            result = self.perform_request(self.URL, client=client2)
            self.assertEqual(result.text, "Hello!")
            self.assert_span()

            self.memory_exporter.clear()

            result = self.perform_request(self.URL)
            self.assertEqual(result.text, "Hello!")
            self.assert_span()


class TestSyncIntegration(BaseTestCases.BaseManualTest):
    def setUp(self):
        super().setUp()
        self.transport = self.create_transport()
        self.client = self.create_client(self.transport)

    def tearDown(self):
        super().tearDown()
        self.client.close()

    def create_transport(
        self,
        tracer_provider: typing.Optional["TracerProvider"] = None,
        request_hook: typing.Optional["RequestHook"] = None,
        response_hook: typing.Optional["ResponseHook"] = None,
        **kwargs,
    ):
        transport = httpx.HTTPTransport(**kwargs)
        telemetry_transport = SyncOpenTelemetryTransport(
            transport,
            tracer_provider=tracer_provider,
            request_hook=request_hook,
            response_hook=response_hook,
        )
        return telemetry_transport

    def create_client(
        self,
        transport: typing.Optional[SyncOpenTelemetryTransport] = None,
        **kwargs,
    ):
        return httpx.Client(transport=transport, **kwargs)

    def perform_request(
        self,
        url: str,
        method: str = "GET",
        headers: typing.Dict[str, str] = None,
        client: typing.Union[httpx.Client, httpx.AsyncClient, None] = None,
    ):
        if client is None:
            return self.client.request(method, url, headers=headers)
        return client.request(method, url, headers=headers)

    def test_credential_removal(self):
        new_url = "http://username:password@mock/status/200"
        self.perform_request(new_url)
        span = self.assert_span()

        self.assertEqual(span.attributes[SpanAttributes.HTTP_URL], self.URL)


class TestAsyncIntegration(BaseTestCases.BaseManualTest):
    response_hook = staticmethod(_async_response_hook)
    request_hook = staticmethod(_async_request_hook)
    no_update_request_hook = staticmethod(_async_no_update_request_hook)

    def setUp(self):
        super().setUp()
        self.transport = self.create_transport()
        self.client = self.create_client(self.transport)

    def create_transport(
        self,
        tracer_provider: typing.Optional["TracerProvider"] = None,
        request_hook: typing.Optional["AsyncRequestHook"] = None,
        response_hook: typing.Optional["AsyncResponseHook"] = None,
        **kwargs,
    ):
        transport = httpx.AsyncHTTPTransport(**kwargs)
        telemetry_transport = AsyncOpenTelemetryTransport(
            transport,
            tracer_provider=tracer_provider,
            request_hook=request_hook,
            response_hook=response_hook,
        )
        return telemetry_transport

    def create_client(
        self,
        transport: typing.Optional[AsyncOpenTelemetryTransport] = None,
        **kwargs,
    ):
        return httpx.AsyncClient(transport=transport, **kwargs)

    def perform_request(
        self,
        url: str,
        method: str = "GET",
        headers: typing.Dict[str, str] = None,
        client: typing.Union[httpx.Client, httpx.AsyncClient, None] = None,
    ):
        async def _perform_request():
            nonlocal client
            nonlocal method
            if client is None:
                client = self.client
            async with client as _client:
                return await _client.request(method, url, headers=headers)

        return _async_call(_perform_request())

    def test_basic_multiple(self):
        # We need to create separate clients because in httpx >= 0.19,
        # closing the client after "with" means the second http call fails
        self.perform_request(
            self.URL, client=self.create_client(self.transport)
        )
        self.perform_request(
            self.URL, client=self.create_client(self.transport)
        )
        self.assert_span(num_spans=2)

    def test_credential_removal(self):
        new_url = "http://username:password@mock/status/200"
        self.perform_request(new_url)
        span = self.assert_span()

        self.assertEqual(span.attributes[SpanAttributes.HTTP_URL], self.URL)


class TestSyncInstrumentationIntegration(BaseTestCases.BaseInstrumentorTest):
    def create_client(
        self,
        transport: typing.Optional[SyncOpenTelemetryTransport] = None,
        **kwargs,
    ):
        return httpx.Client(**kwargs)

    def perform_request(
        self,
        url: str,
        method: str = "GET",
        headers: typing.Dict[str, str] = None,
        client: typing.Union[httpx.Client, httpx.AsyncClient, None] = None,
    ):
        if client is None:
            return self.client.request(method, url, headers=headers)
        return client.request(method, url, headers=headers)

    def create_proxy_transport(self, url):
        return httpx.HTTPTransport(proxy=httpx.Proxy(url))


class TestAsyncInstrumentationIntegration(BaseTestCases.BaseInstrumentorTest):
    response_hook = staticmethod(_async_response_hook)
    request_hook = staticmethod(_async_request_hook)
    no_update_request_hook = staticmethod(_async_no_update_request_hook)

    def setUp(self):
        super().setUp()
        HTTPXClientInstrumentor().instrument()
        self.client = self.create_client()
        self.client2 = self.create_client()
        HTTPXClientInstrumentor().uninstrument()

    def create_client(
        self,
        transport: typing.Optional[AsyncOpenTelemetryTransport] = None,
        **kwargs,
    ):
        return httpx.AsyncClient(**kwargs)

    def perform_request(
        self,
        url: str,
        method: str = "GET",
        headers: typing.Dict[str, str] = None,
        client: typing.Union[httpx.Client, httpx.AsyncClient, None] = None,
    ):
        async def _perform_request():
            nonlocal client
            nonlocal method
            if client is None:
                client = self.client
            async with client as _client:
                return await _client.request(method, url, headers=headers)

        return _async_call(_perform_request())

    def create_proxy_transport(self, url):
        return httpx.AsyncHTTPTransport(proxy=httpx.Proxy(url))

    def test_basic_multiple(self):
        # We need to create separate clients because in httpx >= 0.19,
        # closing the client after "with" means the second http call fails
        self.perform_request(self.URL, client=self.client)
        self.perform_request(self.URL, client=self.client2)
        self.assert_span(num_spans=2)

    def test_async_response_hook_does_nothing_if_not_coroutine(self):
        HTTPXClientInstrumentor().instrument(
            tracer_provider=self.tracer_provider,
            async_response_hook=_response_hook,
        )
        client = self.create_client()
        result = self.perform_request(self.URL, client=client)

        self.assertEqual(result.text, "Hello!")
        span = self.assert_span()
        self.assertEqual(
            dict(span.attributes),
            {
                SpanAttributes.HTTP_METHOD: "GET",
                SpanAttributes.HTTP_URL: self.URL,
                SpanAttributes.HTTP_STATUS_CODE: 200,
            },
        )
        HTTPXClientInstrumentor().uninstrument()

    def test_async_request_hook_does_nothing_if_not_coroutine(self):
        HTTPXClientInstrumentor().instrument(
            tracer_provider=self.tracer_provider,
            async_request_hook=_request_hook,
        )
        client = self.create_client()
        result = self.perform_request(self.URL, client=client)

        self.assertEqual(result.text, "Hello!")
        span = self.assert_span()
        self.assertEqual(span.name, "GET")
        HTTPXClientInstrumentor().uninstrument()
