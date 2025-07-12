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


import asyncio
from unittest.mock import Mock, patch

import tornado.websocket
from http_server_mock import HttpServerMock
from tornado.httpclient import HTTPClientError
from tornado.testing import AsyncHTTPTestCase

from opentelemetry import trace
from opentelemetry.instrumentation.propagators import (
    TraceResponsePropagator,
    get_global_response_propagator,
    set_global_response_propagator,
)
from opentelemetry.instrumentation.tornado import (
    TornadoInstrumentor,
    patch_handler_class,
    unpatch_handler_class,
)
from opentelemetry.semconv._incubating.attributes.http_attributes import (
    HTTP_CLIENT_IP,
    HTTP_HOST,
    HTTP_METHOD,
    HTTP_SCHEME,
    HTTP_STATUS_CODE,
    HTTP_TARGET,
    HTTP_URL,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_PEER_IP,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.test.wsgitestutil import WsgiTestBase
from opentelemetry.trace import SpanKind, StatusCode
from opentelemetry.util.http import (
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE,
    get_excluded_urls,
    get_traced_request_attrs,
)

from .tornado_test_app import (
    AsyncHandler,
    DynamicHandler,
    MainHandler,
    make_app,
)


class TornadoTest(AsyncHTTPTestCase, TestBase):
    # pylint:disable=no-self-use
    def get_app(self):
        tracer = trace.get_tracer(__name__)
        app = make_app(tracer)
        return app

    def setUp(self):
        super().setUp()
        TornadoInstrumentor().instrument(
            server_request_hook=getattr(self, "server_request_hook", None),
            client_request_hook=getattr(self, "client_request_hook", None),
            client_response_hook=getattr(self, "client_response_hook", None),
        )
        # pylint: disable=protected-access
        self.env_patch = patch.dict(
            "os.environ",
            {
                "OTEL_PYTHON_TORNADO_EXCLUDED_URLS": "healthz,ping",
                "OTEL_PYTHON_TORNADO_TRACED_REQUEST_ATTRS": "uri,full_url,query",
            },
        )
        self.env_patch.start()
        self.exclude_patch = patch(
            "opentelemetry.instrumentation.tornado._excluded_urls",
            get_excluded_urls("TORNADO"),
        )
        self.traced_patch = patch(
            "opentelemetry.instrumentation.tornado._traced_request_attrs",
            get_traced_request_attrs("TORNADO"),
        )
        self.exclude_patch.start()
        self.traced_patch.start()

    def tearDown(self):
        TornadoInstrumentor().uninstrument()
        self.env_patch.stop()
        self.exclude_patch.stop()
        self.traced_patch.stop()
        super().tearDown()


class TestTornadoInstrumentor(TornadoTest):
    def test_patch_references(self):
        self.assertEqual(len(TornadoInstrumentor().patched_handlers), 0)

        self.fetch("/")
        self.fetch("/async")
        self.assertEqual(
            TornadoInstrumentor().patched_handlers, [MainHandler, AsyncHandler]
        )

        self.fetch("/async")
        self.fetch("/")
        self.assertEqual(
            TornadoInstrumentor().patched_handlers, [MainHandler, AsyncHandler]
        )

        TornadoInstrumentor().uninstrument()
        self.assertEqual(TornadoInstrumentor().patched_handlers, [])

    def test_patch_applied_only_once(self):
        tracer = trace.get_tracer(__name__)
        self.assertTrue(patch_handler_class(tracer, {}, AsyncHandler))
        self.assertFalse(patch_handler_class(tracer, {}, AsyncHandler))
        self.assertFalse(patch_handler_class(tracer, {}, AsyncHandler))
        unpatch_handler_class(AsyncHandler)


class TestTornadoInstrumentation(TornadoTest, WsgiTestBase):
    def test_http_calls(self):
        methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
        for method in methods:
            self._test_http_method_call(method)

    def _test_http_method_call(self, method):
        body = "" if method in ["POST", "PUT", "PATCH"] else None
        response = self.fetch("/", method=method, body=body)
        self.assertEqual(response.code, 201)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 3)

        manual, server, client = self.sorted_spans(spans)

        self.assertEqual(manual.name, "manual")
        self.assertEqual(manual.parent, server.context)
        self.assertEqual(manual.context.trace_id, client.context.trace_id)

        self.assertEqual(server.name, f"{method} /")
        self.assertTrue(server.parent.is_remote)
        self.assertNotEqual(server.parent, client.context)
        self.assertEqual(server.parent.span_id, client.context.span_id)
        self.assertEqual(server.context.trace_id, client.context.trace_id)
        self.assertEqual(server.kind, SpanKind.SERVER)
        self.assertSpanHasAttributes(
            server,
            {
                HTTP_METHOD: method,
                HTTP_SCHEME: "http",
                HTTP_HOST: "127.0.0.1:" + str(self.get_http_port()),
                HTTP_TARGET: "/",
                HTTP_CLIENT_IP: "127.0.0.1",
                HTTP_STATUS_CODE: 201,
                "tornado.handler": "tests.tornado_test_app.MainHandler",
            },
        )

        self.assertEqual(client.name, method)
        self.assertFalse(client.context.is_remote)
        self.assertIsNone(client.parent)
        self.assertEqual(client.kind, SpanKind.CLIENT)
        self.assertSpanHasAttributes(
            client,
            {
                HTTP_URL: self.get_url("/"),
                HTTP_METHOD: method,
                HTTP_STATUS_CODE: 201,
            },
        )

        self.memory_exporter.clear()

    def test_not_recording(self):
        mock_tracer = Mock()
        mock_span = Mock()
        mock_span.is_recording.return_value = False
        mock_tracer.start_span.return_value = mock_span
        with patch("opentelemetry.trace.get_tracer") as tracer:
            tracer.return_value = mock_tracer
            self.fetch("/")
            self.assertFalse(mock_span.is_recording())
            self.assertTrue(mock_span.is_recording.called)
            self.assertFalse(mock_span.set_attribute.called)
            self.assertFalse(mock_span.set_status.called)

    def test_async_handler(self):
        self._test_async_handler("/async", "AsyncHandler")

    def test_coroutine_handler(self):
        self._test_async_handler("/cor", "CoroutineHandler")

    def _test_async_handler(self, url, handler_name):
        response = self.fetch(url)
        self.assertEqual(response.code, 201)
        spans = self.get_finished_spans()
        self.assertEqual(len(spans), 5)

        client = spans.by_name("GET")
        server = spans.by_name(f"GET {url}")
        sub_wrapper = spans.by_name("sub-task-wrapper")

        sub2 = spans.by_name("sub-task-2")
        self.assertEqual(sub2.name, "sub-task-2")
        self.assertEqual(sub2.parent, sub_wrapper.context)
        self.assertEqual(sub2.context.trace_id, client.context.trace_id)

        sub1 = spans.by_name("sub-task-1")
        self.assertEqual(sub1.name, "sub-task-1")
        self.assertEqual(sub1.parent, sub_wrapper.context)
        self.assertEqual(sub1.context.trace_id, client.context.trace_id)

        self.assertEqual(sub_wrapper.name, "sub-task-wrapper")
        self.assertEqual(sub_wrapper.parent, server.context)
        self.assertEqual(sub_wrapper.context.trace_id, client.context.trace_id)

        self.assertEqual(server.name, f"GET {url}")
        self.assertTrue(server.parent.is_remote)
        self.assertNotEqual(server.parent, client.context)
        self.assertEqual(server.parent.span_id, client.context.span_id)
        self.assertEqual(server.context.trace_id, client.context.trace_id)
        self.assertEqual(server.kind, SpanKind.SERVER)
        self.assertSpanHasAttributes(
            server,
            {
                HTTP_METHOD: "GET",
                HTTP_SCHEME: "http",
                HTTP_HOST: "127.0.0.1:" + str(self.get_http_port()),
                HTTP_TARGET: url,
                HTTP_CLIENT_IP: "127.0.0.1",
                HTTP_STATUS_CODE: 201,
                "tornado.handler": f"tests.tornado_test_app.{handler_name}",
            },
        )

        self.assertEqual(client.name, "GET")
        self.assertFalse(client.context.is_remote)
        self.assertIsNone(client.parent)
        self.assertEqual(client.kind, SpanKind.CLIENT)
        self.assertSpanHasAttributes(
            client,
            {
                HTTP_URL: self.get_url(url),
                HTTP_METHOD: "GET",
                HTTP_STATUS_CODE: 201,
            },
        )

    def test_500(self):
        response = self.fetch("/error")
        self.assertEqual(response.code, 500)

        spans = self.get_finished_spans()
        self.assertEqual(len(spans), 2)

        client = spans.by_name("GET")
        server = spans.by_name("GET /error")

        self.assertEqual(server.name, "GET /error")
        self.assertEqual(server.kind, SpanKind.SERVER)
        self.assertSpanHasAttributes(
            server,
            {
                HTTP_METHOD: "GET",
                HTTP_SCHEME: "http",
                HTTP_HOST: "127.0.0.1:" + str(self.get_http_port()),
                HTTP_TARGET: "/error",
                HTTP_CLIENT_IP: "127.0.0.1",
                HTTP_STATUS_CODE: 500,
                "tornado.handler": "tests.tornado_test_app.BadHandler",
            },
        )

        self.assertEqual(client.name, "GET")
        self.assertEqual(client.kind, SpanKind.CLIENT)
        self.assertSpanHasAttributes(
            client,
            {
                HTTP_URL: self.get_url("/error"),
                HTTP_METHOD: "GET",
                HTTP_STATUS_CODE: 500,
            },
        )

    def test_404(self):
        response = self.fetch("/missing-url")
        self.assertEqual(response.code, 404)

        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 2)
        server, client = spans

        self.assertEqual(server.name, "GET /missing-url")
        self.assertEqual(server.kind, SpanKind.SERVER)
        self.assertSpanHasAttributes(
            server,
            {
                HTTP_METHOD: "GET",
                HTTP_SCHEME: "http",
                HTTP_HOST: "127.0.0.1:" + str(self.get_http_port()),
                HTTP_TARGET: "/missing-url",
                HTTP_CLIENT_IP: "127.0.0.1",
                HTTP_STATUS_CODE: 404,
                "tornado.handler": "tornado.web.ErrorHandler",
            },
        )

        self.assertEqual(client.name, "GET")
        self.assertEqual(client.kind, SpanKind.CLIENT)
        self.assertSpanHasAttributes(
            client,
            {
                HTTP_URL: self.get_url("/missing-url"),
                HTTP_METHOD: "GET",
                HTTP_STATUS_CODE: 404,
            },
        )

    def test_http_error(self):
        response = self.fetch("/raise_403")
        self.assertEqual(response.code, 403)

        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 2)
        server, client = spans

        self.assertEqual(server.name, "GET /raise_403")
        self.assertEqual(server.kind, SpanKind.SERVER)
        self.assertSpanHasAttributes(
            server,
            {
                HTTP_METHOD: "GET",
                HTTP_SCHEME: "http",
                HTTP_HOST: "127.0.0.1:" + str(self.get_http_port()),
                HTTP_TARGET: "/raise_403",
                HTTP_CLIENT_IP: "127.0.0.1",
                HTTP_STATUS_CODE: 403,
                "tornado.handler": "tests.tornado_test_app.RaiseHTTPErrorHandler",
            },
        )

        self.assertEqual(client.name, "GET")
        self.assertEqual(client.kind, SpanKind.CLIENT)
        self.assertSpanHasAttributes(
            client,
            {
                HTTP_URL: self.get_url("/raise_403"),
                HTTP_METHOD: "GET",
                HTTP_STATUS_CODE: 403,
            },
        )

    def test_dynamic_handler(self):
        response = self.fetch("/dyna")
        self.assertEqual(response.code, 404)
        self.memory_exporter.clear()

        self._app.add_handlers(r".+", [(r"/dyna", DynamicHandler)])

        response = self.fetch("/dyna")
        self.assertEqual(response.code, 202)

        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 2)
        server, client = spans

        self.assertEqual(server.name, "GET /dyna")
        self.assertTrue(server.parent.is_remote)
        self.assertNotEqual(server.parent, client.context)
        self.assertEqual(server.parent.span_id, client.context.span_id)
        self.assertEqual(server.context.trace_id, client.context.trace_id)
        self.assertEqual(server.kind, SpanKind.SERVER)
        self.assertSpanHasAttributes(
            server,
            {
                HTTP_METHOD: "GET",
                HTTP_SCHEME: "http",
                HTTP_HOST: "127.0.0.1:" + str(self.get_http_port()),
                HTTP_TARGET: "/dyna",
                HTTP_CLIENT_IP: "127.0.0.1",
                HTTP_STATUS_CODE: 202,
                "tornado.handler": "tests.tornado_test_app.DynamicHandler",
            },
        )

        self.assertEqual(client.name, "GET")
        self.assertFalse(client.context.is_remote)
        self.assertIsNone(client.parent)
        self.assertEqual(client.kind, SpanKind.CLIENT)
        self.assertSpanHasAttributes(
            client,
            {
                HTTP_URL: self.get_url("/dyna"),
                HTTP_METHOD: "GET",
                HTTP_STATUS_CODE: 202,
            },
        )

    def test_handler_on_finish(self):
        response = self.fetch("/on_finish")
        self.assertEqual(response.code, 200)

        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 3)
        auditor, server, client = spans

        self.assertEqual(server.name, "GET /on_finish")
        self.assertTrue(server.parent.is_remote)
        self.assertNotEqual(server.parent, client.context)
        self.assertEqual(server.parent.span_id, client.context.span_id)
        self.assertEqual(server.context.trace_id, client.context.trace_id)
        self.assertEqual(server.kind, SpanKind.SERVER)
        self.assertSpanHasAttributes(
            server,
            {
                HTTP_METHOD: "GET",
                HTTP_SCHEME: "http",
                HTTP_HOST: "127.0.0.1:" + str(self.get_http_port()),
                HTTP_TARGET: "/on_finish",
                HTTP_CLIENT_IP: "127.0.0.1",
                HTTP_STATUS_CODE: 200,
                "tornado.handler": "tests.tornado_test_app.FinishedHandler",
            },
        )

        self.assertEqual(client.name, "GET")
        self.assertFalse(client.context.is_remote)
        self.assertIsNone(client.parent)
        self.assertEqual(client.kind, SpanKind.CLIENT)
        self.assertSpanHasAttributes(
            client,
            {
                HTTP_URL: self.get_url("/on_finish"),
                HTTP_METHOD: "GET",
                HTTP_STATUS_CODE: 200,
            },
        )

        self.assertEqual(auditor.name, "audit_task")
        self.assertFalse(auditor.context.is_remote)
        self.assertEqual(auditor.parent.span_id, server.context.span_id)
        self.assertEqual(auditor.context.trace_id, client.context.trace_id)

        self.assertEqual(auditor.kind, SpanKind.INTERNAL)

    @tornado.testing.gen_test()
    async def test_websockethandler(self):
        ws_client = await tornado.websocket.websocket_connect(
            f"ws://127.0.0.1:{self.get_http_port()}/echo_socket"
        )

        await ws_client.write_message("world")
        resp = await ws_client.read_message()
        self.assertEqual(resp, "hello world")

        ws_client.close()
        await asyncio.sleep(0.5)

        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 3)
        close_span, msg_span, req_span = spans

        self.assertEqual(req_span.name, "GET /echo_socket")
        self.assertEqual(req_span.context.trace_id, msg_span.context.trace_id)
        self.assertIsNone(req_span.parent)
        self.assertEqual(req_span.kind, SpanKind.SERVER)
        self.assertSpanHasAttributes(
            req_span,
            {
                HTTP_METHOD: "GET",
                HTTP_SCHEME: "http",
                HTTP_HOST: f"127.0.0.1:{self.get_http_port()}",
                HTTP_TARGET: "/echo_socket",
                HTTP_CLIENT_IP: "127.0.0.1",
                HTTP_STATUS_CODE: 101,
                "tornado.handler": "tests.tornado_test_app.EchoWebSocketHandler",
            },
        )

        self.assertEqual(msg_span.name, "audit_message")
        self.assertFalse(msg_span.context.is_remote)
        self.assertEqual(msg_span.kind, SpanKind.INTERNAL)
        self.assertEqual(msg_span.parent.span_id, req_span.context.span_id)

        self.assertEqual(close_span.name, "audit_on_close")
        self.assertFalse(close_span.context.is_remote)
        self.assertEqual(close_span.parent.span_id, req_span.context.span_id)
        self.assertEqual(
            close_span.context.trace_id, msg_span.context.trace_id
        )
        self.assertEqual(close_span.kind, SpanKind.INTERNAL)

    def test_exclude_lists(self):
        def test_excluded(path):
            self.fetch(path)
            spans = self.sorted_spans(
                self.memory_exporter.get_finished_spans()
            )
            self.assertEqual(len(spans), 1)
            client = spans[0]
            self.assertEqual(client.name, "GET")
            self.assertEqual(client.kind, SpanKind.CLIENT)
            self.assertSpanHasAttributes(
                client,
                {
                    HTTP_URL: self.get_url(path),
                    HTTP_METHOD: "GET",
                    HTTP_STATUS_CODE: 200,
                },
            )
            self.memory_exporter.clear()

        test_excluded("/healthz")
        test_excluded("/ping")

    def test_traced_attrs(self):
        self.fetch("/pong?q=abc&b=123")
        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 2)
        server_span = spans[0]
        self.assertEqual(server_span.kind, SpanKind.SERVER)
        self.assertSpanHasAttributes(
            server_span, {"uri": "/pong?q=abc&b=123", "query": "q=abc&b=123"}
        )
        self.memory_exporter.clear()

    def test_response_headers(self):
        orig = get_global_response_propagator()
        set_global_response_propagator(TraceResponsePropagator())

        response = self.fetch("/")

        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 3)
        self.assertTraceResponseHeaderMatchesSpan(response.headers, spans[1])

        set_global_response_propagator(orig)

    def test_remove_sensitive_params(self):
        app = HttpServerMock("test_remove_sensitive_params")

        @app.route("/status/200")
        def index():
            return "hello"

        with app.run("localhost", 5000):
            response = self.fetch(
                "http://username:password@localhost:5000/status/200?Signature=secret"
            )
        self.assertEqual(response.code, 200)

        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 1)
        client = spans[0]

        self.assertEqual(client.name, "GET")
        self.assertEqual(client.kind, SpanKind.CLIENT)
        self.assertSpanHasAttributes(
            client,
            {
                HTTP_URL: "http://REDACTED:REDACTED@localhost:5000/status/200?Signature=REDACTED",
                HTTP_METHOD: "GET",
                HTTP_STATUS_CODE: 200,
            },
        )

        self.memory_exporter.clear()


