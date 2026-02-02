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

"""OTLP Collector with ClickHouse export."""

import asyncio
import logging
import threading
from typing import Any, Dict, List, Optional

from opentelemetry.exporter.clickhouse_genai.config import CollectorConfig
from opentelemetry.exporter.clickhouse_genai.connection import (
    ClickHouseConnection,
)
from opentelemetry.exporter.clickhouse_genai.processors.batch_processor import (
    BatchProcessor,
)
from opentelemetry.exporter.clickhouse_genai.receivers.grpc_receiver import (
    OTLPGrpcReceiver,
)
from opentelemetry.exporter.clickhouse_genai.receivers.http_receiver import (
    OTLPHttpReceiver,
)
from opentelemetry.exporter.clickhouse_genai.schema import (
    GENAI_SPANS_COLUMNS,
    SPANS_COLUMNS,
)

logger = logging.getLogger(__name__)


class OTLPClickHouseCollector:
    """OTLP Collector that receives telemetry and exports to ClickHouse.

    This collector runs as a standalone service that:
    - Receives traces, logs, and metrics via gRPC and HTTP OTLP endpoints
    - Batches incoming data for efficient ClickHouse insertion
    - Uses the same schema as the direct SDK exporters

    Example usage:
        config = CollectorConfig(
            grpc_endpoint="0.0.0.0:4317",
            http_endpoint="0.0.0.0:4318",
            endpoint="localhost:9000",
            database="otel_genai",
        )
        collector = OTLPClickHouseCollector(config)
        collector.start()
        # ... collector is now running ...
        collector.stop()
    """

    def __init__(self, config: CollectorConfig):
        """Initialize the OTLP ClickHouse Collector.

        Args:
            config: Collector configuration.
        """
        self.config = config
        self._connection = ClickHouseConnection(config)

        # Initialize batch processors
        self._trace_processor = BatchProcessor(
            export_fn=self._export_traces,
            batch_size=config.batch_size,
            timeout_ms=config.batch_timeout_ms,
            max_queue_size=config.max_queue_size,
        )
        self._log_processor = BatchProcessor(
            export_fn=self._export_logs,
            batch_size=config.batch_size,
            timeout_ms=config.batch_timeout_ms,
            max_queue_size=config.max_queue_size,
        )
        self._metric_processor = BatchProcessor(
            export_fn=self._export_metrics,
            batch_size=config.batch_size,
            timeout_ms=config.batch_timeout_ms,
            max_queue_size=config.max_queue_size,
        )

        # Initialize receivers
        self._grpc_receiver: Optional[OTLPGrpcReceiver] = None
        self._http_receiver: Optional[OTLPHttpReceiver] = None

        if config.enable_grpc:
            self._grpc_receiver = OTLPGrpcReceiver(
                endpoint=config.grpc_endpoint,
                on_traces=self._trace_processor.enqueue,
                on_logs=self._log_processor.enqueue,
                on_metrics=self._metric_processor.enqueue,
                max_workers=config.grpc_max_workers,
            )

        if config.enable_http:
            self._http_receiver = OTLPHttpReceiver(
                endpoint=config.http_endpoint,
                on_traces=self._trace_processor.enqueue,
                on_logs=self._log_processor.enqueue,
                on_metrics=self._metric_processor.enqueue,
            )

        self._running = False
        self._http_loop: Optional[asyncio.AbstractEventLoop] = None
        self._http_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the collector.

        This method:
        1. Creates ClickHouse schema if configured
        2. Starts batch processors
        3. Starts gRPC and HTTP receivers
        """
        if self._running:
            logger.warning("Collector already running")
            return

        logger.info("Starting OTLP ClickHouse Collector...")

        # Ensure ClickHouse schema
        if self.config.create_schema:
            logger.info("Creating ClickHouse schema...")
            self._connection.ensure_database()
            self._connection.create_all_tables()
            logger.info("ClickHouse schema created (all 7 tables)")

        # Start batch processors
        self._trace_processor.start()
        self._log_processor.start()
        self._metric_processor.start()
        logger.info("Batch processors started")

        # Start gRPC receiver
        if self._grpc_receiver:
            self._grpc_receiver.start()

        # Start HTTP receiver in separate thread with its own event loop
        if self._http_receiver:
            self._http_thread = threading.Thread(
                target=self._run_http_receiver,
                name="HTTPReceiver-Thread",
                daemon=True,
            )
            self._http_thread.start()

        self._running = True
        logger.info(
            "OTLP ClickHouse Collector started (gRPC=%s, HTTP=%s)",
            self.config.grpc_endpoint if self._grpc_receiver else "disabled",
            self.config.http_endpoint if self._http_receiver else "disabled",
        )

    def _run_http_receiver(self) -> None:
        """Run HTTP receiver in separate thread."""
        self._http_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._http_loop)

        try:
            self._http_loop.run_until_complete(self._http_receiver.start())
            self._http_loop.run_forever()
        except Exception as e:
            logger.error("HTTP receiver error: %s", e)
        finally:
            self._http_loop.close()

    def stop(self, timeout: float = 10.0) -> None:
        """Stop the collector gracefully.

        Args:
            timeout: Maximum time to wait for graceful shutdown (seconds).
        """
        if not self._running:
            return

        logger.info("Stopping OTLP ClickHouse Collector...")

        # Stop receivers first to stop accepting new data
        if self._grpc_receiver:
            self._grpc_receiver.stop(grace_period=timeout / 2)

        if self._http_receiver and self._http_loop:
            # Schedule HTTP receiver stop in its event loop
            asyncio.run_coroutine_threadsafe(
                self._http_receiver.stop(),
                self._http_loop,
            )
            self._http_loop.call_soon_threadsafe(self._http_loop.stop)

            if self._http_thread:
                self._http_thread.join(timeout=timeout / 2)

        # Stop batch processors (this will flush remaining data)
        self._trace_processor.stop(timeout=timeout / 2)
        self._log_processor.stop(timeout=timeout / 2)
        self._metric_processor.stop(timeout=timeout / 2)

        # Close ClickHouse connection
        self._connection.close()

        self._running = False
        logger.info("OTLP ClickHouse Collector stopped")

    def _export_traces(self, rows: List[Dict[str, Any]]) -> None:
        """Export trace rows to ClickHouse with smart routing.

        Routes spans to appropriate tables based on their SpanCategory:
        - genai_spans: Rows with SpanCategory='genai' or Provider/OperationType set
        - spans: All other rows (db, http, messaging, rpc, other)

        Args:
            rows: List of trace row dictionaries.
        """
        if not rows:
            return

        try:
            # Classify rows based on SpanCategory
            genai_rows = []
            span_rows = []

            for row in rows:
                span_category = row.get("SpanCategory", "")
                # Route GenAI spans to genai_spans table
                if span_category == "genai" or row.get("Provider") or row.get("OperationType"):
                    genai_rows.append(row)
                # Route infrastructure spans to spans table
                elif span_category in ("db", "http", "messaging", "rpc", "faas"):
                    span_rows.append(row)
                # Default: check for category-specific indicators
                elif row.get("DbSystem") or row.get("HttpMethod") or row.get("MessagingSystem") or row.get("RpcSystem"):
                    span_rows.append(row)
                else:
                    # Default to spans table for unknown categories (more generic schema)
                    span_rows.append(row)

            if genai_rows:
                # Filter rows to only include genai_spans table columns
                filtered_genai_rows = [
                    {k: v for k, v in row.items() if k in GENAI_SPANS_COLUMNS}
                    for row in genai_rows
                ]
                self._connection.insert_genai_spans(filtered_genai_rows)
                logger.debug("Exported %d GenAI spans", len(filtered_genai_rows))

            if span_rows:
                # Filter rows to only include spans table columns
                filtered_span_rows = [
                    {k: v for k, v in row.items() if k in SPANS_COLUMNS}
                    for row in span_rows
                ]
                self._connection.insert_spans(filtered_span_rows)
                logger.debug("Exported %d general spans", len(filtered_span_rows))

        except Exception as e:
            logger.error("Failed to export traces to ClickHouse: %s", e)
            raise

    def _export_logs(self, rows: List[Dict[str, Any]]) -> None:
        """Export log rows to ClickHouse.

        Args:
            rows: List of log row dictionaries.
        """
        try:
            self._connection.insert_logs(rows)
        except Exception as e:
            logger.error("Failed to export logs to ClickHouse: %s", e)
            raise

    def _export_metrics(self, rows: List[Dict[str, Any]]) -> None:
        """Export metric rows to ClickHouse.

        Args:
            rows: List of metric row dictionaries.
        """
        try:
            self._connection.insert_metrics(rows)
        except Exception as e:
            logger.error("Failed to export metrics to ClickHouse: %s", e)
            raise

    def wait_for_termination(self, timeout: Optional[float] = None) -> bool:
        """Block until the collector terminates.

        Useful for keeping the main thread alive while the collector runs.

        Args:
            timeout: Maximum time to wait (seconds), None for indefinite.

        Returns:
            True if the collector terminated, False if timeout occurred.
        """
        if self._grpc_receiver:
            return self._grpc_receiver.wait_for_termination(timeout=timeout)
        elif self._http_thread:
            self._http_thread.join(timeout=timeout)
            return not self._http_thread.is_alive()
        return True

    @property
    def is_running(self) -> bool:
        """Check if the collector is running."""
        return self._running

    @property
    def stats(self) -> Dict[str, Any]:
        """Get collector statistics.

        Returns:
            Dictionary with processor and receiver stats.
        """
        return {
            "running": self._running,
            "traces": self._trace_processor.stats,
            "logs": self._log_processor.stats,
            "metrics": self._metric_processor.stats,
            "grpc_enabled": self._grpc_receiver is not None,
            "http_enabled": self._http_receiver is not None,
        }
