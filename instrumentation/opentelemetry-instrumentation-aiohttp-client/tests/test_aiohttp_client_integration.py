# Copyright 2020, OpenTelemetry Authors
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

import asyncio
import contextlib
import typing
import unittest
import urllib.parse
from http import HTTPStatus
from unittest import mock

import aiohttp
import aiohttp.test_utils
import yarl
from http_server_mock import HttpServerMock

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation import aiohttp_client
from opentelemetry.instrumentation._semconv import (
    HTTP_DURATION_HISTOGRAM_BUCKETS_NEW,
    HTTP_DURATION_HISTOGRAM_BUCKETS_OLD,
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
    _StabilityMode,
)
from opentelemetry.instrumentation.aiohttp_client import (
    AioHttpClientInstrumentor,
)
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.semconv._incubating.attributes.http_attributes import (
    HTTP_HOST,
    HTTP_METHOD,
    HTTP_STATUS_CODE,
    HTTP_URL,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_PEER_NAME,
    NET_PEER_PORT,
)
from opentelemetry.semconv._incubating.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.semconv.attributes.http_attributes import (
    HTTP_REQUEST_METHOD,
    HTTP_REQUEST_METHOD_ORIGINAL,
    HTTP_RESPONSE_STATUS_CODE,
)
from opentelemetry.semconv.attributes.url_attributes import URL_FULL
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import Span, StatusCode
from opentelemetry.util._importlib_metadata import entry_points


def run_with_test_server(
    runnable: typing.Callable, url: str, handler: typing.Callable
) -> typing.Tuple[str, int]:
    async def do_request():
        app = aiohttp.web.Application()
        parsed_url = urllib.parse.urlparse(url)
        app.add_routes([aiohttp.web.get(parsed_url.path, handler)])
        app.add_routes([aiohttp.web.post(parsed_url.path, handler)])
        app.add_routes([aiohttp.web.patch(parsed_url.path, handler)])

        with contextlib.suppress(aiohttp.ClientError):
            async with aiohttp.test_utils.TestServer(app) as server:
                netloc = (server.host, server.port)
                await server.start_server()
                await runnable(server)
        return netloc

    loop = asyncio.get_event_loop()
    return loop.run_until_complete(do_request())


