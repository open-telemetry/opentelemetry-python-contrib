# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from functools import partial

import grpc

from opentelemetry import trace
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient
from opentelemetry.test.test_base import TestBase

from ._client import simple_method
from ._hooks import RecordingHook, set_span_attribute
from ._server import create_test_server
from .protobuf import test_server_pb2_grpc


# User defined interceptor. Is used in the tests along with the opentelemetry client interceptor.
class Interceptor(
    grpc.UnaryUnaryClientInterceptor,
    grpc.UnaryStreamClientInterceptor,
    grpc.StreamUnaryClientInterceptor,
    grpc.StreamStreamClientInterceptor,
):
    def __init__(self):
        pass

    def intercept_unary_unary(self, continuation, client_call_details, request):
        return self._intercept_call(continuation, client_call_details, request)

    def intercept_unary_stream(self, continuation, client_call_details, request):
        return self._intercept_call(continuation, client_call_details, request)

    def intercept_stream_unary(self, continuation, client_call_details, request_iterator):
        return self._intercept_call(continuation, client_call_details, request_iterator)

    def intercept_stream_stream(self, continuation, client_call_details, request_iterator):
        return self._intercept_call(continuation, client_call_details, request_iterator)

    @staticmethod
    def _intercept_call(continuation, client_call_details, request_or_iterator):
        return continuation(client_call_details, request_or_iterator)


def request_hook(span, request):
    span.set_attribute("request_data", request.request_data)


def response_hook(span, response):
    span.set_attribute("response_data", response.response_data)


def request_hook_with_exception(_span, _request):
    raise Exception()  # pylint: disable=broad-exception-raised


def response_hook_with_exception(_span, _response):
    raise Exception()  # pylint: disable=broad-exception-raised


class TestHooks(TestBase):
    def setUp(self):
        super().setUp()
        self.server = create_test_server(25565)
        self.server.start()
        # use a user defined interceptor along with the opentelemetry client interceptor
        self.interceptors = [Interceptor()]

    def tearDown(self):
        super().tearDown()
        self.server.stop(None)

    def test_response_and_request_hooks(self):
        instrumentor = GrpcInstrumentorClient()

        try:
            instrumentor.instrument(
                request_hook=request_hook,
                response_hook=response_hook,
            )

            channel = grpc.insecure_channel("localhost:25565")
            channel = grpc.intercept_channel(channel, *self.interceptors)

            stub = test_server_pb2_grpc.GRPCTestServerStub(channel)

            simple_method(stub)
            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)
            span = spans[0]

            self.assertEqual(span.name, "/GRPCTestServer/SimpleMethod")
            self.assertIs(span.kind, trace.SpanKind.CLIENT)

            self.assertIn("request_data", span.attributes)
            self.assertEqual(span.attributes["request_data"], "data")

            self.assertIn("response_data", span.attributes)
            self.assertEqual(span.attributes["response_data"], "data")
        finally:
            instrumentor.uninstrument()

    def test_hooks_with_exception(self):
        instrumentor = GrpcInstrumentorClient()

        try:
            instrumentor.instrument(
                request_hook=request_hook_with_exception,
                response_hook=response_hook_with_exception,
            )

            channel = grpc.insecure_channel("localhost:25565")
            channel = grpc.intercept_channel(channel, *self.interceptors)

            stub = test_server_pb2_grpc.GRPCTestServerStub(channel)

            simple_method(stub)
            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)
            span = spans[0]

            self.assertEqual(span.name, "/GRPCTestServer/SimpleMethod")
            self.assertIs(span.kind, trace.SpanKind.CLIENT)
        finally:
            instrumentor.uninstrument()

    def test_callable_object_hooks(self):
        """Test that callable objects without __name__ are invoked."""
        instrumentor = GrpcInstrumentorClient()
        request_hook_obj = RecordingHook("callable_request_invoked")
        response_hook_obj = RecordingHook("callable_response_invoked")

        try:
            instrumentor.instrument(
                request_hook=request_hook_obj,
                response_hook=response_hook_obj,
            )

            channel = grpc.insecure_channel("localhost:25565")
            channel = grpc.intercept_channel(channel, *self.interceptors)

            stub = test_server_pb2_grpc.GRPCTestServerStub(channel)

            simple_method(stub)
            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)
            span = spans[0]

            self.assertEqual(request_hook_obj.calls, 1)
            self.assertEqual(response_hook_obj.calls, 1)

            self.assertIn("callable_request_invoked", span.attributes)
            self.assertTrue(span.attributes["callable_request_invoked"])
            self.assertIn("callable_response_invoked", span.attributes)
            self.assertTrue(span.attributes["callable_response_invoked"])
        finally:
            instrumentor.uninstrument()

    def test_partial_hooks(self):
        """Test that functools.partial hooks without __name__ are invoked."""
        instrumentor = GrpcInstrumentorClient()
        request_hook_partial = partial(
            set_span_attribute,
            "partial_request_data",
            lambda request: request.request_data,
        )
        response_hook_partial = partial(
            set_span_attribute,
            "partial_response_data",
            lambda response: response.response_data,
        )

        try:
            instrumentor.instrument(
                request_hook=request_hook_partial,
                response_hook=response_hook_partial,
            )

            channel = grpc.insecure_channel("localhost:25565")
            channel = grpc.intercept_channel(channel, *self.interceptors)

            stub = test_server_pb2_grpc.GRPCTestServerStub(channel)

            simple_method(stub)
            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)
            span = spans[0]

            self.assertIn("partial_request_data", span.attributes)
            self.assertEqual(span.attributes["partial_request_data"], "data")
            self.assertIn("partial_response_data", span.attributes)
            self.assertEqual(span.attributes["partial_response_data"], "data")
        finally:
            instrumentor.uninstrument()

    def test_callable_hook_with_exception(self):
        """Test that callable objects that raise exceptions are still invoked once."""
        instrumentor = GrpcInstrumentorClient()
        request_hook_obj = RecordingHook(raises=True)
        response_hook_obj = RecordingHook(raises=True)

        try:
            instrumentor.instrument(
                request_hook=request_hook_obj,
                response_hook=response_hook_obj,
            )

            channel = grpc.insecure_channel("localhost:25565")
            channel = grpc.intercept_channel(channel, *self.interceptors)

            stub = test_server_pb2_grpc.GRPCTestServerStub(channel)

            with self.assertLogs("opentelemetry.instrumentation.grpc._client", level="ERROR") as logs:
                simple_method(stub)
            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)
            span = spans[0]

            self.assertEqual(span.name, "/GRPCTestServer/SimpleMethod")
            self.assertIs(span.kind, trace.SpanKind.CLIENT)
            self.assertEqual(request_hook_obj.calls, 1)
            self.assertEqual(response_hook_obj.calls, 1)
            self.assertEqual(len(logs.records), 2)
            self.assertTrue(all("<unknown>" in output for output in logs.output))
        finally:
            instrumentor.uninstrument()
