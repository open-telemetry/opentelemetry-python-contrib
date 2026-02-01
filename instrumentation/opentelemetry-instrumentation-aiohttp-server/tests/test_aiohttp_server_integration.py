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

from enum import Enum
from http import HTTPStatus

import aiohttp
import pytest
import pytest_asyncio
from multidict import CIMultiDict

from opentelemetry.instrumentation._semconv import (
    HTTP_DURATION_HISTOGRAM_BUCKETS_NEW,
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
    _server_active_requests_count_attrs_new,
    _server_active_requests_count_attrs_old,
    _server_duration_attrs_new,
    _server_duration_attrs_old,
    _StabilityMode,
)
from opentelemetry.instrumentation.aiohttp_server import (
    AioHttpServerInstrumentor,
)
from opentelemetry.instrumentation.utils import suppress_http_instrumentation
from opentelemetry.sdk.metrics.export import (
    HistogramDataPoint,
)
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.semconv._incubating.attributes.http_attributes import (
    HTTP_FLAVOR,
    HTTP_METHOD,
    HTTP_ROUTE,
    HTTP_SCHEME,
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
from opentelemetry.util._importlib_metadata import entry_points
from opentelemetry.util.http import (
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE,
)


class HTTPMethod(Enum):
    """HTTP methods and descriptions"""

    def __repr__(self):
        return f"{self.value}"

    CONNECT = "CONNECT"
    DELETE = "DELETE"
    GET = "GET"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"
    PATCH = "PATCH"
    POST = "POST"
    PUT = "PUT"
    TRACE = "TRACE"


@pytest.fixture(name="test_base", scope="function")
def fixture_test_base():
    test_base = TestBase()
    test_base.setUp()
    try:
        yield test_base
    finally:
        test_base.tearDown()


@pytest.fixture(name="tracer", scope="function")
def fixture_tracer(test_base: TestBase):
    return test_base.tracer_provider, test_base.memory_exporter


@pytest.fixture(name="meter", scope="function")
def fixture_meter(test_base: TestBase):
    return test_base.meter_provider, test_base.memory_metrics_reader


async def default_handler(request, status=200):
    return aiohttp.web.Response(status=status)


@pytest.fixture(name="suppress")
def fixture_suppress():
    return False


@pytest_asyncio.fixture(name="server_fixture")
async def fixture_server_fixture(tracer, aiohttp_server, suppress):
    tracer_provider, _ = tracer

    AioHttpServerInstrumentor().instrument(tracer_provider=tracer_provider)

    app = aiohttp.web.Application()
    app.add_routes([aiohttp.web.get("/test-path", default_handler)])
    if suppress:
        with suppress_http_instrumentation():
            server = await aiohttp_server(app)
    else:
        server = await aiohttp_server(app)

    yield server, app

    AioHttpServerInstrumentor().uninstrument()


def test_checking_instrumentor_pkg_installed():
    (instrumentor_entrypoint,) = entry_points(
        group="opentelemetry_instrumentor", name="aiohttp-server"
    )
    instrumentor = instrumentor_entrypoint.load()()
    assert isinstance(instrumentor, AioHttpServerInstrumentor)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url, expected_method, expected_status_code",
    [
        ("/test-path", HTTPMethod.GET, HTTPStatus.OK),
        ("/not-found", HTTPMethod.GET, HTTPStatus.NOT_FOUND),
    ],
)
async def test_status_code_instrumentation(
    test_base: TestBase,
    server_fixture,
    aiohttp_client,
    url,
    expected_method,
    expected_status_code,
):
    server, _ = server_fixture

    assert len(test_base.get_finished_spans()) == 0
    metrics = test_base.get_sorted_metrics()
    assert len(metrics) == 0

    client = await aiohttp_client(server)
    await client.get(url)

    assert len(test_base.get_finished_spans()) == 1
    metrics = test_base.get_sorted_metrics()
    assert len(metrics) == 2

    [span] = test_base.get_finished_spans()
    assert expected_method.value == span.attributes[HTTP_METHOD]
    assert expected_status_code == span.attributes[HTTP_STATUS_CODE]
    assert url == span.attributes[HTTP_TARGET]


@pytest.mark.asyncio
@pytest.mark.parametrize("suppress", [True])
async def test_suppress_instrumentation(
    test_base: TestBase, server_fixture, aiohttp_client
):
    server, _ = server_fixture
    assert len(test_base.get_finished_spans()) == 0

    client = await aiohttp_client(server)
    await client.get("/test-path")

    assert len(test_base.get_finished_spans()) == 0


