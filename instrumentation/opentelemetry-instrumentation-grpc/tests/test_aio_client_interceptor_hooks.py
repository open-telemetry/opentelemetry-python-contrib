# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
from functools import partial
from unittest import IsolatedAsyncioTestCase

import grpc

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
    raise Exception()  # pylint: disable=broad-exception-raised


def response_hook_with_exception(_span, _response):
    raise Exception()  # pylint: disable=broad-exception-raised


class CallableRequestHook:
    """Callable object without __name__ attribute."""

    def __init__(self):
        self.invoked = False
        self.span = None
        self.request = None

    def __call__(self, span, request):
        self.invoked = True
        self.span = span
        self.request = request
        span.set_attribute("callable_request_invoked", True)


class CallableResponseHook:
    """Callable object without __name__ attribute."""

    def __init__(self):
        self.invoked = False
        self.span = None
        self.response = None

    def __call__(self, span, response):
        self.invoked = True
        self.span = span
        self.response = response
        span.set_attribute("callable_response_invoked", True)


class CallableHookWithException:
    """Callable object that raises an exception."""

    def __call__(self, _span, _arg):
        raise RuntimeError("Hook exception")  # pylint: disable=broad-exception-raised


def _partial_request_hook_impl(attr_name, span, request):
    """Helper for partial hook."""
    span.set_attribute(attr_name, request.request_data)


def _partial_response_hook_impl(attr_name, span, response):
    """Helper for partial hook."""
    span.set_attribute(attr_name, response)


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

    async def test_callable_object_hooks(self):
        """Test that callable objects without __name__ are invoked."""
        instrumentor = GrpcAioInstrumentorClient()
        request_hook_obj = CallableRequestHook()
        response_hook_obj = CallableResponseHook()

        try:
            instrumentor.instrument(
                request_hook=request_hook_obj,
                response_hook=response_hook_obj,
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

            self.assertTrue(request_hook_obj.invoked)
            self.assertTrue(response_hook_obj.invoked)

            self.assertIn("callable_request_invoked", span.attributes)
            self.assertTrue(span.attributes["callable_request_invoked"])
            self.assertIn("callable_response_invoked", span.attributes)
            self.assertTrue(span.attributes["callable_response_invoked"])
        finally:
            instrumentor.uninstrument()

    async def test_partial_hooks(self):
        """Test that functools.partial hooks without __name__ are invoked."""
        instrumentor = GrpcAioInstrumentorClient()
        request_hook_partial = partial(
            _partial_request_hook_impl, "partial_request_data"
        )
        response_hook_partial = partial(
            _partial_response_hook_impl, "partial_response_data"
        )

        try:
            instrumentor.instrument(
                request_hook=request_hook_partial,
                response_hook=response_hook_partial,
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

            self.assertIn("partial_request_data", span.attributes)
            self.assertEqual(span.attributes["partial_request_data"], "data")
            self.assertIn("partial_response_data", span.attributes)
            self.assertEqual(span.attributes["partial_response_data"], "")
        finally:
            instrumentor.uninstrument()

    async def test_callable_hook_with_exception(self):
        """Test that callable objects that raise exceptions are still invoked once."""
        instrumentor = GrpcAioInstrumentorClient()
        request_hook_obj = CallableHookWithException()
        response_hook_obj = CallableHookWithException()

        try:
            instrumentor.instrument(
                request_hook=request_hook_obj,
                response_hook=response_hook_obj,
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