class TestTornadoInstrumentationWithXHeaders(TornadoTest):
    def get_httpserver_options(self):  # pylint: disable=no-self-use
        return {"xheaders": True}

    def test_xheaders(self):
        response = self.fetch("/", headers={"X-Forwarded-For": "12.34.56.78"})
        self.assertEqual(response.code, 201)
        spans = self.get_finished_spans()
        self.assertSpanHasAttributes(
            spans.by_name("GET /"),
            {
                HTTP_METHOD: "GET",
                HTTP_SCHEME: "http",
                HTTP_HOST: "127.0.0.1:" + str(self.get_http_port()),
                HTTP_TARGET: "/",
                HTTP_CLIENT_IP: "12.34.56.78",
                HTTP_STATUS_CODE: 201,
                NET_PEER_IP: "127.0.0.1",
                "tornado.handler": "tests.tornado_test_app.MainHandler",
            },
        )


class TornadoHookTest(TornadoTest):
    _client_request_hook = None
    _client_response_hook = None
    _server_request_hook = None

    def client_request_hook(self, span, handler):
        if self._client_request_hook is not None:
            self._client_request_hook(span, handler)

    def client_response_hook(self, span, handler):
        if self._client_response_hook is not None:
            self._client_response_hook(span, handler)

    def server_request_hook(self, span, handler):
        if self._server_request_hook is not None:
            self._server_request_hook(span, handler)

    def test_hooks(self):
        def server_request_hook(span, handler):
            span.update_name("name from server hook")
            handler.set_header("hello", "world")

        def client_request_hook(span, request):
            span.update_name("name from client hook")

        def client_response_hook(span, response):
            span.set_attribute("attr-from-hook", "value")

        self._server_request_hook = server_request_hook
        self._client_request_hook = client_request_hook
        self._client_response_hook = client_response_hook

        response = self.fetch("/")
        self.assertEqual(response.headers.get("hello"), "world")

        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 3)
        server_span = spans[1]
        self.assertEqual(server_span.kind, SpanKind.SERVER)
        self.assertEqual(server_span.name, "name from server hook")
        self.assertSpanHasAttributes(server_span, {"uri": "/"})
        self.memory_exporter.clear()

        client_span = spans[2]
        self.assertEqual(client_span.kind, SpanKind.CLIENT)
        self.assertEqual(client_span.name, "name from client hook")
        self.assertSpanHasAttributes(client_span, {"attr-from-hook": "value"})

        self.memory_exporter.clear()