@pytest.mark.asyncio
async def test_remove_sensitive_params(
    test_base: TestBase, aiohttp_server, monkeypatch
):
    """Test that sensitive information in URLs is properly redacted."""
    # Use old semconv to test HTTP_URL redaction
    monkeypatch.setenv(
        OTEL_SEMCONV_STABILITY_OPT_IN, _StabilityMode.DEFAULT.value
    )
    _OpenTelemetrySemanticConventionStability._initialized = False

    # Set up instrumentation
    AioHttpServerInstrumentor().instrument()

    # Create app with test route
    app = aiohttp.web.Application()

    async def handler(request):
        return aiohttp.web.Response(text="hello")

    app.router.add_get("/status/200", handler)

    # Start the server
    server = await aiohttp_server(app)

    # Make request with sensitive data in URL
    url = f"http://username:password@{server.host}:{server.port}/status/200?Signature=secret"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            assert response.status == 200
            assert await response.text() == "hello"

    # Verify redaction in span attributes
    spans = test_base.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.attributes[HTTP_METHOD] == "GET"
    assert span.attributes[HTTP_STATUS_CODE] == 200
    assert (
        span.attributes[HTTP_URL]
        == f"http://{server.host}:{server.port}/status/200?Signature=REDACTED"
    )

    # Clean up
    AioHttpServerInstrumentor().uninstrument()


@pytest.mark.asyncio
async def test_remove_sensitive_params_new(
    test_base: TestBase, aiohttp_server, monkeypatch
):
    """Test URL handling with new semantic conventions (no redaction for URL_PATH/URL_QUERY)."""
    # Use new semconv
    monkeypatch.setenv(
        OTEL_SEMCONV_STABILITY_OPT_IN, _StabilityMode.HTTP.value
    )
    _OpenTelemetrySemanticConventionStability._initialized = False

    # Set up instrumentation
    AioHttpServerInstrumentor().instrument()

    # Create app with test route
    app = aiohttp.web.Application()

    async def handler(request):
        return aiohttp.web.Response(text="hello")

    app.router.add_get("/status/200", handler)

    # Start the server
    server = await aiohttp_server(app)

    # Make request with sensitive data in URL
    url = f"http://username:password@{server.host}:{server.port}/status/200?Signature=secret"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            assert response.status == 200
            assert await response.text() == "hello"

    # Verify span attributes with new semconv
    spans = test_base.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.attributes[HTTP_REQUEST_METHOD] == "GET"
    assert span.attributes[HTTP_RESPONSE_STATUS_CODE] == 200
    assert span.attributes[URL_PATH] == "/status/200"
    assert span.attributes[URL_QUERY] == "Signature=REDACTED"
    assert HTTP_URL not in span.attributes

    # Clean up
    AioHttpServerInstrumentor().uninstrument()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "env_var",
    ["OTEL_PYTHON_AIOHTTP_SERVER_EXCLUDED_URLS", "OTEL_PYTHON_EXCLUDED_URLS"],
)
async def test_excluded_urls(
    test_base: TestBase, aiohttp_server, monkeypatch, env_var
):
    """Test that excluded env vars are taken into account."""
    monkeypatch.setenv(env_var, "/status/200")
    AioHttpServerInstrumentor().instrument()

    app = aiohttp.web.Application()

    async def handler(request):
        return aiohttp.web.Response(text="hello")

    app.router.add_get("/status/200", handler)

    server = await aiohttp_server(app)

    url = f"http://{server.host}:{server.port}/status/200"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            assert response.status == 200
            assert await response.text() == "hello"

    spans = test_base.get_finished_spans()
    assert len(spans) == 0

    metrics = test_base.get_sorted_metrics()
    assert len(metrics) == 0

    AioHttpServerInstrumentor().uninstrument()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tracer",
    [
        TestBase().create_tracer_provider(
            sampler=ParentBased(TraceIdRatioBased(0.05))
        )
    ],
)
async def test_non_global_tracer_provider(
    tracer,
    server_fixture,
    aiohttp_client,
):
    n_requests = 1000
    collection_ratio = 0.05
    n_expected_trace_ids = n_requests * collection_ratio

    _, memory_exporter = tracer
    server, _ = server_fixture

    assert len(memory_exporter.get_finished_spans()) == 0

    client = await aiohttp_client(server)
    for _ in range(n_requests):
        await client.get("/test-path")

    trace_ids = {
        span.context.trace_id
        for span in memory_exporter.get_finished_spans()
        if span.context is not None
    }
    assert (
        0.5 * n_expected_trace_ids
        <= len(trace_ids)
        <= 1.5 * n_expected_trace_ids
    )


