# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import itertools
from http import HTTPStatus

import pytest
from sanic import Sanic, response
from sanic_testing.testing import SanicTestClient

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
    _server_active_requests_count_attrs_new,
    _server_active_requests_count_attrs_old,
    _server_duration_attrs_new,
    _server_duration_attrs_old,
    _StabilityMode,
)
from opentelemetry.instrumentation.sanic import SanicInstrumentor
from opentelemetry.semconv._incubating.attributes.http_attributes import (
    HTTP_FLAVOR,
    HTTP_HOST,
    HTTP_METHOD,
    HTTP_ROUTE,
    HTTP_SCHEME,
    HTTP_SERVER_NAME,
    HTTP_STATUS_CODE,
    HTTP_TARGET,
    HTTP_URL,
    HTTP_USER_AGENT,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_HOST_NAME,
    NET_HOST_PORT,
)
from opentelemetry.semconv.attributes.http_attributes import (
    HTTP_REQUEST_METHOD,
    HTTP_RESPONSE_STATUS_CODE,
)
from opentelemetry.semconv.attributes.network_attributes import (
    NETWORK_PROTOCOL_VERSION,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.semconv.attributes.url_attributes import (
    URL_PATH,
    URL_QUERY,
    URL_SCHEME,
)
from opentelemetry.semconv.attributes.user_agent_attributes import (
    USER_AGENT_ORIGINAL,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import StatusCode
from opentelemetry.util._importlib_metadata import entry_points
from opentelemetry.util.http import (
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE,
)

SCOPE = "opentelemetry.instrumentation.sanic"

_app_counter = itertools.count()


def create_app() -> Sanic:
    """Creates a Sanic application with a name that is unique per process."""
    return Sanic(f"otel_sanic_test_{next(_app_counter)}")


@pytest.fixture(name="test_base", scope="function")
def fixture_test_base():
    test_base = TestBase()
    test_base.setUp()
    _OpenTelemetrySemanticConventionStability._initialized = False
    try:
        yield test_base
    finally:
        # Reset semconv stability state otherwise tests can interfere with each other
        _OpenTelemetrySemanticConventionStability._initialized = False
        test_base.tearDown()


@pytest.fixture(name="instrumentor", scope="function")
def fixture_instrumentor(test_base: TestBase):
    instrumentor = SanicInstrumentor()
    instrumentor.instrument(tracer_provider=test_base.tracer_provider)
    try:
        yield instrumentor
    finally:
        instrumentor.uninstrument()


def test_checking_instrumentor_pkg_installed():
    (instrumentor_entrypoint,) = entry_points(group="opentelemetry_instrumentor", name="sanic")
    instrumentor = instrumentor_entrypoint.load()()
    assert isinstance(instrumentor, SanicInstrumentor)


def test_uninstrumented_app_creates_no_spans(test_base: TestBase):
    app = create_app()

    @app.get("/test-path")
    async def handler(request):
        return response.text("hello")

    SanicTestClient(app).get("/test-path")

    assert len(test_base.get_finished_spans()) == 0
    assert len(test_base.get_sorted_metrics(SCOPE)) == 0


@pytest.mark.parametrize(
    "path,expected_status",
    [
        ("/test-path", HTTPStatus.OK),
        ("/not-found", HTTPStatus.NOT_FOUND),
    ],
)
def test_status_code_instrumentation(test_base: TestBase, instrumentor: SanicInstrumentor, path, expected_status):
    app = create_app()

    @app.get("/test-path")
    async def handler(request):
        return response.text("hello")

    assert len(test_base.get_finished_spans()) == 0
    assert len(test_base.get_sorted_metrics(SCOPE)) == 0

    _, server_response = SanicTestClient(app).get(path)
    assert server_response.status == expected_status

    [span] = test_base.get_finished_spans()
    assert span.kind == trace_api.SpanKind.SERVER
    assert span.attributes[HTTP_METHOD] == "GET"
    assert span.attributes[HTTP_STATUS_CODE] == expected_status
    assert span.attributes[HTTP_TARGET] == path
    assert span.status.status_code == StatusCode.UNSET

    # The default semconv mode reports the old duration metric and the counter
    metrics = test_base.get_sorted_metrics(SCOPE)
    assert [metric.name for metric in metrics] == [
        "http.server.active_requests",
        "http.server.duration",
    ]


@pytest.mark.parametrize(
    "registered_route,expected_span_name,request_path,expected_route",
    [
        (
            "/test-path/<url_param:str>",
            "GET /test-path/<url_param:str>",
            "/test-path/foo",
            "/test-path/<url_param:str>",
        ),
        (
            "/object/<object_id:int>/action/<another_param:str>",
            "GET /object/<object_id:int>/action/<another_param:str>",
            "/object/1/action/bar",
            "/object/<object_id:int>/action/<another_param:str>",
        ),
        ("/test-path", "GET", "/i/dont/exist", None),
    ],
)
def test_url_params_instrumentation(
    test_base: TestBase,
    instrumentor: SanicInstrumentor,
    registered_route,
    expected_span_name,
    request_path,
    expected_route,
):
    app = create_app()

    @app.get(registered_route)
    async def handler(request, **kwargs):
        return response.text("hello")

    SanicTestClient(app).get(request_path)

    [span] = test_base.get_finished_spans()
    assert span.name == expected_span_name
    assert span.attributes[HTTP_TARGET] == request_path
    if expected_route is None:
        assert HTTP_ROUTE not in span.attributes
    else:
        assert span.attributes[HTTP_ROUTE] == expected_route


def test_span_covers_handler_and_user_middleware(test_base: TestBase, instrumentor: SanicInstrumentor):
    """The instrumentation middleware runs before and after the middleware
    registered by the application, so the server span is active in application
    request middleware and in the handler, and it is already closed in
    application response middleware."""
    app = create_app()
    observed = []

    @app.get("/test-path")
    async def handler(request):
        observed.append(("handler", trace_api.get_current_span().is_recording()))
        return response.text("hello")

    @app.middleware("request")
    async def user_request_middleware(request):
        observed.append(("request_middleware", trace_api.get_current_span().is_recording()))

    @app.middleware("response")
    async def user_response_middleware(request, server_response):
        observed.append(("response_middleware", trace_api.get_current_span().is_recording()))
        return server_response

    _, server_response = SanicTestClient(app).get("/test-path")
    assert server_response.status == HTTPStatus.OK
    assert server_response.text == "hello"

    assert observed == [
        ("request_middleware", True),
        ("handler", True),
        ("response_middleware", False),
    ]

    [span] = test_base.get_finished_spans()
    assert span.attributes[HTTP_STATUS_CODE] == HTTPStatus.OK
    assert span.end_time is not None


def test_user_response_middleware_does_not_break_span(test_base: TestBase, instrumentor: SanicInstrumentor):
    """A response middleware returning a response short-circuits the remaining
    response middleware, which must not leave the server span unclosed."""
    app = create_app()

    @app.get("/test-path")
    async def handler(request):
        return response.text("hello")

    @app.middleware("response")
    async def user_response_middleware(request, server_response):
        server_response.headers["custom-header"] = "custom-value"
        return server_response

    _, server_response = SanicTestClient(app).get("/test-path")
    assert server_response.status == HTTPStatus.OK
    # the user response middleware ran, i.e. the instrumentation one did not
    # short-circuit the remaining response middleware
    assert server_response.headers.get("custom-header") == "custom-value"

    [span] = test_base.get_finished_spans()
    assert span.end_time is not None
    assert span.attributes[HTTP_STATUS_CODE] == HTTPStatus.OK


def test_websocket_route_is_not_instrumented(test_base: TestBase, instrumentor: SanicInstrumentor):
    app = create_app()

    @app.websocket("/ws")
    async def ws_handler(request, ws):  # pragma: no cover - never upgraded
        await ws.send("hello")

    SanicTestClient(app).get("/ws")

    assert len(test_base.get_finished_spans()) == 0


def test_http_server_error_records_error(test_base: TestBase, instrumentor: SanicInstrumentor):
    app = create_app()

    @app.get("/error")
    async def handler(request):
        raise RuntimeError("boom")

    _, server_response = SanicTestClient(app).get("/error")
    assert server_response.status == HTTPStatus.INTERNAL_SERVER_ERROR

    [span] = test_base.get_finished_spans()
    assert span.attributes[HTTP_STATUS_CODE] == HTTPStatus.INTERNAL_SERVER_ERROR
    assert span.status.status_code == StatusCode.ERROR
    # unhandled exceptions are only reported through the status code
    assert len(span.events) == 0


@pytest.mark.parametrize(
    "env_var",
    ["OTEL_PYTHON_SANIC_EXCLUDED_URLS", "OTEL_PYTHON_EXCLUDED_URLS"],
)
def test_excluded_urls(test_base: TestBase, monkeypatch, env_var):
    monkeypatch.setenv(env_var, "/excluded")

    instrumentor = SanicInstrumentor()
    instrumentor.instrument(tracer_provider=test_base.tracer_provider)
    try:
        app = create_app()

        @app.get("/excluded")
        async def excluded_handler(request):
            return response.text("hello")

        @app.get("/included")
        async def included_handler(request):
            return response.text("hello")

        client = SanicTestClient(app)
        _, server_response = client.get("/excluded")
        assert server_response.status == HTTPStatus.OK
        assert len(test_base.get_finished_spans()) == 0
        assert len(test_base.get_sorted_metrics(SCOPE)) == 0

        client.get("/included")
        [span] = test_base.get_finished_spans()
        assert span.attributes[HTTP_TARGET] == "/included"
    finally:
        instrumentor.uninstrument()


@pytest.mark.parametrize(
    "stability_mode",
    [_StabilityMode.DEFAULT, _StabilityMode.HTTP],
)
def test_remove_sensitive_params(test_base: TestBase, monkeypatch, stability_mode):
    monkeypatch.setenv(OTEL_SEMCONV_STABILITY_OPT_IN, stability_mode.value)

    instrumentor = SanicInstrumentor()
    instrumentor.instrument(tracer_provider=test_base.tracer_provider)
    try:
        app = create_app()

        @app.get("/status/200")
        async def handler(request):
            return response.text("hello")

        SanicTestClient(app).get("/status/200?Signature=secret&a=b")

        [span] = test_base.get_finished_spans()
        if stability_mode == _StabilityMode.DEFAULT:
            assert span.attributes[HTTP_TARGET] == "/status/200?Signature=REDACTED&a=b"
            assert span.attributes[HTTP_URL].endswith("/status/200?Signature=REDACTED&a=b")
        else:
            assert span.attributes[URL_PATH] == "/status/200"
            assert span.attributes[URL_QUERY] == "Signature=REDACTED&a=b"
            assert HTTP_URL not in span.attributes
    finally:
        instrumentor.uninstrument()


def test_custom_request_headers(test_base: TestBase, monkeypatch):
    # pylint: disable=too-many-locals
    monkeypatch.setenv(OTEL_SEMCONV_STABILITY_OPT_IN, _StabilityMode.DEFAULT.value)
    monkeypatch.setenv(
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST,
        "Custom-Request-Header,Regex-Header-.*,.*my-secret.*",
    )
    monkeypatch.setenv(
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS,
        ".*my-secret.*",
    )

    instrumentor = SanicInstrumentor()
    instrumentor.instrument(tracer_provider=test_base.tracer_provider)
    try:
        app = create_app()

        @app.get("/status/200")
        async def handler(request):
            return response.text("hello")

        SanicTestClient(app).get(
            "/status/200",
            headers={
                "custom-request-header": "custom-request-value",
                "Regex-Header-1": "Regex Header Value 1",
                "My-Secret-Header": "My Secret Value",
                "not-captured-header": "not-captured-value",
            },
        )

        [span] = test_base.get_finished_spans()
        expected = {
            "http.request.header.custom_request_header": ("custom-request-value",),
            "http.request.header.regex_header_1": ("Regex Header Value 1",),
            "http.request.header.my_secret_header": ("[REDACTED]",),
        }
        for attribute, value in expected.items():
            assert span.attributes.get(attribute) == value

        assert "http.request.header.not_captured_header" not in span.attributes
    finally:
        instrumentor.uninstrument()


def test_custom_response_headers(test_base: TestBase, monkeypatch):
    monkeypatch.setenv(OTEL_SEMCONV_STABILITY_OPT_IN, _StabilityMode.DEFAULT.value)
    monkeypatch.setenv(
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE,
        "Custom-Response-Header,.*my-secret.*",
    )
    monkeypatch.setenv(
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS,
        ".*my-secret.*",
    )

    instrumentor = SanicInstrumentor()
    instrumentor.instrument(tracer_provider=test_base.tracer_provider)
    try:
        app = create_app()

        @app.get("/status/200")
        async def handler(request):
            return response.text(
                "hello",
                headers={
                    "custom-response-header": "custom-response-value",
                    "My-Secret-Header": "My Secret Value",
                    "not-captured-header": "not-captured-value",
                },
            )

        SanicTestClient(app).get("/status/200")

        [span] = test_base.get_finished_spans()
        expected = {
            "http.response.header.custom_response_header": ("custom-response-value",),
            "http.response.header.my_secret_header": ("[REDACTED]",),
        }
        for attribute, value in expected.items():
            assert span.attributes.get(attribute) == value

        assert "http.response.header.not_captured_header" not in span.attributes
    finally:
        instrumentor.uninstrument()


# pylint: disable=too-many-locals
def test_semantic_conventions_metrics_old_default(test_base: TestBase, monkeypatch):
    monkeypatch.setenv(OTEL_SEMCONV_STABILITY_OPT_IN, _StabilityMode.DEFAULT.value)

    instrumentor = SanicInstrumentor()
    instrumentor.instrument(tracer_provider=test_base.tracer_provider)
    try:
        app = create_app()

        @app.get("/status/200")
        async def handler(request):
            return response.text("hello")

        client = SanicTestClient(app)
        client.get("/status/200?a=b", headers={"User-Agent": "test-agent"})

        [span] = test_base.get_finished_spans()
        assert span.instrumentation_scope.schema_url == "https://opentelemetry.io/schemas/1.11.0"

        assert span.attributes.get(HTTP_METHOD) == "GET"
        assert span.attributes.get(HTTP_SCHEME) == "http"
        assert span.attributes.get(NET_HOST_NAME) == "127.0.0.1"
        assert span.attributes.get(NET_HOST_PORT) == client.port
        assert span.attributes.get(HTTP_TARGET) == "/status/200?a=b"
        assert span.attributes.get(HTTP_USER_AGENT) == "test-agent"
        assert span.attributes.get(HTTP_FLAVOR) == "1.1"
        assert span.attributes.get(HTTP_STATUS_CODE) == 200
        assert span.attributes.get(HTTP_ROUTE) == "/status/200"
        assert span.attributes.get(HTTP_HOST) == "127.0.0.1"
        assert span.attributes.get(HTTP_SERVER_NAME) == f"127.0.0.1:{client.port}"
        assert span.attributes.get(HTTP_URL) == f"http://127.0.0.1:{client.port}/status/200?a=b"

        # New semconv span attributes NOT present
        assert HTTP_REQUEST_METHOD not in span.attributes
        assert URL_SCHEME not in span.attributes
        assert SERVER_ADDRESS not in span.attributes
        assert SERVER_PORT not in span.attributes
        assert URL_PATH not in span.attributes
        assert URL_QUERY not in span.attributes
        assert USER_AGENT_ORIGINAL not in span.attributes
        assert NETWORK_PROTOCOL_VERSION not in span.attributes
        assert HTTP_RESPONSE_STATUS_CODE not in span.attributes

        metrics = test_base.get_sorted_metrics(SCOPE)
        expected_metric_names = [
            "http.server.active_requests",
            "http.server.duration",
        ]
        recommended_metrics_attrs = {
            "http.server.active_requests": _server_active_requests_count_attrs_old,
            "http.server.duration": _server_duration_attrs_old,
        }
        assert [metric.name for metric in metrics] == expected_metric_names
        for metric in metrics:
            if metric.name == "http.server.duration":
                assert metric.unit == "ms"
            for point in metric.data.data_points:
                for attr in point.attributes:
                    assert attr in recommended_metrics_attrs[metric.name]
    finally:
        instrumentor.uninstrument()


# pylint: disable=too-many-locals
def test_semantic_conventions_metrics_new(test_base: TestBase, monkeypatch):
    monkeypatch.setenv(OTEL_SEMCONV_STABILITY_OPT_IN, _StabilityMode.HTTP.value)

    instrumentor = SanicInstrumentor()
    instrumentor.instrument(tracer_provider=test_base.tracer_provider)
    try:
        app = create_app()

        @app.get("/status/200")
        async def handler(request):
            return response.text("hello")

        client = SanicTestClient(app)
        client.get("/status/200?a=b", headers={"User-Agent": "test-agent"})

        [span] = test_base.get_finished_spans()
        assert span.instrumentation_scope.schema_url == "https://opentelemetry.io/schemas/1.21.0"
        assert span.attributes.get(HTTP_REQUEST_METHOD) == "GET"
        assert span.attributes.get(URL_SCHEME) == "http"
        assert span.attributes.get(SERVER_ADDRESS) == "127.0.0.1"
        assert span.attributes.get(SERVER_PORT) == client.port
        assert span.attributes.get(URL_PATH) == "/status/200"
        assert span.attributes.get(URL_QUERY) == "a=b"
        assert span.attributes.get(USER_AGENT_ORIGINAL) == "test-agent"
        assert span.attributes.get(NETWORK_PROTOCOL_VERSION) == "1.1"
        assert span.attributes.get(HTTP_RESPONSE_STATUS_CODE) == 200
        assert span.attributes.get(HTTP_ROUTE) == "/status/200"

        # Old semconv span attributes NOT present
        assert HTTP_METHOD not in span.attributes
        assert HTTP_SCHEME not in span.attributes
        assert HTTP_TARGET not in span.attributes
        assert HTTP_USER_AGENT not in span.attributes
        assert HTTP_FLAVOR not in span.attributes
        assert HTTP_STATUS_CODE not in span.attributes
        assert HTTP_URL not in span.attributes
        assert NET_HOST_NAME not in span.attributes
        assert NET_HOST_PORT not in span.attributes
        assert HTTP_HOST not in span.attributes
        assert HTTP_SERVER_NAME not in span.attributes

        metrics = test_base.get_sorted_metrics(SCOPE)
        expected_metric_names = [
            "http.server.active_requests",
            "http.server.request.duration",
        ]
        recommended_metrics_attrs = {
            "http.server.active_requests": _server_active_requests_count_attrs_new,
            "http.server.request.duration": _server_duration_attrs_new,
        }
        assert [metric.name for metric in metrics] == expected_metric_names
        for metric in metrics:
            if metric.name == "http.server.request.duration":
                assert metric.unit == "s"
            for point in metric.data.data_points:
                for attr in point.attributes:
                    assert attr in recommended_metrics_attrs[metric.name]
    finally:
        instrumentor.uninstrument()