class TestTornadoHTTPClientInstrumentation(TornadoTest, WsgiTestBase):
    def test_http_client_success_response(self):
        response = self.fetch("/")
        self.assertEqual(response.code, 201)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 3)
        manual, server, client = self.sorted_spans(spans)
        self.assertEqual(manual.name, "manual")
        self.assertEqual(server.name, "GET /")
        self.assertEqual(client.name, "GET")
        self.assertEqual(client.status.status_code, StatusCode.UNSET)
        self.memory_exporter.clear()

    def test_http_client_failed_response(self):
        # when an exception isn't thrown
        response = self.fetch("/some-404")
        self.assertEqual(response.code, 404)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        server, client = self.sorted_spans(spans)
        self.assertEqual(server.name, "GET /some-404")
        self.assertEqual(client.name, "GET")
        self.assertEqual(client.status.status_code, StatusCode.ERROR)
        self.memory_exporter.clear()

        # when an exception is thrown
        try:
            response = self.fetch("/some-404", raise_error=True)
            self.assertEqual(response.code, 404)
        except HTTPClientError:
            pass  # expected exception - continue

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        server, client = self.sorted_spans(spans)
        self.assertEqual(server.name, "GET /some-404")
        self.assertEqual(client.name, "GET")
        self.assertEqual(client.status.status_code, StatusCode.ERROR)
        self.memory_exporter.clear()


