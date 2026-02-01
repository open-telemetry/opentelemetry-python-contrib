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

"""gRPC OTLP receiver for ClickHouse Collector."""

import logging
from concurrent import futures
from typing import Any, Callable, Dict, List, Optional

import grpc

from opentelemetry.exporter.clickhouse_genai.processors.transform import (
    otlp_logs_to_rows,
    otlp_metrics_to_rows,
    otlp_spans_to_rows,
)
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
    ExportLogsServiceResponse,
)
from opentelemetry.proto.collector.logs.v1.logs_service_pb2_grpc import (
    LogsServiceServicer,
    add_LogsServiceServicer_to_server,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
    ExportMetricsServiceResponse,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2_grpc import (
    MetricsServiceServicer,
    add_MetricsServiceServicer_to_server,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2_grpc import (
    TraceServiceServicer,
    add_TraceServiceServicer_to_server,
)

logger = logging.getLogger(__name__)


class _TraceServicer(TraceServiceServicer):
    """gRPC TraceService implementation."""

    def __init__(self, on_traces: Callable[[List[Dict[str, Any]]], None]):
        """Initialize the trace servicer.

        Args:
            on_traces: Callback function for processed trace rows.
        """
        self._on_traces = on_traces

    def Export(
        self,
        request: ExportTraceServiceRequest,
        context: grpc.ServicerContext,
    ) -> ExportTraceServiceResponse:
        """Handle incoming trace export requests.

        Args:
            request: OTLP trace export request.
            context: gRPC servicer context.

        Returns:
            Export response.
        """
        try:
            rows = otlp_spans_to_rows(request)
            if rows:
                self._on_traces(rows)
            logger.info("We are processed these traces : %s", rows)
            logger.debug("Received %d spans", len(rows))
            return ExportTraceServiceResponse()
        except Exception as e:
            logger.error("Error processing trace export: %s", e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ExportTraceServiceResponse()


class _LogsServicer(LogsServiceServicer):
    """gRPC LogsService implementation."""

    def __init__(self, on_logs: Callable[[List[Dict[str, Any]]], None]):
        """Initialize the logs servicer.

        Args:
            on_logs: Callback function for processed log rows.
        """
        self._on_logs = on_logs

    def Export(
        self,
        request: ExportLogsServiceRequest,
        context: grpc.ServicerContext,
    ) -> ExportLogsServiceResponse:
        """Handle incoming logs export requests.

        Args:
            request: OTLP logs export request.
            context: gRPC servicer context.

        Returns:
            Export response.
        """
        try:
            rows = otlp_logs_to_rows(request)
            if rows:
                self._on_logs(rows)
            logger.debug("Received %d log records", len(rows))
            return ExportLogsServiceResponse()
        except Exception as e:
            logger.error("Error processing logs export: %s", e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ExportLogsServiceResponse()


class _MetricsServicer(MetricsServiceServicer):
    """gRPC MetricsService implementation."""

    def __init__(self, on_metrics: Callable[[List[Dict[str, Any]]], None]):
        """Initialize the metrics servicer.

        Args:
            on_metrics: Callback function for processed metric rows.
        """
        self._on_metrics = on_metrics

    def Export(
        self,
        request: ExportMetricsServiceRequest,
        context: grpc.ServicerContext,
    ) -> ExportMetricsServiceResponse:
        """Handle incoming metrics export requests.

        Args:
            request: OTLP metrics export request.
            context: gRPC servicer context.

        Returns:
            Export response.
        """
        try:
            rows = otlp_metrics_to_rows(request)
            if rows:
                self._on_metrics(rows)
            logger.debug("Received %d metric data points", len(rows))
            return ExportMetricsServiceResponse()
        except Exception as e:
            logger.error("Error processing metrics export: %s", e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ExportMetricsServiceResponse()


class OTLPGrpcReceiver:
    """gRPC OTLP receiver implementing TraceService, LogsService, MetricsService.

    This receiver listens on the standard OTLP gRPC port (4317) and forwards
    received telemetry data to the provided callback functions.
    """

    def __init__(
        self,
        endpoint: str = "0.0.0.0:4317",
        on_traces: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
        on_logs: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
        on_metrics: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
        max_workers: int = 10,
    ):
        """Initialize the gRPC OTLP receiver.

        Args:
            endpoint: Server endpoint (host:port).
            on_traces: Callback for trace rows.
            on_logs: Callback for log rows.
            on_metrics: Callback for metric rows.
            max_workers: Maximum worker threads for gRPC server.
        """
        self._endpoint = endpoint
        self._on_traces = on_traces or (lambda x: None)
        self._on_logs = on_logs or (lambda x: None)
        self._on_metrics = on_metrics or (lambda x: None)
        self._max_workers = max_workers
        self._server: Optional[grpc.Server] = None

    def start(self) -> None:
        """Start the gRPC server."""
        if self._server is not None:
            logger.warning("gRPC receiver already running")
            return

        self._server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=self._max_workers),
            options=[
                ("grpc.max_receive_message_length", 64 * 1024 * 1024),  # 64MB
                ("grpc.max_send_message_length", 64 * 1024 * 1024),
            ],
        )

        # Add service implementations
        add_TraceServiceServicer_to_server(
            _TraceServicer(self._on_traces),
            self._server,
        )
        add_LogsServiceServicer_to_server(
            _LogsServicer(self._on_logs),
            self._server,
        )
        add_MetricsServiceServicer_to_server(
            _MetricsServicer(self._on_metrics),
            self._server,
        )

        # Bind to endpoint
        self._server.add_insecure_port(self._endpoint)
        self._server.start()
        logger.info("gRPC OTLP receiver started on %s", self._endpoint)

    def stop(self, grace_period: float = 5.0) -> None:
        """Stop the gRPC server gracefully.

        Args:
            grace_period: Time to wait for graceful shutdown (seconds).
        """
        if self._server is None:
            return

        logger.info("Stopping gRPC OTLP receiver...")
        self._server.stop(grace_period)
        self._server = None
        logger.info("gRPC OTLP receiver stopped")

    def wait_for_termination(self, timeout: Optional[float] = None) -> bool:
        """Block until the server terminates.

        Args:
            timeout: Maximum time to wait (seconds), None for indefinite.

        Returns:
            True if the server terminated, False if timeout occurred.
        """
        if self._server is None:
            return True
        return self._server.wait_for_termination(timeout=timeout)

    @property
    def endpoint(self) -> str:
        """Get the server endpoint."""
        return self._endpoint

    @property
    def is_running(self) -> bool:
        """Check if the server is running."""
        return self._server is not None
