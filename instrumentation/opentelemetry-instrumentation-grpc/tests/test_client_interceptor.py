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

import time
from typing import Iterator

import grpc
from tests.protobuf import (  # pylint: disable=no-name-in-module
    test_server_pb2_grpc,
)

import opentelemetry.instrumentation.grpc
from opentelemetry import context, metrics, trace
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient
from opentelemetry.instrumentation.grpc._client import (
    OpenTelemetryClientInterceptor,
)
from opentelemetry.instrumentation.grpc._utilities import _ClientCallDetails
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
from opentelemetry.propagate import get_global_textmap, set_global_textmap
from opentelemetry.sdk.metrics.export import Histogram, HistogramDataPoint
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.mock_textmap import MockTextMapPropagator
from opentelemetry.test.test_base import TestBase

from ._server import create_test_server
from .protobuf.test_server_pb2 import Request, Response


CLIENT_ID = 1

_expected_metric_names = {
    "rpc.client.duration": (Histogram, "ms", "Measures duration of RPC"),
    "rpc.client.request.size": (
        Histogram,
        "By",
        "Measures size of RPC request messages (uncompressed)",
    ),
    "rpc.client.response.size": (
        Histogram,
        "By",
        "Measures size of RPC response messages (uncompressed)",
    ),
    "rpc.client.requests_per_rpc": (
        Histogram,
        "1",
        "Measures the number of messages received per RPC. "
        "Should be 1 for all non-streaming RPCs",
    ),
    "rpc.client.responses_per_rpc": (
        Histogram,
        "1",
        "Measures the number of messages sent per RPC. "
        "Should be 1 for all non-streaming RPCs",
    ),
}


# User defined interceptor. Is used in the tests along with the opentelemetry
# client interceptor.
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


