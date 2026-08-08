# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
from unittest import IsolatedAsyncioTestCase

import grpc

from opentelemetry.instrumentation.grpc import GrpcAioInstrumentorClient
from opentelemetry.test.test_base import TestBase

from ._aio_client import client_streaming_method, simple_method
from ._server import create_test_server
from .protobuf import test_server_pb2_grpc  # pylint: disable=no-name-in-module


def request_hook(span, request):
    span.set_attribute("request_data", request.request_data)


def response_hook(span, response):
    span.set_attribute("response_data", response.response_data)


def request_hook_with_exception(_span, _request):
    raise Exception()  # pylint: disable=broad-exception-raised


def response_hook_with_exception(_span, _response):
    raise Exception()  # pylint: disable=broad-exception-raised


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
            self.assertEqual(span.attributes["response_data"], "data")
        finally:
            instrumentor.uninstrument()

    async def test_response_hook_stream_unary(self):
        instrumentor = GrpcAioInstrumentorClient()

        try:
            instrumentor.instrument(response_hook=response_hook)

            channel = grpc.aio.insecure_channel("localhost:25565")
            stub = test_server_pb2_grpc.GRPCTestServerStub(channel)

            response = await client_streaming_method(stub)
            assert response.response_data == "data"

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)
            span = spans[0]

            self.assertIn("response_data", span.attributes)
            self.assertEqual(span.attributes["response_data"], "data")
        finally:
            instrumentor.uninstrument()

    async def test_response_hook_not_called_on_error(self):
        """There is no response message to hand the hook when the RPC fails."""
        instrumentor = GrpcAioInstrumentorClient()

        try:
            instrumentor.instrument(response_hook=response_hook)

            channel = grpc.aio.insecure_channel("localhost:25565")
            stub = test_server_pb2_grpc.GRPCTestServerStub(channel)

            with self.assertRaises(grpc.RpcError):
                await simple_method(stub, error=True)

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)

            self.assertNotIn("response_data", spans[0].attributes)
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
