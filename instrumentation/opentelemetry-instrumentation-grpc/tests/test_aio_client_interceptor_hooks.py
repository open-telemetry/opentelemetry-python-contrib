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
try:
    from unittest import IsolatedAsyncioTestCase
except ImportError:
    # unittest.IsolatedAsyncioTestCase was introduced in Python 3.8. It's use
    # simplifies the following tests. Without it, the amount of test code
    # increases significantly, with most of the additional code handling
    # the asyncio set up.
    from unittest import TestCase

    class IsolatedAsyncioTestCase(TestCase):
        def run(self, result=None):
            self.skipTest(
                "This test requires Python 3.8 for unittest.IsolatedAsyncioTestCase"
            )


import grpc
import pytest

from opentelemetry.instrumentation.grpc import GrpcAioInstrumentorClient
from opentelemetry.test.test_base import TestBase

from ._aio_client import simple_method
from ._server import create_test_server
from .protobuf import test_server_pb2_grpc  # pylint: disable=no-name-in-module


def request_hook(span, request):
    span.set_attribute("request_data", request.request_data)


def response_hook(span, response):
    span.set_attribute("response_data", response)


def request_hook_with_exception(_span, _request):
    raise Exception()


def response_hook_with_exception(_span, _response):
    raise Exception()


@pytest.mark.asyncio
class TestAioClientInterceptorWithHooks(TestBase, IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.server = create_test_server(25565)
        self.server.start()

    def tearDown(self):
        super().tearDown()
        self.server.stop(None)

    async def test_request_and_response_hooks(self):
        instrumentor = GrpcAioInstrumentorClient()

        try:
            instrumentor.instrument(
                request_hook=request_hook,
                response_hook=response_hook,
            )

            channel = grpc.aio.insecure_channel(
                "localhost:25565",
            )
            stub = test_server_pb2_grpc.GRPCTestServerStub(channel)

            response = await simple_method(stub)
            assert response.response_data == "data"

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)
            span = spans[0]

            self.assertIn("request_data", span.attributes)
            self.assertEqual(span.attributes["request_data"], "data")

            self.assertIn("response_data", span.attributes)
            self.assertEqual(span.attributes["response_data"], "")
        finally:
            instrumentor.uninstrument()

    async def test_hooks_with_exception(self):
        instrumentor = GrpcAioInstrumentorClient()

        try:
            instrumentor.instrument(
                request_hook=request_hook_with_exception,
                response_hook=response_hook_with_exception,
            )

            channel = grpc.aio.insecure_channel(
                "localhost:25565",
            )
            stub = test_server_pb2_grpc.GRPCTestServerStub(channel)

            response = await simple_method(stub)
            assert response.response_data == "data"

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)
            span = spans[0]

            self.assertEqual(span.name, "/GRPCTestServer/SimpleMethod")
        finally:
            instrumentor.uninstrument()
