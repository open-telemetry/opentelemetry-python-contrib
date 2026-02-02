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

"""Transform OTLP protobuf messages to ClickHouse row format."""

from datetime import datetime
from typing import Any, Dict, List

from opentelemetry.exporter.clickhouse_genai.extractors import (
    extract_agent_attributes,
    extract_db_attributes,
    extract_error_attributes,
    extract_genai_attributes,
    extract_http_attributes,
    extract_messaging_attributes,
    extract_network_attributes,
    extract_resource_attributes,
    extract_rpc_attributes,
    extract_session_attributes,
)
from opentelemetry.exporter.clickhouse_genai.utils import (
    extract_log_genai_attributes,
    extract_metric_genai_attributes,
    safe_json_dumps,
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
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.metrics.v1.metrics_pb2 import (
    Metric,
)
from opentelemetry.proto.resource.v1.resource_pb2 import Resource


def _ensure_int(value: Any, default: int = 0) -> int:
    """Ensure value is an integer."""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _ensure_str(value: Any, default: str = "") -> str:
    """Ensure value is a string."""
    if value is None:
        return default
    return str(value)


def _get_any_value(value: AnyValue) -> Any:
    """Extract Python value from OTLP AnyValue protobuf.

    Args:
        value: OTLP AnyValue message.

    Returns:
        Extracted Python value.
    """
    if value.HasField("string_value"):
        return value.string_value
    elif value.HasField("int_value"):
        return value.int_value
    elif value.HasField("double_value"):
        return value.double_value
    elif value.HasField("bool_value"):
        return value.bool_value
    elif value.HasField("bytes_value"):
        return value.bytes_value.decode("utf-8", errors="replace")
    elif value.HasField("array_value"):
        return [_get_any_value(v) for v in value.array_value.values]
    elif value.HasField("kvlist_value"):
        return {
            kv.key: _get_any_value(kv.value)
            for kv in value.kvlist_value.values
        }
    return None


def _kvlist_to_dict(kvlist: List[KeyValue]) -> Dict[str, Any]:
    """Convert list of KeyValue protobuf messages to dict.

    Args:
        kvlist: List of KeyValue messages.

    Returns:
        Dictionary of key-value pairs.
    """
    return {kv.key: _get_any_value(kv.value) for kv in kvlist}


def _nanos_to_datetime(nanos: int) -> datetime:
    """Convert nanoseconds timestamp to datetime.

    Args:
        nanos: Timestamp in nanoseconds since epoch.

    Returns:
        datetime object.
    """
    if nanos <= 0:
        return datetime.fromtimestamp(0)
    return datetime.fromtimestamp(nanos / 1e9)


def _format_trace_id(trace_id: bytes) -> str:
    """Format trace ID bytes as 32-character hex string.

    Args:
        trace_id: 16-byte trace ID.

    Returns:
        32-character hex string.
    """
    if not trace_id or trace_id == b"\x00" * 16:
        return "0" * 32
    return trace_id.hex()


def _format_span_id(span_id: bytes) -> str:
    """Format span ID bytes as 16-character hex string.

    Args:
        span_id: 8-byte span ID.

    Returns:
        16-character hex string.
    """
    if not span_id or span_id == b"\x00" * 8:
        return "0" * 16
    return span_id.hex()


def _span_kind_to_string(kind: int) -> str:
    """Convert OTLP SpanKind enum to string.

    Args:
        kind: OTLP SpanKind value.

    Returns:
        String representation matching ClickHouse enum.
    """
    # OTLP SpanKind values:
    # 0 = UNSPECIFIED, 1 = INTERNAL, 2 = SERVER, 3 = CLIENT, 4 = PRODUCER, 5 = CONSUMER
    # ClickHouse enum: 'INTERNAL'=0, 'SERVER'=1, 'CLIENT'=2, 'PRODUCER'=3, 'CONSUMER'=4
    mapping = {
        0: "INTERNAL",  # Map UNSPECIFIED to INTERNAL
        1: "INTERNAL",
        2: "SERVER",
        3: "CLIENT",
        4: "PRODUCER",
        5: "CONSUMER",
    }
    return mapping.get(kind, "INTERNAL")


def _status_code_to_string(code: int) -> str:
    """Convert OTLP StatusCode enum to string.

    Args:
        code: OTLP StatusCode value.

    Returns:
        String representation.
    """
    mapping = {
        0: "UNSET",
        1: "OK",
        2: "ERROR",
    }
    return mapping.get(code, "UNSET")


def _extract_resource_attrs(resource: Resource) -> Dict[str, Any]:
    """Extract attributes from Resource protobuf.

    Args:
        resource: Resource protobuf message.

    Returns:
        Dictionary of resource attributes.
    """
    return _kvlist_to_dict(resource.attributes)


def otlp_spans_to_rows(
    request: ExportTraceServiceRequest,
) -> List[Dict[str, Any]]:
    """Convert OTLP ExportTraceServiceRequest to ClickHouse rows.

    Args:
        request: OTLP trace export request.

    Returns:
        List of row dictionaries for ClickHouse insertion.
    """
    rows = []

    for resource_spans in request.resource_spans:
        resource = resource_spans.resource
        resource_attrs = _extract_resource_attrs(resource)
        resource_fields = extract_resource_attributes(dict(resource_attrs))

        for scope_spans in resource_spans.scope_spans:
            scope = scope_spans.scope
            scope_name = scope.name if scope else ""

            for span in scope_spans.spans:
                # Extract span attributes (make a mutable copy)
                span_attrs = _kvlist_to_dict(span.attributes)

                # Extract structured fields using the new extractors
                genai_fields = extract_genai_attributes(span_attrs)
                session_fields = extract_session_attributes(span_attrs)
                agent_fields = extract_agent_attributes(span_attrs)
                error_fields = extract_error_attributes(span_attrs)
                network_fields = extract_network_attributes(span_attrs)

                # Extract category-specific fields for routing
                db_fields = extract_db_attributes(span_attrs)
                http_fields = extract_http_attributes(span_attrs)
                messaging_fields = extract_messaging_attributes(span_attrs)
                rpc_fields = extract_rpc_attributes(span_attrs)

                # Calculate duration in milliseconds
                duration_ns = span.end_time_unix_nano - span.start_time_unix_nano
                duration_ms = int(duration_ns / 1_000_000) if duration_ns > 0 else 0

                # Determine span category based on extracted fields
                span_category = ""
                if genai_fields.get("Provider") or genai_fields.get("OperationType"):
                    span_category = "genai"
                elif db_fields.get("DbSystem"):
                    span_category = "db"
                elif http_fields.get("HttpMethod"):
                    span_category = "http"
                elif messaging_fields.get("MessagingSystem"):
                    span_category = "messaging"
                elif rpc_fields.get("RpcSystem"):
                    span_category = "rpc"
                else:
                    span_category = "other"

                # Extract workflow fields before they get lost
                workflow_id = _ensure_str(span_attrs.pop("workflow.id", None) or span_attrs.pop("gen_ai.workflow.id", None))
                workflow_run_id = _ensure_str(span_attrs.pop("workflow.run_id", None) or span_attrs.pop("gen_ai.workflow.run_id", None))
                parent_agent_span_id = _ensure_str(span_attrs.pop("agent.parent_span_id", None) or span_attrs.pop("gen_ai.agent.parent_span_id", None))

                # Build row with all required fields (defaults match schema)
                # Use _ensure_int and _ensure_str for type safety
                row = {
                    # Identifiers
                    "TraceId": _format_trace_id(span.trace_id),
                    "SpanId": _format_span_id(span.span_id),
                    "ParentSpanId": _format_span_id(span.parent_span_id),
                    "TraceState": _ensure_str(span.trace_state),
                    # Session/Workflow context
                    "SessionId": _ensure_str(session_fields.get("SessionId")),
                    "WorkflowId": workflow_id,
                    "WorkflowRunId": workflow_run_id,
                    # Timing (milliseconds)
                    "Timestamp": _nanos_to_datetime(span.start_time_unix_nano),
                    "EndTimestamp": _nanos_to_datetime(span.end_time_unix_nano),
                    "DurationMs": _ensure_int(duration_ms),
                    # Span info
                    "SpanName": _ensure_str(span.name),
                    "SpanKind": _span_kind_to_string(span.kind),
                    "StatusCode": _status_code_to_string(span.status.code),
                    "StatusMessage": _ensure_str(span.status.message),
                    "InstrumentationScope": _ensure_str(scope_name),
                    # Span category (for routing)
                    "SpanCategory": _ensure_str(span_category),
                    # GenAI fields (with defaults for schema)
                    "OperationType": _ensure_str(genai_fields.get("OperationType")),
                    "Provider": _ensure_str(genai_fields.get("Provider")),
                    "RequestModel": _ensure_str(genai_fields.get("RequestModel")),
                    "ResponseModel": _ensure_str(genai_fields.get("ResponseModel")),
                    "ResponseId": _ensure_str(genai_fields.get("ResponseId")),
                    "InputTokens": _ensure_int(genai_fields.get("InputTokens")),
                    "OutputTokens": _ensure_int(genai_fields.get("OutputTokens")),
                    "TotalTokens": _ensure_int(genai_fields.get("TotalTokens")),
                    "EstimatedCostUsd": 0.0,  # Placeholder for cost tracking
                    "FinishReason": _ensure_str(genai_fields.get("FinishReason")),
                    "HasToolCalls": _ensure_int(genai_fields.get("HasToolCalls")),
                    "ToolCallCount": _ensure_int(genai_fields.get("ToolCallCount")),
                    "RequestContent": _ensure_str(genai_fields.get("RequestContent")),
                    "ResponseContent": _ensure_str(genai_fields.get("ResponseContent")),
                    "SystemPrompt": _ensure_str(genai_fields.get("SystemPrompt")),
                    "RequestParams": _ensure_str(genai_fields.get("RequestParams")) or "{}",
                    "ResponseMeta": _ensure_str(genai_fields.get("ResponseMeta")) or "{}",
                    "TokenDetails": _ensure_str(genai_fields.get("TokenDetails")) or "{}",
                    # Session/Agent context
                    "UserId": _ensure_str(session_fields.get("UserId")),
                    "TenantId": _ensure_str(session_fields.get("TenantId")),
                    "AgentName": _ensure_str(agent_fields.get("AgentName")),
                    "AgentType": _ensure_str(agent_fields.get("AgentType")),
                    "AgentStep": _ensure_int(agent_fields.get("AgentStep")),
                    "AgentIteration": _ensure_int(agent_fields.get("AgentIteration")),
                    "ParentAgentSpanId": parent_agent_span_id,
                    # Error tracking
                    "HasError": _ensure_int(error_fields.get("HasError")),
                    "ErrorType": _ensure_str(error_fields.get("ErrorType")),
                    "ErrorMessage": _ensure_str(error_fields.get("ErrorMessage")),
                    # Network fields (for spans table)
                    "NetPeerName": _ensure_str(network_fields.get("NetPeerName")),
                    "NetPeerPort": _ensure_int(network_fields.get("NetPeerPort")),
                    "NetTransport": _ensure_str(network_fields.get("NetTransport")),
                    "ServerAddress": _ensure_str(network_fields.get("ServerAddress")),
                    "ServerPort": _ensure_int(network_fields.get("ServerPort")),
                    # Category-specific fields (for spans table)
                    "DbSystem": _ensure_str(db_fields.get("DbSystem")),
                    "DbName": _ensure_str(db_fields.get("DbName")),
                    "DbStatement": _ensure_str(db_fields.get("DbStatement")),
                    "DbOperation": _ensure_str(db_fields.get("DbOperation")),
                    "DbUser": _ensure_str(db_fields.get("DbUser")),
                    "DbRedisDbIndex": _ensure_int(db_fields.get("DbRedisDbIndex")),
                    "DbMongoCollection": _ensure_str(db_fields.get("DbMongoCollection")),
                    "HttpMethod": _ensure_str(http_fields.get("HttpMethod")),
                    "HttpUrl": _ensure_str(http_fields.get("HttpUrl")),
                    "HttpRoute": _ensure_str(http_fields.get("HttpRoute")),
                    "HttpTarget": _ensure_str(http_fields.get("HttpTarget")),
                    "HttpStatusCode": _ensure_int(http_fields.get("HttpStatusCode")),
                    "HttpRequestBodySize": _ensure_int(http_fields.get("HttpRequestBodySize")),
                    "HttpResponseBodySize": _ensure_int(http_fields.get("HttpResponseBodySize")),
                    "HttpUserAgent": _ensure_str(http_fields.get("HttpUserAgent")),
                    "MessagingSystem": _ensure_str(messaging_fields.get("MessagingSystem")),
                    "MessagingDestination": _ensure_str(messaging_fields.get("MessagingDestination")),
                    "MessagingDestinationKind": _ensure_str(messaging_fields.get("MessagingDestinationKind")),
                    "MessagingOperation": _ensure_str(messaging_fields.get("MessagingOperation")),
                    "MessagingMessageId": _ensure_str(messaging_fields.get("MessagingMessageId")),
                    "MessagingKafkaPartition": _ensure_int(messaging_fields.get("MessagingKafkaPartition"), -1),
                    "MessagingKafkaOffset": _ensure_int(messaging_fields.get("MessagingKafkaOffset"), -1),
                    "MessagingKafkaConsumerGroup": _ensure_str(messaging_fields.get("MessagingKafkaConsumerGroup")),
                    "RpcSystem": _ensure_str(rpc_fields.get("RpcSystem")),
                    "RpcService": _ensure_str(rpc_fields.get("RpcService")),
                    "RpcMethod": _ensure_str(rpc_fields.get("RpcMethod")),
                    "RpcGrpcStatusCode": _ensure_int(rpc_fields.get("RpcGrpcStatusCode"), -1),
                    "CloudRegion": _ensure_str(rpc_fields.get("CloudRegion")),
                    "CloudProvider": _ensure_str(rpc_fields.get("CloudProvider")),
                    "AwsRequestId": _ensure_str(rpc_fields.get("AwsRequestId")),
                    # Service info
                    "ServiceName": _ensure_str(resource_fields.get("ServiceName")) or "unknown",
                    "ServiceVersion": _ensure_str(resource_fields.get("ServiceVersion")),
                    "DeploymentEnvironment": _ensure_str(resource_fields.get("DeploymentEnvironment")),
                    # Overflow attributes (remaining after extraction)
                    "SpanAttributes": safe_json_dumps(span_attrs),
                    "ResourceAttributes": safe_json_dumps(resource_attrs),
                    "Attributes": safe_json_dumps(span_attrs),  # Alias for spans table
                }
                rows.append(row)

    return rows


def otlp_logs_to_rows(
    request: ExportLogsServiceRequest,
) -> List[Dict[str, Any]]:
    """Convert OTLP ExportLogsServiceRequest to ClickHouse rows.

    Args:
        request: OTLP logs export request.

    Returns:
        List of row dictionaries for ClickHouse insertion.
    """
    rows = []

    for resource_logs in request.resource_logs:
        resource = resource_logs.resource
        resource_attrs = _extract_resource_attrs(resource)
        resource_fields = extract_resource_attributes(resource_attrs)

        for scope_logs in resource_logs.scope_logs:
            scope = scope_logs.scope
            scope_name = scope.name if scope else ""

            for log_record in scope_logs.log_records:
                # Extract log attributes
                log_attrs = _kvlist_to_dict(log_record.attributes)

                # Parse body
                body = _get_any_value(log_record.body)
                body_str = ""
                body_json = "{}"
                if isinstance(body, str):
                    body_str = body
                elif body is not None:
                    body_json = safe_json_dumps(body)

                # Extract GenAI-specific fields from body
                genai_fields = extract_log_genai_attributes(log_attrs, body)

                row = {
                    # Timing
                    "Timestamp": _nanos_to_datetime(log_record.time_unix_nano),
                    "ObservedTimestamp": _nanos_to_datetime(
                        log_record.observed_time_unix_nano
                    ),
                    # Trace context
                    "TraceId": _format_trace_id(log_record.trace_id),
                    "SpanId": _format_span_id(log_record.span_id),
                    "TraceFlags": log_record.flags,
                    # Service info
                    "ServiceName": resource_fields.get(
                        "ServiceName", "unknown"
                    ),
                    "ServiceVersion": resource_fields.get(
                        "ServiceVersion", ""
                    ),
                    "DeploymentEnvironment": resource_fields.get(
                        "DeploymentEnvironment", ""
                    ),
                    "InstrumentationScopeName": scope_name,
                    # Log record
                    "SeverityText": log_record.severity_text,
                    "SeverityNumber": log_record.severity_number,
                    # Body
                    "Body": body_str,
                    "BodyJson": body_json,
                    # Overflow attributes
                    "LogAttributesJson": safe_json_dumps(log_attrs),
                    "ResourceAttributesJson": safe_json_dumps(resource_attrs),
                    # GenAI fields
                    **genai_fields,
                }
                rows.append(row)

    return rows


def otlp_metrics_to_rows(
    request: ExportMetricsServiceRequest,
) -> List[Dict[str, Any]]:
    """Convert OTLP ExportMetricsServiceRequest to ClickHouse rows.

    Args:
        request: OTLP metrics export request.

    Returns:
        List of row dictionaries for ClickHouse insertion.
    """
    rows = []

    for resource_metrics in request.resource_metrics:
        resource = resource_metrics.resource
        resource_attrs = _extract_resource_attrs(resource)
        resource_fields = extract_resource_attributes(resource_attrs)

        for scope_metrics in resource_metrics.scope_metrics:
            scope = scope_metrics.scope
            scope_name = scope.name if scope else ""
            scope_version = scope.version if scope else ""

            for metric in scope_metrics.metrics:
                rows.extend(
                    _process_metric(
                        metric,
                        resource_fields,
                        resource_attrs,
                        scope_name,
                        scope_version,
                    )
                )

    return rows


def _process_metric(
    metric: Metric,
    resource_fields: Dict[str, Any],
    resource_attrs: Dict[str, Any],
    scope_name: str,
    scope_version: str,
) -> List[Dict[str, Any]]:
    """Process a single OTLP Metric into ClickHouse rows.

    Args:
        metric: OTLP Metric message.
        resource_fields: Extracted resource fields.
        resource_attrs: Raw resource attributes.
        scope_name: Instrumentation scope name.
        scope_version: Instrumentation scope version.

    Returns:
        List of row dictionaries.
    """
    rows = []
    base_row = {
        "MetricName": metric.name,
        "MetricDescription": metric.description,
        "MetricUnit": metric.unit,
        "InstrumentationScopeName": scope_name,
        "InstrumentationScopeVersion": scope_version,
        "ResourceAttributesJson": safe_json_dumps(resource_attrs),
        **resource_fields,
    }

    # Handle different metric types
    if metric.HasField("gauge"):
        for point in metric.gauge.data_points:
            row = _create_metric_row(
                base_row, point, "gauge", is_monotonic=False, temporality=""
            )
            rows.append(row)

    elif metric.HasField("sum"):
        temporality = _aggregation_temporality_to_string(
            metric.sum.aggregation_temporality
        )
        for point in metric.sum.data_points:
            row = _create_metric_row(
                base_row,
                point,
                "sum",
                is_monotonic=metric.sum.is_monotonic,
                temporality=temporality,
            )
            rows.append(row)

    elif metric.HasField("histogram"):
        temporality = _aggregation_temporality_to_string(
            metric.histogram.aggregation_temporality
        )
        for point in metric.histogram.data_points:
            row = _create_histogram_row(base_row, point, temporality)
            rows.append(row)

    elif metric.HasField("summary"):
        for point in metric.summary.data_points:
            row = _create_summary_row(base_row, point)
            rows.append(row)

    return rows


def _aggregation_temporality_to_string(temporality: int) -> str:
    """Convert AggregationTemporality enum to string.

    Args:
        temporality: AggregationTemporality value.

    Returns:
        String representation.
    """
    mapping = {
        0: "UNSPECIFIED",
        1: "DELTA",
        2: "CUMULATIVE",
    }
    return mapping.get(temporality, "UNSPECIFIED")


def _create_metric_row(
    base_row: Dict[str, Any],
    point: Any,
    metric_type: str,
    is_monotonic: bool,
    temporality: str,
) -> Dict[str, Any]:
    """Create a row for gauge or sum metric data point.

    Args:
        base_row: Base row with common fields.
        point: NumberDataPoint protobuf.
        metric_type: "gauge" or "sum".
        is_monotonic: Whether the metric is monotonic.
        temporality: Aggregation temporality string.

    Returns:
        Row dictionary.
    """
    attrs = _kvlist_to_dict(point.attributes)
    genai_fields = extract_metric_genai_attributes(attrs)

    row = {
        **base_row,
        "Timestamp": _nanos_to_datetime(point.time_unix_nano),
        "StartTimeUnixNano": point.start_time_unix_nano,
        "EndTimeUnixNano": point.time_unix_nano,
        "MetricType": metric_type,
        "IsMonotonic": 1 if is_monotonic else 0,
        "AggregationTemporality": temporality,
        "AttributesJson": safe_json_dumps(attrs),
        # Histogram fields with defaults for non-histogram metrics
        "HistogramCount": 0,
        "HistogramSum": 0.0,
        "HistogramMin": 0.0,
        "HistogramMax": 0.0,
        "BucketCounts": [],
        "ExplicitBounds": [],
        **genai_fields,
    }

    # Set value based on type
    if point.HasField("as_double"):
        row["Value"] = point.as_double
        row["IntValue"] = 0
    else:
        row["Value"] = 0.0
        row["IntValue"] = point.as_int

    # Process exemplars
    exemplar_trace_ids = []
    exemplar_span_ids = []
    exemplar_values = []
    exemplar_timestamps = []
    for exemplar in point.exemplars:
        exemplar_trace_ids.append(_format_trace_id(exemplar.trace_id))
        exemplar_span_ids.append(_format_span_id(exemplar.span_id))
        if exemplar.HasField("as_double"):
            exemplar_values.append(exemplar.as_double)
        else:
            exemplar_values.append(float(exemplar.as_int))
        exemplar_timestamps.append(_nanos_to_datetime(exemplar.time_unix_nano))

    row["Exemplars.TraceId"] = exemplar_trace_ids
    row["Exemplars.SpanId"] = exemplar_span_ids
    row["Exemplars.Value"] = exemplar_values
    row["Exemplars.Timestamp"] = exemplar_timestamps

    return row


def _create_histogram_row(
    base_row: Dict[str, Any],
    point: Any,
    temporality: str,
) -> Dict[str, Any]:
    """Create a row for histogram data point.

    Args:
        base_row: Base row with common fields.
        point: HistogramDataPoint protobuf.
        temporality: Aggregation temporality string.

    Returns:
        Row dictionary.
    """
    attrs = _kvlist_to_dict(point.attributes)
    genai_fields = extract_metric_genai_attributes(attrs)

    row = {
        **base_row,
        "Timestamp": _nanos_to_datetime(point.time_unix_nano),
        "StartTimeUnixNano": point.start_time_unix_nano,
        "EndTimeUnixNano": point.time_unix_nano,
        "MetricType": "histogram",
        "IsMonotonic": 0,
        "AggregationTemporality": temporality,
        "Value": 0.0,
        "IntValue": 0,
        "HistogramCount": point.count,
        "HistogramSum": point.sum if point.HasField("sum") else 0.0,
        "HistogramMin": point.min if point.HasField("min") else 0.0,
        "HistogramMax": point.max if point.HasField("max") else 0.0,
        "BucketCounts": list(point.bucket_counts),
        "ExplicitBounds": list(point.explicit_bounds),
        "AttributesJson": safe_json_dumps(attrs),
        **genai_fields,
    }

    # Process exemplars
    exemplar_trace_ids = []
    exemplar_span_ids = []
    exemplar_values = []
    exemplar_timestamps = []
    for exemplar in point.exemplars:
        exemplar_trace_ids.append(_format_trace_id(exemplar.trace_id))
        exemplar_span_ids.append(_format_span_id(exemplar.span_id))
        if exemplar.HasField("as_double"):
            exemplar_values.append(exemplar.as_double)
        else:
            exemplar_values.append(float(exemplar.as_int))
        exemplar_timestamps.append(_nanos_to_datetime(exemplar.time_unix_nano))

    row["Exemplars.TraceId"] = exemplar_trace_ids
    row["Exemplars.SpanId"] = exemplar_span_ids
    row["Exemplars.Value"] = exemplar_values
    row["Exemplars.Timestamp"] = exemplar_timestamps

    return row


def _create_summary_row(
    base_row: Dict[str, Any],
    point: Any,
) -> Dict[str, Any]:
    """Create a row for summary data point.

    Args:
        base_row: Base row with common fields.
        point: SummaryDataPoint protobuf.

    Returns:
        Row dictionary.
    """
    attrs = _kvlist_to_dict(point.attributes)
    genai_fields = extract_metric_genai_attributes(attrs)

    return {
        **base_row,
        "Timestamp": _nanos_to_datetime(point.time_unix_nano),
        "StartTimeUnixNano": point.start_time_unix_nano,
        "EndTimeUnixNano": point.time_unix_nano,
        "MetricType": "summary",
        "IsMonotonic": 0,
        "AggregationTemporality": "",
        "Value": 0.0,
        "IntValue": 0,
        "HistogramCount": point.count,
        "HistogramSum": point.sum,
        "HistogramMin": 0.0,
        "HistogramMax": 0.0,
        "BucketCounts": [],
        "ExplicitBounds": [],
        "Exemplars.TraceId": [],
        "Exemplars.SpanId": [],
        "Exemplars.Value": [],
        "Exemplars.Timestamp": [],
        "AttributesJson": safe_json_dumps(attrs),
        **genai_fields,
    }