class TestTornadoUninstrument(TornadoTest):
    def test_uninstrument(self):
        response = self.fetch("/")
        self.assertEqual(response.code, 201)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 3)
        manual, server, client = self.sorted_spans(spans)
        self.assertEqual(manual.name, "manual")
        self.assertEqual(server.name, "GET /")
        self.assertEqual(client.name, "GET")
        self.memory_exporter.clear()

        TornadoInstrumentor().uninstrument()

        response = self.fetch("/")
        self.assertEqual(response.code, 201)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        manual = spans[0]
        self.assertEqual(manual.name, "manual")


class TestTornadoWrappedWithOtherFramework(TornadoTest):
    def get_app(self):
        tracer = trace.get_tracer(__name__)
        app = make_app(tracer)

        def middleware(request):
            """Wraps the request with a server span"""
            with tracer.start_as_current_span(
                "test", kind=trace.SpanKind.SERVER
            ):
                app(request)

        return middleware

    def test_mark_span_internal_in_presence_of_another_span(self):
        response = self.fetch("/")
        self.assertEqual(response.code, 201)
        spans = self.sorted_spans(self.memory_exporter.get_finished_spans())
        self.assertEqual(len(spans), 4)

        tornado_handler_span = spans[1]
        self.assertEqual(trace.SpanKind.INTERNAL, tornado_handler_span.kind)

        test_span = spans[2]
        self.assertEqual(trace.SpanKind.SERVER, test_span.kind)
        self.assertEqual(
            test_span.context.span_id, tornado_handler_span.parent.span_id
        )


