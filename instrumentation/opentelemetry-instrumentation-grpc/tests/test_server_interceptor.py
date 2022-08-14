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

# pylint:disable=unused-argument
# pylint:disable=no-self-use

import threading
from concurrent import futures

import grpc

from opentelemetry import trace
import opentelemetry.instrumentation.grpc
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer, server_interceptor
from opentelemetry.sdk.metrics.export import Histogram, HistogramDataPoint
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import StatusCode

from .protobuf.test_server_pb2 import Request, Response
from .protobuf.test_server_pb2_grpc import (
    GRPCTestServerServicer,
    add_GRPCTestServerServicer_to_server,
)
from ._server import TestServer


_expected_metric_names = {
    "rpc.server.duration": (
        Histogram,
        "ms",
        "Measures duration of RPC"
    ),
    "rpc.server.request.size": (
        Histogram,
        "By",
        "Measures size of RPC request messages (uncompressed)",
    ),
    "rpc.server.response.size": (
        Histogram,
        "By",
        "Measures size of RPC response messages (uncompressed)",
    ),
    "rpc.server.requests_per_rpc": (
        Histogram,
        "1",
        "Measures the number of messages received per RPC. "
        "Should be 1 for all non-streaming RPCs"
    ),
    "rpc.server.responses_per_rpc": (
        Histogram,
        "1",
        "Measures the number of messages sent per RPC. "
        "Should be 1 for all non-streaming RPCs",
    ),
}


