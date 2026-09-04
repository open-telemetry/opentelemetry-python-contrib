# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import contextlib
from concurrent import futures
from unittest import mock

import grpc

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.grpc import server_interceptor
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
    def SimpleMethod(self, request, context):
        return Response(
            server_id=request.client_id,
            response_data=request.request_data,
        )


class _ServerMetricsTestMixin:
    _SEM_CONV_MODE = "default"

    def setUp(self):
        super().setUp()
        self.env_patch = mock.patch.dict(
            "os.environ",
            {OTEL_SEMCONV_STABILITY_OPT_IN: self._SEM_CONV_MODE},
        )
        self.env_patch.start()
        _OpenTelemetrySemanticConventionStability._initialized = False

    def tearDown(self):
        super().tearDown()
        self.env_patch.stop()
        _OpenTelemetrySemanticConventionStability._initialized = False

    @staticmethod
    @contextlib.contextmanager
    def _server(max_workers=1, interceptors=None):
        with futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            server = grpc.server(
                executor,
                options=(("grpc.so_reuseport", 0),),
                interceptors=interceptors or [],
            )

            port = server.add_insecure_port("[::]:0")
            channel = grpc.insecure_channel(f"localhost:{port:d}")
            yield server, channel

    def _make_interceptor(self):
        return server_interceptor(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )

    def _call_simple(self, servicer_cls=Servicer):
        interceptor = self._make_interceptor()
        with self._server(interceptors=[interceptor]) as (server, channel):
            add_GRPCTestServerServicer_to_server(servicer_cls(), server)
            rpc_call = "/GRPCTestServer/SimpleMethod"
            msg = Request(client_id=1, request_data="test").SerializeToString()
            try:
                server.start()
                return channel.unary_unary(rpc_call)(msg)
            finally:
                server.stop(None)


class TestServerInterceptorMetricsDefault(_ServerMetricsTestMixin, TestBase):
    _SEM_CONV_MODE = "default"

    def test_unary_call_records_duration_metric(self):
        self._call_simple()

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

    def test_error_call_records_status_in_metric(self):
        class ErrorServicer(GRPCTestServerServicer):
            def SimpleMethod(self, request, context):
                context.abort(grpc.StatusCode.INTERNAL, "test failure")

        with self.assertRaises(grpc.RpcError):
            self._call_simple(ErrorServicer)

        metrics = self.get_sorted_metrics()
        duration_metric = _find_metric(metrics, RPC_SERVER_DURATION)
        self.assertIsNotNone(duration_metric)

        point = list(duration_metric.data.data_points)[0]
        attrs = dict(point.attributes)
        self.assertEqual(
            attrs[RPC_GRPC_STATUS_CODE],
            grpc.StatusCode.INTERNAL.value[0],
        )

    def test_uncaught_exception_records_unknown_status(self):
        class CrashingServicer(GRPCTestServerServicer):
            def SimpleMethod(self, request, context):
                raise RuntimeError("unexpected crash")

        with self.assertRaises(grpc.RpcError):
            self._call_simple(CrashingServicer)

        metrics = self.get_sorted_metrics()
        duration_metric = _find_metric(metrics, RPC_SERVER_DURATION)
        self.assertIsNotNone(duration_metric)

        point = list(duration_metric.data.data_points)[0]
        attrs = dict(point.attributes)
        self.assertEqual(
            attrs[RPC_GRPC_STATUS_CODE],
            grpc.StatusCode.UNKNOWN.value[0],
        )

    def test_streaming_call_records_duration_metric(self):
        class StreamingServicer(GRPCTestServerServicer):
            def ServerStreamingMethod(self, request, context):
                for data in ("one", "two", "three"):
                    yield Response(
                        server_id=request.client_id,
                        response_data=data,
                    )

        interceptor = self._make_interceptor()
        with self._server(interceptors=[interceptor]) as (server, channel):
            add_GRPCTestServerServicer_to_server(StreamingServicer(), server)
            rpc_call = "/GRPCTestServer/ServerStreamingMethod"
            msg = Request(client_id=1, request_data="test").SerializeToString()
            try:
                server.start()
                list(channel.unary_stream(rpc_call)(msg))
            finally:
                server.stop(None)

        metrics = self.get_sorted_metrics()
        duration_metric = _find_metric(metrics, RPC_SERVER_DURATION)
        self.assertIsNotNone(duration_metric)

        point = list(duration_metric.data.data_points)[0]
        attrs = dict(point.attributes)
        self.assertEqual(attrs[RPC_METHOD], "ServerStreamingMethod")
        self.assertEqual(attrs[RPC_SERVICE], "GRPCTestServer")
        self.assertEqual(
            attrs[RPC_GRPC_STATUS_CODE], grpc.StatusCode.OK.value[0]
        )


class TestServerInterceptorMetricsNew(_ServerMetricsTestMixin, TestBase):
    _SEM_CONV_MODE = "rpc"

    def test_unary_call_records_duration_metric(self):
        self._call_simple()

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
        self.assertNotIn(RPC_SYSTEM, attrs)
        self.assertNotIn(RPC_GRPC_STATUS_CODE, attrs)

    def test_error_call_records_status_in_metric(self):
        class ErrorServicer(GRPCTestServerServicer):
            def SimpleMethod(self, request, context):
                context.abort(grpc.StatusCode.INTERNAL, "test failure")

        with self.assertRaises(grpc.RpcError):
            self._call_simple(ErrorServicer)

        metrics = self.get_sorted_metrics()
        duration_metric = _find_metric(metrics, RPC_SERVER_CALL_DURATION)
        self.assertIsNotNone(duration_metric)

        point = list(duration_metric.data.data_points)[0]
        attrs = dict(point.attributes)
        self.assertEqual(attrs[RPC_METHOD], "GRPCTestServer/SimpleMethod")
        self.assertEqual(attrs[RPC_RESPONSE_STATUS_CODE], "INTERNAL")
        self.assertEqual(attrs[ERROR_TYPE], "INTERNAL")

    def test_uncaught_exception_records_unknown_status(self):
        class CrashingServicer(GRPCTestServerServicer):
            def SimpleMethod(self, request, context):
                raise RuntimeError("unexpected crash")

        with self.assertRaises(grpc.RpcError):
            self._call_simple(CrashingServicer)

        metrics = self.get_sorted_metrics()
        duration_metric = _find_metric(metrics, RPC_SERVER_CALL_DURATION)
        self.assertIsNotNone(duration_metric)

        point = list(duration_metric.data.data_points)[0]
        attrs = dict(point.attributes)
        self.assertEqual(attrs[RPC_RESPONSE_STATUS_CODE], "UNKNOWN")
        self.assertEqual(attrs[ERROR_TYPE], "UNKNOWN")


class TestServerInterceptorMetricsDup(_ServerMetricsTestMixin, TestBase):
    _SEM_CONV_MODE = "rpc/dup"

    def test_unary_call_emits_both_histograms(self):
        self._call_simple()

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
        self.assertEqual(
            new_attrs[RPC_SYSTEM_NAME], RpcSystemNameValues.GRPC.value
        )
        self.assertEqual(new_attrs[RPC_METHOD], "GRPCTestServer/SimpleMethod")
        self.assertEqual(new_attrs[RPC_RESPONSE_STATUS_CODE], "OK")
