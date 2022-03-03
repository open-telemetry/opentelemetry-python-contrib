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

import asyncio
import contextlib
import typing
import unittest
import urllib.parse
from functools import partial
from unittest import mock

import aiohttp
import aiohttp.test_utils
from pkg_resources import iter_entry_points

from opentelemetry.instrumentation.aiohttp_server import AioHttpServerInstrumentor
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.test_base import TestBase


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


class TestAioHttpServerIntegration(TestBase):
    URL = "/test-path"

    def setUp(self):
        super().setUp()
        AioHttpServerInstrumentor().instrument()

    def tearDown(self):
        super().tearDown()
        AioHttpServerInstrumentor().uninstrument()

    @staticmethod
    # pylint:disable=unused-argument
    async def default_handler(request, status=200):
        return aiohttp.web.Response(status=status)

    def assert_spans(self, num_spans: int):
        finished_spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(num_spans, len(finished_spans))
        if num_spans == 0:
            return None
        if num_spans == 1:
            return finished_spans[0]
        return finished_spans

    @staticmethod
    def get_default_request(url: str = URL):
        async def default_request(server: aiohttp.test_utils.TestServer):
            async with aiohttp.test_utils.TestClient(server) as session:
                await session.get(url)

        return default_request

    def test_instrument(self):
        host, port = run_with_test_server(
            self.get_default_request(), self.URL, self.default_handler
        )
        span = self.assert_spans(1)
        self.assertEqual("GET", span.attributes[SpanAttributes.HTTP_METHOD])
        self.assertEqual(
            f"http://{host}:{port}/test-path",
            span.attributes[SpanAttributes.HTTP_URL],
        )
        self.assertEqual(200, span.attributes[SpanAttributes.HTTP_STATUS_CODE])

    def test_status_codes(self):
        error_handler = partial(self.default_handler, status=400)
        host, port = run_with_test_server(
            self.get_default_request(), self.URL, error_handler
        )
        span = self.assert_spans(1)
        self.assertEqual("GET", span.attributes[SpanAttributes.HTTP_METHOD])
        self.assertEqual(
            f"http://{host}:{port}/test-path",
            span.attributes[SpanAttributes.HTTP_URL],
        )
        self.assertEqual(400, span.attributes[SpanAttributes.HTTP_STATUS_CODE])

    def test_not_recording(self):
        mock_tracer = mock.Mock()
        mock_span = mock.Mock()
        mock_span.is_recording.return_value = False
        mock_tracer.start_span.return_value = mock_span
        with mock.patch("opentelemetry.trace.get_tracer"):
            # pylint: disable=W0612
            host, port = run_with_test_server(
                self.get_default_request(), self.URL, self.default_handler
            )

            self.assertFalse(mock_span.is_recording())
            self.assertTrue(mock_span.is_recording.called)
            self.assertFalse(mock_span.set_attribute.called)
            self.assertFalse(mock_span.set_status.called)


class TestLoadingAioHttpInstrumentor(unittest.TestCase):
    def test_loading_instrumentor(self):
        entry_points = iter_entry_points(
            "opentelemetry_instrumentor", "aiohttp-server"
        )

        instrumentor = next(entry_points).load()()
        self.assertIsInstance(instrumentor, AioHttpServerInstrumentor)
