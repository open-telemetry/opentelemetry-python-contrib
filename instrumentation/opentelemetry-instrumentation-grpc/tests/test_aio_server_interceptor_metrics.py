# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import IsolatedAsyncioTestCase

import grpc
import grpc.aio

from opentelemetry.instrumentation.grpc import aio_server_interceptor
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
    async def SimpleMethod(self, request, context):
        return Response(
            server_id=request.client_id,
            response_data=request.request_data,
        )

    async def ServerStreamingMethod(self, request, context):
        for data in ("one", "two", "three"):
            yield Response(
                server_id=request.client_id,
                response_data=data,
            )


class TestAioServerInterceptorMetrics(TestBase, IsolatedAsyncioTestCase):
    async def test_unary_call_records_duration_metric(self):
        """Aio server interceptor records rpc.server.call.duration on unary RPC."""
        interceptor = aio_server_interceptor(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )

        server = grpc.aio.server(interceptors=[interceptor])
        add_GRPCTestServerServicer_to_server(Servicer(), server)
        port = server.add_insecure_port("[::]:0")
        channel = grpc.aio.insecure_channel(f"localhost:{port:d}")

        await server.start()
        try:
            rpc_call = "/GRPCTestServer/SimpleMethod"
            request = Request(client_id=1, request_data="test")
            msg = request.SerializeToString()
            await channel.unary_unary(rpc_call)(msg)
        finally:
            await channel.close()
            await server.stop(None)

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

        attrs = dict(point.attributes)
        self.assertEqual(
            attrs[RPC_SYSTEM_NAME], RpcSystemNameValues.GRPC.value
        )
        self.assertEqual(attrs[RPC_METHOD], "GRPCTestServer/SimpleMethod")
        self.assertEqual(attrs[RPC_RESPONSE_STATUS_CODE], "OK")
        self.assertNotIn(ERROR_TYPE, attrs)

    async def test_error_call_records_status_in_metric(self):
        """Aio server metric records gRPC error status code on abort."""

        class ErrorServicer(GRPCTestServerServicer):
            async def SimpleMethod(self, request, context):
                await context.abort(grpc.StatusCode.INTERNAL, "test failure")

        interceptor = aio_server_interceptor(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )

        server = grpc.aio.server(interceptors=[interceptor])
        add_GRPCTestServerServicer_to_server(ErrorServicer(), server)
        port = server.add_insecure_port("[::]:0")
        channel = grpc.aio.insecure_channel(f"localhost:{port:d}")

        await server.start()
        try:
            rpc_call = "/GRPCTestServer/SimpleMethod"
            request = Request(client_id=1, request_data="test")
            msg = request.SerializeToString()
            with self.assertRaises(grpc.aio.AioRpcError):
                await channel.unary_unary(rpc_call)(msg)
        finally:
            await channel.close()
            await server.stop(None)

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
        self.assertEqual(
            attrs[RPC_SYSTEM_NAME], RpcSystemNameValues.GRPC.value
        )
        self.assertEqual(attrs[RPC_METHOD], "GRPCTestServer/SimpleMethod")
        self.assertEqual(attrs[RPC_RESPONSE_STATUS_CODE], "INTERNAL")
        self.assertEqual(attrs[ERROR_TYPE], "INTERNAL")

    async def test_streaming_call_records_duration_metric(self):
        """Aio server interceptor records metric on a streaming RPC."""
        interceptor = aio_server_interceptor(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )

        server = grpc.aio.server(interceptors=[interceptor])
        add_GRPCTestServerServicer_to_server(Servicer(), server)
        port = server.add_insecure_port("[::]:0")
        channel = grpc.aio.insecure_channel(f"localhost:{port:d}")

        await server.start()
        try:
            rpc_call = "/GRPCTestServer/ServerStreamingMethod"
            request = Request(client_id=1, request_data="test")
            msg = request.SerializeToString()
            async for _ in channel.unary_stream(rpc_call)(msg):
                pass
        finally:
            await channel.close()
            await server.stop(None)

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
        self.assertEqual(
            attrs[RPC_METHOD], "GRPCTestServer/ServerStreamingMethod"
        )
        self.assertEqual(attrs[RPC_RESPONSE_STATUS_CODE], "OK")