class TestTornadoCustomRequestResponseHeadersAddedWithServerSpan(TornadoTest):
    @patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3"
        },
    )
    def test_custom_request_headers_added_in_server_span(self):
        headers = {
            "Custom-Test-Header-1": "Test Value 1",
            "Custom-Test-Header-2": "TestValue2,TestValue3",
        }
        response = self.fetch("/", headers=headers)
        self.assertEqual(response.code, 201)
        _, tornado_span, _ = self.sorted_spans(
            self.memory_exporter.get_finished_spans()
        )
        expected = {
            "http.request.header.custom_test_header_1": ("Test Value 1",),
            "http.request.header.custom_test_header_2": (
                "TestValue2,TestValue3",
            ),
        }
        self.assertEqual(tornado_span.kind, trace.SpanKind.SERVER)
        self.assertSpanHasAttributes(tornado_span, expected)

    @patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE: "content-type,content-length,my-custom-header,invalid-header"
        },
    )
    def test_custom_response_headers_added_in_server_span(self):
        response = self.fetch("/test_custom_response_headers")
        self.assertEqual(response.code, 200)
        tornado_span, _ = self.sorted_spans(
            self.memory_exporter.get_finished_spans()
        )
        expected = {
            "http.response.header.content_type": (
                "text/plain; charset=utf-8",
            ),
            "http.response.header.content_length": ("0",),
            "http.response.header.my_custom_header": (
                "my-custom-value-1,my-custom-header-2",
            ),
        }
        self.assertEqual(tornado_span.kind, trace.SpanKind.SERVER)
        self.assertSpanHasAttributes(tornado_span, expected)


