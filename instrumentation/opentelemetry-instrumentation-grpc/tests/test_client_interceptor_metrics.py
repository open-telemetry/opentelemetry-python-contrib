# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import mock

import grpc

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient
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

from ._client import (
    server_streaming_method,
    simple_method,
    simple_method_future,
)
from ._server import create_test_server
from .protobuf import test_server_pb2_grpc

_OLD_BUCKET_BOUNDARIES_MS = (
    5,
    10,
    25,
    50,
    75,
    100,
    250,
    500,
    750,
    1000,
    2500,
    5000,
    7500,
    10000,
)
_NEW_BUCKET_BOUNDARIES_S = (
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
)


def _find_metric(metrics, name):
    return next((m for m in metrics if m.name == name), None)


class _ClientMetricsTestMixin:
    """Common client harness. Subclasses select the semconv mode via ``_SEM_CONV_MODE``."""

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
        GrpcInstrumentorClient().instrument(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )
        self.server = create_test_server(25565)
        self.server.start()
        self.channel = grpc.insecure_channel("localhost:25565")
        self._stub = test_server_pb2_grpc.GRPCTestServerStub(self.channel)

    # pylint:disable=C0103
    def tearDown(self):
        super().tearDown()
        GrpcInstrumentorClient().uninstrument()
        self.server.stop(None)
        self.channel.close()
        self.env_patch.stop()
        _OpenTelemetrySemanticConventionStability._initialized = False


class TestClientInterceptorMetricsDefault(_ClientMetricsTestMixin, TestBase):
    """Default (v1.37) semantic conventions for client metrics."""

    _SEM_CONV_MODE = "default"

    def test_unary_call_records_duration_metric(self):
        simple_method(self._stub)

        metrics = self.get_sorted_metrics()
        duration_metric = _find_metric(metrics, RPC_CLIENT_DURATION)

        self.assertIsNotNone(duration_metric)
        self.assertEqual(duration_metric.unit, "ms")
        self.assertIsNone(_find_metric(metrics, RPC_CLIENT_CALL_DURATION))

        data_points = list(duration_metric.data.data_points)
        self.assertEqual(len(data_points), 1)

        point = data_points[0]
        self.assertEqual(point.count, 1)
        self.assertGreater(point.sum, 0)
        self.assertEqual(point.explicit_bounds, _OLD_BUCKET_BOUNDARIES_MS)

        attrs = dict(point.attributes)
        self.assertEqual(attrs[RPC_SYSTEM], "grpc")
        self.assertEqual(attrs[RPC_METHOD], "SimpleMethod")
        self.assertEqual(attrs[RPC_SERVICE], "GRPCTestServer")
        self.assertEqual(attrs[RPC_GRPC_STATUS_CODE], grpc.StatusCode.OK.value[0])
        self.assertEqual(attrs[SERVER_ADDRESS], "localhost")
        self.assertEqual(attrs[SERVER_PORT], 25565)
        self.assertNotIn(RPC_SYSTEM_NAME, attrs)
        self.assertNotIn(RPC_RESPONSE_STATUS_CODE, attrs)
        self.assertNotIn(ERROR_TYPE, attrs)

    def test_error_call_records_status_in_metric(self):
        with self.assertRaises(grpc.RpcError):
            simple_method(self._stub, error=True)

        metrics = self.get_sorted_metrics()
        duration_metric = _find_metric(metrics, RPC_CLIENT_DURATION)
        self.assertIsNotNone(duration_metric)

        point = list(duration_metric.data.data_points)[0]
        attrs = dict(point.attributes)
        self.assertEqual(attrs[RPC_METHOD], "SimpleMethod")
        self.assertEqual(attrs[RPC_SERVICE], "GRPCTestServer")
        self.assertEqual(
            attrs[RPC_GRPC_STATUS_CODE],
            grpc.StatusCode.INVALID_ARGUMENT.value[0],
        )

    def test_server_streaming_records_duration_metric(self):
        server_streaming_method(self._stub)

        metrics = self.get_sorted_metrics()
        duration_metric = _find_metric(metrics, RPC_CLIENT_DURATION)
        self.assertIsNotNone(duration_metric)

        point = list(duration_metric.data.data_points)[0]
        attrs = dict(point.attributes)
        self.assertEqual(attrs[RPC_METHOD], "ServerStreamingMethod")
        self.assertEqual(attrs[RPC_SERVICE], "GRPCTestServer")
        self.assertEqual(attrs[RPC_GRPC_STATUS_CODE], grpc.StatusCode.OK.value[0])

    def test_future_call_records_correct_status(self):
        future = simple_method_future(self._stub, error=True)
        with self.assertRaises(grpc.RpcError):
            future.result()

        metrics = self.get_sorted_metrics()
        duration_metric = _find_metric(metrics, RPC_CLIENT_DURATION)
        self.assertIsNotNone(duration_metric)

        point = list(duration_metric.data.data_points)[0]
        attrs = dict(point.attributes)
        self.assertEqual(
            attrs[RPC_GRPC_STATUS_CODE],
            grpc.StatusCode.INVALID_ARGUMENT.value[0],
        )


