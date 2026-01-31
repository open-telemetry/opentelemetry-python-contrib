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

"""ClickHouse span exporter for GenAI instrumentation."""

import logging
from typing import Any, Sequence

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from opentelemetry.exporter.clickhouse_genai.config import ClickHouseGenAIConfig
from opentelemetry.exporter.clickhouse_genai.connection import ClickHouseConnection
from opentelemetry.exporter.clickhouse_genai.utils import (
    extract_genai_attributes,
    extract_resource_attributes,
    format_span_id_fixed,
    format_trace_id_fixed,
    ns_to_datetime,
    safe_json_dumps,
)

logger = logging.getLogger(__name__)


class ClickHouseGenAISpanExporter(SpanExporter):
    """ClickHouse span exporter optimized for GenAI traces.

    This exporter sends OpenTelemetry spans to ClickHouse with a schema
    specifically designed for LLM/GenAI observability. It extracts GenAI-specific
    attributes into dedicated columns for fast querying.

    Example usage:
        >>> from opentelemetry import trace
        >>> from opentelemetry.sdk.trace import TracerProvider
        >>> from opentelemetry.sdk.trace.export import BatchSpanProcessor
        >>> from opentelemetry.exporter.clickhouse_genai import (
        ...     ClickHouseGenAISpanExporter,
        ...     ClickHouseGenAIConfig,
        ... )
        >>>
        >>> config = ClickHouseGenAIConfig(
        ...     endpoint="localhost:9000",
        ...     database="otel_genai",
        ... )
        >>> exporter = ClickHouseGenAISpanExporter(config)
        >>> provider = TracerProvider()
        >>> provider.add_span_processor(BatchSpanProcessor(exporter))
        >>> trace.set_tracer_provider(provider)
    """

    def __init__(self, config: ClickHouseGenAIConfig):
        """Initialize ClickHouse span exporter.

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
                self._connection.create_traces_table()
                logger.info("ClickHouse GenAI traces schema initialized")
            except Exception as e:
                logger.error("Failed to initialize schema: %s", e)
                raise

        self._initialized = True

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Export spans to ClickHouse.

        Args:
            spans: Sequence of spans to export.

        Returns:
            SpanExportResult indicating success or failure.
        """
        if not spans:
            return SpanExportResult.SUCCESS

        try:
            self._ensure_initialized()
            rows = [self._span_to_row(span) for span in spans]
            self._connection.insert_traces(rows)
            logger.debug("Exported %d spans to ClickHouse", len(spans))
            return SpanExportResult.SUCCESS
        except Exception as e:
            logger.error("Failed to export spans: %s", e)
            return SpanExportResult.FAILURE

    def _span_to_row(self, span: ReadableSpan) -> dict[str, Any]:
        """Convert OTel span to ClickHouse row.

        Args:
            span: OpenTelemetry span.

        Returns:
            Dictionary representing a ClickHouse row.
        """
        # Make a copy of attributes to extract from
        attrs = dict(span.attributes or {})

        # Extract resource attributes
        resource_attrs = dict(span.resource.attributes) if span.resource else {}
        resource_fields = extract_resource_attributes(resource_attrs)

        # Extract GenAI-specific attributes
        genai_fields = extract_genai_attributes(attrs)

        # Build the row
        row = {
            # Identifiers
            "TraceId": format_trace_id_fixed(span.context.trace_id),
            "SpanId": format_span_id_fixed(span.context.span_id),
            "ParentSpanId": (
                format_span_id_fixed(span.parent.span_id)
                if span.parent
                else "0" * 16
            ),
            "TraceState": str(span.context.trace_state) if span.context.trace_state else "",
            # Timing
            "Timestamp": ns_to_datetime(span.start_time or 0),
            "EndTimestamp": ns_to_datetime(span.end_time or 0),
            "DurationNs": (
                (span.end_time - span.start_time)
                if span.end_time and span.start_time
                else 0
            ),
            # Span info
            "SpanName": span.name,
            "SpanKind": span.kind.name if span.kind else "INTERNAL",
            "StatusCode": (
                span.status.status_code.name
                if span.status and span.status.status_code
                else "UNSET"
            ),
            "StatusMessage": span.status.description if span.status else "",
            "InstrumentationScopeName": (
                span.instrumentation_scope.name
                if span.instrumentation_scope
                else ""
            ),
            "InstrumentationScopeVersion": (
                span.instrumentation_scope.version
                if span.instrumentation_scope
                else ""
            ),
            # Events
            "Events.Timestamp": [
                ns_to_datetime(e.timestamp or 0) for e in (span.events or [])
            ],
            "Events.Name": [e.name for e in (span.events or [])],
            "Events.Attributes": [
                safe_json_dumps(dict(e.attributes) if e.attributes else {})
                for e in (span.events or [])
            ],
            "EventCount": len(span.events or []),
            # Links
            "Links.TraceId": [
                format_trace_id_fixed(link.context.trace_id)
                for link in (span.links or [])
            ],
            "Links.SpanId": [
                format_span_id_fixed(link.context.span_id)
                for link in (span.links or [])
            ],
            "Links.TraceState": [
                str(link.context.trace_state) if link.context.trace_state else ""
                for link in (span.links or [])
            ],
            "Links.Attributes": [
                safe_json_dumps(dict(link.attributes) if link.attributes else {})
                for link in (span.links or [])
            ],
            # Overflow attributes (remaining after extraction)
            "SpanAttributesJson": safe_json_dumps(attrs),
            "ResourceAttributesJson": safe_json_dumps(resource_attrs),
        }

        # Merge resource and GenAI fields
        row.update(resource_fields)
        row.update(genai_fields)

        return row

    def shutdown(self, timeout_millis: float = 30_000) -> None:
        """Shutdown the exporter.

        Args:
            timeout_millis: Timeout in milliseconds.
        """
        self._connection.close()
        logger.debug("ClickHouse span exporter shutdown")

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        """Force flush any pending exports.

        Args:
            timeout_millis: Timeout in milliseconds.

        Returns:
            True if flush succeeded.
        """
        # Native protocol inserts are synchronous, nothing to flush
        return True