class TestTornadoCustomRequestResponseHeadersNotAddedWithInternalSpan(
    TornadoTest
):
    def get_app(self):
        tracer = trace.get_tracer(__name__)
        app = make_app(tracer)

        def middleware(request):
            """Wraps the request with a server span"""
            with tracer.start_as_current_span(
                "test", kind=trace.SpanKind.SERVER
            ):
                app(request)

        return middleware

    @patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3"
        },
    )
    def test_custom_request_headers_not_added_in_internal_span(self):
        headers = {
            "Custom-Test-Header-1": "Test Value 1",
            "Custom-Test-Header-2": "TestValue2,TestValue3",
        }
        response = self.fetch("/", headers=headers)
        self.assertEqual(response.code, 201)
        _, tornado_span, _, _ = self.sorted_spans(
            self.memory_exporter.get_finished_spans()
        )
        not_expected = {
            "http.request.header.custom_test_header_1": ("Test Value 1",),
            "http.request.header.custom_test_header_2": (
                "TestValue2,TestValue3",
            ),
        }
        self.assertEqual(tornado_span.kind, trace.SpanKind.INTERNAL)
        for key, _ in not_expected.items():
            self.assertNotIn(key, tornado_span.attributes)

    @patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE: "content-type,content-length,my-custom-header,invalid-header"
        },
    )
    def test_custom_response_headers_not_added_in_internal_span(self):
        response = self.fetch("/test_custom_response_headers")
        self.assertEqual(response.code, 200)
        tornado_span, _, _ = self.sorted_spans(
            self.memory_exporter.get_finished_spans()
        )
        not_expected = {
            "http.response.header.content_type": (
                "text/plain; charset=utf-8",
            ),
            "http.response.header.content_length": ("0",),
            "http.response.header.my_custom_header": (
                "my-custom-value-1,my-custom-header-2",
            ),
        }
        self.assertEqual(tornado_span.kind, trace.SpanKind.INTERNAL)
        for key, _ in not_expected.items():
            self.assertNotIn(key, tornado_span.attributes)
