# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=arguments-differ,invalid-name,no-self-use,possibly-used-before-assignment

import asyncio
import importlib.util
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from opentelemetry import trace
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.semconv._incubating.attributes.http_attributes import (
    HTTP_METHOD,
    HTTP_STATUS_CODE,
    HTTP_URL,
)
from opentelemetry.test.test_base import TestBase

httpx2_installed = importlib.util.find_spec("httpx2") is not None

if httpx2_installed:
    import httpx2

    from opentelemetry.instrumentation.httpx import (
        AsyncOpenTelemetryTransportHttpx2,
        HTTPX2ClientInstrumentor,
        SyncOpenTelemetryTransportHttpx2,
    )


class _TestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        body = b"Hello!"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


@unittest.skipIf(not httpx2_installed, "httpx2 is not installed")
class TestHTTPX2Instrumentor(TestBase):
    # NOTE: Unlike the httpx tests which use respx for mocking, these tests use
    # a local server for global instrumentation and httpx2.MockTransport for
    # client-level instrumentation. At the time of writing, respx does not yet
    # have stable httpx2 support (see
    # https://github.com/lundberg/respx/issues/316 and PR #317).
    # pytest-httpx2 v1.0.0 exists but uses a fixture-based API that does not fit
    # this unittest-style suite. MockTransport is built in to httpx2 and has zero
    # external dependencies; the local server is used where we need to exercise
    # HTTPTransport.handle_request directly.
    #
    # These tests are intentionally focused on proving that httpx2 reaches each
    # public instrumentation path. The detailed span attributes, metrics,
    # semantic convention modes, header capture, error paths, and suppression
    # behavior are still covered by the original httpx suite because both
    # instrumentors share the same wrapper and transport implementation.

    def setUp(self):
        super().setUp()
        self.env_patch = mock.patch.dict(
            "os.environ",
            {OTEL_SEMCONV_STABILITY_OPT_IN: "default"},
        )
        self.env_patch.start()
        _OpenTelemetrySemanticConventionStability._initialized = False
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _TestHandler)
        self.server_thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.server_thread.start()
        host, port = self.server.server_address
        self.url = f"http://{host}:{port}/status/200"

    def tearDown(self):
        HTTPX2ClientInstrumentor().uninstrument()
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=5)
        self.env_patch.stop()
        super().tearDown()

    def _mock_transport(self, status_code=200):
        def handler(request):
            return httpx2.Response(
                status_code,
                text="Hello!",
                extensions={"http_version": b"HTTP/1.1"},
            )

        return httpx2.MockTransport(handler)

    def _assert_basic_span(self, url=None):
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(span.kind, trace.SpanKind.CLIENT)
        self.assertEqual(span.name, "GET")
        span_attributes = dict(span.attributes)
        self.assertEqual(span_attributes[HTTP_METHOD], "GET")
        self.assertEqual(span_attributes[HTTP_URL], url or self.url)
        self.assertEqual(span_attributes[HTTP_STATUS_CODE], 200)
        return span

    def test_sync_global_instrumentation(self):
        HTTPX2ClientInstrumentor().instrument(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )

        with httpx2.Client() as client:
            response = client.get(self.url)

        self.assertEqual(response.text, "Hello!")
        self._assert_basic_span()

    def test_async_global_instrumentation(self):
        async def do_request():
            HTTPX2ClientInstrumentor().instrument(
                tracer_provider=self.tracer_provider,
                meter_provider=self.meter_provider,
            )
            async with httpx2.AsyncClient() as client:
                return await client.get(self.url)

        response = asyncio.run(do_request())

        self.assertEqual(response.text, "Hello!")
        self._assert_basic_span()

    def test_sync_instrument_client(self):
        url = "http://mock/status/200"
        client = httpx2.Client(transport=self._mock_transport())
        HTTPX2ClientInstrumentor.instrument_client(
            client,
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )

        response = client.get(url)

        self.assertEqual(response.text, "Hello!")
        self._assert_basic_span(url)
        HTTPX2ClientInstrumentor.uninstrument_client(client)
        client.close()

    def test_async_instrument_client(self):
        async def do_request():
            url = "http://mock/status/200"
            client = httpx2.AsyncClient(
                transport=httpx2.MockTransport(
                    lambda request: httpx2.Response(
                        200,
                        text="Hello!",
                        extensions={"http_version": b"HTTP/1.1"},
                    )
                )
            )
            HTTPX2ClientInstrumentor.instrument_client(
                client,
                tracer_provider=self.tracer_provider,
                meter_provider=self.meter_provider,
            )
            response = await client.get(url)
            HTTPX2ClientInstrumentor.uninstrument_client(client)
            await client.aclose()
            return url, response

        url, response = asyncio.run(do_request())

        self.assertEqual(response.text, "Hello!")
        self._assert_basic_span(url)

    def test_uninstrument_client(self):
        url = "http://mock/status/200"
        client = httpx2.Client(transport=self._mock_transport())
        HTTPX2ClientInstrumentor.instrument_client(
            client,
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )
        HTTPX2ClientInstrumentor.uninstrument_client(client)

        response = client.get(url)

        self.assertEqual(response.text, "Hello!")
        self.assertEqual(self.memory_exporter.get_finished_spans(), ())
        client.close()

    def test_sync_transport_wrapper(self):
        url = "http://mock/status/200"
        transport = SyncOpenTelemetryTransportHttpx2(
            self._mock_transport(),
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )

        with httpx2.Client(transport=transport) as client:
            response = client.get(url)

        self.assertEqual(response.text, "Hello!")
        self._assert_basic_span(url)

    def test_async_transport_wrapper(self):
        async def do_request():
            url = "http://mock/status/200"
            transport = AsyncOpenTelemetryTransportHttpx2(
                httpx2.MockTransport(
                    lambda request: httpx2.Response(
                        200,
                        text="Hello!",
                        extensions={"http_version": b"HTTP/1.1"},
                    )
                ),
                tracer_provider=self.tracer_provider,
                meter_provider=self.meter_provider,
            )
            async with httpx2.AsyncClient(transport=transport) as client:
                return url, await client.get(url)

        url, response = asyncio.run(do_request())

        self.assertEqual(response.text, "Hello!")
        self._assert_basic_span(url)

    def test_hooks(self):
        url = "http://mock/status/200"

        def request_hook(span, request):
            span.set_attribute("request_hook", request.method.decode())

        def response_hook(span, request, response):
            span.set_attribute("response_hook", response.status_code)

        client = httpx2.Client(transport=self._mock_transport())
        HTTPX2ClientInstrumentor.instrument_client(
            client,
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
            request_hook=request_hook,
            response_hook=response_hook,
        )

        response = client.get(url)

        self.assertEqual(response.text, "Hello!")
        span = self._assert_basic_span(url)
        self.assertEqual(span.attributes["request_hook"], "GET")
        self.assertEqual(span.attributes["response_hook"], 200)
        HTTPX2ClientInstrumentor.uninstrument_client(client)
        client.close()

    def test_excluded_urls(self):
        self.env_patch.stop()
        with mock.patch.dict(
            "os.environ",
            {"OTEL_PYTHON_HTTPX_EXCLUDED_URLS": self.url},
        ):
            HTTPX2ClientInstrumentor().instrument(
                tracer_provider=self.tracer_provider,
                meter_provider=self.meter_provider,
            )
            with httpx2.Client() as client:
                response = client.get(self.url)
        self.env_patch.start()

        self.assertEqual(response.text, "Hello!")
        self.assertEqual(self.memory_exporter.get_finished_spans(), ())
