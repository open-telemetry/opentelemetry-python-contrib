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

"""HTTP OTLP receiver for ClickHouse Collector."""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from aiohttp import web
from google.protobuf.json_format import Parse

from opentelemetry.exporter.clickhouse_genai.processors.transform import (
    otlp_logs_to_rows,
    otlp_metrics_to_rows,
    otlp_spans_to_rows,
)
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)

logger = logging.getLogger(__name__)


class OTLPHttpReceiver:
    """HTTP OTLP receiver using aiohttp.

    This receiver listens on the standard OTLP HTTP port (4318) and forwards
    received telemetry data to the provided callback functions.

    Supports both protobuf (application/x-protobuf) and JSON (application/json)
    content types.
    """

    def __init__(
        self,
        endpoint: str = "0.0.0.0:4318",
        on_traces: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
        on_logs: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
        on_metrics: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
    ):
        """Initialize the HTTP OTLP receiver.

        Args:
            endpoint: Server endpoint (host:port).
            on_traces: Callback for trace rows.
            on_logs: Callback for log rows.
            on_metrics: Callback for metric rows.
        """
        self._endpoint = endpoint
        self._on_traces = on_traces or (lambda x: None)
        self._on_logs = on_logs or (lambda x: None)
        self._on_metrics = on_metrics or (lambda x: None)
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

    async def start(self) -> None:
        """Start the HTTP server."""
        if self._app is not None:
            logger.warning("HTTP receiver already running")
            return

        self._app = web.Application(
            client_max_size=64 * 1024 * 1024,  # 64MB max request size
        )

        # Add OTLP endpoints
        self._app.router.add_post("/v1/traces", self._handle_traces)
        self._app.router.add_post("/v1/logs", self._handle_logs)
        self._app.router.add_post("/v1/metrics", self._handle_metrics)

        # Add health check endpoint
        self._app.router.add_get("/health", self._handle_health)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        # Parse endpoint
        host, port = self._parse_endpoint(self._endpoint)
        self._site = web.TCPSite(self._runner, host, port)
        await self._site.start()

        logger.info("HTTP OTLP receiver started on %s", self._endpoint)

    async def stop(self) -> None:
        """Stop the HTTP server."""
        if self._runner is None:
            return

        logger.info("Stopping HTTP OTLP receiver...")
        await self._runner.cleanup()
        self._app = None
        self._runner = None
        self._site = None
        logger.info("HTTP OTLP receiver stopped")

    def _parse_endpoint(self, endpoint: str) -> tuple:
        """Parse host:port endpoint string.

        Args:
            endpoint: Endpoint string.

        Returns:
            Tuple of (host, port).
        """
        if ":" in endpoint:
            host, port_str = endpoint.rsplit(":", 1)
            return host, int(port_str)
        return endpoint, 4318

    async def _handle_traces(self, request: web.Request) -> web.Response:
        """Handle POST /v1/traces.

        Args:
            request: HTTP request.

        Returns:
            HTTP response.
        """
        try:
            export_request = await self._parse_request(
                request, ExportTraceServiceRequest
            )
            rows = otlp_spans_to_rows(export_request)
            if rows:
                self._on_traces(rows)
            logger.debug("Received %d spans via HTTP", len(rows))
            return web.Response(
                status=200, content_type="application/json", text="{}"
            )
        except web.HTTPException:
            raise
        except Exception as e:
            logger.error("Error processing trace export: %s", e)
            return web.Response(status=500, text=str(e))

    async def _handle_logs(self, request: web.Request) -> web.Response:
        """Handle POST /v1/logs.

        Args:
            request: HTTP request.

        Returns:
            HTTP response.
        """
        try:
            export_request = await self._parse_request(
                request, ExportLogsServiceRequest
            )
            rows = otlp_logs_to_rows(export_request)
            if rows:
                self._on_logs(rows)
            logger.debug("Received %d log records via HTTP", len(rows))
            return web.Response(
                status=200, content_type="application/json", text="{}"
            )
        except web.HTTPException:
            raise
        except Exception as e:
            logger.error("Error processing logs export: %s", e)
            return web.Response(status=500, text=str(e))

    async def _handle_metrics(self, request: web.Request) -> web.Response:
        """Handle POST /v1/metrics.

        Args:
            request: HTTP request.

        Returns:
            HTTP response.
        """
        try:
            export_request = await self._parse_request(
                request, ExportMetricsServiceRequest
            )
            rows = otlp_metrics_to_rows(export_request)
            if rows:
                self._on_metrics(rows)
            logger.debug("Received %d metric data points via HTTP", len(rows))
            return web.Response(
                status=200, content_type="application/json", text="{}"
            )
        except web.HTTPException:
            raise
        except Exception as e:
            logger.error("Error processing metrics export: %s", e)
            return web.Response(status=500, text=str(e))

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Handle GET /health.

        Args:
            request: HTTP request.

        Returns:
            HTTP response.
        """
        return web.Response(
            status=200,
            content_type="application/json",
            text='{"status": "healthy"}',
        )

    async def _parse_request(
        self, request: web.Request, message_class: type
    ) -> Any:
        """Parse OTLP request from HTTP body.

        Supports both protobuf and JSON content types.

        Args:
            request: HTTP request.
            message_class: Protobuf message class to parse into.

        Returns:
            Parsed protobuf message.

        Raises:
            web.HTTPUnsupportedMediaType: If content type is not supported.
        """
        content_type = request.headers.get("Content-Type", "")
        body = await request.read()

        if "application/x-protobuf" in content_type:
            # Parse protobuf
            message = message_class()
            message.ParseFromString(body)
            return message
        elif "application/json" in content_type:
            # Parse JSON using protobuf JSON format
            return Parse(body, message_class())
        else:
            # Default to protobuf for backwards compatibility
            try:
                message = message_class()
                message.ParseFromString(body)
                return message
            except Exception:
                raise web.HTTPUnsupportedMediaType(
                    text=f"Unsupported Content-Type: {content_type}. "
                    "Expected application/x-protobuf or application/json"
                )

    @property
    def endpoint(self) -> str:
        """Get the server endpoint."""
        return self._endpoint

    @property
    def is_running(self) -> bool:
        """Check if the server is running."""
        return self._app is not None


def run_http_receiver_sync(
    endpoint: str = "0.0.0.0:4318",
    on_traces: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
    on_logs: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
    on_metrics: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
) -> OTLPHttpReceiver:
    """Helper to run HTTP receiver in sync context.

    Creates an event loop and runs the receiver. Useful for testing.

    Args:
        endpoint: Server endpoint.
        on_traces: Callback for trace rows.
        on_logs: Callback for log rows.
        on_metrics: Callback for metric rows.

    Returns:
        Running OTLPHttpReceiver instance.
    """
    receiver = OTLPHttpReceiver(
        endpoint=endpoint,
        on_traces=on_traces,
        on_logs=on_logs,
        on_metrics=on_metrics,
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(receiver.start())

    return receiver
