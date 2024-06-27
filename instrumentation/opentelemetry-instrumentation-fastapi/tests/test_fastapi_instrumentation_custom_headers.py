from collections.abc import Mapping
from typing import Tuple
from unittest.mock import patch

import fastapi
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

import opentelemetry.instrumentation.fastapi as otel_fastapi
from opentelemetry import trace
from opentelemetry.test.globals_test import reset_trace_globals
from opentelemetry.test.test_base import TestBase
from opentelemetry.util.http import (
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE,
)


class MultiMapping(Mapping):

    def __init__(self, *items: Tuple[str, str]):
        self._items = items

    def __len__(self):
        return len(self._items)

    def __getitem__(self, __key):
        raise NotImplementedError("use .items() instead")

    def __iter__(self):
        raise NotImplementedError("use .items() instead")

    def items(self):
        return self._items


@patch.dict(
    "os.environ",
    {
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS: ".*my-secret.*",
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3,Regex-Test-Header-.*,Regex-Invalid-Test-Header-.*,.*my-secret.*",
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3,my-custom-regex-header-.*,invalid-regex-header-.*,.*my-secret.*",
    },
)
class TestHTTPAppWithCustomHeaders(TestBase):
    def setUp(self):
        super().setUp()
        self.app = self._create_app()
        otel_fastapi.FastAPIInstrumentor().instrument_app(self.app)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        super().tearDown()
        with self.disable_logging():
            otel_fastapi.FastAPIInstrumentor().uninstrument_app(self.app)

    @staticmethod
    def _create_app():
        app = fastapi.FastAPI()

        @app.get("/foobar")
        async def _():
            headers = MultiMapping(
                ("custom-test-header-1", "test-header-value-1"),
                ("custom-test-header-2", "test-header-value-2"),
                ("my-custom-regex-header-1", "my-custom-regex-value-1"),
                ("my-custom-regex-header-1", "my-custom-regex-value-2"),
                ("My-Custom-Regex-Header-2", "my-custom-regex-value-3"),
                ("My-Custom-Regex-Header-2", "my-custom-regex-value-4"),
                ("My-Secret-Header", "My Secret Value"),
            )
            content = {"message": "hello world"}
            return JSONResponse(content=content, headers=headers)

        return app

    def test_http_custom_request_headers_in_span_attributes(self):
        expected = {
            "http.request.header.custom_test_header_1": (
                "test-header-value-1",
            ),
            "http.request.header.custom_test_header_2": (
                "test-header-value-2",
            ),
            "http.request.header.regex_test_header_1": ("Regex Test Value 1",),
            "http.request.header.regex_test_header_2": (
                "RegexTestValue2,RegexTestValue3",
            ),
            "http.request.header.my_secret_header": ("[REDACTED]",),
        }
        resp = self.client.get(
            "/foobar",
            headers={
                "custom-test-header-1": "test-header-value-1",
                "custom-test-header-2": "test-header-value-2",
                "Regex-Test-Header-1": "Regex Test Value 1",
                "regex-test-header-2": "RegexTestValue2,RegexTestValue3",
                "My-Secret-Header": "My Secret Value",
            },
        )
        self.assertEqual(200, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 3)

        server_span = [
            span for span in span_list if span.kind == trace.SpanKind.SERVER
        ][0]

        self.assertSpanHasAttributes(server_span, expected)

    def test_http_custom_request_headers_not_in_span_attributes(self):
        not_expected = {
            "http.request.header.custom_test_header_3": (
                "test-header-value-3",
            ),
        }
        resp = self.client.get(
            "/foobar",
            headers={
                "custom-test-header-1": "test-header-value-1",
                "custom-test-header-2": "test-header-value-2",
                "Regex-Test-Header-1": "Regex Test Value 1",
                "regex-test-header-2": "RegexTestValue2,RegexTestValue3",
                "My-Secret-Header": "My Secret Value",
            },
        )
        self.assertEqual(200, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 3)

        server_span = [
            span for span in span_list if span.kind == trace.SpanKind.SERVER
        ][0]

        for key, _ in not_expected.items():
            self.assertNotIn(key, server_span.attributes)

    def test_http_custom_response_headers_in_span_attributes(self):
        expected = {
            "http.response.header.custom_test_header_1": (
                "test-header-value-1",
            ),
            "http.response.header.custom_test_header_2": (
                "test-header-value-2",
            ),
            "http.response.header.my_custom_regex_header_1": (
                "my-custom-regex-value-1",
                "my-custom-regex-value-2",
            ),
            "http.response.header.my_custom_regex_header_2": (
                "my-custom-regex-value-3",
                "my-custom-regex-value-4",
            ),
            "http.response.header.my_secret_header": ("[REDACTED]",),
        }
        resp = self.client.get("/foobar")
        self.assertEqual(200, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 3)

        server_span = [
            span for span in span_list if span.kind == trace.SpanKind.SERVER
        ][0]
        self.assertSpanHasAttributes(server_span, expected)

    def test_http_custom_response_headers_not_in_span_attributes(self):
        not_expected = {
            "http.response.header.custom_test_header_3": (
                "test-header-value-3",
            ),
        }
        resp = self.client.get("/foobar")
        self.assertEqual(200, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 3)

        server_span = [
            span for span in span_list if span.kind == trace.SpanKind.SERVER
        ][0]

        for key, _ in not_expected.items():
            self.assertNotIn(key, server_span.attributes)


