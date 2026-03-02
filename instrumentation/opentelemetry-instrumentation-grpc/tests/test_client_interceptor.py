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
# pylint:disable=cyclic-import

from unittest import mock

import grpc

import opentelemetry.instrumentation.grpc
from opentelemetry import trace
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient
from opentelemetry.instrumentation.grpc._client import (
    OpenTelemetryClientInterceptor,
)
from opentelemetry.instrumentation.grpc._semconv import (
    RPC_RESPONSE_STATUS_CODE,
    RPC_SYSTEM_NAME,
)
from opentelemetry.instrumentation.grpc.grpcext._interceptor import (
    _UnaryClientInfo,
)
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.propagate import get_global_textmap, set_global_textmap
from opentelemetry.sdk.trace import Span as SdkSpan
from opentelemetry.semconv._incubating.attributes.rpc_attributes import (
    RPC_GRPC_STATUS_CODE,
    RPC_METHOD,
    RPC_SERVICE,
    RPC_SYSTEM,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.test.mock_textmap import MockTextMapPropagator
from opentelemetry.test.test_base import TestBase

from ._client import (
    bidirectional_streaming_method,
    client_streaming_method,
    server_streaming_method,
    simple_method,
    simple_method_future,
)
from ._server import create_test_server
from .protobuf import test_server_pb2_grpc
from .protobuf.test_server_pb2 import Request

_CLIENT_SERVER_HOST = "localhost"
_CLIENT_SERVER_PORT = 25565


def _new_client_rpc_attrs(full_method, status_name="OK", error_type=None):
    """Build expected new-semconv attributes for a client RPC span."""
    attrs = {
        RPC_SYSTEM_NAME: "grpc",
        RPC_METHOD: full_method,
        RPC_RESPONSE_STATUS_CODE: status_name,
        SERVER_ADDRESS: _CLIENT_SERVER_HOST,
        SERVER_PORT: _CLIENT_SERVER_PORT,
    }
    if error_type:
        attrs[ERROR_TYPE] = error_type
    return attrs


# User defined interceptor. Is used in the tests along with the opentelemetry client interceptor.
class Interceptor(
    grpc.UnaryUnaryClientInterceptor,
    grpc.UnaryStreamClientInterceptor,
    grpc.StreamUnaryClientInterceptor,
    grpc.StreamStreamClientInterceptor,
):
    def __init__(self):
        pass

    def intercept_unary_unary(
        self, continuation, client_call_details, request
    ):
        return self._intercept_call(continuation, client_call_details, request)

    def intercept_unary_stream(
        self, continuation, client_call_details, request
    ):
        return self._intercept_call(continuation, client_call_details, request)

    def intercept_stream_unary(
        self, continuation, client_call_details, request_iterator
    ):
        return self._intercept_call(
            continuation, client_call_details, request_iterator
        )

    def intercept_stream_stream(
        self, continuation, client_call_details, request_iterator
    ):
        return self._intercept_call(
            continuation, client_call_details, request_iterator
        )

    @staticmethod
    def _intercept_call(
        continuation, client_call_details, request_or_iterator
    ):
        return continuation(client_call_details, request_or_iterator)


class TestClientProto(TestBase):
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
        GrpcInstrumentorClient().instrument()
        self.server = create_test_server(25565)
        self.server.start()
        # use a user defined interceptor along with the opentelemetry client interceptor
        interceptors = [Interceptor()]
        self.channel = grpc.insecure_channel("localhost:25565")
        self.channel = grpc.intercept_channel(self.channel, *interceptors)
        self._stub = test_server_pb2_grpc.GRPCTestServerStub(self.channel)

    def tearDown(self):
        super().tearDown()
        GrpcInstrumentorClient().uninstrument()
        self.server.stop(None)
        self.channel.close()
        self.env_patch.stop()
        _OpenTelemetrySemanticConventionStability._initialized = False

    def test_unary_unary_future(self):
        simple_method_future(self._stub).result()
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]

        self.assertEqual(span.name, "/GRPCTestServer/SimpleMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationScope(
            span, opentelemetry.instrumentation.grpc
        )

    def test_unary_unary(self):
        simple_method(self._stub)
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

    def test_unary_stream(self):
        server_streaming_method(self._stub)
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

    def test_stream_unary(self):
        client_streaming_method(self._stub)
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

    def test_stream_stream(self):
        bidirectional_streaming_method(self._stub)
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

    def test_error_simple(self):
        with self.assertRaises(grpc.RpcError):
            simple_method(self._stub, error=True)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(
            span.status.status_code,
            trace.StatusCode.ERROR,
        )

    def test_error_stream_unary(self):
        with self.assertRaises(grpc.RpcError):
            client_streaming_method(self._stub, error=True)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(
            span.status.status_code,
            trace.StatusCode.ERROR,
        )

    def test_error_unary_stream(self):
        with self.assertRaises(grpc.RpcError):
            server_streaming_method(self._stub, error=True)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(
            span.status.status_code,
            trace.StatusCode.ERROR,
        )

    def test_error_stream_stream(self):
        with self.assertRaises(grpc.RpcError):
            bidirectional_streaming_method(self._stub, error=True)

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(
            span.status.status_code,
            trace.StatusCode.ERROR,
        )

    def test_error_unary_stream_mid_stream(self):
        with self.assertRaises(grpc.RpcError):
            server_streaming_method(self._stub, error_mid_stream=True)

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

    def test_error_stream_stream_mid_stream(self):
        with self.assertRaises(grpc.RpcError):
            bidirectional_streaming_method(self._stub, error_mid_stream=True)

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

    def test_unimplemented(self):
        """Check that calling an unregistered method creates a span with UNIMPLEMENTED status."""
        request = Request(client_id=1, request_data="data")
        with self.assertRaises(grpc.RpcError) as cm:
            self.channel.unary_unary("/GRPCTestServer/UnimplementedMethod")(
                request.SerializeToString()
            )
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

    def test_client_interceptor_falsy_response(
        self,
    ):
        """ensure that client interceptor closes the span only once even if the response is falsy."""

        with mock.patch.object(SdkSpan, "end") as span_end_mock:
            tracer_provider, _exporter = self.create_tracer_provider()
            tracer = tracer_provider.get_tracer(__name__)

            interceptor = OpenTelemetryClientInterceptor(tracer)

            def invoker(_request, _metadata):
                return {}

            request = Request(client_id=1, request_data="data")
            interceptor.intercept_unary(
                request,
                {},
                _UnaryClientInfo(
                    full_method="/GRPCTestServer/SimpleMethod",
                    timeout=None,
                ),
                invoker=invoker,
            )
            self.assertEqual(span_end_mock.call_count, 1)

    def test_client_interceptor_trace_context_propagation(
        self,
    ):  # pylint: disable=no-self-use
        """ensure that client interceptor correctly inject trace context into all outgoing requests."""
        previous_propagator = get_global_textmap()
        try:
            set_global_textmap(MockTextMapPropagator())
            interceptor = OpenTelemetryClientInterceptor(trace.NoOpTracer())

            carrier = tuple()

            def invoker(request, metadata):
                nonlocal carrier
                carrier = metadata
                return {}

            request = Request(client_id=1, request_data="data")
            interceptor.intercept_unary(
                request,
                {},
                _UnaryClientInfo(
                    full_method="/GRPCTestServer/SimpleMethod", timeout=None
                ),
                invoker=invoker,
            )

            assert len(carrier) == 2
            assert carrier[0][0] == "mock-traceid"
            assert carrier[0][1] == "0"
            assert carrier[1][0] == "mock-spanid"
            assert carrier[1][1] == "0"

        finally:
            set_global_textmap(previous_propagator)

    # --- new semconv (OTEL_SEMCONV_STABILITY_OPT_IN=rpc) tests ---

    def test_unary_unary_new_semconv(self):
        simple_method(self._stub)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "/GRPCTestServer/SimpleMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)
        self.assertSpanHasAttributes(
            span, _new_client_rpc_attrs("/GRPCTestServer/SimpleMethod")
        )

    def test_unary_stream_new_semconv(self):
        server_streaming_method(self._stub)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "/GRPCTestServer/ServerStreamingMethod")
        self.assertSpanHasAttributes(
            span, _new_client_rpc_attrs("/GRPCTestServer/ServerStreamingMethod")
        )

    def test_stream_unary_new_semconv(self):
        client_streaming_method(self._stub)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "/GRPCTestServer/ClientStreamingMethod")
        self.assertSpanHasAttributes(
            span, _new_client_rpc_attrs("/GRPCTestServer/ClientStreamingMethod")
        )

    def test_stream_stream_new_semconv(self):
        bidirectional_streaming_method(self._stub)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "/GRPCTestServer/BidirectionalStreamingMethod")
        self.assertSpanHasAttributes(
            span,
            _new_client_rpc_attrs("/GRPCTestServer/BidirectionalStreamingMethod"),
        )

    def test_error_simple_new_semconv(self):
        with self.assertRaises(grpc.RpcError):
            simple_method(self._stub, error=True)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(span.status.status_code, trace.StatusCode.ERROR)
        self.assertSpanHasAttributes(
            span,
            _new_client_rpc_attrs(
                "/GRPCTestServer/SimpleMethod",
                status_name="INVALID_ARGUMENT",
                error_type="INVALID_ARGUMENT",
            ),
        )

    def test_error_stream_unary_new_semconv(self):
        with self.assertRaises(grpc.RpcError):
            client_streaming_method(self._stub, error=True)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(span.status.status_code, trace.StatusCode.ERROR)
        self.assertSpanHasAttributes(
            span,
            _new_client_rpc_attrs(
                "/GRPCTestServer/ClientStreamingMethod",
                status_name="INVALID_ARGUMENT",
                error_type="INVALID_ARGUMENT",
            ),
        )

    def test_error_unary_stream_new_semconv(self):
        with self.assertRaises(grpc.RpcError):
            server_streaming_method(self._stub, error=True)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(span.status.status_code, trace.StatusCode.ERROR)
        self.assertSpanHasAttributes(
            span,
            _new_client_rpc_attrs(
                "/GRPCTestServer/ServerStreamingMethod",
                status_name="INVALID_ARGUMENT",
                error_type="INVALID_ARGUMENT",
            ),
        )

    def test_error_stream_stream_new_semconv(self):
        with self.assertRaises(grpc.RpcError):
            bidirectional_streaming_method(self._stub, error=True)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(span.status.status_code, trace.StatusCode.ERROR)
        self.assertSpanHasAttributes(
            span,
            _new_client_rpc_attrs(
                "/GRPCTestServer/BidirectionalStreamingMethod",
                status_name="INVALID_ARGUMENT",
                error_type="INVALID_ARGUMENT",
            ),
        )

    def test_error_unary_stream_mid_stream_new_semconv(self):
        with self.assertRaises(grpc.RpcError):
            server_streaming_method(self._stub, error_mid_stream=True)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(span.status.status_code, trace.StatusCode.ERROR)
        self.assertSpanHasAttributes(
            span,
            _new_client_rpc_attrs(
                "/GRPCTestServer/ServerStreamingMethod",
                status_name="INVALID_ARGUMENT",
                error_type="INVALID_ARGUMENT",
            ),
        )

    def test_error_stream_stream_mid_stream_new_semconv(self):
        with self.assertRaises(grpc.RpcError):
            bidirectional_streaming_method(self._stub, error_mid_stream=True)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(span.status.status_code, trace.StatusCode.ERROR)
        self.assertSpanHasAttributes(
            span,
            _new_client_rpc_attrs(
                "/GRPCTestServer/BidirectionalStreamingMethod",
                status_name="INVALID_ARGUMENT",
                error_type="INVALID_ARGUMENT",
            ),
        )

    def test_unimplemented_new_semconv(self):
        """Check that calling an unregistered method records UNIMPLEMENTED in new semconv."""
        request = Request(client_id=1, request_data="data")
        with self.assertRaises(grpc.RpcError) as cm:
            self.channel.unary_unary("/GRPCTestServer/UnimplementedMethod")(
                request.SerializeToString()
            )
        self.assertEqual(cm.exception.code(), grpc.StatusCode.UNIMPLEMENTED)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertIs(span.status.status_code, trace.StatusCode.ERROR)
        self.assertSpanHasAttributes(
            span,
            _new_client_rpc_attrs(
                "/GRPCTestServer/UnimplementedMethod",
                status_name="UNIMPLEMENTED",
                error_type="UNIMPLEMENTED",
            ),
        )

    # --- both semconv (OTEL_SEMCONV_STABILITY_OPT_IN=rpc/dup) tests ---

    def test_unary_unary_both_semconv(self):
        """Verify that dup mode reports both old and new semconv attributes."""
        simple_method(self._stub)
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "/GRPCTestServer/SimpleMethod")
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
                SERVER_ADDRESS: _CLIENT_SERVER_HOST,
                SERVER_PORT: _CLIENT_SERVER_PORT,
            },
        )

    def test_unary_unary_with_suppress_key(self):
        with suppress_instrumentation():
            simple_method(self._stub)
            spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_unary_stream_with_suppress_key(self):
        with suppress_instrumentation():
            server_streaming_method(self._stub)
            spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_stream_unary_with_suppress_key(self):
        with suppress_instrumentation():
            client_streaming_method(self._stub)
            spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_stream_stream_with_suppress_key(self):
        with suppress_instrumentation():
            bidirectional_streaming_method(self._stub)
            spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)
