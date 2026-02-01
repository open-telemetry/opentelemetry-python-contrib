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

"""ClickHouse metrics exporter for GenAI instrumentation."""

import logging
from typing import Any

from opentelemetry.exporter.clickhouse_genai.config import (
    ClickHouseGenAIConfig,
)
from opentelemetry.exporter.clickhouse_genai.connection import (
    ClickHouseConnection,
)
from opentelemetry.exporter.clickhouse_genai.utils import (
    extract_metric_genai_attributes,
    extract_resource_attributes,
    format_span_id_fixed,
    format_trace_id_fixed,
    ns_to_datetime,
    safe_json_dumps,
)
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    Gauge,
    Histogram,
    MetricExporter,
    MetricExportResult,
    MetricsData,
    Sum,
)

logger = logging.getLogger(__name__)


class ClickHouseGenAIMetricsExporter(MetricExporter):
    """ClickHouse metrics exporter for GenAI metrics.

    This exporter sends OpenTelemetry metrics to ClickHouse with a schema
    optimized for GenAI observability, including token usage and operation
    duration metrics.

    Example usage:
        >>> from opentelemetry import metrics
        >>> from opentelemetry.sdk.metrics import MeterProvider
        >>> from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        >>> from opentelemetry.exporter.clickhouse_genai import (
        ...     ClickHouseGenAIMetricsExporter,
        ...     ClickHouseGenAIConfig,
        ... )
        >>>
        >>> config = ClickHouseGenAIConfig(endpoint="localhost:9000")
        >>> exporter = ClickHouseGenAIMetricsExporter(config)
        >>> reader = PeriodicExportingMetricReader(exporter)
        >>> provider = MeterProvider(metric_readers=[reader])
        >>> metrics.set_meter_provider(provider)
    """

    def __init__(
        self,
        config: ClickHouseGenAIConfig,
        preferred_temporality: dict[type, AggregationTemporality]
        | None = None,
        preferred_aggregation: dict | None = None,
    ):
        """Initialize ClickHouse metrics exporter.

        Args:
            config: ClickHouse configuration.
            preferred_temporality: Preferred temporality by instrument type.
            preferred_aggregation: Preferred aggregation by instrument type.
        """
        super().__init__(
            preferred_temporality=preferred_temporality,
            preferred_aggregation=preferred_aggregation,
        )
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
                self._connection.create_metrics_table()
                logger.info("ClickHouse GenAI metrics schema initialized")
            except Exception as e:
                logger.error("Failed to initialize metrics schema: %s", e)
                raise

        self._initialized = True

    def export(
        self,
        metrics_data: MetricsData,
        timeout_millis: float = 10_000,
        **kwargs,
    ) -> MetricExportResult:
        """Export metrics to ClickHouse.

        Args:
            metrics_data: Metrics data to export.
            timeout_millis: Timeout in milliseconds.

        Returns:
            MetricExportResult indicating success or failure.
        """
        if not metrics_data or not metrics_data.resource_metrics:
            return MetricExportResult.SUCCESS

        try:
            self._ensure_initialized()
            rows = []

            for resource_metrics in metrics_data.resource_metrics:
                resource_attrs = dict(resource_metrics.resource.attributes)
                resource_fields = extract_resource_attributes(resource_attrs)

                for scope_metrics in resource_metrics.scope_metrics:
                    scope_name = (
                        scope_metrics.scope.name if scope_metrics.scope else ""
                    )
                    scope_version = (
                        scope_metrics.scope.version
                        if scope_metrics.scope
                        else ""
                    )

                    for metric in scope_metrics.metrics:
                        metric_rows = self._metric_to_rows(
                            metric,
                            resource_fields,
                            resource_attrs,
                            scope_name,
                            scope_version,
                        )
                        rows.extend(metric_rows)

            if rows:
                self._connection.insert_metrics(rows)
                logger.debug(
                    "Exported %d metric rows to ClickHouse", len(rows)
                )

            return MetricExportResult.SUCCESS
        except Exception as e:
            logger.error("Failed to export metrics: %s", e)
            return MetricExportResult.FAILURE

    def _metric_to_rows(
        self,
        metric,
        resource_fields: dict[str, Any],
        resource_attrs: dict[str, Any],
        scope_name: str,
        scope_version: str,
    ) -> list[dict[str, Any]]:
        """Convert OTel metric to ClickHouse rows.

        Args:
            metric: OpenTelemetry metric.
            resource_fields: Extracted resource fields.
            resource_attrs: Original resource attributes.
            scope_name: Instrumentation scope name.
            scope_version: Instrumentation scope version.

        Returns:
            List of dictionaries representing ClickHouse rows.
        """
        rows = []
        metric_type = self._get_metric_type(metric.data)

        for data_point in metric.data.data_points:
            # Make a copy of attributes to extract from
            attrs = (
                dict(data_point.attributes) if data_point.attributes else {}
            )
            genai_fields = extract_metric_genai_attributes(attrs)

            row = {
                # Timing
                "Timestamp": ns_to_datetime(data_point.time_unix_nano),
                "StartTimeUnixNano": getattr(
                    data_point, "start_time_unix_nano", 0
                )
                or 0,
                "EndTimeUnixNano": data_point.time_unix_nano,
                # Metric identity
                "MetricName": metric.name,
                "MetricDescription": metric.description or "",
                "MetricUnit": metric.unit or "",
                "MetricType": metric_type,
                # Scope
                "InstrumentationScopeName": scope_name,
                "InstrumentationScopeVersion": scope_version,
                # Overflow
                "AttributesJson": safe_json_dumps(attrs),
                "ResourceAttributesJson": safe_json_dumps(resource_attrs),
            }

            # Add resource and GenAI fields
            row.update(resource_fields)
            row.update(genai_fields)

            # Handle different metric types
            if isinstance(metric.data, Gauge):
                row["Value"] = float(data_point.value)
                row["IntValue"] = (
                    int(data_point.value)
                    if isinstance(data_point.value, int)
                    else 0
                )
            elif isinstance(metric.data, Sum):
                row["Value"] = float(data_point.value)
                row["IntValue"] = (
                    int(data_point.value)
                    if isinstance(data_point.value, int)
                    else 0
                )
                row["IsMonotonic"] = 1 if metric.data.is_monotonic else 0
                row["AggregationTemporality"] = (
                    metric.data.aggregation_temporality.name
                )
            elif isinstance(metric.data, Histogram):
                row["HistogramCount"] = data_point.count
                row["HistogramSum"] = data_point.sum or 0
                row["HistogramMin"] = (
                    data_point.min if data_point.min is not None else 0
                )
                row["HistogramMax"] = (
                    data_point.max if data_point.max is not None else 0
                )
                row["BucketCounts"] = list(data_point.bucket_counts)
                row["ExplicitBounds"] = list(data_point.explicit_bounds)
                row["AggregationTemporality"] = (
                    metric.data.aggregation_temporality.name
                )

            # Handle exemplars if present
            exemplars = getattr(data_point, "exemplars", None)
            if exemplars:
                row["Exemplars.TraceId"] = [
                    format_trace_id_fixed(e.trace_id) for e in exemplars
                ]
                row["Exemplars.SpanId"] = [
                    format_span_id_fixed(e.span_id) for e in exemplars
                ]
                row["Exemplars.Value"] = [float(e.value) for e in exemplars]
                row["Exemplars.Timestamp"] = [
                    ns_to_datetime(e.time_unix_nano) for e in exemplars
                ]
            else:
                row["Exemplars.TraceId"] = []
                row["Exemplars.SpanId"] = []
                row["Exemplars.Value"] = []
                row["Exemplars.Timestamp"] = []

            rows.append(row)

        return rows

    def _get_metric_type(self, data) -> str:
        """Get metric type string.

        Args:
            data: Metric data object.

        Returns:
            Metric type string.
        """
        if isinstance(data, Gauge):
            return "GAUGE"
        elif isinstance(data, Sum):
            return "SUM"
        elif isinstance(data, Histogram):
            return "HISTOGRAM"
        return "UNKNOWN"

    def shutdown(self, timeout_millis: float = 30_000) -> None:
        """Shutdown the exporter.

        Args:
            timeout_millis: Timeout in milliseconds.
        """
        self._connection.close()
        logger.debug("ClickHouse metrics exporter shutdown")

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        """Force flush any pending exports.

        Args:
            timeout_millis: Timeout in milliseconds.

        Returns:
            True if flush succeeded.
        """
        return True
