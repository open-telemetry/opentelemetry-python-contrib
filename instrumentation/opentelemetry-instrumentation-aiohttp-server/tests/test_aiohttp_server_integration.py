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

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.aiohttp_server import (
    AioHttpServerInstrumentor,
)
from opentelemetry.instrumentation.utils import suppress_http_instrumentation
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.globals_test import reset_trace_globals
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
    server_fixture,
    aiohttp_client,
    url,
    expected_method,
    expected_status_code,
):
    _, memory_exporter = tracer
    server, _ = server_fixture

    assert len(memory_exporter.get_finished_spans()) == 0

    client = await aiohttp_client(server)
    await client.get(url)

    assert len(memory_exporter.get_finished_spans()) == 1

    [span] = memory_exporter.get_finished_spans()

    assert expected_method.value == span.attributes[SpanAttributes.HTTP_METHOD]
    assert (
        expected_status_code
        == span.attributes[SpanAttributes.HTTP_STATUS_CODE]
    )

    assert (
        f"http://{server.host}:{server.port}{url}"
        == span.attributes[SpanAttributes.HTTP_URL]
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
