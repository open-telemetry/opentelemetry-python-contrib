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

from opentelemetry import metrics as metrics_api
from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.aiohttp_server import (
    AioHttpServerInstrumentor,
)
from opentelemetry.instrumentation.utils import suppress_http_instrumentation
from opentelemetry.semconv._incubating.attributes.http_attributes import (
    HTTP_METHOD,
    HTTP_STATUS_CODE,
    HTTP_TARGET,
    HTTP_URL,
)
from opentelemetry.test.globals_test import (
    reset_metrics_globals,
    reset_trace_globals,
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


@pytest.fixture(name="tracer", scope="function")
def fixture_tracer():
    test_base = TestBase()

    tracer_provider, memory_exporter = test_base.create_tracer_provider()

    reset_trace_globals()
    trace_api.set_tracer_provider(tracer_provider)

    yield tracer_provider, memory_exporter

    reset_trace_globals()
    memory_exporter.clear()


@pytest.fixture(name="meter", scope="function")
def fixture_meter():
    test_base = TestBase()

    meter_provider, memory_reader = test_base.create_meter_provider()

    reset_metrics_globals()
    metrics_api.set_meter_provider(meter_provider)

    yield meter_provider, memory_reader

    reset_metrics_globals()


async def default_handler(request, status=200):
    return aiohttp.web.Response(status=status)


@pytest.fixture(name="suppress")
def fixture_suppress():
    return False


@pytest_asyncio.fixture(name="server_fixture")
async def fixture_server_fixture(tracer, aiohttp_server, suppress):
    _, memory_exporter = tracer

    AioHttpServerInstrumentor().instrument()

    app = aiohttp.web.Application()
    app.add_routes(
        [
            aiohttp.web.get("/test-path", default_handler),
            aiohttp.web.get("/test-path/{url_param}", default_handler),
            aiohttp.web.get(
                "/object/{object_id}/action/{another_param}", default_handler
            ),
        ]
    )
    if suppress:
        with suppress_http_instrumentation():
            server = await aiohttp_server(app)
    else:
        server = await aiohttp_server(app)

    yield server, app

    memory_exporter.clear()

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
    tracer,
    meter,
    server_fixture,
    aiohttp_client,
    url,
    expected_method,
    expected_status_code,
):
    _, memory_exporter = tracer
    _, metrics_reader = meter
    server, _ = server_fixture

    assert len(memory_exporter.get_finished_spans()) == 0
    metrics = _get_sorted_metrics(metrics_reader.get_metrics_data())
    assert len(metrics) == 0

    client = await aiohttp_client(server)
    await client.get(url)

    assert len(memory_exporter.get_finished_spans()) == 1
    metrics = _get_sorted_metrics(metrics_reader.get_metrics_data())
    assert len(metrics) == 2

    [span] = memory_exporter.get_finished_spans()

    assert expected_method.value == span.attributes[HTTP_METHOD]
    assert expected_status_code == span.attributes[HTTP_STATUS_CODE]

    assert (
        f"http://{server.host}:{server.port}{url}" == span.attributes[HTTP_URL]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "span_name, example_paths",
    [
        (
            "GET /test-path/{url_param}",
            (
                "/test-path/foo",
                "/test-path/bar",
            ),
        ),
        (
            "GET /object/{object_id}/action/{another_param}",
            (
                "/object/1/action/bar",
                "/object/234/action/baz",
            ),
        ),
        (
            "GET",
            (
                "/i/dont/exist",
                "/me-neither",
            ),
        ),
    ],
)
async def test_url_params_instrumentation(
    tracer,
    server_fixture,
    aiohttp_client,
    span_name,
    example_paths,
):
    _, memory_exporter = tracer
    server, _ = server_fixture

    assert len(memory_exporter.get_finished_spans()) == 0

    client = await aiohttp_client(server)
    for path in example_paths:
        await client.get(path)

    assert len(memory_exporter.get_finished_spans()) == 2

    for request_path, span in zip(
        example_paths, memory_exporter.get_finished_spans()
    ):
        assert span_name == span.name
        assert request_path == span.attributes[HTTP_TARGET]
        full_url = f"http://{server.host}:{server.port}{request_path}"
        assert full_url == span.attributes[HTTP_URL]


@pytest.mark.asyncio
@pytest.mark.parametrize("suppress", [True])
async def test_suppress_instrumentation(
    tracer, server_fixture, aiohttp_client
):
    _, memory_exporter = tracer
    server, _ = server_fixture
    assert len(memory_exporter.get_finished_spans()) == 0

    client = await aiohttp_client(server)
    await client.get("/test-path")

    assert len(memory_exporter.get_finished_spans()) == 0


@pytest.mark.asyncio
async def test_remove_sensitive_params(tracer, aiohttp_server):
    """Test that sensitive information in URLs is properly redacted."""
    _, memory_exporter = tracer

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
    spans = memory_exporter.get_finished_spans()
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
    memory_exporter.clear()


def _get_sorted_metrics(metrics_data):
    resource_metrics = metrics_data.resource_metrics if metrics_data else []

    all_metrics = []
    for metrics in resource_metrics:
        for scope_metrics in metrics.scope_metrics:
            all_metrics.extend(scope_metrics.metrics)

    return sorted(
        all_metrics,
        key=lambda m: m.name,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "env_var",
    ["OTEL_PYTHON_AIOHTTP_SERVER_EXCLUDED_URLS", "OTEL_PYTHON_EXCLUDED_URLS"],
)
async def test_excluded_urls(
    tracer, meter, aiohttp_server, monkeypatch, env_var
):
    """Test that excluded env vars are taken into account."""
    _, memory_exporter = tracer
    _, metrics_reader = meter

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

    spans = memory_exporter.get_finished_spans()
    assert len(spans) == 0

    metrics = _get_sorted_metrics(metrics_reader.get_metrics_data())
    assert len(metrics) == 0

    AioHttpServerInstrumentor().uninstrument()


@pytest.mark.asyncio
async def test_custom_request_headers(tracer, aiohttp_server, monkeypatch):
    # pylint: disable=too-many-locals
    _, memory_exporter = tracer

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

    spans = memory_exporter.get_finished_spans()
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
async def test_custom_response_headers(tracer, aiohttp_server, monkeypatch):
    _, memory_exporter = tracer

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

    spans = memory_exporter.get_finished_spans()
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