class TestClientInterceptorMetricsNew(_ClientMetricsTestMixin, TestBase):
    """New (v1.40) semantic conventions selected by ``rpc`` opt-in."""

    _SEM_CONV_MODE = "rpc"

    def test_unary_call_records_duration_metric(self):
        simple_method(self._stub)

        metrics = self.get_sorted_metrics()
        duration_metric = _find_metric(metrics, RPC_CLIENT_CALL_DURATION)

        self.assertIsNotNone(duration_metric)
        self.assertEqual(duration_metric.unit, "s")
        self.assertIsNone(_find_metric(metrics, RPC_CLIENT_DURATION))

        point = list(duration_metric.data.data_points)[0]
        self.assertEqual(point.count, 1)
        self.assertGreater(point.sum, 0)
        self.assertEqual(point.explicit_bounds, _NEW_BUCKET_BOUNDARIES_S)

        attrs = dict(point.attributes)
        self.assertEqual(attrs[RPC_SYSTEM_NAME], RpcSystemNameValues.GRPC.value)
        self.assertEqual(attrs[RPC_METHOD], "GRPCTestServer/SimpleMethod")
        self.assertEqual(attrs[RPC_RESPONSE_STATUS_CODE], "OK")
        self.assertEqual(attrs[SERVER_ADDRESS], "localhost")
        self.assertEqual(attrs[SERVER_PORT], 25565)
        self.assertNotIn(RPC_SYSTEM, attrs)
        self.assertNotIn(RPC_SERVICE, attrs)
        self.assertNotIn(RPC_GRPC_STATUS_CODE, attrs)
        self.assertNotIn(ERROR_TYPE, attrs)

    def test_error_call_records_status_in_metric(self):
        with self.assertRaises(grpc.RpcError):
            simple_method(self._stub, error=True)

        metrics = self.get_sorted_metrics()
        duration_metric = _find_metric(metrics, RPC_CLIENT_CALL_DURATION)
        self.assertIsNotNone(duration_metric)

        point = list(duration_metric.data.data_points)[0]
        attrs = dict(point.attributes)
        self.assertEqual(attrs[RPC_METHOD], "GRPCTestServer/SimpleMethod")
        self.assertEqual(attrs[RPC_RESPONSE_STATUS_CODE], "INVALID_ARGUMENT")
        self.assertEqual(attrs[ERROR_TYPE], "INVALID_ARGUMENT")

    def test_server_streaming_records_duration_metric(self):
        server_streaming_method(self._stub)

        metrics = self.get_sorted_metrics()
        duration_metric = _find_metric(metrics, RPC_CLIENT_CALL_DURATION)
        self.assertIsNotNone(duration_metric)

        point = list(duration_metric.data.data_points)[0]
        attrs = dict(point.attributes)
        self.assertEqual(attrs[RPC_METHOD], "GRPCTestServer/ServerStreamingMethod")
        self.assertEqual(attrs[RPC_RESPONSE_STATUS_CODE], "OK")


class TestClientInterceptorMetricsDup(_ClientMetricsTestMixin, TestBase):
    """Dual emission when ``rpc/dup`` is opted in."""

    _SEM_CONV_MODE = "rpc/dup"

    def test_unary_call_emits_both_histograms(self):
        simple_method(self._stub)

        metrics = self.get_sorted_metrics()
        old = _find_metric(metrics, RPC_CLIENT_DURATION)
        new = _find_metric(metrics, RPC_CLIENT_CALL_DURATION)

        self.assertIsNotNone(old)
        self.assertIsNotNone(new)
        self.assertEqual(old.unit, "ms")
        self.assertEqual(new.unit, "s")

        old_attrs = dict(list(old.data.data_points)[0].attributes)
        new_attrs = dict(list(new.data.data_points)[0].attributes)

        self.assertEqual(old_attrs[RPC_SYSTEM], "grpc")
        self.assertEqual(old_attrs[RPC_METHOD], "SimpleMethod")
        self.assertEqual(old_attrs[RPC_SERVICE], "GRPCTestServer")

        self.assertEqual(new_attrs[RPC_SYSTEM_NAME], RpcSystemNameValues.GRPC.value)
        self.assertEqual(new_attrs[RPC_METHOD], "GRPCTestServer/SimpleMethod")
        self.assertEqual(new_attrs[RPC_RESPONSE_STATUS_CODE], "OK")

    def test_error_call_emits_both_histograms(self):
        with self.assertRaises(grpc.RpcError):
            simple_method(self._stub, error=True)

        metrics = self.get_sorted_metrics()
        old = _find_metric(metrics, RPC_CLIENT_DURATION)
        new = _find_metric(metrics, RPC_CLIENT_CALL_DURATION)

        self.assertIsNotNone(old)
        self.assertIsNotNone(new)

        old_attrs = dict(list(old.data.data_points)[0].attributes)
        new_attrs = dict(list(new.data.data_points)[0].attributes)

        self.assertEqual(
            old_attrs[RPC_GRPC_STATUS_CODE],
            grpc.StatusCode.INVALID_ARGUMENT.value[0],
        )
        self.assertEqual(new_attrs[RPC_RESPONSE_STATUS_CODE], "INVALID_ARGUMENT")
        self.assertEqual(new_attrs[ERROR_TYPE], "INVALID_ARGUMENT")
