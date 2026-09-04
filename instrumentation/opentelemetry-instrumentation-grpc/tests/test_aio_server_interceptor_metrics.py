# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import IsolatedAsyncioTestCase, mock

import grpc
import grpc.aio

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.grpc import aio_server_interceptor
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
    RPC_SERVER_CALL_DURATION,
    RPC_SERVER_DURATION,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.test.test_base import TestBase

from .protobuf.test_server_pb2 import Request, Response
from .protobuf.test_server_pb2_grpc import (
    GRPCTestServerServicer,
    add_GRPCTestServerServicer_to_server,
)


def _find_metric(metrics, name):
    return next((m for m in metrics if m.name == name), None)


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


class _AioServerMetricsTestMixin:
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

    # pylint:disable=C0103
    def tearDown(self):
        super().tearDown()
        self.env_patch.stop()
        _OpenTelemetrySemanticConventionStability._initialized = False

    def _make_interceptor(self):
        return aio_server_interceptor(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )

    async def _run_simple(self, servicer_cls=Servicer):
        interceptor = self._make_interceptor()
        server = grpc.aio.server(interceptors=[interceptor])
        add_GRPCTestServerServicer_to_server(servicer_cls(), server)
        port = server.add_insecure_port("[::]:0")
        channel = grpc.aio.insecure_channel(f"localhost:{port:d}")
        await server.start()
        try:
            rpc_call = "/GRPCTestServer/SimpleMethod"
            msg = Request(client_id=1, request_data="test").SerializeToString()
            await channel.unary_unary(rpc_call)(msg)
        finally:
            await channel.close()
            await server.stop(None)


class TestAioServerInterceptorMetricsDefault(
    _AioServerMetricsTestMixin, TestBase, IsolatedAsyncioTestCase
):
    _SEM_CONV_MODE = "default"

    async def test_unary_call_records_duration_metric(self):
        await self._run_simple()

        metrics = self.get_sorted_metrics()
        duration_metric = _find_metric(metrics, RPC_SERVER_DURATION)
        self.assertIsNotNone(duration_metric)
        self.assertEqual(duration_metric.unit, "ms")
        self.assertIsNone(_find_metric(metrics, RPC_SERVER_CALL_DURATION))

        point = list(duration_metric.data.data_points)[0]
        attrs = dict(point.attributes)
        self.assertEqual(attrs[RPC_SYSTEM], "grpc")
        self.assertEqual(attrs[RPC_METHOD], "SimpleMethod")
        self.assertEqual(attrs[RPC_SERVICE], "GRPCTestServer")
        self.assertEqual(
            attrs[RPC_GRPC_STATUS_CODE], grpc.StatusCode.OK.value[0]
        )
        self.assertNotIn(RPC_SYSTEM_NAME, attrs)
        self.assertNotIn(RPC_RESPONSE_STATUS_CODE, attrs)
        self.assertNotIn(ERROR_TYPE, attrs)

    async def test_error_call_records_status_in_metric(self):
        class ErrorServicer(GRPCTestServerServicer):
            async def SimpleMethod(self, request, context):
                await context.abort(grpc.StatusCode.INTERNAL, "test failure")

        with self.assertRaises(grpc.aio.AioRpcError):
            await self._run_simple(ErrorServicer)

        metrics = self.get_sorted_metrics()
        duration_metric = _find_metric(metrics, RPC_SERVER_DURATION)
        self.assertIsNotNone(duration_metric)

        point = list(duration_metric.data.data_points)[0]
        attrs = dict(point.attributes)
        self.assertEqual(
            attrs[RPC_GRPC_STATUS_CODE], grpc.StatusCode.INTERNAL.value[0]
        )


class TestAioServerInterceptorMetricsNew(
    _AioServerMetricsTestMixin, TestBase, IsolatedAsyncioTestCase
):
    _SEM_CONV_MODE = "rpc"

    async def test_unary_call_records_duration_metric(self):
        await self._run_simple()

        metrics = self.get_sorted_metrics()
        duration_metric = _find_metric(metrics, RPC_SERVER_CALL_DURATION)
        self.assertIsNotNone(duration_metric)
        self.assertEqual(duration_metric.unit, "s")
        self.assertIsNone(_find_metric(metrics, RPC_SERVER_DURATION))

        point = list(duration_metric.data.data_points)[0]
        attrs = dict(point.attributes)
        self.assertEqual(
            attrs[RPC_SYSTEM_NAME], RpcSystemNameValues.GRPC.value
        )
        self.assertEqual(attrs[RPC_METHOD], "GRPCTestServer/SimpleMethod")
        self.assertEqual(attrs[RPC_RESPONSE_STATUS_CODE], "OK")
        self.assertNotIn(ERROR_TYPE, attrs)

    async def test_error_call_records_status_in_metric(self):
        class ErrorServicer(GRPCTestServerServicer):
            async def SimpleMethod(self, request, context):
                await context.abort(grpc.StatusCode.INTERNAL, "test failure")

        with self.assertRaises(grpc.aio.AioRpcError):
            await self._run_simple(ErrorServicer)

        metrics = self.get_sorted_metrics()
        duration_metric = _find_metric(metrics, RPC_SERVER_CALL_DURATION)
        self.assertIsNotNone(duration_metric)

        point = list(duration_metric.data.data_points)[0]
        attrs = dict(point.attributes)
        self.assertEqual(attrs[RPC_METHOD], "GRPCTestServer/SimpleMethod")
        self.assertEqual(attrs[RPC_RESPONSE_STATUS_CODE], "INTERNAL")
        self.assertEqual(attrs[ERROR_TYPE], "INTERNAL")


class TestAioServerInterceptorMetricsDup(
    _AioServerMetricsTestMixin, TestBase, IsolatedAsyncioTestCase
):
    _SEM_CONV_MODE = "rpc/dup"

    async def test_unary_call_emits_both_histograms(self):
        await self._run_simple()

        metrics = self.get_sorted_metrics()
        old = _find_metric(metrics, RPC_SERVER_DURATION)
        new = _find_metric(metrics, RPC_SERVER_CALL_DURATION)

        self.assertIsNotNone(old)
        self.assertIsNotNone(new)
        self.assertEqual(old.unit, "ms")
        self.assertEqual(new.unit, "s")

        old_attrs = dict(list(old.data.data_points)[0].attributes)
        new_attrs = dict(list(new.data.data_points)[0].attributes)

        self.assertEqual(old_attrs[RPC_SYSTEM], "grpc")
        self.assertEqual(old_attrs[RPC_METHOD], "SimpleMethod")
        self.assertEqual(old_attrs[RPC_SERVICE], "GRPCTestServer")
        self.assertEqual(new_attrs[RPC_METHOD], "GRPCTestServer/SimpleMethod")
        self.assertEqual(new_attrs[RPC_RESPONSE_STATUS_CODE], "OK")
