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

"""ClickHouse logs exporter for GenAI instrumentation."""

import logging
from typing import Any, Sequence

from opentelemetry.sdk._logs import LogData, LogRecord
from opentelemetry.sdk._logs.export import LogExporter, LogExportResult

from opentelemetry.exporter.clickhouse_genai.config import ClickHouseGenAIConfig
from opentelemetry.exporter.clickhouse_genai.connection import ClickHouseConnection
from opentelemetry.exporter.clickhouse_genai.utils import (
    extract_log_genai_attributes,
    extract_resource_attributes,
    format_span_id_fixed,
    format_trace_id_fixed,
    ns_to_datetime,
    safe_json_dumps,
)

logger = logging.getLogger(__name__)


class ClickHouseGenAILogsExporter(LogExporter):
    """ClickHouse logs exporter for GenAI log events.

    This exporter sends OpenTelemetry log records to ClickHouse with a schema
    optimized for GenAI observability, including structured fields for
    gen_ai.{role}.message and gen_ai.choice events.

    Example usage:
        >>> from opentelemetry.sdk._logs import LoggerProvider
        >>> from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        >>> from opentelemetry.exporter.clickhouse_genai import (
        ...     ClickHouseGenAILogsExporter,
        ...     ClickHouseGenAIConfig,
        ... )
        >>>
        >>> config = ClickHouseGenAIConfig(endpoint="localhost:9000")
        >>> exporter = ClickHouseGenAILogsExporter(config)
        >>> provider = LoggerProvider()
        >>> provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    """

    def __init__(self, config: ClickHouseGenAIConfig):
        """Initialize ClickHouse logs exporter.

        Args:
            config: ClickHouse configuration.
        """
        self.config = config
        self._connection = ClickHouseConnection(config)
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Ensure database and tables are created."""
        if self._initialized:
            return

        if self.config.create_schema:
            try:
                self._connection.ensure_database()
                self._connection.create_logs_table()
                logger.info("ClickHouse GenAI logs schema initialized")
            except Exception as e:
                logger.error("Failed to initialize logs schema: %s", e)
                raise

        self._initialized = True

    def export(self, batch: Sequence[LogData]) -> LogExportResult:
        """Export log records to ClickHouse.

        Args:
            batch: Sequence of log data to export.

        Returns:
            LogExportResult indicating success or failure.
        """
        if not batch:
            return LogExportResult.SUCCESS

        try:
            self._ensure_initialized()
            rows = [self._log_to_row(log_data) for log_data in batch]
            self._connection.insert_logs(rows)
            logger.debug("Exported %d log records to ClickHouse", len(batch))
            return LogExportResult.SUCCESS
        except Exception as e:
            logger.error("Failed to export logs: %s", e)
            return LogExportResult.FAILURE

    def _log_to_row(self, log_data: LogData) -> dict[str, Any]:
        """Convert OTel log record to ClickHouse row.

        Args:
            log_data: OpenTelemetry log data.

        Returns:
            Dictionary representing a ClickHouse row.
        """
        log_record = log_data.log_record

        # Make a copy of attributes to extract from
        attrs = dict(log_record.attributes) if log_record.attributes else {}

        # Extract resource attributes
        resource_attrs = (
            dict(log_data.resource.attributes) if log_data.resource else {}
        )
        resource_fields = extract_resource_attributes(resource_attrs)

        # Extract GenAI-specific attributes from log record
        body = log_record.body
        genai_fields = extract_log_genai_attributes(attrs, body)

        # Get event name from various sources
        event_name = genai_fields.get("EventName", "")
        if not event_name:
            # Try to get from instrumentation info
            event_name = getattr(log_record, "event_name", "") or ""

        row = {
            # Timing
            "Timestamp": ns_to_datetime(log_record.timestamp or 0),
            "ObservedTimestamp": ns_to_datetime(
                log_record.observed_timestamp or log_record.timestamp or 0
            ),
            # Trace context
            "TraceId": (
                format_trace_id_fixed(log_record.trace_id)
                if log_record.trace_id
                else "0" * 32
            ),
            "SpanId": (
                format_span_id_fixed(log_record.span_id)
                if log_record.span_id
                else "0" * 16
            ),
            "TraceFlags": log_record.trace_flags or 0,
            # Scope
            "InstrumentationScopeName": (
                log_data.instrumentation_scope.name
                if log_data.instrumentation_scope
                else ""
            ),
            # Log record
            "SeverityText": log_record.severity_text or "",
            "SeverityNumber": (
                log_record.severity_number.value
                if log_record.severity_number
                else 0
            ),
            # Event name
            "EventName": event_name,
            # Raw body
            "Body": str(body) if isinstance(body, str) else "",
            "BodyJson": safe_json_dumps(body) if isinstance(body, dict) else "{}",
            # Overflow
            "LogAttributesJson": safe_json_dumps(attrs),
            "ResourceAttributesJson": safe_json_dumps(resource_attrs),
        }

        # Add resource and GenAI fields
        row.update(resource_fields)
        row.update(genai_fields)

        return row

    def shutdown(self, timeout_millis: float = 30_000) -> None:
        """Shutdown the exporter.

        Args:
            timeout_millis: Timeout in milliseconds.
        """
        self._connection.close()
        logger.debug("ClickHouse logs exporter shutdown")

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        """Force flush any pending exports.

        Args:
            timeout_millis: Timeout in milliseconds.

        Returns:
            True if flush succeeded.
        """
        return True
