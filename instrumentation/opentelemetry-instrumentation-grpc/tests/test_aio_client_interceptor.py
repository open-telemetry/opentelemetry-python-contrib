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
from unittest import IsolatedAsyncioTestCase

import grpc

import opentelemetry.instrumentation.grpc
from opentelemetry import trace
from opentelemetry.instrumentation.grpc import (
    GrpcAioInstrumentorClient,
    aio_client_interceptors,
)
from opentelemetry.instrumentation.grpc._aio_client import (
    UnaryUnaryAioClientInterceptor,
)
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.propagate import get_global_textmap, set_global_textmap
from opentelemetry.semconv._incubating.attributes.rpc_attributes import (
    RPC_GRPC_STATUS_CODE,
    RPC_METHOD,
    RPC_SERVICE,
    RPC_SYSTEM,
)
from opentelemetry.test.mock_textmap import MockTextMapPropagator
from opentelemetry.test.test_base import TestBase

from ._aio_client import (
    bidirectional_streaming_method,
    client_streaming_method,
    server_streaming_method,
    simple_method,
)
from ._server import create_test_server
from .protobuf import test_server_pb2_grpc  # pylint: disable=no-name-in-module


class RecordingInterceptor(grpc.aio.UnaryUnaryClientInterceptor):
    recorded_details = None

    async def intercept_unary_unary(
        self, continuation, client_call_details, request
    ):
        self.recorded_details = client_call_details
        return await continuation(client_call_details, request)