class TestAioHttpIntegration(TestBase):
    _test_status_codes = (
        (HTTPStatus.OK, StatusCode.UNSET),
        (HTTPStatus.TEMPORARY_REDIRECT, StatusCode.UNSET),
        (HTTPStatus.NOT_FOUND, StatusCode.ERROR),
        (HTTPStatus.BAD_REQUEST, StatusCode.ERROR),
        (HTTPStatus.SERVICE_UNAVAILABLE, StatusCode.ERROR),
        (HTTPStatus.GATEWAY_TIMEOUT, StatusCode.ERROR),
    )

    def setUp(self):
        super().setUp()
        _OpenTelemetrySemanticConventionStability._initialized = False

    def _assert_spans(self, spans, num_spans=1):
        finished_spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(num_spans, len(finished_spans))
        self.assertEqual(
            [
                (
                    span.name,
                    (span.status.status_code, span.status.description),
                    dict(span.attributes),
                )
                for span in finished_spans
            ],
            spans,
        )

    def _assert_metrics(self, num_metrics: int = 1):
        metrics = self.get_sorted_metrics()
        self.assertEqual(len(metrics), num_metrics)
        return metrics

    @staticmethod
    def _http_request(
        trace_config,
        url: str,
        method: str = "GET",
        status_code: int = HTTPStatus.OK,
        request_handler: typing.Callable = None,
        **kwargs,
    ) -> typing.Tuple[str, int]:
        """Helper to start an aiohttp test server and send an actual HTTP request to it."""

        async def default_handler(request):
            assert "traceparent" in request.headers
            return aiohttp.web.Response(status=int(status_code))

        async def client_request(server: aiohttp.test_utils.TestServer):
            async with aiohttp.test_utils.TestClient(
                server, trace_configs=[trace_config]
            ) as client:
                await client.request(
                    method, url, trace_request_ctx={}, **kwargs
                )

        handler = request_handler or default_handler
        return run_with_test_server(client_request, url, handler)

    def test_status_codes(self):
        index = 0
        for status_code, span_status in self._test_status_codes:
            with self.subTest(status_code=status_code):
                path = "test-path?query=param#foobar"
                host, port = self._http_request(
                    trace_config=aiohttp_client.create_trace_config(),
                    url=f"/{path}",
                    status_code=status_code,
                )
                url = f"http://{host}:{port}/{path}"
                attributes = {
                    HTTP_METHOD: "GET",
                    HTTP_URL: url,
                    HTTP_STATUS_CODE: status_code,
                }

                spans = [("GET", (span_status, None), attributes)]
                self._assert_spans(spans)
                self.memory_exporter.clear()
                metrics = self._assert_metrics(1)
                duration_data_point = metrics[0].data.data_points[index]
                self.assertEqual(
                    dict(duration_data_point.attributes),
                    {
                        HTTP_STATUS_CODE: status_code,
                        HTTP_METHOD: "GET",
                        HTTP_HOST: host,
                        NET_PEER_NAME: host,
                        NET_PEER_PORT: port,
                    },
                )
                self.assertEqual(
                    duration_data_point.explicit_bounds,
                    HTTP_DURATION_HISTOGRAM_BUCKETS_OLD,
                )
                index += 1

    def test_status_codes_new_semconv(self):
        index = 0
        for status_code, span_status in self._test_status_codes:
            with self.subTest(status_code=status_code):
                path = "test-path?query=param#foobar"
                host, port = self._http_request(
                    trace_config=aiohttp_client.create_trace_config(
                        sem_conv_opt_in_mode=_StabilityMode.HTTP
                    ),
                    url=f"/{path}",
                    status_code=status_code,
                )
                url = f"http://{host}:{port}/{path}"
                attributes = {
                    HTTP_REQUEST_METHOD: "GET",
                    URL_FULL: url,
                    HTTP_RESPONSE_STATUS_CODE: status_code,
                    SERVER_ADDRESS: host,
                    SERVER_PORT: port,
                }
                if status_code >= 400:
                    attributes[ERROR_TYPE] = str(status_code.value)
                spans = [("GET", (span_status, None), attributes)]
                self._assert_spans(spans)
                self.memory_exporter.clear()
                metrics = self._assert_metrics(1)
                duration_data_point = metrics[0].data.data_points[index]
                self.assertEqual(
                    duration_data_point.attributes.get(
                        HTTP_RESPONSE_STATUS_CODE
                    ),
                    status_code,
                )
                self.assertEqual(
                    duration_data_point.attributes.get(HTTP_REQUEST_METHOD),
                    "GET",
                )
                if status_code >= 400:
                    self.assertEqual(
                        duration_data_point.attributes.get(ERROR_TYPE),
                        str(status_code.value),
                    )
                self.assertEqual(
                    duration_data_point.explicit_bounds,
                    HTTP_DURATION_HISTOGRAM_BUCKETS_NEW,
                )
                index += 1

    def test_status_codes_both_semconv(self):
        index = 0
        for status_code, span_status in self._test_status_codes:
            with self.subTest(status_code=status_code):
                path = "test-path?query=param#foobar"
                host, port = self._http_request(
                    trace_config=aiohttp_client.create_trace_config(
                        sem_conv_opt_in_mode=_StabilityMode.HTTP_DUP
                    ),
                    url=f"/{path}",
                    status_code=status_code,
                )
                url = f"http://{host}:{port}/{path}"
                attributes = {
                    HTTP_REQUEST_METHOD: "GET",
                    HTTP_METHOD: "GET",
                    HTTP_HOST: host,
                    URL_FULL: url,
                    HTTP_URL: url,
                    HTTP_RESPONSE_STATUS_CODE: status_code,
                    HTTP_STATUS_CODE: status_code,
                    SERVER_ADDRESS: host,
                    SERVER_PORT: port,
                    NET_PEER_PORT: port,
                }

                if status_code >= 400:
                    attributes[ERROR_TYPE] = str(status_code.value)

                spans = [("GET", (span_status, None), attributes)]
                self._assert_spans(spans, 1)
                self.memory_exporter.clear()
                metrics = self._assert_metrics(2)
                duration_data_point = metrics[0].data.data_points[index]
                self.assertEqual(
                    duration_data_point.attributes.get(HTTP_STATUS_CODE),
                    status_code,
                )
                self.assertEqual(
                    duration_data_point.attributes.get(HTTP_METHOD),
                    "GET",
                )
                self.assertEqual(
                    duration_data_point.attributes.get(ERROR_TYPE),
                    None,
                )
                duration_data_point = metrics[1].data.data_points[index]
                self.assertEqual(
                    duration_data_point.attributes.get(
                        HTTP_RESPONSE_STATUS_CODE
                    ),
                    status_code,
                )
                self.assertEqual(
                    duration_data_point.attributes.get(HTTP_REQUEST_METHOD),
                    "GET",
                )
                if status_code >= 400:
                    self.assertEqual(
                        duration_data_point.attributes.get(ERROR_TYPE),
                        str(status_code.value),
                    )
                index += 1

    def test_metrics(self):
        with self.subTest(status_code=200):
            host, port = self._http_request(
                trace_config=aiohttp_client.create_trace_config(),
                url="/test-path?query=param#foobar",
                status_code=200,
            )
            metrics = self._assert_metrics(1)
            self.assertEqual(len(metrics[0].data.data_points), 1)
            duration_data_point = metrics[0].data.data_points[0]
            self.assertEqual(
                dict(metrics[0].data.data_points[0].attributes),
                {
                    HTTP_STATUS_CODE: 200,
                    HTTP_METHOD: "GET",
                    HTTP_HOST: host,
                    NET_PEER_NAME: host,
                    NET_PEER_PORT: port,
                },
            )
            self.assertEqual(duration_data_point.count, 1)
            self.assertTrue(duration_data_point.min > 0)
            self.assertTrue(duration_data_point.max > 0)
            self.assertTrue(duration_data_point.sum > 0)

    def test_schema_url(self):
        with self.subTest(status_code=200):
            self._http_request(
                trace_config=aiohttp_client.create_trace_config(),
                url="/test-path?query=param#foobar",
                status_code=200,
            )

            span = self.memory_exporter.get_finished_spans()[0]
            self.assertEqual(
                span.instrumentation_info.schema_url,
                "https://opentelemetry.io/schemas/1.11.0",
            )
            self.memory_exporter.clear()

    def test_schema_url_new_semconv(self):
        with self.subTest(status_code=200):
            self._http_request(
                trace_config=aiohttp_client.create_trace_config(
                    sem_conv_opt_in_mode=_StabilityMode.HTTP
                ),
                url="/test-path?query=param#foobar",
                status_code=200,
            )

            span = self.memory_exporter.get_finished_spans()[0]
            self.assertEqual(
                span.instrumentation_info.schema_url,
                "https://opentelemetry.io/schemas/1.21.0",
            )
            self.memory_exporter.clear()

    def test_schema_url_both_semconv(self):
        with self.subTest(status_code=200):
            self._http_request(
                trace_config=aiohttp_client.create_trace_config(
                    sem_conv_opt_in_mode=_StabilityMode.HTTP_DUP
                ),
                url="/test-path?query=param#foobar",
                status_code=200,
            )

            span = self.memory_exporter.get_finished_spans()[0]
            self.assertEqual(
                span.instrumentation_info.schema_url,
                "https://opentelemetry.io/schemas/1.21.0",
            )
            self.memory_exporter.clear()

    def test_not_recording(self):
        mock_tracer = mock.Mock()
        mock_span = mock.Mock()
        mock_span.is_recording.return_value = False
        mock_tracer.start_span.return_value = mock_span
        with mock.patch("opentelemetry.trace.get_tracer"):
            # pylint: disable=W0612
            self._http_request(
                trace_config=aiohttp_client.create_trace_config(),
                url="/test-path?query=param#foobar",
            )
            self.assertFalse(mock_span.is_recording())
            self.assertTrue(mock_span.is_recording.called)
            self.assertFalse(mock_span.set_attribute.called)
            self.assertFalse(mock_span.set_status.called)

    def test_hooks(self):
        method = "PATCH"
        path = "/some/path"
        expected = "PATCH - /some/path"

        def request_hook(span: Span, params: aiohttp.TraceRequestStartParams):
            span.update_name(f"{params.method} - {params.url.path}")

        def response_hook(
            span: Span,
            params: typing.Union[
                aiohttp.TraceRequestEndParams,
                aiohttp.TraceRequestExceptionParams,
            ],
        ):
            span.set_attribute("response_hook_attr", "value")

        host, port = self._http_request(
            trace_config=aiohttp_client.create_trace_config(
                request_hook=request_hook,
                response_hook=response_hook,
            ),
            method=method,
            url=path,
            status_code=HTTPStatus.OK,
        )

        for span in self.memory_exporter.get_finished_spans():
            self.assertEqual(span.name, expected)
            self.assertEqual(
                (span.status.status_code, span.status.description),
                (StatusCode.UNSET, None),
            )
            self.assertEqual(span.attributes[HTTP_METHOD], method)
            self.assertEqual(
                span.attributes[HTTP_URL],
                f"http://{host}:{port}{path}",
            )
            self.assertEqual(span.attributes[HTTP_STATUS_CODE], HTTPStatus.OK)
            self.assertIn("response_hook_attr", span.attributes)
            self.assertEqual(span.attributes["response_hook_attr"], "value")
        self.memory_exporter.clear()

    def test_url_filter_option(self):
        # Strips all query params from URL before adding as a span attribute.
        def strip_query_params(url: yarl.URL) -> str:
            return str(url.with_query(None))

        host, port = self._http_request(
            trace_config=aiohttp_client.create_trace_config(
                url_filter=strip_query_params
            ),
            url="/some/path?query=param&other=param2",
            status_code=HTTPStatus.OK,
        )

        self._assert_spans(
            [
                (
                    "GET",
                    (StatusCode.UNSET, None),
                    {
                        HTTP_METHOD: "GET",
                        HTTP_URL: f"http://{host}:{port}/some/path",
                        HTTP_STATUS_CODE: int(HTTPStatus.OK),
                    },
                )
            ]
        )

    def test_connection_errors(self):
        trace_configs = [aiohttp_client.create_trace_config()]

        for url, expected_status in (
            ("http://this-is-unknown.local/", StatusCode.ERROR),
            ("http://127.0.0.1:1/", StatusCode.ERROR),
        ):
            with self.subTest(expected_status=expected_status):

                async def do_request(url):
                    async with aiohttp.ClientSession(
                        trace_configs=trace_configs,
                    ) as session:
                        async with session.get(url):
                            pass

                loop = asyncio.get_event_loop()
                with self.assertRaises(aiohttp.ClientConnectorError):
                    loop.run_until_complete(do_request(url))

            self._assert_spans(
                [
                    (
                        "GET",
                        (expected_status, "ClientConnectorError"),
                        {
                            HTTP_METHOD: "GET",
                            HTTP_URL: url,
                        },
                    )
                ]
            )
            self.memory_exporter.clear()

    def test_basic_exception(self):
        async def request_handler(request):
            assert "traceparent" in request.headers

        host, port = self._http_request(
            trace_config=aiohttp_client.create_trace_config(),
            url="/test",
            request_handler=request_handler,
        )
        span = self.memory_exporter.get_finished_spans()[0]
        self.assertEqual(len(span.events), 1)
        self.assertEqual(span.events[0].name, "exception")
        self._assert_spans(
            [
                (
                    "GET",
                    (StatusCode.ERROR, "ServerDisconnectedError"),
                    {
                        HTTP_METHOD: "GET",
                        HTTP_URL: f"http://{host}:{port}/test",
                    },
                )
            ]
        )
        metrics = self._assert_metrics(1)
        duration_data_point = metrics[0].data.data_points[0]
        self.assertEqual(
            dict(duration_data_point.attributes),
            {
                HTTP_METHOD: "GET",
                HTTP_HOST: host,
                NET_PEER_NAME: host,
                NET_PEER_PORT: port,
            },
        )

    def test_basic_exception_new_semconv(self):
        async def request_handler(request):
            assert "traceparent" in request.headers

        host, port = self._http_request(
            trace_config=aiohttp_client.create_trace_config(
                sem_conv_opt_in_mode=_StabilityMode.HTTP
            ),
            url="/test",
            request_handler=request_handler,
        )
        span = self.memory_exporter.get_finished_spans()[0]
        self.assertEqual(len(span.events), 1)
        self.assertEqual(span.events[0].name, "exception")
        self._assert_spans(
            [
                (
                    "GET",
                    (StatusCode.ERROR, "ServerDisconnectedError"),
                    {
                        HTTP_REQUEST_METHOD: "GET",
                        URL_FULL: f"http://{host}:{port}/test",
                        ERROR_TYPE: "ServerDisconnectedError",
                        SERVER_ADDRESS: host,
                        SERVER_PORT: port,
                    },
                )
            ]
        )
        metrics = self._assert_metrics(1)
        duration_data_point = metrics[0].data.data_points[0]
        self.assertEqual(
            dict(duration_data_point.attributes),
            {
                HTTP_REQUEST_METHOD: "GET",
                ERROR_TYPE: "ServerDisconnectedError",
                SERVER_ADDRESS: host,
                SERVER_PORT: port,
            },
        )

    def test_basic_exception_both_semconv(self):
        async def request_handler(request):
            assert "traceparent" in request.headers

        host, port = self._http_request(
            trace_config=aiohttp_client.create_trace_config(
                sem_conv_opt_in_mode=_StabilityMode.HTTP_DUP
            ),
            url="/test",
            request_handler=request_handler,
        )
        span = self.memory_exporter.get_finished_spans()[0]
        self.assertEqual(len(span.events), 1)
        self.assertEqual(span.events[0].name, "exception")
        self._assert_spans(
            [
                (
                    "GET",
                    (StatusCode.ERROR, "ServerDisconnectedError"),
                    {
                        HTTP_REQUEST_METHOD: "GET",
                        URL_FULL: f"http://{host}:{port}/test",
                        ERROR_TYPE: "ServerDisconnectedError",
                        HTTP_METHOD: "GET",
                        HTTP_URL: f"http://{host}:{port}/test",
                        HTTP_HOST: host,
                        SERVER_ADDRESS: host,
                        SERVER_PORT: port,
                        NET_PEER_PORT: port,
                    },
                )
            ]
        )
        metrics = self._assert_metrics(2)
        duration_data_point = metrics[0].data.data_points[0]
        self.assertEqual(
            dict(duration_data_point.attributes),
            {
                HTTP_METHOD: "GET",
                HTTP_HOST: host,
                NET_PEER_NAME: host,
                NET_PEER_PORT: port,
            },
        )
        duration_data_point = metrics[1].data.data_points[0]
        self.assertEqual(
            dict(duration_data_point.attributes),
            {
                HTTP_REQUEST_METHOD: "GET",
                ERROR_TYPE: "ServerDisconnectedError",
                SERVER_ADDRESS: host,
                SERVER_PORT: port,
            },
        )

    def test_timeout(self):
        async def request_handler(request):
            await asyncio.sleep(1)
            assert "traceparent" in request.headers
            return aiohttp.web.Response()

        host, port = self._http_request(
            trace_config=aiohttp_client.create_trace_config(),
            url="/test_timeout",
            request_handler=request_handler,
            timeout=aiohttp.ClientTimeout(sock_read=0.01),
        )

        self._assert_spans(
            [
                (
                    "GET",
                    (StatusCode.ERROR, "SocketTimeoutError"),
                    {
                        HTTP_METHOD: "GET",
                        HTTP_URL: f"http://{host}:{port}/test_timeout",
                    },
                )
            ]
        )

    def test_too_many_redirects(self):
        async def request_handler(request):
            # Create a redirect loop.
            location = request.url
            assert "traceparent" in request.headers
            raise aiohttp.web.HTTPFound(location=location)

        host, port = self._http_request(
            trace_config=aiohttp_client.create_trace_config(),
            url="/test_too_many_redirects",
            request_handler=request_handler,
            max_redirects=2,
        )

        self._assert_spans(
            [
                (
                    "GET",
                    (StatusCode.ERROR, "TooManyRedirects"),
                    {
                        HTTP_METHOD: "GET",
                        HTTP_URL: f"http://{host}:{port}/test_too_many_redirects",
                    },
                )
            ]
        )

    def test_nonstandard_http_method(self):
        trace_configs = [aiohttp_client.create_trace_config()]
        app = HttpServerMock("nonstandard_method")

        @app.route("/status/200", methods=["NONSTANDARD"])
        def index():
            return ("", 405, {})

        url = "http://localhost:5000/status/200"

        with app.run("localhost", 5000):
            with self.subTest(url=url):

                async def do_request(url):
                    async with aiohttp.ClientSession(
                        trace_configs=trace_configs,
                    ) as session:
                        async with session.request("NONSTANDARD", url):
                            pass

                loop = asyncio.get_event_loop()
                loop.run_until_complete(do_request(url))

        self._assert_spans(
            [
                (
                    "HTTP",
                    (StatusCode.ERROR, None),
                    {
                        HTTP_METHOD: "_OTHER",
                        HTTP_URL: url,
                        HTTP_STATUS_CODE: int(HTTPStatus.METHOD_NOT_ALLOWED),
                    },
                )
            ]
        )
        self.memory_exporter.clear()

    def test_nonstandard_http_method_new_semconv(self):
        trace_configs = [
            aiohttp_client.create_trace_config(
                sem_conv_opt_in_mode=_StabilityMode.HTTP
            )
        ]
        app = HttpServerMock("nonstandard_method")

        @app.route("/status/200", methods=["NONSTANDARD"])
        def index():
            return ("", 405, {})

        url = "http://localhost:5000/status/200"

        with app.run("localhost", 5000):
            with self.subTest(url=url):

                async def do_request(url):
                    async with aiohttp.ClientSession(
                        trace_configs=trace_configs,
                    ) as session:
                        async with session.request("NONSTANDARD", url):
                            pass

                loop = asyncio.get_event_loop()
                loop.run_until_complete(do_request(url))

        self._assert_spans(
            [
                (
                    "HTTP",
                    (StatusCode.ERROR, None),
                    {
                        HTTP_REQUEST_METHOD: "_OTHER",
                        URL_FULL: url,
                        HTTP_RESPONSE_STATUS_CODE: int(
                            HTTPStatus.METHOD_NOT_ALLOWED
                        ),
                        HTTP_REQUEST_METHOD_ORIGINAL: "NONSTANDARD",
                        ERROR_TYPE: "405",
                        SERVER_ADDRESS: "localhost",
                        SERVER_PORT: 5000,
                    },
                )
            ]
        )
        self.memory_exporter.clear()

    def test_credential_removal(self):
        trace_configs = [aiohttp_client.create_trace_config()]

        app = HttpServerMock("test_credential_removal")

        @app.route("/status/200")
        def index():
            return "hello"

        url = "http://username:password@localhost:5000/status/200"

        with app.run("localhost", 5000):
            with self.subTest(url=url):

                async def do_request(url):
                    async with aiohttp.ClientSession(
                        trace_configs=trace_configs,
                    ) as session:
                        async with session.get(url):
                            pass

                loop = asyncio.get_event_loop()
                loop.run_until_complete(do_request(url))

        self._assert_spans(
            [
                (
                    "GET",
                    (StatusCode.UNSET, None),
                    {
                        HTTP_METHOD: "GET",
                        HTTP_URL: ("http://localhost:5000/status/200"),
                        HTTP_STATUS_CODE: int(HTTPStatus.OK),
                    },
                )
            ]
        )
        self.memory_exporter.clear()


