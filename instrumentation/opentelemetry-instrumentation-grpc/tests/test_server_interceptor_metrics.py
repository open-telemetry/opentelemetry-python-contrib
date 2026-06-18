# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import contextlib
from concurrent import futures

import grpc

from opentelemetry.instrumentation.grpc import server_interceptor
from opentelemetry.semconv._incubating.attributes.error_attributes import (
    ERROR_TYPE,
)
from opentelemetry.semconv._incubating.attributes.rpc_attributes import (
    RPC_METHOD,
    RPC_RESPONSE_STATUS_CODE,
    RPC_SYSTEM_NAME,
    RpcSystemNameValues,
)
from opentelemetry.semconv._incubating.metrics.rpc_metrics import (
    RPC_SERVER_CALL_DURATION,
)
from opentelemetry.test.test_base import TestBase

from .protobuf.test_server_pb2 import Request, Response
from .protobuf.test_server_pb2_grpc import (
    GRPCTestServerServicer,
    add_GRPCTestServerServicer_to_server,
)


class Servicer(GRPCTestServerServicer):
    def SimpleMethod(self, request, context):
        return Response(
            server_id=request.client_id,
            response_data=request.request_data,
        )


class TestServerInterceptorMetrics(TestBase):
    @staticmethod
    @contextlib.contextmanager
    def server(max_workers=1, interceptors=None):
        with futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=interceptors or [],
            )

            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")
            yield server, channel

    def test_unary_call_records_duration_metric(self):
        """A unary server RPC produces an rpc.server.call.duration histogram."""
        interceptor = server_interceptor(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )

        with self.server(max_workers=1, interceptors=[interceptor]) as (
            server,
            channel,
        ):
            add_GRPCTestServerServicer_to_server(Servicer(), server)

            rpc_call = "/GRPCTestServer/SimpleMethod"
            request = Request(client_id=1, request_data="test")
            msg = request.SerializeToString()
            try:
                server.start()
                channel.unary_unary(rpc_call)(msg)
            finally:
                server.stop(None)

        metrics = self.get_sorted_metrics()
        duration_metric = next(
            (m for m in metrics if m.name == RPC_SERVER_CALL_DURATION),
            None,
        )

        self.assertIsNotNone(
            duration_metric,
            f"Expected metric '{RPC_SERVER_CALL_DURATION}' not found. "
            f"Got: {[m.name for m in metrics]}",
        )
        self.assertEqual(duration_metric.unit, "s")

        data_points = list(duration_metric.data.data_points)
        self.assertEqual(len(data_points), 1)

        point = data_points[0]
        self.assertEqual(point.count, 1)
        self.assertGreater(point.sum, 0)
        self.assertEqual(
            point.explicit_bounds,
            (
                0.005,
                0.01,
                0.025,
                0.05,
                0.075,
                0.1,
                0.25,
                0.5,
                0.75,
                1,
                2.5,
                5,
                7.5,
                10,
            ),
        )

        attrs = dict(point.attributes)
        self.assertEqual(
            attrs[RPC_SYSTEM_NAME], RpcSystemNameValues.GRPC.value
        )
        self.assertEqual(attrs[RPC_METHOD], "GRPCTestServer/SimpleMethod")
        self.assertEqual(attrs[RPC_RESPONSE_STATUS_CODE], "OK")
        self.assertNotIn(ERROR_TYPE, attrs)

    def test_error_call_records_status_in_metric(self):
        """Server metric records the gRPC error status code on abort."""

        class ErrorServicer(GRPCTestServerServicer):
            def SimpleMethod(self, request, context):
                context.abort(grpc.StatusCode.INTERNAL, "test failure")

        interceptor = server_interceptor(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )

        with self.server(max_workers=1, interceptors=[interceptor]) as (
            server,
            channel,
        ):
            add_GRPCTestServerServicer_to_server(ErrorServicer(), server)

            rpc_call = "/GRPCTestServer/SimpleMethod"
            request = Request(client_id=1, request_data="test")
            msg = request.SerializeToString()
            try:
                server.start()
                with self.assertRaises(grpc.RpcError):
                    channel.unary_unary(rpc_call)(msg)
            finally:
                server.stop(None)

        metrics = self.get_sorted_metrics()
        duration_metric = next(
            (m for m in metrics if m.name == RPC_SERVER_CALL_DURATION),
            None,
        )

        self.assertIsNotNone(duration_metric)

        data_points = list(duration_metric.data.data_points)
        self.assertEqual(len(data_points), 1)

        point = data_points[0]
        self.assertEqual(point.count, 1)
        self.assertGreater(point.sum, 0)

        attrs = dict(point.attributes)
        self.assertEqual(
            attrs[RPC_SYSTEM_NAME], RpcSystemNameValues.GRPC.value
        )
        self.assertEqual(attrs[RPC_METHOD], "GRPCTestServer/SimpleMethod")
        self.assertEqual(attrs[RPC_RESPONSE_STATUS_CODE], "INTERNAL")
        self.assertEqual(attrs[ERROR_TYPE], "INTERNAL")

    def test_uncaught_exception_records_unknown_status(self):
        """Uncaught handler exception records UNKNOWN status in metric."""

        class CrashingServicer(GRPCTestServerServicer):
            def SimpleMethod(self, request, context):
                raise RuntimeError("unexpected crash")

        interceptor = server_interceptor(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )

        with self.server(max_workers=1, interceptors=[interceptor]) as (
            server,
            channel,
        ):
            add_GRPCTestServerServicer_to_server(CrashingServicer(), server)

            rpc_call = "/GRPCTestServer/SimpleMethod"
            request = Request(client_id=1, request_data="test")
            msg = request.SerializeToString()
            try:
                server.start()
                with self.assertRaises(grpc.RpcError):
                    channel.unary_unary(rpc_call)(msg)
            finally:
                server.stop(None)

        metrics = self.get_sorted_metrics()
        duration_metric = next(
            (m for m in metrics if m.name == RPC_SERVER_CALL_DURATION),
            None,
        )

        self.assertIsNotNone(duration_metric)

        data_points = list(duration_metric.data.data_points)
        self.assertEqual(len(data_points), 1)

        point = data_points[0]
        attrs = dict(point.attributes)
        self.assertEqual(attrs[RPC_RESPONSE_STATUS_CODE], "UNKNOWN")
        self.assertEqual(attrs[ERROR_TYPE], "UNKNOWN")

    def test_streaming_call_records_duration_metric(self):
        """Server interceptor records metric on a streaming RPC."""

        class StreamingServicer(GRPCTestServerServicer):
            def ServerStreamingMethod(self, request, context):
                for data in ("one", "two", "three"):
                    yield Response(
                        server_id=request.client_id,
                        response_data=data,
                    )

        interceptor = server_interceptor(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )

        with self.server(max_workers=1, interceptors=[interceptor]) as (
            server,
            channel,
        ):
            add_GRPCTestServerServicer_to_server(StreamingServicer(), server)

            rpc_call = "/GRPCTestServer/ServerStreamingMethod"
            request = Request(client_id=1, request_data="test")
            msg = request.SerializeToString()
            try:
                server.start()
                list(channel.unary_stream(rpc_call)(msg))
            finally:
                server.stop(None)

        metrics = self.get_sorted_metrics()
        duration_metric = next(
            (m for m in metrics if m.name == RPC_SERVER_CALL_DURATION),
            None,
        )

        self.assertIsNotNone(
            duration_metric,
            f"Expected metric '{RPC_SERVER_CALL_DURATION}' not found "
            f"for streaming RPC. Got: {[m.name for m in metrics]}",
        )

        data_points = list(duration_metric.data.data_points)
        self.assertEqual(len(data_points), 1)

        point = data_points[0]
        self.assertEqual(point.count, 1)
        self.assertGreater(point.sum, 0)

        attrs = dict(point.attributes)
        self.assertEqual(
            attrs[RPC_SYSTEM_NAME], RpcSystemNameValues.GRPC.value
        )
        self.assertEqual(
            attrs[RPC_METHOD], "GRPCTestServer/ServerStreamingMethod"
        )
        self.assertEqual(attrs[RPC_RESPONSE_STATUS_CODE], "OK")
