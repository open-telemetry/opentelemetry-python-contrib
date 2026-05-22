# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import grpc

from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient
from opentelemetry.semconv._incubating.attributes.error_attributes import (
    ERROR_TYPE,
)
from opentelemetry.semconv._incubating.attributes.rpc_attributes import (
    RPC_METHOD,
    RPC_RESPONSE_STATUS_CODE,
    RPC_SYSTEM_NAME,
    RpcSystemNameValues,
)
from opentelemetry.semconv._incubating.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.semconv._incubating.metrics.rpc_metrics import (
    RPC_CLIENT_CALL_DURATION,
)
from opentelemetry.test.test_base import TestBase

from ._client import server_streaming_method, simple_method
from ._server import create_test_server
from .protobuf import test_server_pb2_grpc


class TestClientInterceptorMetrics(TestBase):
    def setUp(self):
        super().setUp()
        GrpcInstrumentorClient().instrument(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )
        self.server = create_test_server(25565)
        self.server.start()
        self.channel = grpc.insecure_channel("localhost:25565")
        self._stub = test_server_pb2_grpc.GRPCTestServerStub(self.channel)

    def tearDown(self):
        super().tearDown()
        GrpcInstrumentorClient().uninstrument()
        self.server.stop(None)
        self.channel.close()

    def test_unary_call_records_duration_metric(self):
        """A unary client RPC produces an rpc.client.call.duration histogram."""
        simple_method(self._stub)

        metrics = self.get_sorted_metrics()
        duration_metric = next(
            (m for m in metrics if m.name == RPC_CLIENT_CALL_DURATION),
            None,
        )

        self.assertIsNotNone(
            duration_metric,
            f"Expected metric '{RPC_CLIENT_CALL_DURATION}' not found. "
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
            (0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10),
        )

        attrs = dict(point.attributes)
        self.assertEqual(
            attrs[RPC_SYSTEM_NAME], RpcSystemNameValues.GRPC.value
        )
        self.assertEqual(attrs[RPC_METHOD], "GRPCTestServer/SimpleMethod")
        self.assertEqual(attrs[RPC_RESPONSE_STATUS_CODE], "OK")
        self.assertEqual(attrs[SERVER_ADDRESS], "localhost")
        self.assertEqual(attrs[SERVER_PORT], 25565)
        self.assertNotIn(ERROR_TYPE, attrs)

    def test_error_call_records_status_in_metric(self):
        """Client metric records the gRPC error status code on failure."""
        with self.assertRaises(grpc.RpcError):
            simple_method(self._stub, error=True)

        metrics = self.get_sorted_metrics()
        duration_metric = next(
            (m for m in metrics if m.name == RPC_CLIENT_CALL_DURATION),
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
        self.assertEqual(attrs[RPC_RESPONSE_STATUS_CODE], "INVALID_ARGUMENT")
        self.assertEqual(attrs[ERROR_TYPE], "INVALID_ARGUMENT")

    def test_server_streaming_records_duration_metric(self):
        """Client metric is recorded for a server-streaming RPC."""
        server_streaming_method(self._stub)

        metrics = self.get_sorted_metrics()
        duration_metric = next(
            (m for m in metrics if m.name == RPC_CLIENT_CALL_DURATION),
            None,
        )

        self.assertIsNotNone(
            duration_metric,
            f"Expected metric '{RPC_CLIENT_CALL_DURATION}' not found "
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