class TestAioHttpClientInstrumentor(TestBase):
    URL = "/test-path"

    def setUp(self):
        super().setUp()
        AioHttpClientInstrumentor().instrument()
        _OpenTelemetrySemanticConventionStability._initialized = False

    def tearDown(self):
        super().tearDown()
        AioHttpClientInstrumentor().uninstrument()

    @staticmethod
    # pylint:disable=unused-argument
    async def default_handler(request):
        return aiohttp.web.Response(status=int(200))

    @staticmethod
    def get_default_request(url: str = URL):
        async def default_request(server: aiohttp.test_utils.TestServer):
            async with aiohttp.test_utils.TestClient(server) as session:
                await session.get(url)

        return default_request

    def _assert_spans(self, num_spans: int):
        finished_spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(num_spans, len(finished_spans))
        if num_spans == 0:
            return None
        if num_spans == 1:
            return finished_spans[0]
        return finished_spans

    def _assert_metrics(self, num_metrics: int = 1):
        metrics = self.get_sorted_metrics()
        self.assertEqual(len(metrics), num_metrics)
        return metrics

    def test_instrument(self):
        host, port = run_with_test_server(
            self.get_default_request(), self.URL, self.default_handler
        )
        span = self._assert_spans(1)
        self.assertEqual("GET", span.name)
        self.assertEqual("GET", span.attributes[HTTP_METHOD])
        self.assertEqual(
            f"http://{host}:{port}/test-path",
            span.attributes[HTTP_URL],
        )
        self.assertEqual(200, span.attributes[HTTP_STATUS_CODE])
        metrics = self._assert_metrics(1)
        duration_data_point = metrics[0].data.data_points[0]
        self.assertEqual(duration_data_point.count, 1)
        self.assertEqual(
            dict(duration_data_point.attributes),
            {
                HTTP_HOST: host,
                HTTP_STATUS_CODE: 200,
                HTTP_METHOD: "GET",
                NET_PEER_NAME: host,
                NET_PEER_PORT: port,
            },
        )

    def test_instrument_new_semconv(self):
        AioHttpClientInstrumentor().uninstrument()
        with mock.patch.dict(
            "os.environ", {OTEL_SEMCONV_STABILITY_OPT_IN: "http"}
        ):
            AioHttpClientInstrumentor().instrument()
            host, port = run_with_test_server(
                self.get_default_request(), self.URL, self.default_handler
            )
            span = self._assert_spans(1)
            self.assertEqual("GET", span.name)
            self.assertEqual("GET", span.attributes[HTTP_REQUEST_METHOD])
            self.assertEqual(
                f"http://{host}:{port}/test-path",
                span.attributes[URL_FULL],
            )
            self.assertEqual(200, span.attributes[HTTP_RESPONSE_STATUS_CODE])
            metrics = self._assert_metrics(1)
            duration_data_point = metrics[0].data.data_points[0]
            self.assertEqual(duration_data_point.count, 1)
            self.assertEqual(
                dict(duration_data_point.attributes),
                {
                    HTTP_RESPONSE_STATUS_CODE: 200,
                    HTTP_REQUEST_METHOD: "GET",
                    SERVER_ADDRESS: host,
                    SERVER_PORT: port,
                },
            )

    def test_instrument_both_semconv(self):
        AioHttpClientInstrumentor().uninstrument()
        with mock.patch.dict(
            "os.environ", {OTEL_SEMCONV_STABILITY_OPT_IN: "http/dup"}
        ):
            AioHttpClientInstrumentor().instrument()
            host, port = run_with_test_server(
                self.get_default_request(), self.URL, self.default_handler
            )
            url = f"http://{host}:{port}/test-path"
            span = self._assert_spans(1)
            self.assertEqual("GET", span.name)
            self.assertEqual(
                dict(span.attributes),
                {
                    HTTP_REQUEST_METHOD: "GET",
                    HTTP_METHOD: "GET",
                    HTTP_HOST: host,
                    URL_FULL: url,
                    HTTP_URL: url,
                    HTTP_RESPONSE_STATUS_CODE: 200,
                    HTTP_STATUS_CODE: 200,
                    SERVER_ADDRESS: host,
                    SERVER_PORT: port,
                    NET_PEER_PORT: port,
                },
            )
            metrics = self._assert_metrics(2)
            duration_data_point = metrics[0].data.data_points[0]
            self.assertEqual(duration_data_point.count, 1)
            self.assertEqual(
                dict(duration_data_point.attributes),
                {
                    HTTP_STATUS_CODE: 200,
                    HTTP_METHOD: "GET",
                    HTTP_HOST: host,
                    NET_PEER_NAME: host,
                    NET_PEER_PORT: port,
                },
            )
            duration_data_point = metrics[1].data.data_points[0]
            self.assertEqual(duration_data_point.count, 1)
            self.assertEqual(
                dict(duration_data_point.attributes),
                {
                    HTTP_RESPONSE_STATUS_CODE: 200,
                    HTTP_REQUEST_METHOD: "GET",
                    SERVER_ADDRESS: host,
                    SERVER_PORT: port,
                },
            )

    def test_instrument_with_custom_trace_config(self):
        trace_config = aiohttp.TraceConfig()

        AioHttpClientInstrumentor().uninstrument()
        AioHttpClientInstrumentor().instrument(trace_configs=[trace_config])

        async def make_request(server: aiohttp.test_utils.TestServer):
            async with aiohttp.test_utils.TestClient(server) as client:
                trace_configs = client.session._trace_configs
                self.assertEqual(2, len(trace_configs))
                self.assertTrue(trace_config in trace_configs)
                async with client as session:
                    await session.get(TestAioHttpClientInstrumentor.URL)

        run_with_test_server(make_request, self.URL, self.default_handler)
        self._assert_spans(1)

    def test_every_request_by_new_session_creates_one_span(self):
        async def make_request(server: aiohttp.test_utils.TestServer):
            async with aiohttp.test_utils.TestClient(server) as client:
                async with client as session:
                    await session.get(TestAioHttpClientInstrumentor.URL)

        for request_no in range(3):
            self.memory_exporter.clear()
            with self.subTest(request_no=request_no):
                run_with_test_server(
                    make_request, self.URL, self.default_handler
                )
                self._assert_spans(1)

    def test_instrument_with_existing_trace_config(self):
        trace_config = aiohttp.TraceConfig()

        async def create_session(server: aiohttp.test_utils.TestServer):
            async with aiohttp.test_utils.TestClient(
                server, trace_configs=[trace_config]
            ) as client:
                # pylint:disable=protected-access
                trace_configs = client.session._trace_configs
                self.assertEqual(2, len(trace_configs))
                self.assertTrue(trace_config in trace_configs)
                async with client as session:
                    await session.get(TestAioHttpClientInstrumentor.URL)

        run_with_test_server(create_session, self.URL, self.default_handler)
        self._assert_spans(1)

    def test_no_op_tracer_provider(self):
        AioHttpClientInstrumentor().uninstrument()
        AioHttpClientInstrumentor().instrument(
            tracer_provider=trace_api.NoOpTracerProvider()
        )

        run_with_test_server(
            self.get_default_request(), self.URL, self.default_handler
        )
        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

    def test_uninstrument(self):
        AioHttpClientInstrumentor().uninstrument()
        run_with_test_server(
            self.get_default_request(), self.URL, self.default_handler
        )

        self._assert_spans(0)

        AioHttpClientInstrumentor().instrument()
        run_with_test_server(
            self.get_default_request(), self.URL, self.default_handler
        )
        self._assert_spans(1)

    def test_uninstrument_session(self):
        async def uninstrument_request(server: aiohttp.test_utils.TestServer):
            client = aiohttp.test_utils.TestClient(server)
            AioHttpClientInstrumentor().uninstrument_session(client.session)
            async with client as session:
                await session.get(self.URL)

        run_with_test_server(
            uninstrument_request, self.URL, self.default_handler
        )
        self._assert_spans(0)

        run_with_test_server(
            self.get_default_request(), self.URL, self.default_handler
        )
        self._assert_spans(1)

    def test_suppress_instrumentation(self):
        with suppress_instrumentation():
            run_with_test_server(
                self.get_default_request(), self.URL, self.default_handler
            )
        self._assert_spans(0)

    @staticmethod
    async def suppressed_request(server: aiohttp.test_utils.TestServer):
        async with aiohttp.test_utils.TestClient(server) as client:
            with suppress_instrumentation():
                await client.get(TestAioHttpClientInstrumentor.URL)

    def test_suppress_instrumentation_after_creation(self):
        run_with_test_server(
            self.suppressed_request, self.URL, self.default_handler
        )
        self._assert_spans(0)

    def test_suppress_instrumentation_with_server_exception(self):
        # pylint:disable=unused-argument
        async def raising_handler(request):
            raise aiohttp.web.HTTPFound(location=self.URL)

        run_with_test_server(
            self.suppressed_request, self.URL, raising_handler
        )
        self._assert_spans(0)

    def test_url_filter(self):
        def strip_query_params(url: yarl.URL) -> str:
            return str(url.with_query(None))

        AioHttpClientInstrumentor().uninstrument()
        AioHttpClientInstrumentor().instrument(url_filter=strip_query_params)

        url = "/test-path?query=params"
        host, port = run_with_test_server(
            self.get_default_request(url), url, self.default_handler
        )
        span = self._assert_spans(1)
        self.assertEqual(
            f"http://{host}:{port}/test-path",
            span.attributes[HTTP_URL],
        )

    def test_hooks(self):
        def request_hook(span: Span, params: aiohttp.TraceRequestStartParams):
            span.update_name(f"{params.method} - {params.url.path}")

        def response_hook(
            span: Span,
            params: typing.Union[
                aiohttp.TraceRequestEndParams,
                aiohttp.TraceRequestExceptionParams,
            ],
        ):
            span.set_attribute("response_hook_attr", "value")

        AioHttpClientInstrumentor().uninstrument()
        AioHttpClientInstrumentor().instrument(
            request_hook=request_hook, response_hook=response_hook
        )

        url = "/test-path"
        run_with_test_server(
            self.get_default_request(url), url, self.default_handler
        )
        span = self._assert_spans(1)
        self.assertEqual("GET - /test-path", span.name)
        self.assertIn("response_hook_attr", span.attributes)
        self.assertEqual(span.attributes["response_hook_attr"], "value")


class TestLoadingAioHttpInstrumentor(unittest.TestCase):
    def test_loading_instrumentor(self):
        (entry_point,) = entry_points(
            group="opentelemetry_instrumentor", name="aiohttp-client"
        )

        instrumentor = entry_point.load()()
        self.assertIsInstance(instrumentor, AioHttpClientInstrumentor)
