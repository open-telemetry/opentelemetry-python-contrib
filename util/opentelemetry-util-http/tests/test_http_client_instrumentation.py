import os
from http.client import HTTPConnection, HTTPResponse, HTTPSConnection
from typing import Tuple

from opentelemetry import trace
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.httptest import HttpTestBase
from opentelemetry.test.test_base import TestBase
from opentelemetry.util.http.httplib import (
    HttpClientInstrumentor,
    set_ip_on_next_http_connection,
)


class TestHttpBase(TestBase, HttpTestBase):
    def setUp(self):
        super().setUp()
        self.server_thread, self.server = self.run_server()
        self.http_instrumentor = HttpClientInstrumentor()

    def tearDown(self):
        self.server.shutdown()
        self.server_thread.join()
        super().tearDown()

    def instrument_http(self, semconv_mode):
        original = os.environ.get("OTEL_SEMCONV_STABILITY_OPT_IN")
        os.environ["OTEL_SEMCONV_STABILITY_OPT_IN"] = semconv_mode
        self.http_instrumentor.instrument()
        return original

    def uninstrument_http(self, original_value):
        self.http_instrumentor.uninstrument()
        if original_value is None:
            del os.environ["OTEL_SEMCONV_STABILITY_OPT_IN"]
        else:
            os.environ["OTEL_SEMCONV_STABILITY_OPT_IN"] = original_value

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

    def test_basic_with_span_default(self):
        original = self.instrument_http("")
        try:
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span(
                "HTTP GET"
            ) as span, set_ip_on_next_http_connection(span):
                resp, body = self.perform_request()
            assert resp.status == 200
            assert body == b"Hello!"
            span = self.assert_span(num_spans=1)
            self.assertEqual(
                span.attributes, {SpanAttributes.NET_PEER_IP: "127.0.0.1"}
            )
        finally:
            self.uninstrument_http(original)

    def test_basic_with_span_new(self):
        original = self.instrument_http("http")
        try:
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span(
                "HTTP GET"
            ) as span, set_ip_on_next_http_connection(span):
                resp, body = self.perform_request()
            assert resp.status == 200
            assert body == b"Hello!"
            span = self.assert_span(num_spans=1)
            self.assertEqual(
                span.attributes, {SpanAttributes.CLIENT_ADDRESS: "127.0.0.1"}
            )
        finally:
            self.uninstrument_http(original)

    def test_basic_with_span_both(self):
        original = self.instrument_http("http/dup")
        try:
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span(
                "HTTP GET"
            ) as span, set_ip_on_next_http_connection(span):
                resp, body = self.perform_request()
            assert resp.status == 200
            assert body == b"Hello!"
            span = self.assert_span(num_spans=1)
            self.assertEqual(
                span.attributes,
                {
                    SpanAttributes.NET_PEER_IP: "127.0.0.1",
                    SpanAttributes.CLIENT_ADDRESS: "127.0.0.1",
                },
            )
        finally:
            self.uninstrument_http(original)

    def perform_request(self, secure=False) -> Tuple[HTTPResponse, bytes]:
        conn_cls = HTTPSConnection if secure else HTTPConnection
        conn = conn_cls(self.server.server_address[0], self.server.server_port)
        resp = None
        try:
            conn.request("GET", "/", headers={"Connection": "close"})
            resp = conn.getresponse()
            return resp, resp.read()
        finally:
            if resp:
                resp.close()
            conn.close()