@pytest.mark.asyncio
async def test_custom_request_headers(
    test_base: TestBase, aiohttp_server, monkeypatch
):
    # pylint: disable=too-many-locals
    monkeypatch.setenv(
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS,
        ".*my-secret.*",
    )
    monkeypatch.setenv(
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST,
        "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3,Regex-Test-Header-.*,Regex-Invalid-Test-Header-.*,.*my-secret.*",
    )
    AioHttpServerInstrumentor().instrument()

    app = aiohttp.web.Application()

    async def handler(request):
        return aiohttp.web.Response(text="hello")

    app.router.add_get("/status/200", handler)

    server = await aiohttp_server(app)

    url = f"http://{server.host}:{server.port}/status/200"
    async with aiohttp.ClientSession() as session:
        headers = {
            "custom-test-header-1": "test-header-value-1",
            "custom-test-header-2": "test-header-value-2",
            "Regex-Test-Header-1": "Regex Test Value 1",
            "regex-test-header-2": "RegexTestValue2,RegexTestValue3",
            "My-Secret-Header": "My Secret Value",
        }
        async with session.get(url, headers=headers) as response:
            assert response.status == 200
            assert await response.text() == "hello"

    spans = test_base.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    expected = {
        "http.request.header.custom_test_header_1": ("test-header-value-1",),
        "http.request.header.custom_test_header_2": ("test-header-value-2",),
        "http.request.header.regex_test_header_1": ("Regex Test Value 1",),
        "http.request.header.regex_test_header_2": (
            "RegexTestValue2,RegexTestValue3",
        ),
        "http.request.header.my_secret_header": ("[REDACTED]",),
    }

    for attribute, value in expected.items():
        assert span.attributes.get(attribute) == value

    assert "http.request.header.custom_test_header_3" not in span.attributes

    AioHttpServerInstrumentor().uninstrument()


@pytest.mark.asyncio
async def test_custom_response_headers(
    test_base: TestBase, aiohttp_server, monkeypatch
):
    monkeypatch.setenv(
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS,
        ".*my-secret.*",
    )
    monkeypatch.setenv(
        OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE,
        "Custom-Test-Header-1,Custom-Test-Header-2,Custom-Test-Header-3,my-custom-regex-header-.*,invalid-regex-header-.*,.*my-secret.*",
    )
    AioHttpServerInstrumentor().instrument()

    app = aiohttp.web.Application()

    async def handler(request):
        headers = CIMultiDict(
            **{
                "custom-test-header-1": "test-header-value-1",
                "custom-test-header-2": "test-header-value-2",
                "my-custom-regex-header-1": "my-custom-regex-value-1,my-custom-regex-value-2",
                "My-Custom-Regex-Header-2": "my-custom-regex-value-3,my-custom-regex-value-4",
                "My-Secret-Header": "My Secret Value",
            }
        )
        return aiohttp.web.Response(text="hello", headers=headers)

    app.router.add_get("/status/200", handler)

    server = await aiohttp_server(app)

    url = f"http://{server.host}:{server.port}/status/200"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            assert response.status == 200
            assert await response.text() == "hello"

    spans = test_base.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    expected = {
        "http.response.header.custom_test_header_1": ("test-header-value-1",),
        "http.response.header.custom_test_header_2": ("test-header-value-2",),
        "http.response.header.my_custom_regex_header_1": (
            "my-custom-regex-value-1,my-custom-regex-value-2",
        ),
        "http.response.header.my_custom_regex_header_2": (
            "my-custom-regex-value-3,my-custom-regex-value-4",
        ),
        "http.response.header.my_secret_header": ("[REDACTED]",),
    }

    for attribute, value in expected.items():
        assert span.attributes.get(attribute) == value

    assert "http.response.header.custom_test_header_3" not in span.attributes

    AioHttpServerInstrumentor().uninstrument()


