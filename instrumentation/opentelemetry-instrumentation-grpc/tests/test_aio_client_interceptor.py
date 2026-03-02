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
from unittest import IsolatedAsyncioTestCase, mock

import grpc

import opentelemetry.instrumentation.grpc
from opentelemetry import trace
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.grpc import (
    GrpcAioInstrumentorClient,
    aio_client_interceptors,
)
from opentelemetry.instrumentation.grpc._aio_client import (
    UnaryUnaryAioClientInterceptor,
)
from opentelemetry.instrumentation.grpc._semconv import (
    RPC_RESPONSE_STATUS_CODE,
    RPC_SYSTEM_NAME,
)
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.propagate import get_global_textmap, set_global_textmap
from opentelemetry.semconv._incubating.attributes.rpc_attributes import (
    RPC_GRPC_STATUS_CODE,
    RPC_METHOD,
    RPC_SERVICE,
    RPC_SYSTEM,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.test.mock_textmap import MockTextMapPropagator
from opentelemetry.test.test_base import TestBase


def _new_aio_client_rpc_attrs(full_method, status_name="OK", error_type=None):
    """Build expected new-semconv attributes for an aio client RPC span.

    Note: server.address / server.port are not asserted here because
    aio_client_interceptors() is constructed without the channel target,
    so those attributes are not available to the interceptor.
    """
    attrs = {
        RPC_SYSTEM_NAME: "grpc",
        RPC_METHOD: full_method,
        RPC_RESPONSE_STATUS_CODE: status_name,
    }
    if error_type:
        attrs[ERROR_TYPE] = error_type
    return attrs

from ._aio_client import (
    bidirectional_streaming_method,
    client_streaming_method,
    server_streaming_method,
    simple_method,
)
from ._server import create_test_server
from .protobuf import test_server_pb2_grpc  # pylint: disable=no-name-in-module
from .protobuf.test_server_pb2 import Request


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
        test_name = self._testMethodName if hasattr(self, "_testMethodName") else ""
        sem_conv_mode = "default"
        if "new_semconv" in test_name:
            sem_conv_mode = "rpc"
        elif "both_semconv" in test_name:
            sem_conv_mode = "rpc/dup"
        self.env_patch = mock.patch.dict(
            "os.environ", {OTEL_SEMCONV_STABILITY_OPT_IN: sem_conv_mode}
        )
        self.env_patch.start()
        _OpenTelemetrySemanticConventionStability._initialized = False
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
        self.env_patch.stop()
        _OpenTelemetrySemanticConventionStability._initialized = False

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

    async def test_error_unary_stream_mid_stream(self):
        with self.assertRaises(grpc.RpcError):
            async for _ in server_streaming_method(
                self._stub, error_mid_stream=True
            ):
                pass

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(span.status.status_code, trace.StatusCode.ERROR)
        self.assertSpanHasAttributes(
            span,
            {
                RPC_METHOD: "ServerStreamingMethod",
                RPC_SERVICE: "GRPCTestServer",
                RPC_SYSTEM: "grpc",
                RPC_GRPC_STATUS_CODE: grpc.StatusCode.INVALID_ARGUMENT.value[0],
            },
        )

    async def test_error_stream_stream_mid_stream(self):
        with self.assertRaises(grpc.RpcError):
            async for _ in bidirectional_streaming_method(
                self._stub, error_mid_stream=True
            ):
                pass

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(span.status.status_code, trace.StatusCode.ERROR)
        self.assertSpanHasAttributes(
            span,
            {
                RPC_METHOD: "BidirectionalStreamingMethod",
                RPC_SERVICE: "GRPCTestServer",
                RPC_SYSTEM: "grpc",
                RPC_GRPC_STATUS_CODE: grpc.StatusCode.INVALID_ARGUMENT.value[0],
            },
        )

    async def test_unimplemented(self):
        """Check that calling an unregistered method creates a span with UNIMPLEMENTED status."""
        request = Request(client_id=1, request_data="data")
        with self.assertRaises(grpc.RpcError) as cm:
            await self._channel.unary_unary(
                "/GRPCTestServer/UnimplementedMethod"
            )(request.SerializeToString())
        self.assertEqual(cm.exception.code(), grpc.StatusCode.UNIMPLEMENTED)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(span.status.status_code, trace.StatusCode.ERROR)
        self.assertSpanHasAttributes(
            span,
            {
                RPC_METHOD: "UnimplementedMethod",
                RPC_SERVICE: "GRPCTestServer",
                RPC_SYSTEM: "grpc",
                RPC_GRPC_STATUS_CODE: grpc.StatusCode.UNIMPLEMENTED.value[0],
            },
        )

    # --- new semconv (OTEL_SEMCONV_STABILITY_OPT_IN=rpc) tests ---

    async def test_unary_unary_new_semconv(self):
        response = await simple_method(self._stub)
        assert response.response_data == "data"

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "/GRPCTestServer/SimpleMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)
        self.assertSpanHasAttributes(
            span, _new_aio_client_rpc_attrs("/GRPCTestServer/SimpleMethod")
        )

    async def test_unary_stream_new_semconv(self):
        async for _ in server_streaming_method(self._stub):
            pass

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertSpanHasAttributes(
            span,
            _new_aio_client_rpc_attrs("/GRPCTestServer/ServerStreamingMethod"),
        )

    async def test_stream_unary_new_semconv(self):
        await client_streaming_method(self._stub)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertSpanHasAttributes(
            span,
            _new_aio_client_rpc_attrs("/GRPCTestServer/ClientStreamingMethod"),
        )

    async def test_stream_stream_new_semconv(self):
        async for _ in bidirectional_streaming_method(self._stub):
            pass

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertSpanHasAttributes(
            span,
            _new_aio_client_rpc_attrs(
                "/GRPCTestServer/BidirectionalStreamingMethod"
            ),
        )

    async def test_error_simple_new_semconv(self):
        with self.assertRaises(grpc.RpcError):
            await simple_method(self._stub, error=True)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(span.status.status_code, trace.StatusCode.ERROR)
        self.assertSpanHasAttributes(
            span,
            _new_aio_client_rpc_attrs(
                "/GRPCTestServer/SimpleMethod",
                status_name="INVALID_ARGUMENT",
                error_type="INVALID_ARGUMENT",
            ),
        )

    async def test_error_unary_stream_new_semconv(self):
        with self.assertRaises(grpc.RpcError):
            async for _ in server_streaming_method(self._stub, error=True):
                pass

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(span.status.status_code, trace.StatusCode.ERROR)
        self.assertSpanHasAttributes(
            span,
            _new_aio_client_rpc_attrs(
                "/GRPCTestServer/ServerStreamingMethod",
                status_name="INVALID_ARGUMENT",
                error_type="INVALID_ARGUMENT",
            ),
        )

    async def test_error_stream_unary_new_semconv(self):
        with self.assertRaises(grpc.RpcError):
            await client_streaming_method(self._stub, error=True)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(span.status.status_code, trace.StatusCode.ERROR)
        self.assertSpanHasAttributes(
            span,
            _new_aio_client_rpc_attrs(
                "/GRPCTestServer/ClientStreamingMethod",
                status_name="INVALID_ARGUMENT",
                error_type="INVALID_ARGUMENT",
            ),
        )

    async def test_error_stream_stream_new_semconv(self):
        with self.assertRaises(grpc.RpcError):
            async for _ in bidirectional_streaming_method(self._stub, error=True):
                pass

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(span.status.status_code, trace.StatusCode.ERROR)
        self.assertSpanHasAttributes(
            span,
            _new_aio_client_rpc_attrs(
                "/GRPCTestServer/BidirectionalStreamingMethod",
                status_name="INVALID_ARGUMENT",
                error_type="INVALID_ARGUMENT",
            ),
        )

    async def test_error_unary_stream_mid_stream_new_semconv(self):
        with self.assertRaises(grpc.RpcError):
            async for _ in server_streaming_method(
                self._stub, error_mid_stream=True
            ):
                pass

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(span.status.status_code, trace.StatusCode.ERROR)
        self.assertSpanHasAttributes(
            span,
            _new_aio_client_rpc_attrs(
                "/GRPCTestServer/ServerStreamingMethod",
                status_name="INVALID_ARGUMENT",
                error_type="INVALID_ARGUMENT",
            ),
        )

    async def test_error_stream_stream_mid_stream_new_semconv(self):
        with self.assertRaises(grpc.RpcError):
            async for _ in bidirectional_streaming_method(
                self._stub, error_mid_stream=True
            ):
                pass

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(span.status.status_code, trace.StatusCode.ERROR)
        self.assertSpanHasAttributes(
            span,
            _new_aio_client_rpc_attrs(
                "/GRPCTestServer/BidirectionalStreamingMethod",
                status_name="INVALID_ARGUMENT",
                error_type="INVALID_ARGUMENT",
            ),
        )

    async def test_unimplemented_new_semconv(self):
        """Check that calling an unregistered method records UNIMPLEMENTED in new semconv."""
        request = Request(client_id=1, request_data="data")
        with self.assertRaises(grpc.RpcError) as cm:
            await self._channel.unary_unary(
                "/GRPCTestServer/UnimplementedMethod"
            )(request.SerializeToString())
        self.assertEqual(cm.exception.code(), grpc.StatusCode.UNIMPLEMENTED)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(span.status.status_code, trace.StatusCode.ERROR)
        self.assertSpanHasAttributes(
            span,
            _new_aio_client_rpc_attrs(
                "/GRPCTestServer/UnimplementedMethod",
                status_name="UNIMPLEMENTED",
                error_type="UNIMPLEMENTED",
            ),
        )

    # --- both semconv (OTEL_SEMCONV_STABILITY_OPT_IN=rpc/dup) tests ---

    async def test_unary_unary_both_semconv(self):
        """Verify that dup mode reports both old and new semconv attributes."""
        response = await simple_method(self._stub)
        assert response.response_data == "data"

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertSpanHasAttributes(
            span,
            {
                # old semconv attributes
                RPC_SYSTEM: "grpc",
                RPC_METHOD: "SimpleMethod",  # old value wins in dup mode
                RPC_SERVICE: "GRPCTestServer",
                RPC_GRPC_STATUS_CODE: grpc.StatusCode.OK.value[0],
                # new semconv attributes
                RPC_SYSTEM_NAME: "grpc",
                RPC_RESPONSE_STATUS_CODE: "OK",
            },
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