class TestAioClientInterceptor(TestBase, IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.server = create_test_server(25565)
        self.server.start()

        interceptors = aio_client_interceptors()
        self._channel = grpc.aio.insecure_channel(
            "localhost:25565", interceptors=interceptors
        )

        self._stub = test_server_pb2_grpc.GRPCTestServerStub(self._channel)

    def tearDown(self):
        super().tearDown()
        self.server.stop(1000)

    async def asyncTearDown(self):
        await self._channel.close()

    async def test_instrument(self):
        instrumentor = GrpcAioInstrumentorClient()

        try:
            instrumentor.instrument()

            channel = grpc.aio.insecure_channel("localhost:25565")
            stub = test_server_pb2_grpc.GRPCTestServerStub(channel)

            response = await simple_method(stub)
            assert response.response_data == "data"

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)
        finally:
            instrumentor.uninstrument()

    async def test_uninstrument(self):
        instrumentor = GrpcAioInstrumentorClient()

        instrumentor.instrument()
        instrumentor.uninstrument()

        channel = grpc.aio.insecure_channel("localhost:25565")
        stub = test_server_pb2_grpc.GRPCTestServerStub(channel)

        response = await simple_method(stub)
        assert response.response_data == "data"

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    async def test_unary_unary(self):
        response = await simple_method(self._stub)
        assert response.response_data == "data"

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]

        self.assertEqual(span.name, "/GRPCTestServer/SimpleMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationScope(
            span, opentelemetry.instrumentation.grpc
        )

        self.assertSpanHasAttributes(
            span,
            {
                RPC_METHOD: "SimpleMethod",
                RPC_SERVICE: "GRPCTestServer",
                RPC_SYSTEM: "grpc",
                RPC_GRPC_STATUS_CODE: grpc.StatusCode.OK.value[0],
            },
        )

    async def test_unary_stream(self):
        async for response in server_streaming_method(self._stub):
            self.assertEqual(response.response_data, "data")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]

        self.assertEqual(span.name, "/GRPCTestServer/ServerStreamingMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationScope(
            span, opentelemetry.instrumentation.grpc
        )

        self.assertSpanHasAttributes(
            span,
            {
                RPC_METHOD: "ServerStreamingMethod",
                RPC_SERVICE: "GRPCTestServer",
                RPC_SYSTEM: "grpc",
                RPC_GRPC_STATUS_CODE: grpc.StatusCode.OK.value[0],
            },
        )

    async def test_stream_unary(self):
        response = await client_streaming_method(self._stub)
        assert response.response_data == "data"

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]

        self.assertEqual(span.name, "/GRPCTestServer/ClientStreamingMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationScope(
            span, opentelemetry.instrumentation.grpc
        )

        self.assertSpanHasAttributes(
            span,
            {
                RPC_METHOD: "ClientStreamingMethod",
                RPC_SERVICE: "GRPCTestServer",
                RPC_SYSTEM: "grpc",
                RPC_GRPC_STATUS_CODE: grpc.StatusCode.OK.value[0],
            },
        )

    async def test_stream_stream(self):
        async for response in bidirectional_streaming_method(self._stub):
            self.assertEqual(response.response_data, "data")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]

        self.assertEqual(
            span.name, "/GRPCTestServer/BidirectionalStreamingMethod"
        )
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationScope(
            span, opentelemetry.instrumentation.grpc
        )

        self.assertSpanHasAttributes(
            span,
            {
                RPC_METHOD: "BidirectionalStreamingMethod",
                RPC_SERVICE: "GRPCTestServer",
                RPC_SYSTEM: "grpc",
                RPC_GRPC_STATUS_CODE: grpc.StatusCode.OK.value[0],
            },
        )

    async def test_error_simple(self):
        with self.assertRaises(grpc.RpcError):
            await simple_method(self._stub, error=True)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(
            span.status.status_code,
            trace.StatusCode.ERROR,
        )

    async def test_error_unary_stream(self):
        with self.assertRaises(grpc.RpcError):
            async for _ in server_streaming_method(self._stub, error=True):
                pass

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(
            span.status.status_code,
            trace.StatusCode.ERROR,
        )

    async def test_error_stream_unary(self):
        with self.assertRaises(grpc.RpcError):
            await client_streaming_method(self._stub, error=True)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(
            span.status.status_code,
            trace.StatusCode.ERROR,
        )

    async def test_error_stream_stream(self):
        with self.assertRaises(grpc.RpcError):
            async for _ in bidirectional_streaming_method(
                self._stub, error=True
            ):
                pass

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(
            span.status.status_code,
            trace.StatusCode.ERROR,
        )

    # pylint:disable=no-self-use
    async def test_client_interceptor_trace_context_propagation(self):
        """ensure that client interceptor correctly inject trace context into all outgoing requests."""

        previous_propagator = get_global_textmap()

        try:
            set_global_textmap(MockTextMapPropagator())

            interceptor = UnaryUnaryAioClientInterceptor(trace.NoOpTracer())
            recording_interceptor = RecordingInterceptor()
            interceptors = [interceptor, recording_interceptor]

            channel = grpc.aio.insecure_channel(
                "localhost:25565", interceptors=interceptors
            )

            stub = test_server_pb2_grpc.GRPCTestServerStub(channel)
            await simple_method(stub)

            metadata = recording_interceptor.recorded_details.metadata
            assert len(metadata) == 3
            assert metadata.get_all("key") == ["value"]
            assert metadata.get_all("mock-traceid") == ["0"]
            assert metadata.get_all("mock-spanid") == ["0"]
        finally:
            set_global_textmap(previous_propagator)

    async def test_unary_unary_with_suppress_key(self):
        with suppress_instrumentation():
            response = await simple_method(self._stub)
            assert response.response_data == "data"

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 0)

    async def test_unary_stream_with_suppress_key(self):
        with suppress_instrumentation():
            async for response in server_streaming_method(self._stub):
                self.assertEqual(response.response_data, "data")

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 0)

    async def test_stream_unary_with_suppress_key(self):
        with suppress_instrumentation():
            response = await client_streaming_method(self._stub)
            assert response.response_data == "data"

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 0)

    async def test_stream_stream_with_suppress_key(self):
        with suppress_instrumentation():
            async for response in bidirectional_streaming_method(self._stub):
                self.assertEqual(response.response_data, "data")

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 0)
