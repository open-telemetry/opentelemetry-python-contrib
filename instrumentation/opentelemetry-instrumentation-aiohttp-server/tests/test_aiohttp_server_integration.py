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

from opentelemetry import metrics as metrics_api
from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.aiohttp_server import (
    AioHttpServerInstrumentor,
)
from opentelemetry.instrumentation.utils import suppress_http_instrumentation
from opentelemetry.semconv._incubating.attributes.http_attributes import (
    HTTP_METHOD,
    HTTP_STATUS_CODE,
    HTTP_URL,
)
from opentelemetry.test.globals_test import (
    reset_metrics_globals,
    reset_trace_globals,
)
from opentelemetry.test.test_base import TestBase
from opentelemetry.util._importlib_metadata import entry_points


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


@pytest.fixture(name="tracer", scope="session")
def fixture_tracer():
    test_base = TestBase()

    tracer_provider, memory_exporter = test_base.create_tracer_provider()

    reset_trace_globals()
    trace_api.set_tracer_provider(tracer_provider)

    yield tracer_provider, memory_exporter

    reset_trace_globals()


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
    app.add_routes([aiohttp.web.get("/test-path", default_handler)])
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
