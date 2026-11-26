# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pylint:disable=unused-argument

from concurrent import futures
from unittest import IsolatedAsyncioTestCase

import grpc

from opentelemetry.instrumentation.grpc import (
    GrpcAioInstrumentorClient,
    GrpcAioInstrumentorServer,
    GrpcInstrumentorClient,
    GrpcInstrumentorServer,
)
from opentelemetry.sdk.metrics.export import HistogramDataPoint
from opentelemetry.semconv._incubating.attributes.rpc_attributes import (
    RPC_METHOD,
    RPC_RESPONSE_STATUS_CODE,
    RPC_SYSTEM_NAME,
)
from opentelemetry.semconv._incubating.metrics.rpc_metrics import (
    RPC_CLIENT_CALL_DURATION,
    RPC_SERVER_CALL_DURATION,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.test.test_base import TestBase

from . import _aio_client, _client
from ._server import TestServer
from .protobuf import test_server_pb2, test_server_pb2_grpc

SIMPLE_METHOD = "GRPCTestServer/SimpleMethod"
SERVER_STREAMING_METHOD = "GRPCTestServer/ServerStreamingMethod"
CLIENT_STREAMING_METHOD = "GRPCTestServer/ClientStreamingMethod"
BIDI_STREAMING_METHOD = "GRPCTestServer/BidirectionalStreamingMethod"


class _FailingServer(TestServer):
    # pylint: disable=invalid-name
    def SimpleMethod(self, request, context):
        if request.request_data == "raise":
            raise ValueError("boom")
        return super().SimpleMethod(request, context)


class _AioServer(test_server_pb2_grpc.GRPCTestServerServicer):
    # pylint: disable=invalid-name
    async def SimpleMethod(self, request, context):
        if request.request_data == "error":
            await context.abort(grpc.StatusCode.INTERNAL, "aio error")
        return test_server_pb2.Response(server_id=1, response_data="data")

    async def ServerStreamingMethod(self, request, context):
        for _ in range(3):
            yield test_server_pb2.Response(server_id=1, response_data="data")


class _MetricsAssertions(TestBase):
    def _duration_points(self, metric_name):
        points = []
        metrics_data = self.memory_metrics_reader.get_metrics_data()
        if metrics_data is None:
            return points
        for resource_metrics in metrics_data.resource_metrics:
            for scope_metrics in resource_metrics.scope_metrics:
                for metric in scope_metrics.metrics:
                    if metric.name == metric_name:
                        self.assertEqual(metric.unit, "s")
                        points.extend(metric.data.data_points)
        return points

    def _assert_duration(self, metric_name, method, status_code, error_type="None", count=1):
        points = [
            point
            for point in self._duration_points(metric_name)
            if point.attributes.get(RPC_METHOD) == method
            and point.attributes.get(RPC_RESPONSE_STATUS_CODE) == status_code
        ]
        self.assertEqual(len(points), 1, f"{metric_name} {method} {status_code}: {points}")
        point = points[0]
        self.assertIsInstance(point, HistogramDataPoint)
        self.assertEqual(point.count, count)
        self.assertGreaterEqual(point.sum, 0)
        expected = {
            RPC_SYSTEM_NAME: "grpc",
            RPC_METHOD: method,
            RPC_RESPONSE_STATUS_CODE: status_code,
            # calls without errors have the "None" error type
            ERROR_TYPE: error_type,
        }
        self.assertEqual(dict(point.attributes), expected)
        for value in point.attributes.values():
            self.assertIsInstance(value, str)


class TestServerCallDuration(_MetricsAssertions):
    def setUp(self):
        super().setUp()
        GrpcInstrumentorServer().instrument(meter_provider=self.meter_provider)
        # pylint: disable=consider-using-with
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
        test_server_pb2_grpc.add_GRPCTestServerServicer_to_server(_FailingServer(), self.server)
        port = self.server.add_insecure_port("localhost:0")
        self.server.start()
        self.channel = grpc.insecure_channel(f"localhost:{port}")
        self.stub = test_server_pb2_grpc.GRPCTestServerStub(self.channel)

    def tearDown(self):
        self.channel.close()
        self.server.stop(None)
        GrpcInstrumentorServer().uninstrument()
        super().tearDown()

    def test_unary_ok(self):
        _client.simple_method(self.stub)
        _client.simple_method(self.stub)
        self._assert_duration(RPC_SERVER_CALL_DURATION, SIMPLE_METHOD, "OK", count=2)

    def test_unary_non_error_status(self):
        # INVALID_ARGUMENT is not a server error, so error.type must not be set
        with self.assertRaises(grpc.RpcError):
            _client.simple_method(self.stub, error=True)
        self._assert_duration(RPC_SERVER_CALL_DURATION, SIMPLE_METHOD, "INVALID_ARGUMENT")

    def test_unary_uncaught_exception(self):
        with self.assertRaises(grpc.RpcError):
            self.stub.SimpleMethod(test_server_pb2.Request(client_id=1, request_data="raise"))
        self._assert_duration(RPC_SERVER_CALL_DURATION, SIMPLE_METHOD, "UNKNOWN", error_type="UNKNOWN")

    def test_server_streaming(self):
        _client.server_streaming_method(self.stub)
        self._assert_duration(RPC_SERVER_CALL_DURATION, SERVER_STREAMING_METHOD, "OK")

    def test_server_streaming_abort(self):
        with self.assertRaises(grpc.RpcError):
            _client.server_streaming_method(self.stub, error=True)
        self._assert_duration(RPC_SERVER_CALL_DURATION, SERVER_STREAMING_METHOD, "INVALID_ARGUMENT")

    def test_client_streaming(self):
        _client.client_streaming_method(self.stub)
        self._assert_duration(RPC_SERVER_CALL_DURATION, CLIENT_STREAMING_METHOD, "OK")

    def test_uninstrumented(self):
        GrpcInstrumentorServer().uninstrument()
        # pylint: disable=consider-using-with
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
        test_server_pb2_grpc.add_GRPCTestServerServicer_to_server(TestServer(), server)
        port = server.add_insecure_port("localhost:0")
        server.start()
        try:
            with grpc.insecure_channel(f"localhost:{port}") as channel:
                _client.simple_method(test_server_pb2_grpc.GRPCTestServerStub(channel))
        finally:
            server.stop(None)
        self.assertEqual(self._duration_points(RPC_SERVER_CALL_DURATION), [])


class TestClientCallDuration(_MetricsAssertions):
    def setUp(self):
        super().setUp()
        # pylint: disable=consider-using-with
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
        test_server_pb2_grpc.add_GRPCTestServerServicer_to_server(TestServer(), self.server)
        port = self.server.add_insecure_port("localhost:0")
        self.server.start()
        GrpcInstrumentorClient().instrument(meter_provider=self.meter_provider)
        self.channel = grpc.insecure_channel(f"localhost:{port}")
        self.stub = test_server_pb2_grpc.GRPCTestServerStub(self.channel)

    def tearDown(self):
        self.channel.close()
        self.server.stop(None)
        GrpcInstrumentorClient().uninstrument()
        super().tearDown()

    def test_unary_ok(self):
        _client.simple_method(self.stub)
        self._assert_duration(RPC_CLIENT_CALL_DURATION, SIMPLE_METHOD, "OK")

    def test_unary_error(self):
        # every non-OK status is an error on the client side
        with self.assertRaises(grpc.RpcError):
            _client.simple_method(self.stub, error=True)
        self._assert_duration(
            RPC_CLIENT_CALL_DURATION,
            SIMPLE_METHOD,
            "INVALID_ARGUMENT",
            error_type="INVALID_ARGUMENT",
        )

    def test_unary_future(self):
        _client.simple_method_future(self.stub).result()
        self._assert_duration(RPC_CLIENT_CALL_DURATION, SIMPLE_METHOD, "OK")

    def test_unary_future_error(self):
        future = _client.simple_method_future(self.stub, error=True)
        with self.assertRaises(grpc.RpcError):
            future.result()
        self._assert_duration(
            RPC_CLIENT_CALL_DURATION,
            SIMPLE_METHOD,
            "INVALID_ARGUMENT",
            error_type="INVALID_ARGUMENT",
        )

    def test_server_streaming(self):
        _client.server_streaming_method(self.stub)
        self._assert_duration(RPC_CLIENT_CALL_DURATION, SERVER_STREAMING_METHOD, "OK")

    def test_server_streaming_error(self):
        with self.assertRaises(grpc.RpcError):
            _client.server_streaming_method(self.stub, error=True)
        self._assert_duration(
            RPC_CLIENT_CALL_DURATION,
            SERVER_STREAMING_METHOD,
            "INVALID_ARGUMENT",
            error_type="INVALID_ARGUMENT",
        )

    def test_client_streaming(self):
        _client.client_streaming_method(self.stub)
        self._assert_duration(RPC_CLIENT_CALL_DURATION, CLIENT_STREAMING_METHOD, "OK")

    def test_bidirectional_streaming(self):
        _client.bidirectional_streaming_method(self.stub)
        self._assert_duration(RPC_CLIENT_CALL_DURATION, BIDI_STREAMING_METHOD, "OK")


class TestAioCallDuration(_MetricsAssertions, IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        GrpcAioInstrumentorServer().instrument(meter_provider=self.meter_provider)
        GrpcAioInstrumentorClient().instrument(meter_provider=self.meter_provider)
        self.server = grpc.aio.server()
        test_server_pb2_grpc.add_GRPCTestServerServicer_to_server(_AioServer(), self.server)
        port = self.server.add_insecure_port("localhost:0")
        await self.server.start()
        self.channel = grpc.aio.insecure_channel(f"localhost:{port}")
        self.stub = test_server_pb2_grpc.GRPCTestServerStub(self.channel)

    async def asyncTearDown(self):
        await self.channel.close()
        await self.server.stop(None)
        GrpcAioInstrumentorClient().uninstrument()
        GrpcAioInstrumentorServer().uninstrument()

    async def test_unary_ok(self):
        await _aio_client.simple_method(self.stub)
        self._assert_duration(RPC_SERVER_CALL_DURATION, SIMPLE_METHOD, "OK")
        self._assert_duration(RPC_CLIENT_CALL_DURATION, SIMPLE_METHOD, "OK")

    async def test_unary_abort(self):
        with self.assertRaises(grpc.aio.AioRpcError):
            await _aio_client.simple_method(self.stub, error=True)
        self._assert_duration(RPC_SERVER_CALL_DURATION, SIMPLE_METHOD, "INTERNAL", error_type="INTERNAL")
        self._assert_duration(RPC_CLIENT_CALL_DURATION, SIMPLE_METHOD, "INTERNAL", error_type="INTERNAL")

    async def test_server_streaming(self):
        responses = [response async for response in _aio_client.server_streaming_method(self.stub)]
        self.assertEqual(len(responses), 3)
        self._assert_duration(RPC_SERVER_CALL_DURATION, SERVER_STREAMING_METHOD, "OK")
        self._assert_duration(RPC_CLIENT_CALL_DURATION, SERVER_STREAMING_METHOD, "OK")