class TestOpenTelemetryClientInterceptor(TestBase):
    def assertEvent(self, event, name, attributes, msg=None):
        self.assertEqual(event.name, name, msg=msg)
        for key, val in attributes.items():
            out_msg = (
                str(event.attributes)
                if msg is None
                else ", ".join([msg, str(event.attributes)])
            )
            self.assertIn(key, event.attributes, msg=out_msg)
            self.assertEqual(val, event.attributes[key], msg=out_msg)

    def assertEqualMetricInstrumentationScope(self, scope_metrics, module):
        self.assertEqual(scope_metrics.scope.name, module.__name__)
        self.assertEqual(scope_metrics.scope.version, module.__version__)

    def assertMetricDataPointHasAttributes(self, data_point, attributes):
        for key, val in attributes.items():
            self.assertIn(key, data_point.attributes)
            self.assertEqual(val, data_point.attributes[key])

    def setUp(self):
        super().setUp()
        GrpcInstrumentorClient().instrument()
        self.server = create_test_server(25565)
        self.server.start()
        # use a user defined interceptor along with the opentelemetry client
        # interceptor
        interceptors = [Interceptor()]
        self.channel = grpc.insecure_channel("localhost:25565")
        self.channel = grpc.intercept_channel(self.channel, *interceptors)
        self._stub = test_server_pb2_grpc.GRPCTestServerStub(self.channel)

    def tearDown(self):
        super().tearDown()
        GrpcInstrumentorClient().uninstrument()
        self.server.stop(None)
        self.channel.close()

    #
    # Unary-Unary-RPC
    #

    def test_unary_unary(self):
        data = "data"
        request = Request(client_id=CLIENT_ID, request_data=data)
        response = self._stub.SimpleMethod(request)

        # check response
        self.assertIsInstance(response, Response)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.name, "/GRPCTestServer/SimpleMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "SimpleMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.OK.value[
                    0
                ],
            },
        )

        # check events
        self.assertEqual(len(span.events), 2)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "SENT",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: request.ByteSize(),
            },
        )
        self.assertEvent(
            span.events[1],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: response.ByteSize(),
            },
        )

    def test_unary_unary_abort(self):
        data = "abort"
        request = Request(client_id=CLIENT_ID, request_data=data)

        with self.assertRaises(grpc.RpcError):
            self._stub.SimpleMethod(request)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.name, "/GRPCTestServer/SimpleMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "SimpleMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.FAILED_PRECONDITION.value[
                    0
                ],
            },
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.FAILED_PRECONDITION}: {data}",
        )

        # check events
        self.assertEqual(len(span.events), 2)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "SENT",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: request.ByteSize(),
            },
        )
        self.assertEvent(
            span.events[1],
            "exception",
            {
                "exception.type": "_InactiveRpcError",
                # "exception.message": error_message,
                # "exception.stacktrace": "...",
                "exception.escaped": str(False),
            },
        )

    def test_unary_unary_cancel_on_server_side(self):
        data = "cancel"
        request = Request(client_id=CLIENT_ID, request_data=data)

        with self.assertRaises(grpc.RpcError):
            self._stub.SimpleMethod(request)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.name, "/GRPCTestServer/SimpleMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "SimpleMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.CANCELLED.value[
                    0
                ],
            },
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.CANCELLED}: "
            f"{grpc.StatusCode.CANCELLED.value[1].upper()}",
        )

        # check events
        self.assertEqual(len(span.events), 2)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "SENT",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: request.ByteSize(),
            },
        )
        self.assertEvent(
            span.events[1],
            "exception",
            {
                "exception.type": "_InactiveRpcError",
                # "exception.message": error_message,
                # "exception.stacktrace": "...",
                "exception.escaped": str(False),
            },
        )

    def test_unary_unary_error(self):
        data = "error"
        request = Request(client_id=CLIENT_ID, request_data=data)

        with self.assertRaises(grpc.RpcError):
            self._stub.SimpleMethod(request)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.name, "/GRPCTestServer/SimpleMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "SimpleMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.INVALID_ARGUMENT.value[
                    0
                ],
            },
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.INVALID_ARGUMENT}: {data}",
        )

        # check events
        self.assertEqual(len(span.events), 2)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "SENT",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: request.ByteSize(),
            },
        )
        self.assertEvent(
            span.events[1],
            "exception",
            {
                "exception.type": "_InactiveRpcError",
                # "exception.message": error_message,
                # "exception.stacktrace": "...",
                "exception.escaped": str(False),
            },
        )

    def test_unary_unary_exception(self):
        data = "exception"
        request = Request(client_id=CLIENT_ID, request_data=data)

        with self.assertRaises(grpc.RpcError):
            self._stub.SimpleMethod(request)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.name, "/GRPCTestServer/SimpleMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "SimpleMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.UNKNOWN.value[
                    0
                ],
            },
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.UNKNOWN}: "
            f"Exception calling application: {data}",
        )

        # check events
        self.assertEqual(len(span.events), 2)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "SENT",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: request.ByteSize(),
            },
        )
        self.assertEvent(
            span.events[1],
            "exception",
            {
                "exception.type": "_InactiveRpcError",
                # "exception.message": error_message,
                # "exception.stacktrace": "...",
                "exception.escaped": str(False),
            },
        )

    def test_unary_unary_future(self):
        data = "data"
        request = Request(client_id=CLIENT_ID, request_data=data)

        response_future = self._stub.SimpleMethod.future(request)
        response = response_future.result()

        # check API and response
        self.assertIsInstance(response_future, grpc.Call)
        self.assertIsInstance(response_future, grpc.Future)
        self.assertIsInstance(response, Response)

        # span is finished in done callback which is run in different thread,
        # so we are waiting for it
        for _ in range(5):
            if len(self.memory_exporter.get_finished_spans()) == 0:
                time.sleep(0.1)
            else:
                break

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        self.assertEqual(span.name, "/GRPCTestServer/SimpleMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "SimpleMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.OK.value[
                    0
                ],
            },
        )

        # check events
        self.assertEqual(len(span.events), 2)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "SENT",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: request.ByteSize(),
            },
        )
        self.assertEvent(
            span.events[1],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: response.ByteSize(),
            },
        )

    def test_unary_unary_future_cancel_on_client_side(self):
        sleep = 1.0
        data = f"sleep {sleep:f}"
        request = Request(client_id=CLIENT_ID, request_data=data)

        with self.assertRaises(grpc.FutureCancelledError):
            response_future = self._stub.SimpleMethod.future(request)
            time.sleep(sleep / 2)
            response_future.cancel()
            response_future.result()

        # span is finished in done callback which is run in different thread,
        # so we are waiting for it
        for _ in range(5):
            if len(self.memory_exporter.get_finished_spans()) == 0:
                time.sleep(0.1)
            else:
                break

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        self.assertEqual(span.name, "/GRPCTestServer/SimpleMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "SimpleMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.CANCELLED.value[
                    0
                ],
            },
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.CANCELLED}: Locally cancelled by application!",
        )

        # check events
        self.assertEqual(len(span.events), 1)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "SENT",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: request.ByteSize(),
            },
        )

    def test_unary_unary_future_error(self):
        data = "error"
        request = Request(client_id=CLIENT_ID, request_data=data)

        with self.assertRaises(grpc.RpcError):
            response_future = self._stub.SimpleMethod.future(request)
            response_future.result()

        # check API and response
        self.assertIsInstance(response_future, grpc.Call)
        self.assertIsInstance(response_future, grpc.Future)

        # span is finished in done callback which is run in different thread,
        # so we are waiting for it
        for _ in range(5):
            if len(self.memory_exporter.get_finished_spans()) == 0:
                time.sleep(0.1)
            else:
                break

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        self.assertEqual(span.name, "/GRPCTestServer/SimpleMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.INVALID_ARGUMENT}: {data}",
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "SimpleMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.INVALID_ARGUMENT.value[
                    0
                ],
            },
        )

        # check events
        self.assertEqual(len(span.events), 2)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "SENT",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: request.ByteSize(),
            },
        )
        self.assertEvent(
            span.events[1],
            "exception",
            {
                "exception.type": "_MultiThreadedRendezvous",
                # "exception.message": error_message,
                # "exception.stacktrace": "...",
                "exception.escaped": str(False),
            },
        )

    def test_unary_unary_metrics(self):
        data = "data"
        request = Request(client_id=CLIENT_ID, request_data=data)
        response = self._stub.SimpleMethod(request)

        # check response
        self.assertIsInstance(response, Response)

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
                        _expected_metric_names[metric.name][2],
                    )

                    data_points = list(metric.data.data_points)
                    self.assertEqual(len(data_points), 1)

                    for point in data_points:
                        if isinstance(metric.data, Histogram):
                            self.assertIsInstance(point, HistogramDataPoint)
                            self.assertEqual(point.count, 1)
                            if metric.name == "rpc.client.duration":
                                self.assertGreaterEqual(point.sum, 0)
                            elif metric.name == "rpc.client.request.size":
                                self.assertEqual(point.sum, request.ByteSize())
                            elif metric.name == "rpc.client.response.size":
                                self.assertEqual(
                                    point.sum, response.ByteSize()
                                )
                            elif metric.name == "rpc.client.requests_per_rpc":
                                self.assertEqual(point.sum, 1)
                            elif metric.name == "rpc.client.responses_per_rpc":
                                self.assertEqual(point.sum, 1)

                        self.assertMetricDataPointHasAttributes(
                            point,
                            {
                                SpanAttributes.RPC_METHOD: "SimpleMethod",
                                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                                SpanAttributes.RPC_SYSTEM: "grpc",
                            },
                        )
                        if metric.name == "rpc.client.duration":
                            self.assertMetricDataPointHasAttributes(
                                point,
                                {
                                    SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.OK.value[
                                        0
                                    ]
                                },
                            )

    def test_unary_unary_metrics_error(self):
        data = "error"
        request = Request(client_id=CLIENT_ID, request_data=data)
        with self.assertRaises(grpc.RpcError):
            self._stub.SimpleMethod(request)

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
                    len(scope_metric.metrics), len(_expected_metric_names) - 2
                )
                self.assertNotIn(
                    "rpc.client.response.size", scope_metric.metrics
                )
                self.assertNotIn(
                    "rpc.client.responses_per_rpc", scope_metric.metrics
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
                        _expected_metric_names[metric.name][2],
                    )

                    data_points = list(metric.data.data_points)
                    self.assertEqual(len(data_points), 1)

                    for point in data_points:
                        if isinstance(metric.data, Histogram):
                            self.assertIsInstance(point, HistogramDataPoint)
                            self.assertEqual(point.count, 1)
                            if metric.name == "rpc.client.duration":
                                self.assertGreaterEqual(point.sum, 0)
                            elif metric.name == "rpc.client.request.size":
                                self.assertEqual(point.sum, request.ByteSize())
                            elif metric.name == "rpc.client.requests_per_rpc":
                                self.assertEqual(point.sum, 1)

                        self.assertMetricDataPointHasAttributes(
                            point,
                            {
                                SpanAttributes.RPC_METHOD: "SimpleMethod",
                                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                                SpanAttributes.RPC_SYSTEM: "grpc",
                            },
                        )
                        if metric.name == "rpc.client.duration":
                            self.assertMetricDataPointHasAttributes(
                                point,
                                {
                                    SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.INVALID_ARGUMENT.value[
                                        0
                                    ]
                                },
                            )

    def test_unary_unary_metrics_future(self):
        data = "data"
        request = Request(client_id=CLIENT_ID, request_data=data)

        response_future = self._stub.SimpleMethod.future(request)
        response = response_future.result()

        # check API and response
        self.assertIsInstance(response_future, grpc.Call)
        self.assertIsInstance(response_future, grpc.Future)
        self.assertIsInstance(response, Response)

        # span is finished in done callback which is run in different thread,
        # so we are waiting for it
        for _ in range(5):
            if len(self.memory_exporter.get_finished_spans()) == 0:
                time.sleep(0.1)
            else:
                break

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
                        _expected_metric_names[metric.name][2],
                    )

                    data_points = list(metric.data.data_points)
                    self.assertEqual(len(data_points), 1)

                    for point in data_points:
                        if isinstance(metric.data, Histogram):
                            self.assertIsInstance(point, HistogramDataPoint)
                            self.assertEqual(point.count, 1)
                            if metric.name == "rpc.client.duration":
                                self.assertGreaterEqual(point.sum, 0)
                            elif metric.name == "rpc.client.request.size":
                                self.assertEqual(point.sum, request.ByteSize())
                            elif metric.name == "rpc.client.response.size":
                                self.assertEqual(
                                    point.sum, response.ByteSize()
                                )
                            elif metric.name == "rpc.client.requests_per_rpc":
                                self.assertEqual(point.sum, 1)
                            elif metric.name == "rpc.client.responses_per_rpc":
                                self.assertEqual(point.sum, 1)

                        self.assertMetricDataPointHasAttributes(
                            point,
                            {
                                SpanAttributes.RPC_METHOD: "SimpleMethod",
                                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                                SpanAttributes.RPC_SYSTEM: "grpc",
                            },
                        )
                        if metric.name == "rpc.client.duration":
                            self.assertMetricDataPointHasAttributes(
                                point,
                                {
                                    SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.OK.value[
                                        0
                                    ]
                                },
                            )

    def test_unary_unary_with_suppress_key(self):
        token = context.attach(
            context.set_value(_SUPPRESS_INSTRUMENTATION_KEY, True)
        )

        request = Request(client_id=CLIENT_ID, request_data="data")
        try:
            self._stub.SimpleMethod(request)
            spans = self.memory_exporter.get_finished_spans()
        finally:
            context.detach(token)
        self.assertEqual(len(spans), 0)

    #
    # Unary-Stream-RPC
    #

    def test_unary_stream(self):
        data = "data"
        request = Request(client_id=CLIENT_ID, request_data=data)
        response_iterator = self._stub.ServerStreamingMethod(request)
        responses = list(response_iterator)

        # check API and response
        self.assertIsInstance(response_iterator, grpc.Call)
        self.assertIsInstance(response_iterator, grpc.Future)
        self.assertIsInstance(response_iterator, Iterator)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.name, "/GRPCTestServer/ServerStreamingMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "ServerStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.OK.value[
                    0
                ],
            },
        )

        # check events
        self.assertEqual(len(span.events), len(responses) + 1)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "SENT",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: request.ByteSize(),
            },
        )
        for res_id, response in enumerate(responses, start=1):
            self.assertEvent(
                span.events[res_id],
                "message",
                {
                    SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                    SpanAttributes.MESSAGE_ID: res_id,
                    SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: response.ByteSize(),
                },
                msg=f"Response ID: {res_id:d}",
            )

    def test_unary_stream_abort(self):
        data = "abort"
        request = Request(client_id=CLIENT_ID, request_data=data)

        responses = []
        with self.assertRaises(grpc.RpcError):
            response_iterator = self._stub.ServerStreamingMethod(request)
            for response in response_iterator:
                responses.append(response)

        # check API and response
        self.assertIsInstance(response_iterator, grpc.Call)
        self.assertIsInstance(response_iterator, grpc.Future)
        self.assertIsInstance(response_iterator, Iterator)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.name, "/GRPCTestServer/ServerStreamingMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "ServerStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.FAILED_PRECONDITION.value[
                    0
                ],
            },
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.FAILED_PRECONDITION}: {data}",
        )

        # check events
        self.assertEqual(len(span.events), len(responses) + 2)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "SENT",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: request.ByteSize(),
            },
        )
        for res_id, response in enumerate(responses, start=1):
            self.assertEvent(
                span.events[res_id],
                "message",
                {
                    SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                    SpanAttributes.MESSAGE_ID: res_id,
                    SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: response.ByteSize(),
                },
            )
        self.assertEvent(
            span.events[-1],
            "exception",
            {
                "exception.type": "_MultiThreadedRendezvous",
                # "exception.message": error_message,
                # "exception.stacktrace": "...",
                "exception.escaped": str(False),
            },
        )

    def test_unary_stream_cancel_on_client_side(self):
        sleep = 1.0
        data = f"sleep {sleep:f}"
        request = Request(client_id=CLIENT_ID, request_data=data)

        responses = []
        with self.assertRaises(grpc.RpcError):
            response_iterator = self._stub.ServerStreamingMethod(request)
            responses.append(next(response_iterator))
            response_iterator.cancel()
            responses.append(next(response_iterator))

        # check API and response
        self.assertIsInstance(response_iterator, grpc.Call)
        self.assertIsInstance(response_iterator, grpc.Future)
        self.assertIsInstance(response_iterator, Iterator)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.name, "/GRPCTestServer/ServerStreamingMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "ServerStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.CANCELLED.value[
                    0
                ],
            },
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.CANCELLED}: Locally cancelled by application!",
        )

        # check events
        self.assertGreater(len(span.events), len(responses) + 1)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "SENT",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: request.ByteSize(),
            },
        )
        for res_id, response in enumerate(responses, start=1):
            self.assertEvent(
                span.events[res_id],
                "message",
                {
                    SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                    SpanAttributes.MESSAGE_ID: res_id,
                    SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: response.ByteSize(),
                },
            )

    def test_unary_stream_cancel_on_server_side(self):
        data = "cancel"
        request = Request(client_id=CLIENT_ID, request_data=data)

        responses = []
        with self.assertRaises(grpc.RpcError):
            response_iterator = self._stub.ServerStreamingMethod(request)
            for response in response_iterator:
                responses.append(response)

        # check API and response
        self.assertIsInstance(response_iterator, grpc.Call)
        self.assertIsInstance(response_iterator, grpc.Future)
        self.assertIsInstance(response_iterator, Iterator)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.name, "/GRPCTestServer/ServerStreamingMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "ServerStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.CANCELLED.value[
                    0
                ],
            },
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.CANCELLED}: "
            f"{grpc.StatusCode.CANCELLED.value[1].upper()}",
        )

        # check events
        self.assertEqual(len(span.events), len(responses) + 2)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "SENT",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: request.ByteSize(),
            },
        )
        for res_id, response in enumerate(responses, start=1):
            self.assertEvent(
                span.events[res_id],
                "message",
                {
                    SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                    SpanAttributes.MESSAGE_ID: res_id,
                    SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: response.ByteSize(),
                },
            )
        self.assertEvent(
            span.events[-1],
            "exception",
            {
                "exception.type": "_MultiThreadedRendezvous",
                # "exception.message": error_message,
                # "exception.stacktrace": "...",
                "exception.escaped": str(False),
            },
        )

    def test_unary_stream_error(self):
        data = "error"
        request = Request(client_id=CLIENT_ID, request_data=data)

        responses = []
        with self.assertRaises(grpc.RpcError):
            response_iterator = self._stub.ServerStreamingMethod(request)
            for response in response_iterator:
                responses.append(response)

        # check API and response
        self.assertIsInstance(response_iterator, grpc.Call)
        self.assertIsInstance(response_iterator, grpc.Future)
        self.assertIsInstance(response_iterator, Iterator)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.name, "/GRPCTestServer/ServerStreamingMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "ServerStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.INVALID_ARGUMENT.value[
                    0
                ],
            },
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.INVALID_ARGUMENT}: {data}",
        )

        # check events
        self.assertEqual(len(span.events), len(responses) + 2)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "SENT",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: request.ByteSize(),
            },
        )
        for res_id, response in enumerate(responses, start=1):
            self.assertEvent(
                span.events[res_id],
                "message",
                {
                    SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                    SpanAttributes.MESSAGE_ID: res_id,
                    SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: response.ByteSize(),
                },
            )
        self.assertEvent(
            span.events[-1],
            "exception",
            {
                "exception.type": "_MultiThreadedRendezvous",
                # "exception.message": error_message,
                # "exception.stacktrace": "...",
                "exception.escaped": str(False),
            },
        )

    def test_unary_stream_exception(self):
        data = "exception"
        request = Request(client_id=CLIENT_ID, request_data=data)

        responses = []
        with self.assertRaises(grpc.RpcError):
            response_iterator = self._stub.ServerStreamingMethod(request)
            for response in response_iterator:
                responses.append(response)

        # check API and response
        self.assertIsInstance(response_iterator, grpc.Call)
        self.assertIsInstance(response_iterator, grpc.Future)
        self.assertIsInstance(response_iterator, Iterator)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.name, "/GRPCTestServer/ServerStreamingMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "ServerStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.UNKNOWN.value[
                    0
                ],
            },
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.UNKNOWN}: "
            f"Exception iterating responses: {data}",
        )

        # check events
        self.assertEqual(len(span.events), len(responses) + 2)
        self.assertEvent(
            span.events[0],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "SENT",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: request.ByteSize(),
            },
        )
        for res_id, response in enumerate(responses, start=1):
            self.assertEvent(
                span.events[res_id],
                "message",
                {
                    SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                    SpanAttributes.MESSAGE_ID: res_id,
                    SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: response.ByteSize(),
                },
            )
        self.assertEvent(
            span.events[-1],
            "exception",
            {
                "exception.type": "_MultiThreadedRendezvous",
                # "exception.message": error_message,
                # "exception.stacktrace": "...",
                "exception.escaped": str(False),
            },
        )

    def test_unary_stream_metrics(self):
        data = "data"
        request = Request(client_id=CLIENT_ID, request_data=data)
        response_iterator = self._stub.ServerStreamingMethod(request)
        responses = list(response_iterator)

        # check API and response
        self.assertIsInstance(response_iterator, grpc.Call)
        self.assertIsInstance(response_iterator, grpc.Future)
        self.assertIsInstance(response_iterator, Iterator)

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
                        _expected_metric_names[metric.name][2],
                    )

                    data_points = list(metric.data.data_points)
                    self.assertEqual(len(data_points), 1)

                    for point in data_points:
                        if isinstance(metric.data, Histogram):
                            self.assertIsInstance(point, HistogramDataPoint)
                            if metric.name == "rpc.client.duration":
                                self.assertEqual(point.count, 1)
                                self.assertGreaterEqual(point.sum, 0)
                            elif metric.name == "rpc.client.request.size":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, request.ByteSize())
                            elif metric.name == "rpc.client.response.size":
                                self.assertEqual(point.count, len(responses))
                                self.assertEqual(
                                    point.sum,
                                    sum(r.ByteSize() for r in responses),
                                )
                            elif metric.name == "rpc.client.requests_per_rpc":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, 1)
                            elif metric.name == "rpc.client.responses_per_rpc":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, len(responses))

                        self.assertMetricDataPointHasAttributes(
                            point,
                            {
                                SpanAttributes.RPC_METHOD: "ServerStreamingMethod",
                                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                                SpanAttributes.RPC_SYSTEM: "grpc",
                            },
                        )
                        if metric.name == "rpc.client.duration":
                            self.assertMetricDataPointHasAttributes(
                                point,
                                {
                                    SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.OK.value[
                                        0
                                    ]
                                },
                            )

    def test_unary_stream_metrics_error(self):
        data = "error"
        request = Request(client_id=CLIENT_ID, request_data=data)

        responses = []
        with self.assertRaises(grpc.RpcError):
            response_iterator = self._stub.ServerStreamingMethod(request)
            for response in response_iterator:
                responses.append(response)

        # check API and response
        self.assertIsInstance(response_iterator, grpc.Call)
        self.assertIsInstance(response_iterator, grpc.Future)
        self.assertIsInstance(response_iterator, Iterator)

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
                        _expected_metric_names[metric.name][2],
                    )

                    data_points = list(metric.data.data_points)
                    self.assertEqual(len(data_points), 1)

                    for point in data_points:
                        if isinstance(metric.data, Histogram):
                            self.assertIsInstance(point, HistogramDataPoint)
                            if metric.name == "rpc.client.duration":
                                self.assertEqual(point.count, 1)
                                self.assertGreaterEqual(point.sum, 0)
                            elif metric.name == "rpc.client.request.size":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, request.ByteSize())
                            elif metric.name == "rpc.client.response.size":
                                self.assertEqual(point.count, len(responses))
                                self.assertEqual(
                                    point.sum,
                                    sum(r.ByteSize() for r in responses),
                                )
                            elif metric.name == "rpc.client.requests_per_rpc":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, 1)
                            elif metric.name == "rpc.client.responses_per_rpc":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, len(responses))

                        self.assertMetricDataPointHasAttributes(
                            point,
                            {
                                SpanAttributes.RPC_METHOD: "ServerStreamingMethod",
                                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                                SpanAttributes.RPC_SYSTEM: "grpc",
                            },
                        )
                        if metric.name == "rpc.client.duration":
                            self.assertMetricDataPointHasAttributes(
                                point,
                                {
                                    SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.INVALID_ARGUMENT.value[
                                        0
                                    ]
                                },
                            )

    def test_unary_stream_with_suppress_key(self):
        token = context.attach(
            context.set_value(_SUPPRESS_INSTRUMENTATION_KEY, True)
        )
        data = "data"
        request = Request(client_id=CLIENT_ID, request_data=data)

        try:
            list(self._stub.ServerStreamingMethod(request))
            spans = self.memory_exporter.get_finished_spans()
        finally:
            context.detach(token)
        self.assertEqual(len(spans), 0)

    #
    # Stream-Unary-RPC
    #

    def test_stream_unary(self):
        data = "data"
        requests = []

        def request_messages(data):
            nonlocal requests

            for _ in range(5):
                request = Request(client_id=CLIENT_ID, request_data=data)
                requests.append(request)
                yield request

        response = self._stub.ClientStreamingMethod(request_messages(data))

        # check response
        self.assertIsInstance(response, Response)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.name, "/GRPCTestServer/ClientStreamingMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "ClientStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.OK.value[
                    0
                ],
            },
        )

        # check events
        self.assertEqual(len(span.events), len(requests) + 1)
        for req_id, request in enumerate(requests, start=1):
            self.assertEvent(
                span.events[req_id - 1],
                "message",
                {
                    SpanAttributes.MESSAGE_TYPE: "SENT",
                    SpanAttributes.MESSAGE_ID: req_id,
                    SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: request.ByteSize(),
                },
                msg=f"Request ID: {req_id:d}",
            )
        self.assertEvent(
            span.events[len(requests)],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: response.ByteSize(),
            },
        )

    def test_stream_unary_abort(self):
        data = "abort"
        requests = []

        def request_messages(data):
            nonlocal requests

            for _ in range(5):
                request = Request(client_id=CLIENT_ID, request_data=data)
                requests.append(request)
                yield request

        with self.assertRaises(grpc.RpcError):
            self._stub.ClientStreamingMethod(request_messages(data))

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.name, "/GRPCTestServer/ClientStreamingMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "ClientStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.FAILED_PRECONDITION.value[
                    0
                ],
            },
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.FAILED_PRECONDITION}: {data}",
        )

        # check events
        self.assertEqual(len(span.events), len(requests) + 1)
        for req_id, request in enumerate(requests, start=1):
            self.assertEvent(
                span.events[req_id - 1],
                "message",
                {
                    SpanAttributes.MESSAGE_TYPE: "SENT",
                    SpanAttributes.MESSAGE_ID: req_id,
                    SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: request.ByteSize(),
                },
                msg=f"Request ID: {req_id:d}",
            )
        self.assertEvent(
            span.events[len(requests)],
            "exception",
            {
                "exception.type": "_InactiveRpcError",
                # "exception.message": error_message,
                # "exception.stacktrace": "...",
                "exception.escaped": str(False),
            },
        )

    def test_stream_unary_cancel_on_server_side(self):
        data = "cancel"
        requests = []

        def request_messages(data):
            nonlocal requests

            for _ in range(5):
                request = Request(client_id=CLIENT_ID, request_data=data)
                requests.append(request)
                yield request

        with self.assertRaises(grpc.RpcError):
            self._stub.ClientStreamingMethod(request_messages(data))

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.name, "/GRPCTestServer/ClientStreamingMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "ClientStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.CANCELLED.value[
                    0
                ],
            },
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.CANCELLED}: "
            f"{grpc.StatusCode.CANCELLED.value[1].upper()}",
        )

        # check events
        self.assertEqual(len(span.events), len(requests) + 1)
        for req_id, request in enumerate(requests, start=1):
            self.assertEvent(
                span.events[req_id - 1],
                "message",
                {
                    SpanAttributes.MESSAGE_TYPE: "SENT",
                    SpanAttributes.MESSAGE_ID: req_id,
                    SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: request.ByteSize(),
                },
                msg=f"Request ID: {req_id:d}",
            )
        self.assertEvent(
            span.events[len(requests)],
            "exception",
            {
                "exception.type": "_InactiveRpcError",
                # "exception.message": error_message,
                # "exception.stacktrace": "...",
                "exception.escaped": str(False),
            },
        )

    def test_stream_unary_error(self):
        data = "error"
        requests = []

        def request_messages(data):
            nonlocal requests

            for _ in range(5):
                request = Request(client_id=CLIENT_ID, request_data=data)
                requests.append(request)
                yield request

        with self.assertRaises(grpc.RpcError):
            self._stub.ClientStreamingMethod(request_messages(data))

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.name, "/GRPCTestServer/ClientStreamingMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "ClientStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.INVALID_ARGUMENT.value[
                    0
                ],
            },
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.INVALID_ARGUMENT}: {data}",
        )

        # check events
        self.assertEqual(len(span.events), len(requests) + 1)
        for req_id, request in enumerate(requests, start=1):
            self.assertEvent(
                span.events[req_id - 1],
                "message",
                {
                    SpanAttributes.MESSAGE_TYPE: "SENT",
                    SpanAttributes.MESSAGE_ID: req_id,
                    SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: request.ByteSize(),
                },
                msg=f"Request ID: {req_id:d}",
            )
        self.assertEvent(
            span.events[len(requests)],
            "exception",
            {
                "exception.type": "_InactiveRpcError",
                # "exception.message": error_message,
                # "exception.stacktrace": "...",
                "exception.escaped": str(False),
            },
        )

    def test_stream_unary_exception(self):
        data = "exception"
        requests = []

        def request_messages(data):
            nonlocal requests

            for _ in range(5):
                request = Request(client_id=CLIENT_ID, request_data=data)
                requests.append(request)
                yield request

        with self.assertRaises(grpc.RpcError):
            self._stub.ClientStreamingMethod(request_messages(data))

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.name, "/GRPCTestServer/ClientStreamingMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "ClientStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.UNKNOWN.value[
                    0
                ],
            },
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.UNKNOWN}: "
            f"Exception calling application: {data}",
        )

        # check events
        self.assertEqual(len(span.events), len(requests) + 1)
        for req_id, request in enumerate(requests, start=1):
            self.assertEvent(
                span.events[req_id - 1],
                "message",
                {
                    SpanAttributes.MESSAGE_TYPE: "SENT",
                    SpanAttributes.MESSAGE_ID: req_id,
                    SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: request.ByteSize(),
                },
                msg=f"Request ID: {req_id:d}",
            )
        self.assertEvent(
            span.events[len(requests)],
            "exception",
            {
                "exception.type": "_InactiveRpcError",
                # "exception.message": error_message,
                # "exception.stacktrace": "...",
                "exception.escaped": str(False),
            },
        )

    def test_stream_unary_future(self):
        data = "data"
        requests = []

        def request_messages(data):
            nonlocal requests

            for _ in range(5):
                request = Request(client_id=CLIENT_ID, request_data=data)
                requests.append(request)
                yield request

        response_future = self._stub.ClientStreamingMethod.future(
            request_messages(data)
        )
        response = response_future.result()

        # check API and response
        self.assertIsInstance(response_future, grpc.Call)
        self.assertIsInstance(response_future, grpc.Future)
        self.assertIsInstance(response, Response)

        # span is finished in done callback which is run in different thread,
        # so we are waiting for it
        for _ in range(5):
            if len(self.memory_exporter.get_finished_spans()) == 0:
                time.sleep(0.1)
            else:
                break

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.name, "/GRPCTestServer/ClientStreamingMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "ClientStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.OK.value[
                    0
                ],
            },
        )

        # check events
        self.assertEqual(len(span.events), len(requests) + 1)
        for req_id, request in enumerate(requests, start=1):
            self.assertEvent(
                span.events[req_id - 1],
                "message",
                {
                    SpanAttributes.MESSAGE_TYPE: "SENT",
                    SpanAttributes.MESSAGE_ID: req_id,
                    SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: request.ByteSize(),
                },
                msg=f"Request ID: {req_id:d}",
            )
        self.assertEvent(
            span.events[len(requests)],
            "message",
            {
                SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                SpanAttributes.MESSAGE_ID: 1,
                SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: response.ByteSize(),
            },
        )

    def test_stream_unary_future_cancel_on_client_side(self):
        sleep = 1.0
        data = f"sleep {sleep:f}"
        requests = []

        def request_messages(data):
            nonlocal requests

            for _ in range(5):
                request = Request(client_id=CLIENT_ID, request_data=data)
                requests.append(request)
                yield request

        with self.assertRaises(grpc.FutureCancelledError):
            response_future = self._stub.ClientStreamingMethod.future(
                request_messages(data)
            )
            time.sleep(sleep / 2)
            response_future.cancel()
            response_future.result()

        # check API and response
        self.assertIsInstance(response_future, grpc.Call)
        self.assertIsInstance(response_future, grpc.Future)

        # span is finished in done callback which is run in different thread,
        # so we are waiting for it
        for _ in range(5):
            if len(self.memory_exporter.get_finished_spans()) == 0:
                time.sleep(0.1)
            else:
                break

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.name, "/GRPCTestServer/ClientStreamingMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "ClientStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.CANCELLED.value[
                    0
                ],
            },
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.CANCELLED}: Locally cancelled by application!",
        )

        # check events
        self.assertEqual(len(span.events), len(requests))
        for req_id, request in enumerate(requests, start=1):
            self.assertEvent(
                span.events[req_id - 1],
                "message",
                {
                    SpanAttributes.MESSAGE_TYPE: "SENT",
                    SpanAttributes.MESSAGE_ID: req_id,
                    SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: request.ByteSize(),
                },
                msg=f"Request ID: {req_id:d}",
            )

    def test_stream_unary_future_error(self):
        data = "error"
        requests = []

        def request_messages(data):
            nonlocal requests

            for _ in range(5):
                request = Request(client_id=CLIENT_ID, request_data=data)
                requests.append(request)
                yield request

        with self.assertRaises(grpc.RpcError):
            response_future = self._stub.ClientStreamingMethod.future(
                request_messages(data)
            )
            response_future.result()

        # check API and response
        self.assertIsInstance(response_future, grpc.Call)
        self.assertIsInstance(response_future, grpc.Future)

        # span is finished in done callback which is run in different thread,
        # so we are waiting for it
        for _ in range(5):
            if len(self.memory_exporter.get_finished_spans()) == 0:
                time.sleep(0.1)
            else:
                break

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(span.name, "/GRPCTestServer/ClientStreamingMethod")
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "ClientStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.INVALID_ARGUMENT.value[
                    0
                ],
            },
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.INVALID_ARGUMENT}: {data}",
        )

        # check events
        self.assertEqual(len(span.events), len(requests) + 1)
        for req_id, request in enumerate(requests, start=1):
            self.assertEvent(
                span.events[req_id - 1],
                "message",
                {
                    SpanAttributes.MESSAGE_TYPE: "SENT",
                    SpanAttributes.MESSAGE_ID: req_id,
                    SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: request.ByteSize(),
                },
                msg=f"Request ID: {req_id:d}",
            )
        self.assertEvent(
            span.events[len(requests)],
            "exception",
            {
                "exception.type": "_MultiThreadedRendezvous",
                # "exception.message": error_message,
                # "exception.stacktrace": "...",
                "exception.escaped": str(False),
            },
        )

    def test_stream_unary_metrics(self):
        data = "data"
        requests = []

        def request_messages(data):
            nonlocal requests

            for _ in range(5):
                request = Request(client_id=CLIENT_ID, request_data=data)
                requests.append(request)
                yield request

        response = self._stub.ClientStreamingMethod(request_messages(data))

        # check response
        self.assertIsInstance(response, Response)

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
                        _expected_metric_names[metric.name][2],
                    )

                    data_points = list(metric.data.data_points)
                    self.assertEqual(len(data_points), 1)

                    for point in data_points:
                        if isinstance(metric.data, Histogram):
                            self.assertIsInstance(point, HistogramDataPoint)
                            if metric.name == "rpc.client.duration":
                                self.assertEqual(point.count, 1)
                                self.assertGreaterEqual(point.sum, 0)
                            elif metric.name == "rpc.client.request.size":
                                self.assertEqual(point.count, len(requests))
                                self.assertEqual(
                                    point.sum,
                                    sum(r.ByteSize() for r in requests),
                                )
                            elif metric.name == "rpc.client.response.size":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(
                                    point.sum, response.ByteSize()
                                )
                            elif metric.name == "rpc.client.requests_per_rpc":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, len(requests))
                            elif metric.name == "rpc.client.responses_per_rpc":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, 1)

                        self.assertMetricDataPointHasAttributes(
                            point,
                            {
                                SpanAttributes.RPC_METHOD: "ClientStreamingMethod",
                                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                                SpanAttributes.RPC_SYSTEM: "grpc",
                            },
                        )
                        if metric.name == "rpc.client.duration":
                            self.assertMetricDataPointHasAttributes(
                                point,
                                {
                                    SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.OK.value[
                                        0
                                    ]
                                },
                            )

    def test_stream_unary_metrics_error(self):
        data = "error"
        requests = []

        def request_messages(data):
            nonlocal requests

            for _ in range(5):
                request = Request(client_id=CLIENT_ID, request_data=data)
                requests.append(request)
                yield request

        with self.assertRaises(grpc.RpcError):
            self._stub.ClientStreamingMethod(request_messages(data))

        # streams depend on threads -> wait for completition
        time.sleep(0.1)

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
                    len(scope_metric.metrics),
                    len(_expected_metric_names) - 2,
                    msg=", ".join([m.name for m in scope_metric.metrics]),
                )
                self.assertNotIn(
                    "rpc.client.response.size", scope_metric.metrics
                )
                self.assertNotIn(
                    "rpc.client.responses_per_rpc", scope_metric.metrics
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
                        _expected_metric_names[metric.name][2],
                    )

                    data_points = list(metric.data.data_points)
                    self.assertEqual(len(data_points), 1)

                    for point in data_points:
                        if isinstance(metric.data, Histogram):
                            self.assertIsInstance(point, HistogramDataPoint)
                            if metric.name == "rpc.client.duration":
                                self.assertEqual(point.count, 1)
                                self.assertGreaterEqual(point.sum, 0)
                            elif metric.name == "rpc.client.request.size":
                                self.assertEqual(point.count, len(requests))
                                self.assertEqual(
                                    point.sum,
                                    sum(r.ByteSize() for r in requests),
                                )
                            elif metric.name == "rpc.client.requests_per_rpc":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, len(requests))

                        self.assertMetricDataPointHasAttributes(
                            point,
                            {
                                SpanAttributes.RPC_METHOD: "ClientStreamingMethod",
                                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                                SpanAttributes.RPC_SYSTEM: "grpc",
                            },
                        )
                        if metric.name == "rpc.client.duration":
                            self.assertMetricDataPointHasAttributes(
                                point,
                                {
                                    SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.INVALID_ARGUMENT.value[
                                        0
                                    ]
                                },
                            )

    def test_stream_unary_metrics_future(self):
        data = "data"
        requests = []

        def request_messages(data):
            nonlocal requests

            for _ in range(5):
                request = Request(client_id=CLIENT_ID, request_data=data)
                requests.append(request)
                yield request

        response_future = self._stub.ClientStreamingMethod.future(
            request_messages(data)
        )
        response = response_future.result()

        # check API and response
        self.assertIsInstance(response_future, grpc.Call)
        self.assertIsInstance(response_future, grpc.Future)
        self.assertIsInstance(response, Response)

        # span is finished in done callback which is run in different thread,
        # so we are waiting for it
        for _ in range(5):
            if len(self.memory_exporter.get_finished_spans()) == 0:
                time.sleep(0.1)
            else:
                break

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
                        _expected_metric_names[metric.name][2],
                    )

                    data_points = list(metric.data.data_points)
                    self.assertEqual(len(data_points), 1)

                    for point in data_points:
                        if isinstance(metric.data, Histogram):
                            self.assertIsInstance(point, HistogramDataPoint)
                            if metric.name == "rpc.client.duration":
                                self.assertEqual(point.count, 1)
                                self.assertGreaterEqual(point.sum, 0)
                            elif metric.name == "rpc.client.request.size":
                                self.assertEqual(point.count, len(requests))
                                self.assertEqual(
                                    point.sum,
                                    sum(r.ByteSize() for r in requests),
                                )
                            elif metric.name == "rpc.client.response.size":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(
                                    point.sum, response.ByteSize()
                                )
                            elif metric.name == "rpc.client.requests_per_rpc":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, len(requests))
                            elif metric.name == "rpc.client.responses_per_rpc":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, 1)

                        self.assertMetricDataPointHasAttributes(
                            point,
                            {
                                SpanAttributes.RPC_METHOD: "ClientStreamingMethod",
                                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                                SpanAttributes.RPC_SYSTEM: "grpc",
                            },
                        )
                        if metric.name == "rpc.client.duration":
                            self.assertMetricDataPointHasAttributes(
                                point,
                                {
                                    SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.OK.value[
                                        0
                                    ]
                                },
                            )

    def test_stream_unary_with_suppress_key(self):
        token = context.attach(
            context.set_value(_SUPPRESS_INSTRUMENTATION_KEY, True)
        )

        def request_messages(data):
            for _ in range(5):
                request = Request(client_id=CLIENT_ID, request_data=data)
                yield request

        try:
            self._stub.ClientStreamingMethod(request_messages("data"))
            spans = self.memory_exporter.get_finished_spans()
        finally:
            context.detach(token)
        self.assertEqual(len(spans), 0)

    #
    # Stream-Stream-RPC
    #

    def test_stream_stream(self):
        data = "data"
        requests = []

        def request_messages(data):
            nonlocal requests

            for _ in range(5):
                request = Request(client_id=CLIENT_ID, request_data=data)
                requests.append(request)
                yield request

        response_iterator = self._stub.BidirectionalStreamingMethod(
            request_messages(data)
        )
        responses = list(response_iterator)

        # check API and response
        self.assertIsInstance(response_iterator, grpc.Call)
        self.assertIsInstance(response_iterator, grpc.Future)
        self.assertIsInstance(response_iterator, Iterator)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(
            span.name, "/GRPCTestServer/BidirectionalStreamingMethod"
        )
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "BidirectionalStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.OK.value[
                    0
                ],
            },
        )

        # check events
        self.assertEqual(len(span.events), len(requests) + len(responses))
        # requests and responses occur random
        req_id = 0
        res_id = 0
        for event in span.events:
            self.assertIn(SpanAttributes.MESSAGE_TYPE, event.attributes)
            if event.attributes[SpanAttributes.MESSAGE_TYPE] == "SENT":
                req_id += 1
                self.assertEvent(
                    event,
                    "message",
                    {
                        SpanAttributes.MESSAGE_TYPE: "SENT",
                        SpanAttributes.MESSAGE_ID: req_id,
                        SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: requests[
                            req_id - 1
                        ].ByteSize(),
                    },
                )
            elif event.attributes[SpanAttributes.MESSAGE_TYPE] == "RECEIVED":
                res_id += 1
                self.assertEvent(
                    event,
                    "message",
                    {
                        SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                        SpanAttributes.MESSAGE_ID: res_id,
                        SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: responses[
                            res_id - 1
                        ].ByteSize(),
                    },
                )
            else:
                self.fail(
                    "unknown message type: "
                    f"{event.attributes[SpanAttributes.MESSAGE_TYPE]}"
                )
        self.assertEqual(len(requests), req_id)
        self.assertEqual(len(responses), res_id)

    def test_stream_stream_abort(self):
        data = "abort"
        requests = []

        def request_messages(data):
            nonlocal requests

            for _ in range(5):
                request = Request(client_id=CLIENT_ID, request_data=data)
                requests.append(request)
                yield request

        responses = []
        with self.assertRaises(grpc.RpcError):
            response_iterator = self._stub.BidirectionalStreamingMethod(
                request_messages(data)
            )
            for response in response_iterator:
                responses.append(response)

        # check API and response
        self.assertIsInstance(response_iterator, grpc.Call)
        self.assertIsInstance(response_iterator, grpc.Future)
        self.assertIsInstance(response_iterator, Iterator)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(
            span.name, "/GRPCTestServer/BidirectionalStreamingMethod"
        )
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "BidirectionalStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.FAILED_PRECONDITION.value[
                    0
                ],
            },
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.FAILED_PRECONDITION}: {data}",
        )

        # check events
        self.assertEqual(len(span.events), len(requests) + len(responses) + 1)
        # requests and responses occur random
        req_id = 0
        res_id = 0
        for event in span.events[:-1]:
            self.assertIn(SpanAttributes.MESSAGE_TYPE, event.attributes)
            if event.attributes[SpanAttributes.MESSAGE_TYPE] == "SENT":
                req_id += 1
                self.assertEvent(
                    event,
                    "message",
                    {
                        SpanAttributes.MESSAGE_TYPE: "SENT",
                        SpanAttributes.MESSAGE_ID: req_id,
                        SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: requests[
                            req_id - 1
                        ].ByteSize(),
                    },
                )
            elif event.attributes[SpanAttributes.MESSAGE_TYPE] == "RECEIVED":
                res_id += 1
                self.assertEvent(
                    event,
                    "message",
                    {
                        SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                        SpanAttributes.MESSAGE_ID: res_id,
                        SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: responses[
                            res_id - 1
                        ].ByteSize(),
                    },
                )
            else:
                self.fail(
                    "unknown message type: "
                    f"{event.attributes[SpanAttributes.MESSAGE_TYPE]}"
                )
        self.assertEqual(len(requests), req_id)
        self.assertEqual(len(responses), res_id)

        self.assertEvent(
            span.events[-1],
            "exception",
            {
                "exception.type": "_MultiThreadedRendezvous",
                # "exception.message": error_message,
                # "exception.stacktrace": "...",
                "exception.escaped": str(False),
            },
        )

    def test_stream_stream_cancel_on_client_side(self):
        sleep = 1.0
        data = f"sleep {sleep:f}"
        requests = []

        def request_messages(data):
            nonlocal requests

            for _ in range(5):
                request = Request(client_id=CLIENT_ID, request_data=data)
                requests.append(request)
                yield request

        responses = []
        with self.assertRaises(grpc.RpcError):
            response_iterator = self._stub.BidirectionalStreamingMethod(
                request_messages(data)
            )
            responses.append(next(response_iterator))
            response_iterator.cancel()
            responses.append(next(response_iterator))

        # check API and response
        self.assertIsInstance(response_iterator, grpc.Call)
        self.assertIsInstance(response_iterator, grpc.Future)
        self.assertIsInstance(response_iterator, Iterator)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(
            span.name, "/GRPCTestServer/BidirectionalStreamingMethod"
        )
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "BidirectionalStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.CANCELLED.value[
                    0
                ],
            },
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.CANCELLED}: Locally cancelled by application!",
        )

        # check events
        self.assertGreaterEqual(
            len(span.events),
            len(requests) + len(responses),
            msg=", ".join([e.name for e in span.events]),
        )
        # requests and responses occur random
        req_id = 0
        res_id = 0
        for event_id, event in enumerate(span.events, start=1):
            if event.name == "message":
                self.assertIn(SpanAttributes.MESSAGE_TYPE, event.attributes)
                if event.attributes[SpanAttributes.MESSAGE_TYPE] == "SENT":
                    req_id += 1
                    self.assertEvent(
                        event,
                        "message",
                        {
                            SpanAttributes.MESSAGE_TYPE: "SENT",
                            SpanAttributes.MESSAGE_ID: req_id,
                            SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: requests[
                                req_id - 1
                            ].ByteSize(),
                        },
                    )
                elif (
                    event.attributes[SpanAttributes.MESSAGE_TYPE] == "RECEIVED"
                ):
                    res_id += 1
                    self.assertEvent(
                        event,
                        "message",
                        {
                            SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                            SpanAttributes.MESSAGE_ID: res_id,
                            SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: responses[
                                res_id - 1
                            ].ByteSize(),
                        },
                    )
                else:
                    self.fail(
                        "unknown message type: "
                        f"{event.attributes[SpanAttributes.MESSAGE_TYPE]}"
                    )
            elif event.name == "exception":
                self.assertEvent(
                    event,
                    "exception",
                    {
                        "exception.type": "_MultiThreadedRendezvous",
                        # "exception.message": error_message,
                        # "exception.stacktrace": "...",
                        "exception.escaped": str(False),
                    },
                )
                self.assertEqual(event_id, len(span.events))
            else:
                self.fail(f"unknown event name: {event.name}")
        self.assertEqual(len(requests), req_id)
        self.assertEqual(len(responses), res_id)

    def test_stream_stream_cancel_on_server_side(self):
        data = "cancel"
        requests = []

        def request_messages(data):
            nonlocal requests

            for _ in range(5):
                request = Request(client_id=CLIENT_ID, request_data=data)
                requests.append(request)
                yield request

        responses = []
        with self.assertRaises(grpc.RpcError):
            response_iterator = self._stub.BidirectionalStreamingMethod(
                request_messages(data)
            )
            for response in response_iterator:
                responses.append(response)

        # check API and response
        self.assertIsInstance(response_iterator, grpc.Call)
        self.assertIsInstance(response_iterator, grpc.Future)
        self.assertIsInstance(response_iterator, Iterator)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(
            span.name, "/GRPCTestServer/BidirectionalStreamingMethod"
        )
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "BidirectionalStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.CANCELLED.value[
                    0
                ],
            },
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.CANCELLED}: "
            f"{grpc.StatusCode.CANCELLED.value[1].upper()}",
        )

        # check events
        self.assertEqual(len(span.events), len(requests) + len(responses) + 1)
        # requests and responses occur random
        req_id = 0
        res_id = 0
        for event in span.events[:-1]:
            self.assertIn(SpanAttributes.MESSAGE_TYPE, event.attributes)
            if event.attributes[SpanAttributes.MESSAGE_TYPE] == "SENT":
                req_id += 1
                self.assertEvent(
                    event,
                    "message",
                    {
                        SpanAttributes.MESSAGE_TYPE: "SENT",
                        SpanAttributes.MESSAGE_ID: req_id,
                        SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: requests[
                            req_id - 1
                        ].ByteSize(),
                    },
                )
            elif event.attributes[SpanAttributes.MESSAGE_TYPE] == "RECEIVED":
                res_id += 1
                self.assertEvent(
                    event,
                    "message",
                    {
                        SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                        SpanAttributes.MESSAGE_ID: res_id,
                        SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: responses[
                            res_id - 1
                        ].ByteSize(),
                    },
                )
            else:
                self.fail(
                    "unknown message type: "
                    f"{event.attributes[SpanAttributes.MESSAGE_TYPE]}"
                )
        self.assertEqual(len(requests), req_id)
        self.assertEqual(len(responses), res_id)

        self.assertEvent(
            span.events[-1],
            "exception",
            {
                "exception.type": "_MultiThreadedRendezvous",
                # "exception.message": error_message,
                # "exception.stacktrace": "...",
                "exception.escaped": str(False),
            },
        )

    def test_stream_stream_error(self):
        data = "error"
        requests = []

        def request_messages(data):
            nonlocal requests

            for _ in range(5):
                request = Request(client_id=CLIENT_ID, request_data=data)
                requests.append(request)
                yield request

        responses = []
        with self.assertRaises(grpc.RpcError):
            response_iterator = self._stub.BidirectionalStreamingMethod(
                request_messages(data)
            )
            for response in response_iterator:
                responses.append(response)

        # check API and response
        self.assertIsInstance(response_iterator, grpc.Call)
        self.assertIsInstance(response_iterator, grpc.Future)
        self.assertIsInstance(response_iterator, Iterator)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(
            span.name, "/GRPCTestServer/BidirectionalStreamingMethod"
        )
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "BidirectionalStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.INVALID_ARGUMENT.value[
                    0
                ],
            },
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.INVALID_ARGUMENT}: {data}",
        )

        # check events
        self.assertEqual(len(span.events), len(requests) + len(responses) + 1)
        # requests and responses occur random
        req_id = 0
        res_id = 0
        for event in span.events[:-1]:
            self.assertIn(SpanAttributes.MESSAGE_TYPE, event.attributes)
            if event.attributes[SpanAttributes.MESSAGE_TYPE] == "SENT":
                req_id += 1
                self.assertEvent(
                    event,
                    "message",
                    {
                        SpanAttributes.MESSAGE_TYPE: "SENT",
                        SpanAttributes.MESSAGE_ID: req_id,
                        SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: requests[
                            req_id - 1
                        ].ByteSize(),
                    },
                )
            elif event.attributes[SpanAttributes.MESSAGE_TYPE] == "RECEIVED":
                res_id += 1
                self.assertEvent(
                    event,
                    "message",
                    {
                        SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                        SpanAttributes.MESSAGE_ID: res_id,
                        SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: responses[
                            res_id - 1
                        ].ByteSize(),
                    },
                )
            else:
                self.fail(
                    "unknown message type: "
                    f"{event.attributes[SpanAttributes.MESSAGE_TYPE]}"
                )
        self.assertEqual(len(requests), req_id)
        self.assertEqual(len(responses), res_id)

        self.assertEvent(
            span.events[-1],
            "exception",
            {
                "exception.type": "_MultiThreadedRendezvous",
                # "exception.message": error_message,
                # "exception.stacktrace": "...",
                "exception.escaped": str(False),
            },
        )

    def test_stream_stream_exception(self):
        data = "exception"
        requests = []

        def request_messages(data):
            nonlocal requests

            for _ in range(5):
                request = Request(client_id=CLIENT_ID, request_data=data)
                requests.append(request)
                yield request

        responses = []
        with self.assertRaises(grpc.RpcError):
            response_iterator = self._stub.BidirectionalStreamingMethod(
                request_messages(data)
            )
            for response in response_iterator:
                responses.append(response)

        # check API and response
        self.assertIsInstance(response_iterator, grpc.Call)
        self.assertIsInstance(response_iterator, grpc.Future)
        self.assertIsInstance(response_iterator, Iterator)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]
        self.assertEqual(
            span.name, "/GRPCTestServer/BidirectionalStreamingMethod"
        )
        self.assertIs(span.kind, trace.SpanKind.CLIENT)

        # check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.grpc
        )

        # check span attributes
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.RPC_METHOD: "BidirectionalStreamingMethod",
                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                SpanAttributes.RPC_SYSTEM: "grpc",
                SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.UNKNOWN.value[
                    0
                ],
            },
        )

        # make sure this span errored, with the right status and detail
        self.assertEqual(span.status.status_code, trace.StatusCode.ERROR)
        self.assertEqual(
            span.status.description,
            f"{grpc.StatusCode.UNKNOWN}: "
            f"Exception iterating responses: {data}",
        )

        # check events
        self.assertEqual(len(span.events), len(requests) + len(responses) + 1)
        # requests and responses occur random
        req_id = 0
        res_id = 0
        for event in span.events[:-1]:
            self.assertIn(SpanAttributes.MESSAGE_TYPE, event.attributes)
            if event.attributes[SpanAttributes.MESSAGE_TYPE] == "SENT":
                req_id += 1
                self.assertEvent(
                    event,
                    "message",
                    {
                        SpanAttributes.MESSAGE_TYPE: "SENT",
                        SpanAttributes.MESSAGE_ID: req_id,
                        SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: requests[
                            req_id - 1
                        ].ByteSize(),
                    },
                )
            elif event.attributes[SpanAttributes.MESSAGE_TYPE] == "RECEIVED":
                res_id += 1
                self.assertEvent(
                    event,
                    "message",
                    {
                        SpanAttributes.MESSAGE_TYPE: "RECEIVED",
                        SpanAttributes.MESSAGE_ID: res_id,
                        SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: responses[
                            res_id - 1
                        ].ByteSize(),
                    },
                )
            else:
                self.fail(
                    "unknown message type: "
                    f"{event.attributes[SpanAttributes.MESSAGE_TYPE]}"
                )
        self.assertEqual(len(requests), req_id)
        self.assertEqual(len(responses), res_id)

        self.assertEvent(
            span.events[-1],
            "exception",
            {
                "exception.type": "_MultiThreadedRendezvous",
                # "exception.message": error_message,
                # "exception.stacktrace": "...",
                "exception.escaped": str(False),
            },
        )

    def test_stream_stream_metrics(self):
        data = "data"
        requests = []

        def request_messages(data):
            nonlocal requests

            for _ in range(5):
                request = Request(client_id=CLIENT_ID, request_data=data)
                requests.append(request)
                yield request

        response_iterator = self._stub.BidirectionalStreamingMethod(
            request_messages(data)
        )
        responses = list(response_iterator)

        # check API and response
        self.assertIsInstance(response_iterator, grpc.Call)
        self.assertIsInstance(response_iterator, grpc.Future)
        self.assertIsInstance(response_iterator, Iterator)

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
                        _expected_metric_names[metric.name][2],
                    )

                    data_points = list(metric.data.data_points)
                    self.assertEqual(len(data_points), 1)

                    for point in data_points:
                        if isinstance(metric.data, Histogram):
                            self.assertIsInstance(point, HistogramDataPoint)
                            if metric.name == "rpc.client.duration":
                                self.assertEqual(point.count, 1)
                                self.assertGreaterEqual(point.sum, 0)
                            elif metric.name == "rpc.client.request.size":
                                self.assertEqual(point.count, len(requests))
                                self.assertEqual(
                                    point.sum,
                                    sum(r.ByteSize() for r in requests),
                                )
                            elif metric.name == "rpc.client.response.size":
                                self.assertEqual(point.count, len(responses))
                                self.assertEqual(
                                    point.sum,
                                    sum(r.ByteSize() for r in responses),
                                )
                            elif metric.name == "rpc.client.requests_per_rpc":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, len(requests))
                            elif metric.name == "rpc.client.responses_per_rpc":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, len(responses))

                        self.assertMetricDataPointHasAttributes(
                            point,
                            {
                                SpanAttributes.RPC_METHOD: "BidirectionalStreamingMethod",
                                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                                SpanAttributes.RPC_SYSTEM: "grpc",
                            },
                        )
                        if metric.name == "rpc.client.duration":
                            self.assertMetricDataPointHasAttributes(
                                point,
                                {
                                    SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.OK.value[
                                        0
                                    ]
                                },
                            )

    def test_stream_stream_metrics_error(self):
        data = "error"
        requests = []

        def request_messages(data):
            nonlocal requests

            for _ in range(5):
                request = Request(client_id=CLIENT_ID, request_data=data)
                requests.append(request)
                yield request

        responses = []
        with self.assertRaises(grpc.RpcError):
            response_iterator = self._stub.BidirectionalStreamingMethod(
                request_messages(data)
            )
            for response in response_iterator:
                responses.append(response)

        # check API and response
        self.assertIsInstance(response_iterator, grpc.Call)
        self.assertIsInstance(response_iterator, grpc.Future)
        self.assertIsInstance(response_iterator, Iterator)

        # streams depend on threads -> wait for completition
        time.sleep(0.1)

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
                    len(scope_metric.metrics),
                    len(_expected_metric_names),
                    msg=", ".join([m.name for m in scope_metric.metrics]),
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
                        _expected_metric_names[metric.name][2],
                    )

                    data_points = list(metric.data.data_points)
                    self.assertEqual(len(data_points), 1)

                    for point in data_points:
                        if isinstance(metric.data, Histogram):
                            self.assertIsInstance(point, HistogramDataPoint)
                            if metric.name == "rpc.client.duration":
                                self.assertEqual(point.count, 1)
                                self.assertGreaterEqual(point.sum, 0)
                            elif metric.name == "rpc.client.request.size":
                                self.assertEqual(point.count, len(requests))
                                self.assertEqual(
                                    point.sum,
                                    sum(r.ByteSize() for r in requests),
                                )
                            elif metric.name == "rpc.client.response.size":
                                self.assertEqual(point.count, len(responses))
                                self.assertEqual(
                                    point.sum,
                                    sum(r.ByteSize() for r in responses),
                                )
                            elif metric.name == "rpc.client.requests_per_rpc":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, len(requests))
                            elif metric.name == "rpc.client.responses_per_rpc":
                                self.assertEqual(point.count, 1)
                                self.assertEqual(point.sum, len(responses))

                        self.assertMetricDataPointHasAttributes(
                            point,
                            {
                                SpanAttributes.RPC_METHOD: "BidirectionalStreamingMethod",
                                SpanAttributes.RPC_SERVICE: "GRPCTestServer",
                                SpanAttributes.RPC_SYSTEM: "grpc",
                            },
                        )
                        if metric.name == "rpc.client.duration":
                            self.assertMetricDataPointHasAttributes(
                                point,
                                {
                                    SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.INVALID_ARGUMENT.value[
                                        0
                                    ]
                                },
                            )

    def test_stream_stream_with_suppress_key(self):
        token = context.attach(
            context.set_value(_SUPPRESS_INSTRUMENTATION_KEY, True)
        )

        def request_messages(data):
            for _ in range(5):
                yield Request(client_id=CLIENT_ID, request_data=data)

        try:
            self._stub.BidirectionalStreamingMethod(request_messages("data"))
            spans = self.memory_exporter.get_finished_spans()
        finally:
            context.detach(token)

        self.assertEqual(len(spans), 0)

    def test_client_interceptor_trace_context_propagation(
        self,
    ):  # pylint: disable=no-self-use
        """ensure that client interceptor correctly inject trace context into
        all outgoing requests.
        """

        previous_propagator = get_global_textmap()
        try:
            set_global_textmap(MockTextMapPropagator())
            interceptor = OpenTelemetryClientInterceptor(
                metrics.NoOpMeter("test"), trace.NoOpTracer()
            )

            carrier = tuple()

            def invoker(client_call_details, request):
                nonlocal carrier
                carrier = client_call_details.metadata
                return {}

            request = Request(client_id=1, request_data="data")
            interceptor.intercept_unary_unary(
                invoker,
                _ClientCallDetails(
                    method="/GRPCTestServer/SimpleMethod",
                    timeout=None,
                    metadata=None,
                    credentials=None,
                    wait_for_ready=False,
                    compression=None,
                ),
                request,
            )

            assert len(carrier) == 2
            assert carrier[0][0] == "mock-traceid"
            assert carrier[0][1] == "0"
            assert carrier[1][0] == "mock-spanid"
            assert carrier[1][1] == "0"

        finally:
            set_global_textmap(previous_propagator)
