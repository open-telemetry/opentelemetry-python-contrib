# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import IsolatedAsyncioTestCase, mock

import grpc

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.grpc import GrpcAioInstrumentorClient
from opentelemetry.semconv._incubating.attributes.rpc_attributes import (
    RPC_GRPC_STATUS_CODE,
    RPC_METHOD,
    RPC_RESPONSE_STATUS_CODE,
    RPC_SERVICE,
    RPC_SYSTEM,
    RPC_SYSTEM_NAME,
    RpcSystemNameValues,
)
from opentelemetry.semconv._incubating.metrics.rpc_metrics import (
    RPC_CLIENT_CALL_DURATION,
    RPC_CLIENT_DURATION,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.test.test_base import TestBase

from ._aio_client import server_streaming_method, simple_method
from ._server import create_test_server
from .protobuf import test_server_pb2_grpc


def _find_metric(metrics, name):
    return next((m for m in metrics if m.name == name), None)


class _AioClientMetricsTestMixin:
    _SEM_CONV_MODE = "default"

    # pylint:disable=C0103
    def setUp(self):
        super().setUp()
        self.env_patch = mock.patch.dict(
            "os.environ",
            {OTEL_SEMCONV_STABILITY_OPT_IN: self._SEM_CONV_MODE},
        )
        self.env_patch.start()
        _OpenTelemetrySemanticConventionStability._initialized = False
        GrpcAioInstrumentorClient().instrument(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )
        self.server = create_test_server(25565)
        self.server.start()

    # pylint:disable=C0103
    def tearDown(self):
        super().tearDown()
        GrpcAioInstrumentorClient().uninstrument()
        self.server.stop(None)
        self.env_patch.stop()
        _OpenTelemetrySemanticConventionStability._initialized = False


class TestAioClientInterceptorMetricsDefault(
    _AioClientMetricsTestMixin, TestBase, IsolatedAsyncioTestCase
):
    _SEM_CONV_MODE = "default"

    async def test_unary_call_records_duration_metric(self):
        channel = grpc.aio.insecure_channel("localhost:25565")
        stub = test_server_pb2_grpc.GRPCTestServerStub(channel)
        try:
            await simple_method(stub)
        finally:
            await channel.close()

        metrics = self.get_sorted_metrics()
        duration_metric = _find_metric(metrics, RPC_CLIENT_DURATION)
        self.assertIsNotNone(duration_metric)
        self.assertEqual(duration_metric.unit, "ms")
        self.assertIsNone(_find_metric(metrics, RPC_CLIENT_CALL_DURATION))

        point = list(duration_metric.data.data_points)[0]
        attrs = dict(point.attributes)
        self.assertEqual(attrs[RPC_SYSTEM], "grpc")
        self.assertEqual(attrs[RPC_METHOD], "SimpleMethod")
        self.assertEqual(attrs[RPC_SERVICE], "GRPCTestServer")
        self.assertEqual(
            attrs[RPC_GRPC_STATUS_CODE], grpc.StatusCode.OK.value[0]
        )
        self.assertEqual(attrs[SERVER_ADDRESS], "localhost")
        self.assertEqual(attrs[SERVER_PORT], 25565)
        self.assertNotIn(RPC_SYSTEM_NAME, attrs)
        self.assertNotIn(RPC_RESPONSE_STATUS_CODE, attrs)
        self.assertNotIn(ERROR_TYPE, attrs)

    async def test_error_call_records_status_in_metric(self):
        channel = grpc.aio.insecure_channel("localhost:25565")
        stub = test_server_pb2_grpc.GRPCTestServerStub(channel)
        try:
            with self.assertRaises(grpc.aio.AioRpcError):
                await simple_method(stub, error=True)
        finally:
            await channel.close()

        metrics = self.get_sorted_metrics()
        duration_metric = _find_metric(metrics, RPC_CLIENT_DURATION)
        self.assertIsNotNone(duration_metric)

        point = list(duration_metric.data.data_points)[0]
        attrs = dict(point.attributes)
        self.assertEqual(attrs[RPC_METHOD], "SimpleMethod")
        self.assertEqual(
            attrs[RPC_GRPC_STATUS_CODE],
            grpc.StatusCode.INVALID_ARGUMENT.value[0],
        )

    async def test_server_streaming_records_duration_metric(self):
        channel = grpc.aio.insecure_channel("localhost:25565")
        stub = test_server_pb2_grpc.GRPCTestServerStub(channel)
        try:
            async for _ in server_streaming_method(stub):
                pass
        finally:
            await channel.close()

        metrics = self.get_sorted_metrics()
        duration_metric = _find_metric(metrics, RPC_CLIENT_DURATION)
        self.assertIsNotNone(duration_metric)

        point = list(duration_metric.data.data_points)[0]
        attrs = dict(point.attributes)
        self.assertEqual(attrs[RPC_METHOD], "ServerStreamingMethod")
        self.assertEqual(attrs[RPC_SERVICE], "GRPCTestServer")


class TestAioClientInterceptorMetricsNew(
    _AioClientMetricsTestMixin, TestBase, IsolatedAsyncioTestCase
):
    _SEM_CONV_MODE = "rpc"

    async def test_unary_call_records_duration_metric(self):
        channel = grpc.aio.insecure_channel("localhost:25565")
        stub = test_server_pb2_grpc.GRPCTestServerStub(channel)
        try:
            await simple_method(stub)
        finally:
            await channel.close()

        metrics = self.get_sorted_metrics()
        duration_metric = _find_metric(metrics, RPC_CLIENT_CALL_DURATION)
        self.assertIsNotNone(duration_metric)
        self.assertEqual(duration_metric.unit, "s")
        self.assertIsNone(_find_metric(metrics, RPC_CLIENT_DURATION))

        point = list(duration_metric.data.data_points)[0]
        attrs = dict(point.attributes)
        self.assertEqual(
            attrs[RPC_SYSTEM_NAME], RpcSystemNameValues.GRPC.value
        )
        self.assertEqual(attrs[RPC_METHOD], "GRPCTestServer/SimpleMethod")
        self.assertEqual(attrs[RPC_RESPONSE_STATUS_CODE], "OK")
        self.assertEqual(attrs[SERVER_ADDRESS], "localhost")
        self.assertEqual(attrs[SERVER_PORT], 25565)
        self.assertNotIn(ERROR_TYPE, attrs)

    async def test_error_call_records_status_in_metric(self):
        channel = grpc.aio.insecure_channel("localhost:25565")
        stub = test_server_pb2_grpc.GRPCTestServerStub(channel)
        try:
            with self.assertRaises(grpc.aio.AioRpcError):
                await simple_method(stub, error=True)
        finally:
            await channel.close()

        metrics = self.get_sorted_metrics()
        duration_metric = _find_metric(metrics, RPC_CLIENT_CALL_DURATION)
        self.assertIsNotNone(duration_metric)

        point = list(duration_metric.data.data_points)[0]
        attrs = dict(point.attributes)
        self.assertEqual(attrs[RPC_METHOD], "GRPCTestServer/SimpleMethod")
        self.assertEqual(attrs[RPC_RESPONSE_STATUS_CODE], "INVALID_ARGUMENT")
        self.assertEqual(attrs[ERROR_TYPE], "INVALID_ARGUMENT")


class TestAioClientInterceptorMetricsDup(
    _AioClientMetricsTestMixin, TestBase, IsolatedAsyncioTestCase
):
    _SEM_CONV_MODE = "rpc/dup"

    async def test_unary_call_emits_both_histograms(self):
        channel = grpc.aio.insecure_channel("localhost:25565")
        stub = test_server_pb2_grpc.GRPCTestServerStub(channel)
        try:
            await simple_method(stub)
        finally:
            await channel.close()

        metrics = self.get_sorted_metrics()
        old = _find_metric(metrics, RPC_CLIENT_DURATION)
        new = _find_metric(metrics, RPC_CLIENT_CALL_DURATION)

        self.assertIsNotNone(old)
        self.assertIsNotNone(new)
        self.assertEqual(old.unit, "ms")
        self.assertEqual(new.unit, "s")

        old_attrs = dict(list(old.data.data_points)[0].attributes)
        new_attrs = dict(list(new.data.data_points)[0].attributes)

        self.assertEqual(old_attrs[RPC_METHOD], "SimpleMethod")
        self.assertEqual(old_attrs[RPC_SERVICE], "GRPCTestServer")
        self.assertEqual(new_attrs[RPC_METHOD], "GRPCTestServer/SimpleMethod")
        self.assertEqual(new_attrs[RPC_RESPONSE_STATUS_CODE], "OK")