# pylint: disable=too-many-locals
@pytest.mark.asyncio
async def test_semantic_conventions_metrics_old_default(
    test_base: TestBase, aiohttp_server, monkeypatch
):
    monkeypatch.setenv(
        OTEL_SEMCONV_STABILITY_OPT_IN, _StabilityMode.DEFAULT.value
    )
    _OpenTelemetrySemanticConventionStability._initialized = False

    AioHttpServerInstrumentor().instrument()
    app = aiohttp.web.Application()
    app.router.add_get("/test-path", default_handler)
    server = await aiohttp_server(app)
    client_session = aiohttp.ClientSession()
    try:
        url = f"http://{server.host}:{server.port}/test-path?query=test"
        async with client_session.get(  # pylint: disable=not-async-context-manager
            url, headers={"User-Agent": "test-agent"}
        ) as response:
            assert response.status == 200
        spans = test_base.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]

        # Verify old semconv schema URL
        assert (
            span.instrumentation_scope.schema_url
            == "https://opentelemetry.io/schemas/1.11.0"
        )

        # Old semconv span attributes present
        assert span.attributes.get(HTTP_METHOD) == "GET"
        assert span.attributes.get(HTTP_SCHEME) == "http"
        assert span.attributes.get(NET_HOST_NAME) == server.host
        assert span.attributes.get(NET_HOST_PORT) == server.port
        assert span.attributes.get(HTTP_TARGET) == "/test-path?query=test"
        assert span.attributes.get(HTTP_USER_AGENT) == "test-agent"
        assert span.attributes.get(HTTP_FLAVOR) == "1.1"
        assert span.attributes.get(HTTP_STATUS_CODE) == 200
        assert span.attributes.get(HTTP_ROUTE) == "default_handler"
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

        metrics = test_base.get_sorted_metrics()
        expected_metric_names = [
            "http.server.active_requests",
            "http.server.duration",
        ]
        recommended_metrics_attrs = {
            "http.server.active_requests": _server_active_requests_count_attrs_old,
            "http.server.duration": _server_duration_attrs_old,
        }
        for metric in metrics:
            assert metric.name in expected_metric_names
            if metric.name == "http.server.duration":
                assert metric.unit == "ms"
            for point in metric.data.data_points:
                for attr in point.attributes:
                    assert attr in recommended_metrics_attrs[metric.name]

    finally:
        await client_session.close()
        AioHttpServerInstrumentor().uninstrument()


# pylint: disable=too-many-locals
@pytest.mark.asyncio
async def test_semantic_conventions_metrics_new(
    test_base: TestBase, meter, aiohttp_server, monkeypatch
):
    monkeypatch.setenv(
        OTEL_SEMCONV_STABILITY_OPT_IN, _StabilityMode.HTTP.value
    )
    _OpenTelemetrySemanticConventionStability._initialized = False

    AioHttpServerInstrumentor().instrument()
    app = aiohttp.web.Application()
    app.router.add_get("/test-path", default_handler)
    server = await aiohttp_server(app)
    client_session = aiohttp.ClientSession()
    try:
        url = f"http://{server.host}:{server.port}/test-path?query=test"
        async with client_session.get(  # pylint: disable=not-async-context-manager
            url, headers={"User-Agent": "test-agent"}
        ) as response:
            assert response.status == 200
        spans = test_base.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]

        # Verify new semconv schema URL
        assert (
            span.instrumentation_scope.schema_url
            == "https://opentelemetry.io/schemas/1.21.0"
        )

        # New semconv span attributes present
        assert span.attributes.get(HTTP_REQUEST_METHOD) == "GET"
        assert span.attributes.get(URL_SCHEME) == "http"
        assert span.attributes.get(SERVER_ADDRESS) == server.host
        assert span.attributes.get(SERVER_PORT) == server.port
        assert span.attributes.get(URL_PATH) == "/test-path"
        assert span.attributes.get(URL_QUERY) == "query=test"
        assert span.attributes.get(USER_AGENT_ORIGINAL) == "test-agent"
        assert span.attributes.get(NETWORK_PROTOCOL_VERSION) == "1.1"
        assert span.attributes.get(HTTP_RESPONSE_STATUS_CODE) == 200
        assert span.attributes.get(HTTP_ROUTE) == "default_handler"
        # Old semconv span attributes NOT present
        assert HTTP_METHOD not in span.attributes
        assert HTTP_SCHEME not in span.attributes
        assert NET_HOST_NAME not in span.attributes
        assert NET_HOST_PORT not in span.attributes
        assert HTTP_TARGET not in span.attributes
        assert HTTP_USER_AGENT not in span.attributes
        assert HTTP_FLAVOR not in span.attributes
        assert HTTP_STATUS_CODE not in span.attributes

        metrics = test_base.get_sorted_metrics()
        expected_metric_names = [
            "http.server.active_requests",
            "http.server.request.duration",
        ]
        recommended_metrics_attrs = {
            "http.server.active_requests": _server_active_requests_count_attrs_new,
            "http.server.request.duration": _server_duration_attrs_new,
        }
        for metric in metrics:
            assert metric.name in expected_metric_names
            if metric.name == "http.server.request.duration":
                assert metric.unit == "s"
            for point in metric.data.data_points:
                if (
                    isinstance(point, HistogramDataPoint)
                    and metric.name == "http.server.request.duration"
                ):
                    assert (
                        point.explicit_bounds
                        == HTTP_DURATION_HISTOGRAM_BUCKETS_NEW
                    )
                for attr in point.attributes:
                    assert attr in recommended_metrics_attrs[metric.name]

    finally:
        await client_session.close()
        AioHttpServerInstrumentor().uninstrument()


