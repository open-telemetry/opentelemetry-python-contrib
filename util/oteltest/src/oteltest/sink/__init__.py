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


import abc
from concurrent import futures

import grpc  # type: ignore
from oteltest.sink.private import (
    _LogsServiceServicer,
    _MetricsServiceServicer,
    _TraceServiceServicer,
)

from opentelemetry.proto.collector.logs.v1 import (  # type: ignore
    logs_service_pb2_grpc,
)
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,  # type: ignore
)
from opentelemetry.proto.collector.metrics.v1 import (  # type: ignore
    metrics_service_pb2_grpc,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,  # type: ignore
)
from opentelemetry.proto.collector.trace.v1 import (  # type: ignore
    trace_service_pb2_grpc,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,  # type: ignore
)


class RequestHandler(abc.ABC):
    """
    The RequestHandler interface is meant to be implemented by users of the otelsink API. If you use the API,
    you'll want to create a RequestHandler implementation, instantiate it, and pass the instance to the GrpcSink
    constructor. As messages arrive, the callbacks defined by this interface will be invoked.

    grpc_sink = GrpcSink(MyRequestHandler())
    """

    @abc.abstractmethod
    def handle_logs(self, request: ExportLogsServiceRequest, context):
        pass

    @abc.abstractmethod
    def handle_metrics(self, request: ExportMetricsServiceRequest, context):
        pass

    @abc.abstractmethod
    def handle_trace(self, request: ExportTraceServiceRequest, context):
        pass


class GrpcSink:
    """
    This is an OTel GRPC server to which you can send metrics, traces, and
    logs. It requires a RequestHandler implementation passed in.
    """

    def __init__(self, request_handler: RequestHandler):
        self.svr = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        trace_service_pb2_grpc.add_TraceServiceServicer_to_server(
            _TraceServiceServicer(request_handler.handle_trace), self.svr
        )
        metrics_service_pb2_grpc.add_MetricsServiceServicer_to_server(
            _MetricsServiceServicer(request_handler.handle_metrics), self.svr
        )
        logs_service_pb2_grpc.add_LogsServiceServicer_to_server(
            _LogsServiceServicer(request_handler.handle_logs), self.svr
        )
        self.svr.add_insecure_port("0.0.0.0:4317")

    def start(self):
        """Starts the server. Does not block."""
        self.svr.start()

    def wait_for_termination(self):
        """Blocks until the server stops."""
        try:
            self.svr.wait_for_termination()
        except BaseException:
            print("terminated")

    def stop(self):
        """Stops the server immediately."""
        self.svr.stop(grace=None)


class PrintHandler(RequestHandler):
    """
    A RequestHandler implementation that prints the received messages.
    """

    def handle_logs(self, request, context):  # noqa: ARG002
        print(f"log request: {request}", flush=True)  # noqa: T201

    def handle_metrics(self, request, context):  # noqa: ARG002
        print(f"metrics request: {request}", flush=True)  # noqa: T201

    def handle_trace(self, request, context):  # noqa: ARG002
        print(f"trace request: {request}", flush=True)  # noqa: T201


def run_with_print_handler():
    """
    Runs otelsink with a PrintHandler.
    """
    print("starting otelsink with a print handler", flush=True)
    sink = GrpcSink(PrintHandler())
    sink.start()
    sink.wait_for_termination()