class TestOpenTelemetryServerInterceptor(TestBase):
    # pylint:disable=C0103

    def assertEvent(self, event, name, attributes):
        self.assertEqual(event.name, name)
        for key, val in attributes.items():
            self.assertIn(key, event.attributes, msg=str(event.attributes))
            self.assertEqual(
                val, event.attributes[key], msg=str(event.attributes)
            )

    def assertEqualMetricInstrumentationScope(self, scope_metrics, module):
        self.assertEqual(scope_metrics.scope.name, module.__name__)
        self.assertEqual(scope_metrics.scope.version, module.__version__)

    def assertMetricDataPointHasAttributes(self, data_point, attributes):
        for key, val in attributes.items():
            self.assertIn(key, data_point.attributes)
            self.assertEqual(val, data_point.attributes[key])

    def test_instrumentor(self):

        grpc_server_instrumentor = GrpcInstrumentorServer()
        grpc_server_instrumentor.instrument()
        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
            )
            add_GRPCTestServerServicer_to_server(TestServer(), server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            rpc_call = "/GRPCTestServer/SimpleMethod"
            request = Request(client_id=1, request_data="test")
            request_ser = request.SerializeToString()

            try:
                server.start()
                response = channel.unary_unary(rpc_call)(request_ser)
            finally:
                server.stop(None)

            spans_list = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans_list), 1)
            span = spans_list[0]
            self.assertEqual(span.name, rpc_call)
            self.assertIs(span.kind, trace.SpanKind.SERVER)

            # Check version and name in span's instrumentation info
            self.assertEqualSpanInstrumentationInfo(
                span, opentelemetry.instrumentation.grpc
            )

            # check attributes
            self.assertSpanHasAttributes(
                span,
                {
                    SpanAttributes.NET_PEER_IP: "[::1]",
                    # SpanAttributes.NET_PEER_PORT: "0",
                    SpanAttributes.NET_PEER_NAME: "localhost",
                    SpanAttributes.RPC_METHOD: "SimpleMethod",
                    SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                    SpanAttributes.RPC_SYSTEM: "grpc",
                    SpanAttributes.RPC_GRPC_STATUS_CODE:
                        grpc.StatusCode.OK.value[0],
                },
            )

            # check events
            self.assertEqual(len(span.events), 2)
            self.assertEvent(
                span.events[0],
                "message",
                {
                    SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                    SpanAttributes.MESSAGE_ID: 1,
                    SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(request_ser)
                }
            )
            self.assertEvent(
                span.events[1],
                "message",
                {
                    SpanAttributes.MESSAGE_TYPE: "SENT",
                    SpanAttributes.MESSAGE_ID: 1,
                    SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(response)
                }
            )

            grpc_server_instrumentor.uninstrument()

    def test_uninstrument(self):

        grpc_server_instrumentor = GrpcInstrumentorServer()
        grpc_server_instrumentor.instrument()
        grpc_server_instrumentor.uninstrument()
        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
            )
            add_GRPCTestServerServicer_to_server(TestServer(), server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            rpc_call = "/GRPCTestServer/SimpleMethod"
            request_ser = Request().SerializeToString()

            try:
                server.start()
                channel.unary_unary(rpc_call)(request_ser)
            finally:
                server.stop(None)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

        # metrics_data = self.memory_metrics_reader.get_metrics_data()
        # self.assertEqual(len(metrics_data.resource_metrics), 0)

    def test_create_span(self):
        """Check that the interceptor wraps calls with spans server-side."""

        # Intercept gRPC calls...
        interceptor = server_interceptor()

        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=[interceptor],
            )
            add_GRPCTestServerServicer_to_server(TestServer(), server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            rpc_call = "/GRPCTestServer/SimpleMethod"
            request = Request(client_id=1, request_data="test")
            request_ser = request.SerializeToString()

            try:
                server.start()
                response = channel.unary_unary(rpc_call)(request_ser)
            finally:
                server.stop(None)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        self.assertEqual(span.name, rpc_call)
        self.assertIs(span.kind, trace.SpanKind.SERVER)

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # Check attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.NET_PEER_IP: "[::1]",
                # SpanAttributes.NET_PEER_PORT: "0",
                SpanAttributes.NET_PEER_NAME: "localhost",
                SpanAttributes.RPC_METHOD: "SimpleMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE:
                    grpc.StatusCode.OK.value[0],
            },
        )

        # check events
        self.assertEqual(len(span.events), 2)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(request_ser)
            }
        )
        self.assertEvent(
            span.events[1],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "SENT",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(response)
            }
        )

    def test_create_two_spans(self):
        """Verify that the interceptor captures sub spans within the given
        trace"""

        class TwoSpanServicer(GRPCTestServerServicer):
            # pylint:disable=C0103
            def SimpleMethod(self, request, context):

                # create another span
                tracer = trace.get_tracer(__name__)
                with tracer.start_as_current_span("child") as child:
                    child.add_event("child event")

                return Response(
                    server_id=request.client_id,
                    response_data=request.request_data,
                )

        # Intercept gRPC calls...
        interceptor = server_interceptor()

        # setup the server
        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=[interceptor],
            )
            add_GRPCTestServerServicer_to_server(TwoSpanServicer(), server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            # setup the RPC
            rpc_call = "/GRPCTestServer/SimpleMethod"
            request = Request(client_id=1, request_data="test")
            request_ser = request.SerializeToString()

            try:
                server.start()
                response = channel.unary_unary(rpc_call)(request_ser)
            finally:
                server.stop(None)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 2)
        child_span = spans_list[0]
        parent_span = spans_list[1]

        self.assertEqual(parent_span.name, rpc_call)
        self.assertIs(parent_span.kind, trace.SpanKind.SERVER)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            parent_span, opentelemetry.instrumentation.grpc
        )

        # check parent attributes
        self.assertSpanHasAttributes(
            parent_span,
            {
                SpanAttributes.NET_PEER_IP: "[::1]",
                # SpanAttributes.NET_PEER_PORT: "0",
                SpanAttributes.NET_PEER_NAME: "localhost",
                SpanAttributes.RPC_METHOD: "SimpleMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE:
                    grpc.StatusCode.OK.value[0],
            },
        )

        # check parent events
        self.assertEqual(len(parent_span.events), 2)
        self.assertEvent(
            parent_span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(request_ser)
            }
        )
        self.assertEvent(
            parent_span.events[1],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "SENT",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(response)
            }
        )

        # check the child span
        self.assertEqual(child_span.name, "child")
        self.assertEqual(
            parent_span.context.trace_id, child_span.context.trace_id
        )

        # check child event
        self.assertEqual(len(child_span.events), 1)
        self.assertEvent(
            child_span.events[0],
            "child event",
            {}
        )

    def test_create_span_streaming(self):
        """Check that the interceptor wraps calls with spans server-side, on a
        streaming call."""

        # Intercept gRPC calls...
        interceptor = server_interceptor()

        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=[interceptor],
            )
            add_GRPCTestServerServicer_to_server(TestServer(), server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            # setup the RPC
            rpc_call = "/GRPCTestServer/ServerStreamingMethod"
            request = Request(client_id=1, request_data="test")
            request_ser = request.SerializeToString()

            try:
                server.start()
                responses = list(channel.unary_stream(rpc_call)(request_ser))
            finally:
                server.stop(None)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        self.assertEqual(span.name, rpc_call)
        self.assertIs(span.kind, trace.SpanKind.SERVER)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.NET_PEER_IP: "[::1]",
                # SpanAttributes.NET_PEER_PORT: "0",
                SpanAttributes.NET_PEER_NAME: "localhost",
                SpanAttributes.RPC_METHOD: "ServerStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE:
                    grpc.StatusCode.OK.value[0],
            },
        )

        # check events
        self.assertEqual(len(span.events), len(responses) + 1)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(request_ser)
            }
        )
        for res_id, (event, response) in enumerate(
            zip(span.events[1:], responses), start=1
        ):
            self.assertEvent(
                event,
                "message",
                {
                    SpanAttributes.MESSAGE_TYPE: "SENT",
                    SpanAttributes.MESSAGE_ID: res_id,
                    SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(response)
                }
            )

    def test_create_two_spans_streaming(self):
        """Verify that the interceptor captures sub spans in a
        streaming call, within the given trace"""

        class TwoSpanServicer(GRPCTestServerServicer):
            # pylint:disable=C0103
            def ServerStreamingMethod(self, request, context):

                # create another span
                tracer = trace.get_tracer(__name__)
                with tracer.start_as_current_span("child") as child:
                    child.add_event("child event")

                for data in ("one", "two", "three"):
                    yield Response(
                        server_id=request.client_id,
                        response_data=data,
                    )

        # Intercept gRPC calls...
        interceptor = server_interceptor()

        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=[interceptor],
            )
            add_GRPCTestServerServicer_to_server(TwoSpanServicer(), server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            # setup the RPC
            rpc_call = "/GRPCTestServer/ServerStreamingMethod"
            request = Request(client_id=1, request_data="test")
            request_ser = request.SerializeToString()

            try:
                server.start()
                list(channel.unary_stream(rpc_call)(request_ser))
            finally:
                server.stop(None)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 2)
        child_span = spans_list[0]
        parent_span = spans_list[1]

        self.assertEqual(parent_span.name, rpc_call)
        self.assertIs(parent_span.kind, trace.SpanKind.SERVER)

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            parent_span, opentelemetry.instrumentation.grpc
        )

        # Check attributes
        self.assertSpanHasAttributes(
            parent_span,
            {
                SpanAttributes.NET_PEER_IP: "[::1]",
                # SpanAttributes.NET_PEER_PORT: "0",
                SpanAttributes.NET_PEER_NAME: "localhost",
                SpanAttributes.RPC_METHOD: "ServerStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE:
                    grpc.StatusCode.OK.value[0],
            },
        )

        # Check the child span
        self.assertEqual(child_span.name, "child")
        self.assertEqual(
            parent_span.context.trace_id, child_span.context.trace_id
        )

    def test_span_lifetime(self):
        """Check that the span is active for the duration of the call."""

        interceptor = server_interceptor()

        # To capture the current span at the time the handler is called
        active_span_in_handler = None

        def handler(request, context):
            nonlocal active_span_in_handler
            active_span_in_handler = trace.get_current_span()
            return Response()

        servicer = TestServer()
        servicer.SimpleMethod = handler

        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=[interceptor],
            )
            add_GRPCTestServerServicer_to_server(servicer, server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            rpc_call = "/GRPCTestServer/SimpleMethod"
            request_ser = Request().SerializeToString()

            active_span_before_call = trace.get_current_span()
            try:
                server.start()
                channel.unary_unary(rpc_call)(request_ser)
            finally:
                server.stop(None)
        active_span_after_call = trace.get_current_span()

        self.assertEqual(active_span_before_call, trace.INVALID_SPAN)
        self.assertEqual(active_span_after_call, trace.INVALID_SPAN)
        self.assertIsInstance(active_span_in_handler, trace.Span)
        self.assertIsNone(active_span_in_handler.parent)

    def test_span_lifetime_streaming(self):
        """Check that the span is active for the duration of the call."""

        interceptor = server_interceptor()

        # To capture the current span at the time the handler is called
        active_span_in_handler = None

        def handler(request, context):
            nonlocal active_span_in_handler
            active_span_in_handler = trace.get_current_span()
            for data in ("one", "two", "three"):
                yield Response(
                    server_id=request.client_id,
                    response_data=data,
                )

        servicer = TestServer()
        servicer.ServerStreamingMethod = handler

        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=[interceptor],
            )
            add_GRPCTestServerServicer_to_server(servicer, server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            rpc_call = "/GRPCTestServer/ServerStreamingMethod"
            request = Request(client_id=1, request_data="test")
            request_ser = request.SerializeToString()

            active_span_before_call = trace.get_current_span()
            try:
                server.start()
                list(channel.unary_stream(rpc_call)(request_ser))
            finally:
                server.stop(None)
        active_span_after_call = trace.get_current_span()

        self.assertEqual(active_span_before_call, trace.INVALID_SPAN)
        self.assertEqual(active_span_after_call, trace.INVALID_SPAN)
        self.assertIsInstance(active_span_in_handler, trace.Span)
        self.assertIsNone(active_span_in_handler.parent)

    def test_sequential_server_spans(self):
        """Check that sequential RPCs get separate server spans."""

        interceptor = server_interceptor()

        # Capture the currently active span in each thread
        active_spans_in_handler = []

        def handler(request, context):
            active_spans_in_handler.append(trace.get_current_span())
            return Response()

        servicer = TestServer()
        servicer.SimpleMethod = handler

        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=[interceptor],
            )
            add_GRPCTestServerServicer_to_server(servicer, server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            rpc_call = "/GRPCTestServer/SimpleMethod"
            request_ser = Request().SerializeToString()

            try:
                server.start()
                response_1 = channel.unary_unary(rpc_call)(request_ser)
                response_2 = channel.unary_unary(rpc_call)(request_ser)
            finally:
                server.stop(None)

        self.assertEqual(len(active_spans_in_handler), 2)
        # pylint:disable=unbalanced-tuple-unpacking
        span1, span2 = active_spans_in_handler
        # Spans should belong to separate traces
        self.assertNotEqual(span1.context.span_id, span2.context.span_id)
        self.assertNotEqual(span1.context.trace_id, span2.context.trace_id)

        for span, response in zip([span1, span2], [response_1, response_2]):
            # each should be a root span
            self.assertIsNone(span2.parent)

            # check attributes
            self.assertSpanHasAttributes(
                span,
                {
                    SpanAttributes.NET_PEER_IP: "[::1]",
                    # SpanAttributes.NET_PEER_PORT: "0",
                    SpanAttributes.NET_PEER_NAME: "localhost",
                    SpanAttributes.RPC_METHOD: "SimpleMethod",
                    SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                    SpanAttributes.RPC_SYSTEM: "grpc",
                    SpanAttributes.RPC_GRPC_STATUS_CODE:
                        grpc.StatusCode.OK.value[0],
                },
            )

            self.assertEqual(len(span.events), 2)
            self.assertEvent(
                span.events[0],
                "message",
                {
                    SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                    SpanAttributes.MESSAGE_ID: 1,
                    SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(request_ser)
                }
            )
            self.assertEvent(
                span.events[1],
                "message",
                {
                    SpanAttributes.MESSAGE_TYPE: "SENT",
                    SpanAttributes.MESSAGE_ID: 1,
                    SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(response)
                }
            )

    def test_concurrent_server_spans(self):
        """Check that concurrent RPC calls don't interfere with each other.

        This is the same check as test_sequential_server_spans except that the
        RPCs are concurrent. Two handlers are invoked at the same time on two
        separate threads. Each one should see a different active span and
        context.
        """

        interceptor = server_interceptor()

        # Capture the currently active span in each thread
        active_spans_in_handler = []
        latch = get_latch(2)

        def handler(request, context):
            latch()
            active_spans_in_handler.append(trace.get_current_span())
            return Response()

        servicer = TestServer()
        servicer.SimpleMethod = handler

        with futures.ThreadPoolExecutor(max_workers=2) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=[interceptor],
            )
            add_GRPCTestServerServicer_to_server(servicer, server)

            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            rpc_call = "/GRPCTestServer/SimpleMethod"
            request = Request(client_id=1, request_data="test")
            request_ser = request.SerializeToString()

            try:
                server.start()
                # Interleave calls so spans are active on each thread at the
                # same time
                with futures.ThreadPoolExecutor(max_workers=2) as tpe:
                    f1 = tpe.submit(
                        channel.unary_unary(rpc_call), request_ser
                    )
                    f2 = tpe.submit(
                        channel.unary_unary(rpc_call), request_ser
                    )
                futures.wait((f1, f2))
            finally:
                server.stop(None)

        self.assertEqual(len(active_spans_in_handler), 2)
        # pylint:disable=unbalanced-tuple-unpacking
        span1, span2 = active_spans_in_handler
        # Spans should belong to separate traces
        self.assertNotEqual(span1.context.span_id, span2.context.span_id)
        self.assertNotEqual(span1.context.trace_id, span2.context.trace_id)

        for span, response in zip([span1, span2], [f1.result(), f2.result()]):
            # each should be a root span
            self.assertIsNone(span2.parent)

            # Check attributes
            self.assertSpanHasAttributes(
                span,
                {
                    SpanAttributes.NET_PEER_IP: "[::1]",
                    # SpanAttributes.NET_PEER_PORT: "0",
                    SpanAttributes.NET_PEER_NAME: "localhost",
                    SpanAttributes.RPC_METHOD: "SimpleMethod",
                    SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                    SpanAttributes.RPC_SYSTEM: "grpc",
                    SpanAttributes.RPC_GRPC_STATUS_CODE:
                        grpc.StatusCode.OK.value[0],
                },
            )

            # check events
            self.assertEqual(len(span.events), 2)
            self.assertEvent(
                span.events[0],
                "message",
                {
                    SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                    SpanAttributes.MESSAGE_ID: 1,
                    SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(request_ser)
                }
            )
            self.assertEvent(
                span.events[1],
                "message",
                {
                    SpanAttributes.MESSAGE_TYPE: "SENT",
                    SpanAttributes.MESSAGE_ID: 1,
                    SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(response)
                }
            )

    def test_abort(self):
        """Check that we can catch an abort properly"""

        abort_message = "abort"

        # Intercept gRPC calls...
        interceptor = server_interceptor()

        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=[interceptor],
            )
            add_GRPCTestServerServicer_to_server(TestServer(), server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            rpc_call = "/GRPCTestServer/SimpleMethod"
            request = Request(client_id=1, request_data=abort_message)
            request_ser = request.SerializeToString()

            server.start()
            # unfortunately, these are just bare exceptions in grpc...
            with self.assertRaises(Exception):
                channel.unary_unary(rpc_call)(request_ser)
            server.stop(None)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        self.assertEqual(span.name, rpc_call)
        self.assertIs(span.kind, trace.SpanKind.SERVER)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.FAILED_PRECONDITION}: {abort_message}",
        )

        # check attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.NET_PEER_IP: "[::1]",
                # SpanAttributes.NET_PEER_PORT: "0",
                SpanAttributes.NET_PEER_NAME: "localhost",
                SpanAttributes.RPC_METHOD: "SimpleMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE:
                    grpc.StatusCode.FAILED_PRECONDITION.value[0],
            },
        )

        # check events
        self.assertEqual(len(span.events), 1)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(request_ser)
            }
        )

    def test_abort_streaming(self):
        """Check that we can catch an abort of a streaming call properly"""

        abort_message = "abort"

        # Intercept gRPC calls...
        interceptor = server_interceptor()

        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=[interceptor],
            )
            add_GRPCTestServerServicer_to_server(TestServer(), server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            # setup the RPC
            rpc_call = "/GRPCTestServer/ServerStreamingMethod"
            request = Request(client_id=1, request_data=abort_message)
            request_ser = request.SerializeToString()

            server.start()
            responses = []
            with self.assertRaises(Exception):
                for res in channel.unary_stream(rpc_call)(request_ser):
                    responses.append(res)
            server.stop(None)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        self.assertEqual(span.name, rpc_call)
        self.assertIs(span.kind, trace.SpanKind.SERVER)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.FAILED_PRECONDITION}: {abort_message}",
        )

        # check attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.NET_PEER_IP: "[::1]",
                # SpanAttributes.NET_PEER_PORT: "0",
                SpanAttributes.NET_PEER_NAME: "localhost",
                SpanAttributes.RPC_METHOD: "ServerStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE:
                    grpc.StatusCode.FAILED_PRECONDITION.value[0],
            },
        )

        # check events
        self.assertEqual(len(span.events), 2)
        self.assertEqual(len(responses), 1)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(request_ser)
            }
        )
        self.assertEvent(
            span.events[1],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "SENT",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(responses[0])
            }
        )

    def test_cancel(self):
        """Check that we can catch a cancellation properly"""

        cancel_message = "cancel"

        # Intercept gRPC calls...
        interceptor = server_interceptor()

        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=[interceptor],
            )
            add_GRPCTestServerServicer_to_server(TestServer(), server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            rpc_call = "/GRPCTestServer/SimpleMethod"
            request = Request(client_id=1, request_data=cancel_message)
            request_ser = request.SerializeToString()

            server.start()
            # unfortunately, these are just bare exceptions in grpc...
            with self.assertRaises(Exception):  # as cm:
                channel.unary_unary(rpc_call)(request_ser)
            # exc = cm.exception
            server.stop(None)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        self.assertEqual(span.name, rpc_call)
        self.assertIs(span.kind, trace.SpanKind.SERVER)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.CANCELLED}: {grpc.StatusCode.CANCELLED.value[1]}",
        )
        # self.assertEqual(
        #     span.status.description,
        #     f"{exc.code()}: {exc.details()}",
        # )

        # check attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.NET_PEER_IP: "[::1]",
                # SpanAttributes.NET_PEER_PORT: "0",
                SpanAttributes.NET_PEER_NAME: "localhost",
                SpanAttributes.RPC_METHOD: "SimpleMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE:
                    grpc.StatusCode.CANCELLED.value[0],
            },
        )

        # check events
        self.assertEqual(len(span.events), 2)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(request_ser)
            }
        )
        self.assertEvent(
            span.events[1],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "SENT",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: 0
            }
        )

    def test_cancel_streaming(self):
        """Check that we can catch a cancellation of a streaming call properly.
        """

        cancel_message = "cancel"

        # Intercept gRPC calls...
        interceptor = server_interceptor()

        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=[interceptor],
            )
            add_GRPCTestServerServicer_to_server(TestServer(), server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            # setup the RPC
            rpc_call = "/GRPCTestServer/ServerStreamingMethod"
            request = Request(client_id=1, request_data=cancel_message)
            request_ser = request.SerializeToString()

            server.start()
            responses = []
            with self.assertRaises(Exception):
                for res in channel.unary_stream(rpc_call)(request_ser):
                    responses.append(res)
            server.stop(None)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        self.assertEqual(span.name, rpc_call)
        self.assertIs(span.kind, trace.SpanKind.SERVER)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.CANCELLED}: {grpc.StatusCode.CANCELLED.value[1]}",
        )
        # self.assertEqual(
        #     span.status.description,
        #     f"{exc.code()}: {exc.details()}",
        # )

        # check attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.NET_PEER_IP: "[::1]",
                # SpanAttributes.NET_PEER_PORT: "0",
                SpanAttributes.NET_PEER_NAME: "localhost",
                SpanAttributes.RPC_METHOD: "ServerStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE:
                    grpc.StatusCode.CANCELLED.value[0],
            },
        )

        # check events
        self.assertEqual(len(span.events), 2)
        self.assertEqual(len(responses), 1)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(request_ser)
            }
        )
        self.assertEvent(
            span.events[1],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "SENT",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(responses[0])
            }
        )

    def test_error(self):
        """Check that we can catch an error properly"""

        error_message = "error"

        # Intercept gRPC calls...
        interceptor = server_interceptor()

        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=[interceptor],
            )
            add_GRPCTestServerServicer_to_server(TestServer(), server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            rpc_call = "/GRPCTestServer/SimpleMethod"
            request = Request(client_id=1, request_data=error_message)
            request_ser = request.SerializeToString()

            server.start()
            # unfortunately, these are just bare exceptions in grpc...
            with self.assertRaises(Exception):
                channel.unary_unary(rpc_call)(request_ser)
            server.stop(None)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        self.assertEqual(span.name, rpc_call)
        self.assertIs(span.kind, trace.SpanKind.SERVER)

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.INVALID_ARGUMENT}: {error_message}",
        )

        # Check attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.NET_PEER_IP: "[::1]",
                # SpanAttributes.NET_PEER_PORT: "0",
                SpanAttributes.NET_PEER_NAME: "localhost",
                SpanAttributes.RPC_METHOD: "SimpleMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE:
                    grpc.StatusCode.INVALID_ARGUMENT.value[0],
            },
        )

        # Check events
        self.assertEqual(len(span.events), 2)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(request_ser)
            }
        )
        self.assertEvent(
            span.events[1],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "SENT",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: 0
            }
        )

    def test_error_streaming(self):
        """Check that we can catch an error in a streaming call properly"""

        error_message = "error"

        # Intercept gRPC calls...
        interceptor = server_interceptor()

        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=[interceptor],
            )
            add_GRPCTestServerServicer_to_server(TestServer(), server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            # setup the RPC
            rpc_call = "/GRPCTestServer/ServerStreamingMethod"
            request = Request(client_id=1, request_data=error_message)
            request_ser = request.SerializeToString()

            server.start()
            responses = []
            with self.assertRaises(Exception):
                for res in channel.unary_stream(rpc_call)(request_ser):
                    responses.append(res)
            server.stop(None)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        self.assertEqual(span.name, rpc_call)
        self.assertIs(span.kind, trace.SpanKind.SERVER)

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.INVALID_ARGUMENT}: {error_message}",
        )

        # Check attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.NET_PEER_IP: "[::1]",
                # SpanAttributes.NET_PEER_PORT: "0",
                SpanAttributes.NET_PEER_NAME: "localhost",
                SpanAttributes.RPC_METHOD: "ServerStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE:
                    grpc.StatusCode.INVALID_ARGUMENT.value[0],
            },
        )

        # Check events
        self.assertEqual(len(span.events), 2)
        self.assertEqual(len(responses), 1)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(request_ser)
            }
        )
        self.assertEvent(
            span.events[1],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "SENT",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(responses[0])
            }
        )

    def test_raise_exception(self):
        """Check that we can catch a raised exception properly"""

        exc_message = "exception"

        # Intercept gRPC calls...
        interceptor = server_interceptor()

        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=[interceptor],
            )
            add_GRPCTestServerServicer_to_server(TestServer(), server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            rpc_call = "/GRPCTestServer/SimpleMethod"
            request = Request(client_id=1, request_data=exc_message)
            request_ser = request.SerializeToString()

            server.start()
            # unfortunately, these are just bare exceptions in grpc...
            with self.assertRaises(Exception):
                channel.unary_unary(rpc_call)(request_ser)
            server.stop(None)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        self.assertEqual(span.name, rpc_call)
        self.assertIs(span.kind, trace.SpanKind.SERVER)

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{ValueError.__name__}: {exc_message}",
        )

        # Check attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.NET_PEER_IP: "[::1]",
                # SpanAttributes.NET_PEER_PORT: "0",
                SpanAttributes.NET_PEER_NAME: "localhost",
                SpanAttributes.RPC_METHOD: "SimpleMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE:
                    grpc.StatusCode.UNKNOWN.value[0],
            },
        )

        # Check events
        self.assertEqual(len(span.events), 2)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(request_ser)
            }
        )
        self.assertEvent(
            span.events[1],
            "exception",
            {
                "exception.type": ValueError.__name__,
                "exception.message": exc_message,
                # "exception.stacktrace": "...",
                "exception.escaped": str(False),
            }
        )

    def test_raise_exception_streaming(self):
        """Check that we can catch a raised exception in a streaming call
        properly.
        """

        exc_message = "exception"

        # Intercept gRPC calls...
        interceptor = server_interceptor()

        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=[interceptor],
            )
            add_GRPCTestServerServicer_to_server(TestServer(), server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            # setup the RPC
            rpc_call = "/GRPCTestServer/ServerStreamingMethod"
            request = Request(client_id=1, request_data=exc_message)
            request_ser = request.SerializeToString()

            server.start()
            responses = []
            with self.assertRaises(Exception):
                for res in channel.unary_stream(rpc_call)(request_ser):
                    responses.append(res)
            server.stop(None)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        self.assertEqual(span.name, rpc_call)
        self.assertIs(span.kind, trace.SpanKind.SERVER)

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{ValueError.__name__}: {exc_message}",
        )

        # Check attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.NET_PEER_IP: "[::1]",
                # SpanAttributes.NET_PEER_PORT: "0",
                SpanAttributes.NET_PEER_NAME: "localhost",
                SpanAttributes.RPC_METHOD: "ServerStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE:
                    grpc.StatusCode.UNKNOWN.value[0],
            },
        )

        # Check events
        self.assertEqual(len(span.events), 3)
        self.assertEqual(len(responses), 1)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(request_ser)
            }
        )
        self.assertEvent(
            span.events[1],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "SENT",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: len(responses[0])
            }
        )
        self.assertEvent(
            span.events[2],
            "exception",
            {
                "exception.type": ValueError.__name__,
                "exception.message": exc_message,
                # "exception.stacktrace": "...",
                "exception.escaped": str(False),
            }
        )

    def test_metrics(self):
        # Intercept gRPC calls...
        interceptor = server_interceptor()

        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=[interceptor],
            )
            add_GRPCTestServerServicer_to_server(TestServer(), server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            rpc_call = "/GRPCTestServer/SimpleMethod"
            request = Request(client_id=1, request_data="test")
            request_ser = request.SerializeToString()

            try:
                server.start()
                response = channel.unary_unary(rpc_call)(request_ser)
            finally:
                server.stop(None)

        metrics_list = self.memory_metrics_reader.get_metrics_data()

        self.assertNotEqual(len(metrics_list.resource_metrics), 0)
        for resource_metric in metrics_list.resource_metrics:
            self.assertNotEqual(len(resource_metric.scope_metrics), 0)
            for scope_metric in resource_metric.scope_metrics:
                self.assertNotEqual(len(scope_metric.metrics), 0)
                self.assertEqualMetricInstrumentationScope(
                    scope_metric, opentelemetry.instrumentation.grpc
                )
                self.assertEqual(
                    len(scope_metric.metrics), len(_expected_metric_names)
                )

                for metric in scope_metric.metrics:
                    self.assertIn(metric.name, _expected_metric_names)
                    self.assertIsInstance(
                        metric.data, _expected_metric_names[metric.name][0]
                    )
                    self.assertEqual(
                        metric.unit, _expected_metric_names[metric.name][1]
                    )
                    self.assertEqual(
                        metric.description,
                        _expected_metric_names[metric.name][2]
                    )

                    data_points = list(metric.data.data_points)
                    self.assertEqual(len(data_points), 1)

                    for point in data_points:
                        if isinstance(metric.data, Histogram):
                            self.assertIsInstance(
                                point, HistogramDataPoint
                            )
                            self.assertEqual(point.count, 1)
                            if metric.name == "rpc.server.duration":
                                self.assertGreaterEqual(point.sum, 0)
                            elif metric.name == "rpc.server.request.size":
                                self.assertEqual(point.sum, len(request_ser))
                            elif metric.name == "rpc.server.response.size":
                                self.assertEqual(point.sum, len(response))
                            elif metric.name == "rpc.server.requests_per_rpc":
                                self.assertEqual(point.sum, 1)
                            elif metric.name == "rpc.server.responses_per_rpc":
                                self.assertEqual(point.sum, 1)

                        self.assertMetricDataPointHasAttributes(
                            point,
                            {
                                SpanAttributes.NET_PEER_IP: "[::1]",
                                # SpanAttributes.NET_PEER_PORT: "0",
                                SpanAttributes.NET_PEER_NAME: "localhost",
                                SpanAttributes.RPC_METHOD: "SimpleMethod",
                                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                                SpanAttributes.RPC_SYSTEM: "grpc",
                            },
                        )
                        if metric.name == "rpc.server.duration":
                            self.assertMetricDataPointHasAttributes(
                                point,
                                {
                                    SpanAttributes.RPC_GRPC_STATUS_CODE:
                                        grpc.StatusCode.OK.value[0]
                                },
                            )

    def test_metrics_error(self):

        error_message = "error"

        # Intercept gRPC calls...
        interceptor = server_interceptor()

        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=[interceptor],
            )
            add_GRPCTestServerServicer_to_server(TestServer(), server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            rpc_call = "/GRPCTestServer/SimpleMethod"
            request = Request(client_id=1, request_data=error_message)
            request_ser = request.SerializeToString()

            try:
                server.start()
                with self.assertRaises(grpc.RpcError):
                    channel.unary_unary(rpc_call)(request_ser)
            finally:
                server.stop(None)

        metrics_list = self.memory_metrics_reader.get_metrics_data()

        self.assertNotEqual(len(metrics_list.resource_metrics), 0)
        for resource_metric in metrics_list.resource_metrics:
            self.assertNotEqual(len(resource_metric.scope_metrics), 0)
            for scope_metric in resource_metric.scope_metrics:
                self.assertNotEqual(len(scope_metric.metrics), 0)
                self.assertEqualMetricInstrumentationScope(
                    scope_metric, opentelemetry.instrumentation.grpc
                )
                self.assertEqual(
                    len(scope_metric.metrics), len(_expected_metric_names)
                )

                for metric in scope_metric.metrics:
                    self.assertIn(metric.name, _expected_metric_names)
                    self.assertIsInstance(
                        metric.data, _expected_metric_names[metric.name][0]
                    )
                    self.assertEqual(
                        metric.unit, _expected_metric_names[metric.name][1]
                    )
                    self.assertEqual(
                        metric.description,
                        _expected_metric_names[metric.name][2]
                    )

                    data_points = list(metric.data.data_points)
                    self.assertEqual(len(data_points), 1)

                    for point in data_points:
                        if isinstance(metric.data, Histogram):
                            self.assertIsInstance(
                                point, HistogramDataPoint
                            )
                            self.assertEqual(point.count, 1)
                            if metric.name == "rpc.server.duration":
                                self.assertGreaterEqual(point.sum, 0)
                            elif metric.name == "rpc.server.request.size":
                                self.assertEqual(point.sum, len(request_ser))
                            elif metric.name == "rpc.server.response.size":
                                self.assertEqual(point.sum, 0)
                            elif metric.name == "rpc.server.requests_per_rpc":
                                self.assertEqual(point.sum, 1)
                            elif metric.name == "rpc.server.responses_per_rpc":
                                self.assertEqual(point.sum, 1)

                        self.assertMetricDataPointHasAttributes(
                            point,
                            {
                                SpanAttributes.NET_PEER_IP: "[::1]",
                                # SpanAttributes.NET_PEER_PORT: "0",
                                SpanAttributes.NET_PEER_NAME: "localhost",
                                SpanAttributes.RPC_METHOD: "SimpleMethod",
                                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                                SpanAttributes.RPC_SYSTEM: "grpc",
                            },
                        )
                        if metric.name == "rpc.server.duration":
                            self.assertMetricDataPointHasAttributes(
                                point,
                                {
                                    SpanAttributes.RPC_GRPC_STATUS_CODE:
                                        grpc.StatusCode.INVALID_ARGUMENT.value[
                                            0
                                        ]
                                },
                            )

    def test_metrics_three_calls(self):
        no_calls = 3

        # Intercept gRPC calls...
        interceptor = server_interceptor()

        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=[interceptor],
            )
            add_GRPCTestServerServicer_to_server(TestServer(), server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            rpc_call = "/GRPCTestServer/SimpleMethod"
            request = Request(client_id=1, request_data="test")
            request_ser = request.SerializeToString()

            try:
                server.start()
                for _ in range(no_calls):
                    response = channel.unary_unary(rpc_call)(request_ser)
            finally:
                server.stop(None)

        metrics_list = self.memory_metrics_reader.get_metrics_data()

        self.assertNotEqual(len(metrics_list.resource_metrics), 0)
        for resource_metric in metrics_list.resource_metrics:
            self.assertNotEqual(len(resource_metric.scope_metrics), 0)
            for scope_metric in resource_metric.scope_metrics:
                self.assertNotEqual(len(scope_metric.metrics), 0)
                self.assertEqualMetricInstrumentationScope(
                    scope_metric, opentelemetry.instrumentation.grpc
                )
                self.assertEqual(
                    len(scope_metric.metrics), len(_expected_metric_names)
                )

                for metric in scope_metric.metrics:
                    self.assertIn(metric.name, _expected_metric_names)
                    self.assertIsInstance(
                        metric.data, _expected_metric_names[metric.name][0]
                    )
                    self.assertEqual(
                        metric.unit, _expected_metric_names[metric.name][1]
                    )
                    self.assertEqual(
                        metric.description,
                        _expected_metric_names[metric.name][2]
                    )

                    data_points = list(metric.data.data_points)
                    self.assertEqual(len(data_points), 1)

                    for point in data_points:
                        if isinstance(metric.data, Histogram):
                            self.assertIsInstance(
                                point, HistogramDataPoint
                            )
                            self.assertEqual(point.count, no_calls)
                            if metric.name == "rpc.server.duration":
                                self.assertGreaterEqual(point.sum, 0)
                            elif metric.name == "rpc.server.request.size":
                                self.assertEqual(
                                    point.sum, no_calls * len(request_ser)
                                )
                            elif metric.name == "rpc.server.response.size":
                                self.assertEqual(
                                    point.sum, no_calls * len(response)
                                )
                            elif metric.name == "rpc.server.requests_per_rpc":
                                self.assertEqual(point.sum, no_calls)
                            elif metric.name == "rpc.server.responses_per_rpc":
                                self.assertEqual(point.sum, no_calls)

                        self.assertMetricDataPointHasAttributes(
                            point,
                            {
                                SpanAttributes.NET_PEER_IP: "[::1]",
                                # SpanAttributes.NET_PEER_PORT: "0",
                                SpanAttributes.NET_PEER_NAME: "localhost",
                                SpanAttributes.RPC_METHOD: "SimpleMethod",
                                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                                SpanAttributes.RPC_SYSTEM: "grpc",
                            },
                        )
                        if metric.name == "rpc.server.duration":
                            self.assertMetricDataPointHasAttributes(
                                point,
                                {
                                    SpanAttributes.RPC_GRPC_STATUS_CODE:
                                        grpc.StatusCode.OK.value[0]
                                },
                            )

    def test_metrics_client_streaming(self):

        # Intercept gRPC calls...
        interceptor = server_interceptor()

        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=[interceptor],
            )
            add_GRPCTestServerServicer_to_server(TestServer(), server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            # setup the RPC
            rpc_call = "/GRPCTestServer/ClientStreamingMethod"
            request = Request(client_id=1, request_data="test")
            requests = [request.SerializeToString() for _ in range(5)]

            try:
                server.start()
                response = channel.stream_unary(rpc_call)(iter(requests))
            finally:
                server.stop(None)

        metrics_list = self.memory_metrics_reader.get_metrics_data()

        self.assertNotEqual(len(metrics_list.resource_metrics), 0)
        for resource_metric in metrics_list.resource_metrics:
            self.assertNotEqual(len(resource_metric.scope_metrics), 0)
            for scope_metric in resource_metric.scope_metrics:
                self.assertNotEqual(len(scope_metric.metrics), 0)
                self.assertEqualMetricInstrumentationScope(
                    scope_metric, opentelemetry.instrumentation.grpc
                )
                self.assertEqual(
                    len(scope_metric.metrics), len(_expected_metric_names)
                )

                for metric in scope_metric.metrics:
                    self.assertIn(metric.name, _expected_metric_names)
                    self.assertIsInstance(
                        metric.data, _expected_metric_names[metric.name][0]
                    )
                    self.assertEqual(
                        metric.unit, _expected_metric_names[metric.name][1]
                    )
                    self.assertEqual(
                        metric.description,
                        _expected_metric_names[metric.name][2]
                    )

                    data_points = list(metric.data.data_points)
                    self.assertEqual(len(data_points), 1)

                    for point in data_points:
                        if isinstance(metric.data, Histogram):
                            self.assertIsInstance(
                                point, HistogramDataPoint
                            )
                            if metric.name == "rpc.server.duration":
                                self.assertEqual(point.count, 1)
                                self.assertGreaterEqual(point.sum, 0)
                            elif metric.name == "rpc.server.request.size":
                                self.assertEqual(point.count, len(requests))
                                self.assertEqual(
                                    point.sum, sum(map(len, requests))
                                )
                            elif metric.name == "rpc.server.response.size":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, len(response))
                            elif metric.name == "rpc.server.requests_per_rpc":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, len(requests))
                            elif metric.name == "rpc.server.responses_per_rpc":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, 1)

                        self.assertMetricDataPointHasAttributes(
                            point,
                            {
                                SpanAttributes.NET_PEER_IP: "[::1]",
                                # SpanAttributes.NET_PEER_PORT: "0",
                                SpanAttributes.NET_PEER_NAME: "localhost",
                                SpanAttributes.RPC_METHOD:
                                    "ClientStreamingMethod",
                                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                                SpanAttributes.RPC_SYSTEM: "grpc",
                            },
                        )
                        if metric.name == "rpc.server.duration":
                            self.assertMetricDataPointHasAttributes(
                                point,
                                {
                                    SpanAttributes.RPC_GRPC_STATUS_CODE:
                                        grpc.StatusCode.OK.value[0]
                                },
                            )

    def test_metrics_client_streaming_abort(self):

        error_message = "abort"

        # Intercept gRPC calls...
        interceptor = server_interceptor()

        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=[interceptor],
            )
            add_GRPCTestServerServicer_to_server(TestServer(), server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            # setup the RPC
            rpc_call = "/GRPCTestServer/ClientStreamingMethod"
            request = Request(client_id=1, request_data=error_message)
            requests = [request.SerializeToString() for _ in range(5)]

            try:
                server.start()
                with self.assertRaises(grpc.RpcError):
                    channel.stream_unary(rpc_call)(iter(requests))
            finally:
                server.stop(None)

        metrics_list = self.memory_metrics_reader.get_metrics_data()

        self.assertNotEqual(len(metrics_list.resource_metrics), 0)
        for resource_metric in metrics_list.resource_metrics:
            self.assertNotEqual(len(resource_metric.scope_metrics), 0)
            for scope_metric in resource_metric.scope_metrics:
                self.assertNotEqual(len(scope_metric.metrics), 0)
                self.assertEqualMetricInstrumentationScope(
                    scope_metric, opentelemetry.instrumentation.grpc
                )
                self.assertLess(
                    len(scope_metric.metrics), len(_expected_metric_names)
                )

                for metric in scope_metric.metrics:
                    self.assertIn(metric.name, _expected_metric_names)
                    self.assertIsInstance(
                        metric.data, _expected_metric_names[metric.name][0]
                    )
                    self.assertEqual(
                        metric.unit, _expected_metric_names[metric.name][1]
                    )
                    self.assertEqual(
                        metric.description,
                        _expected_metric_names[metric.name][2]
                    )

                    data_points = list(metric.data.data_points)
                    self.assertEqual(len(data_points), 1)

                    for point in data_points:
                        if isinstance(metric.data, Histogram):
                            self.assertIsInstance(
                                point, HistogramDataPoint
                            )
                            if metric.name == "rpc.server.duration":
                                self.assertEqual(point.count, 1)
                                self.assertGreaterEqual(point.sum, 0)
                            elif metric.name == "rpc.server.request.size":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, len(requests[0]))
                            elif metric.name == "rpc.server.response.size":
                                self.assertEqual(point.count, 0)
                                self.assertEqual(point.sum, 0)
                            elif metric.name == "rpc.server.requests_per_rpc":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, 1)
                            elif metric.name == "rpc.server.responses_per_rpc":
                                self.assertEqual(point.count, 0)
                                self.assertEqual(point.sum, 0)

                        self.assertMetricDataPointHasAttributes(
                            point,
                            {
                                SpanAttributes.NET_PEER_IP: "[::1]",
                                # SpanAttributes.NET_PEER_PORT: "0",
                                SpanAttributes.NET_PEER_NAME: "localhost",
                                SpanAttributes.RPC_METHOD:
                                    "ClientStreamingMethod",
                                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                                SpanAttributes.RPC_SYSTEM: "grpc",
                            },
                        )
                        if metric.name == "rpc.server.duration":
                            self.assertMetricDataPointHasAttributes(
                                point,
                                {
                                    SpanAttributes.RPC_GRPC_STATUS_CODE:
                                        grpc.StatusCode.FAILED_PRECONDITION.value[
                                            0
                                        ]
                                },
                            )

    def test_metrics_server_streaming(self):

        # Intercept gRPC calls...
        interceptor = server_interceptor()

        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=[interceptor],
            )
            add_GRPCTestServerServicer_to_server(TestServer(), server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            # setup the RPC
            rpc_call = "/GRPCTestServer/ServerStreamingMethod"
            request = Request(client_id=1, request_data="test")
            request_ser = request.SerializeToString()

            try:
                server.start()
                responses = list(channel.unary_stream(rpc_call)(request_ser))
            finally:
                server.stop(None)

        metrics_list = self.memory_metrics_reader.get_metrics_data()

        self.assertNotEqual(len(metrics_list.resource_metrics), 0)
        for resource_metric in metrics_list.resource_metrics:
            self.assertNotEqual(len(resource_metric.scope_metrics), 0)
            for scope_metric in resource_metric.scope_metrics:
                self.assertNotEqual(len(scope_metric.metrics), 0)
                self.assertEqualMetricInstrumentationScope(
                    scope_metric, opentelemetry.instrumentation.grpc
                )
                self.assertEqual(
                    len(scope_metric.metrics), len(_expected_metric_names)
                )

                for metric in scope_metric.metrics:
                    self.assertIn(metric.name, _expected_metric_names)
                    self.assertIsInstance(
                        metric.data, _expected_metric_names[metric.name][0]
                    )
                    self.assertEqual(
                        metric.unit, _expected_metric_names[metric.name][1]
                    )
                    self.assertEqual(
                        metric.description,
                        _expected_metric_names[metric.name][2]
                    )

                    data_points = list(metric.data.data_points)
                    self.assertEqual(len(data_points), 1)

                    for point in data_points:
                        if isinstance(metric.data, Histogram):
                            self.assertIsInstance(
                                point, HistogramDataPoint
                            )
                            if metric.name == "rpc.server.duration":
                                self.assertEqual(point.count, 1)
                                self.assertGreaterEqual(point.sum, 0)
                            elif metric.name == "rpc.server.request.size":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, len(request_ser))
                            elif metric.name == "rpc.server.response.size":
                                self.assertEqual(point.count, len(responses))
                                self.assertEqual(
                                    point.sum, sum(map(len, responses))
                                )
                            elif metric.name == "rpc.server.requests_per_rpc":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, 1)
                            elif metric.name == "rpc.server.responses_per_rpc":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, len(responses))

                        self.assertMetricDataPointHasAttributes(
                            point,
                            {
                                SpanAttributes.NET_PEER_IP: "[::1]",
                                # SpanAttributes.NET_PEER_PORT: "0",
                                SpanAttributes.NET_PEER_NAME: "localhost",
                                SpanAttributes.RPC_METHOD:
                                    "ServerStreamingMethod",
                                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                                SpanAttributes.RPC_SYSTEM: "grpc",
                            },
                        )
                        if metric.name == "rpc.server.duration":
                            self.assertMetricDataPointHasAttributes(
                                point,
                                {
                                    SpanAttributes.RPC_GRPC_STATUS_CODE:
                                        grpc.StatusCode.OK.value[0]
                                },
                            )

    def test_metrics_bidirectional_streaming(self):

        # Intercept gRPC calls...
        interceptor = server_interceptor()

        with futures.ThreadPoolExecutor(max_workers=1) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=[interceptor],
            )
            add_GRPCTestServerServicer_to_server(TestServer(), server)
            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")

            # setup the RPC
            rpc_call = "/GRPCTestServer/BidirectionalStreamingMethod"
            request = Request(client_id=1, request_data="test")
            requests = [request.SerializeToString() for _ in range(5)]

            try:
                server.start()
                responses = list(
                    channel.stream_stream(rpc_call)(iter(requests))
                )
            finally:
                server.stop(None)

        metrics_list = self.memory_metrics_reader.get_metrics_data()

        self.assertNotEqual(len(metrics_list.resource_metrics), 0)
        for resource_metric in metrics_list.resource_metrics:
            self.assertNotEqual(len(resource_metric.scope_metrics), 0)
            for scope_metric in resource_metric.scope_metrics:
                self.assertNotEqual(len(scope_metric.metrics), 0)
                self.assertEqualMetricInstrumentationScope(
                    scope_metric, opentelemetry.instrumentation.grpc
                )
                self.assertEqual(
                    len(scope_metric.metrics), len(_expected_metric_names)
                )

                for metric in scope_metric.metrics:
                    self.assertIn(metric.name, _expected_metric_names)
                    self.assertIsInstance(
                        metric.data, _expected_metric_names[metric.name][0]
                    )
                    self.assertEqual(
                        metric.unit, _expected_metric_names[metric.name][1]
                    )
                    self.assertEqual(
                        metric.description,
                        _expected_metric_names[metric.name][2]
                    )

                    data_points = list(metric.data.data_points)
                    self.assertEqual(len(data_points), 1)

                    for point in data_points:
                        if isinstance(metric.data, Histogram):
                            self.assertIsInstance(
                                point, HistogramDataPoint
                            )
                            if metric.name == "rpc.server.duration":
                                self.assertEqual(point.count, 1)
                                self.assertGreaterEqual(point.sum, 0)
                            elif metric.name == "rpc.server.request.size":
                                self.assertEqual(point.count, len(requests))
                                self.assertEqual(
                                    point.sum, sum(map(len, requests))
                                )
                            elif metric.name == "rpc.server.response.size":
                                self.assertEqual(point.count, len(responses))
                                self.assertEqual(
                                    point.sum, sum(map(len, responses))
                                )
                            elif metric.name == "rpc.server.requests_per_rpc":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, len(requests))
                            elif metric.name == "rpc.server.responses_per_rpc":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, len(responses))

                        self.assertMetricDataPointHasAttributes(
                            point,
                            {
                                SpanAttributes.NET_PEER_IP: "[::1]",
                                # SpanAttributes.NET_PEER_PORT: "0",
                                SpanAttributes.NET_PEER_NAME: "localhost",
                                SpanAttributes.RPC_METHOD:
                                    "BidirectionalStreamingMethod",
                                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                                SpanAttributes.RPC_SYSTEM: "grpc",
                            },
                        )
                        if metric.name == "rpc.server.duration":
                            self.assertMetricDataPointHasAttributes(
                                point,
                                {
                                    SpanAttributes.RPC_GRPC_STATUS_CODE:
                                        grpc.StatusCode.OK.value[0]
                                },
                            )


def get_latch(num):
    """Get a countdown latch function for use in n threads."""
    cv = threading.Condition()
    count = 0

    def countdown_latch():
        """Block until n-1 other threads have called."""
        nonlocal count
        cv.acquire()
        count += 1
        cv.notify()
        cv.release()
        cv.acquire()
        while count < num:
            cv.wait()
        cv.release()

    return countdown_latch