@patch.dict(
    "os.environ",
    {
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS: ".*my-secret.*",
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3,Regex-Test-Header-.*,Regex-Invalid-Test-Header-.*,.*my-secret.*",
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3,my-custom-regex-header-.*,invalid-regex-header-.*,.*my-secret.*",
    },
)
class TestWebSocketAppWithCustomHeaders(TestBase):
    def setUp(self):
        super().setUp()
        self.app = self._create_app()
        otel_fastapi.FastAPIInstrumentor().instrument_app(self.app)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        super().tearDown()
        with self.disable_logging():
            otel_fastapi.FastAPIInstrumentor().uninstrument_app(self.app)

    @staticmethod
    def _create_app():
        app = fastapi.FastAPI()

        @app.websocket("/foobar_web")
        async def _(websocket: fastapi.WebSocket):
            message = await websocket.receive()
            if message.get("type") == "websocket.connect":
                await websocket.send(
                    {
                        "type": "websocket.accept",
                        "headers": [
                            (b"custom-test-header-1", b"test-header-value-1"),
                            (b"custom-test-header-2", b"test-header-value-2"),
                            (b"Regex-Test-Header-1", b"Regex Test Value 1"),
                            (
                                b"regex-test-header-2",
                                b"RegexTestValue2,RegexTestValue3",
                            ),
                            (b"My-Secret-Header", b"My Secret Value"),
                        ],
                    }
                )
                await websocket.send_json({"message": "hello world"})
                await websocket.close()
            if message.get("type") == "websocket.disconnect":
                pass

        return app

    def test_web_socket_custom_request_headers_in_span_attributes(self):
        expected = {
            "http.request.header.custom_test_header_1": (
                "test-header-value-1",
            ),
            "http.request.header.custom_test_header_2": (
                "test-header-value-2",
            ),
        }

        with self.client.websocket_connect(
            "/foobar_web",
            headers={
                "custom-test-header-1": "test-header-value-1",
                "custom-test-header-2": "test-header-value-2",
            },
        ) as websocket:
            data = websocket.receive_json()
            self.assertEqual(data, {"message": "hello world"})

        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 5)

        server_span = [
            span for span in span_list if span.kind == trace.SpanKind.SERVER
        ][0]

        self.assertSpanHasAttributes(server_span, expected)

    @patch.dict(
        "os.environ",
        {
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS: ".*my-secret.*",
            OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3,Regex-Test-Header-.*,Regex-Invalid-Test-Header-.*,.*my-secret.*",
        },
    )
    def test_web_socket_custom_request_headers_not_in_span_attributes(self):
        not_expected = {
            "http.request.header.custom_test_header_3": (
                "test-header-value-3",
            ),
        }

        with self.client.websocket_connect(
            "/foobar_web",
            headers={
                "custom-test-header-1": "test-header-value-1",
                "custom-test-header-2": "test-header-value-2",
            },
        ) as websocket:
            data = websocket.receive_json()
            self.assertEqual(data, {"message": "hello world"})

        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 5)

        server_span = [
            span for span in span_list if span.kind == trace.SpanKind.SERVER
        ][0]

        for key, _ in not_expected.items():
            self.assertNotIn(key, server_span.attributes)

    def test_web_socket_custom_response_headers_in_span_attributes(self):
        expected = {
            "http.response.header.custom_test_header_1": (
                "test-header-value-1",
            ),
            "http.response.header.custom_test_header_2": (
                "test-header-value-2",
            ),
        }

        with self.client.websocket_connect("/foobar_web") as websocket:
            data = websocket.receive_json()
            self.assertEqual(data, {"message": "hello world"})

        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 5)

        server_span = [
            span for span in span_list if span.kind == trace.SpanKind.SERVER
        ][0]

        self.assertSpanHasAttributes(server_span, expected)

    def test_web_socket_custom_response_headers_not_in_span_attributes(self):
        not_expected = {
            "http.response.header.custom_test_header_3": (
                "test-header-value-3",
            ),
        }

        with self.client.websocket_connect("/foobar_web") as websocket:
            data = websocket.receive_json()
            self.assertEqual(data, {"message": "hello world"})

        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 5)

        server_span = [
            span for span in span_list if span.kind == trace.SpanKind.SERVER
        ][0]

        for key, _ in not_expected.items():
            self.assertNotIn(key, server_span.attributes)


@patch.dict(
    "os.environ",
    {
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST: "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3",
    },
)
class TestNonRecordingSpanWithCustomHeaders(TestBase):
    def setUp(self):
        super().setUp()
        self.app = fastapi.FastAPI()

        @self.app.get("/foobar")
        async def _():
            return {"message": "hello world"}

        reset_trace_globals()
        tracer_provider = trace.NoOpTracerProvider()
        trace.set_tracer_provider(tracer_provider=tracer_provider)

        self._instrumentor = otel_fastapi.FastAPIInstrumentor()
        self._instrumentor.instrument_app(self.app)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        super().tearDown()
        with self.disable_logging():
            self._instrumentor.uninstrument_app(self.app)

    def test_custom_header_not_present_in_non_recording_span(self):
        resp = self.client.get(
            "/foobar",
            headers={
                "custom-test-header-1": "test-header-value-1",
            },
        )
        self.assertEqual(200, resp.status_code)
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(span_list), 0)