# pylint: disable=too-many-locals
# pylint: disable=too-many-statements
@pytest.mark.asyncio
async def test_semantic_conventions_metrics_both(
    test_base: TestBase, meter, aiohttp_server, monkeypatch
):
    monkeypatch.setenv(
        OTEL_SEMCONV_STABILITY_OPT_IN, _StabilityMode.HTTP_DUP.value
    )
    _OpenTelemetrySemanticConventionStability._initialized = False

    AioHttpServerInstrumentor().instrument()
    app = aiohttp.web.Application()
    app.router.add_get("/test-path", default_handler)
    server = await aiohttp_server(app)
    client_session = aiohttp.ClientSession()
    try:
        url = f"http://{server.host}:{server.port}/test-path?query=test"
        async with client_session.get(  # pylint: disable=not-async-context-manager
            url, headers={"User-Agent": "test-agent"}
        ) as response:
            assert response.status == 200
        spans = test_base.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]

        # Verify new semconv schema URL (both mode uses new schema)
        assert (
            span.instrumentation_scope.schema_url
            == "https://opentelemetry.io/schemas/1.21.0"
        )

        # Both old and new semconv span attributes present
        assert span.attributes.get(HTTP_METHOD) == "GET"
        assert span.attributes.get(HTTP_REQUEST_METHOD) == "GET"
        assert span.attributes.get(HTTP_SCHEME) == "http"
        assert span.attributes.get(URL_SCHEME) == "http"
        assert span.attributes.get(NET_HOST_NAME) == server.host
        assert span.attributes.get(SERVER_ADDRESS) == server.host
        assert span.attributes.get(NET_HOST_PORT) == server.port
        assert span.attributes.get(SERVER_PORT) == server.port
        assert span.attributes.get(HTTP_TARGET) == "/test-path?query=test"
        assert span.attributes.get(URL_PATH) == "/test-path"
        assert span.attributes.get(URL_QUERY) == "query=test"
        assert span.attributes.get(HTTP_USER_AGENT) == "test-agent"
        assert span.attributes.get(USER_AGENT_ORIGINAL) == "test-agent"
        assert span.attributes.get(HTTP_FLAVOR) == "1.1"
        assert span.attributes.get(NETWORK_PROTOCOL_VERSION) == "1.1"
        assert span.attributes.get(HTTP_STATUS_CODE) == 200
        assert span.attributes.get(HTTP_RESPONSE_STATUS_CODE) == 200
        assert span.attributes.get(HTTP_ROUTE) == "default_handler"

        metrics = test_base.get_sorted_metrics()
        assert len(metrics) == 3  # Both duration metrics + active requests
        server_active_requests_count_attrs_both = list(
            _server_active_requests_count_attrs_old
        )
        server_active_requests_count_attrs_both.extend(
            _server_active_requests_count_attrs_new
        )
        recommended_metrics_attrs = {
            "http.server.active_requests": server_active_requests_count_attrs_both,
            "http.server.duration": _server_duration_attrs_old,
            "http.server.request.duration": _server_duration_attrs_new,
        }
        for metric in metrics:
            if metric.unit == "ms":
                assert metric.name == "http.server.duration"
            elif metric.unit == "s":
                assert metric.name == "http.server.request.duration"
            else:
                assert metric.name == "http.server.active_requests"

            for point in metric.data.data_points:
                if (
                    isinstance(point, HistogramDataPoint)
                    and metric.name == "http.server.request.duration"
                ):
                    assert (
                        point.explicit_bounds
                        == HTTP_DURATION_HISTOGRAM_BUCKETS_NEW
                    )
                for attr in point.attributes:
                    assert attr in recommended_metrics_attrs[metric.name]

    finally:
        await client_session.close()
        AioHttpServerInstrumentor().uninstrument()
