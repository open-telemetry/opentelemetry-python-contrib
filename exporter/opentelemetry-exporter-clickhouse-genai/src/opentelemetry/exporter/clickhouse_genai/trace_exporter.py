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

"""ClickHouse span exporter for GenAI instrumentation.

Routes spans to appropriate tables based on semantic conventions:
- genai_spans: LLM/AI interactions (gen_ai.* attributes)
- spans: All other spans (db.*, http.*, messaging.*, rpc.*, etc.)
"""

import logging
from typing import Any, Sequence

from opentelemetry.exporter.clickhouse_genai.classifier import classify_span
from opentelemetry.exporter.clickhouse_genai.config import (
    ClickHouseGenAIConfig,
)
from opentelemetry.exporter.clickhouse_genai.connection import (
    ClickHouseConnection,
)
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
    format_span_id_fixed,
    format_trace_id_fixed,
    ns_to_datetime,
    safe_json_dumps,
)
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

logger = logging.getLogger(__name__)


class ClickHouseGenAISpanExporter(SpanExporter):
    """ClickHouse span exporter with smart routing for GenAI and infrastructure spans.

    This exporter classifies incoming spans based on OpenTelemetry semantic conventions
    and routes them to appropriate ClickHouse tables:

    - genai_spans: LLM/AI interactions (Provider, Model, Tokens, Content)
    - spans: All other spans (db.*, http.*, messaging.*, rpc.*)

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
                self._connection.create_all_tables()
                logger.info("ClickHouse GenAI schema initialized (all tables)")
            except Exception as e:
                logger.error("Failed to initialize schema: %s", e)
                raise

        self._initialized = True

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Export spans to ClickHouse with smart routing.

        Classifies each span and routes to the appropriate table:
        - genai_spans for LLM interactions
        - spans for database, HTTP, messaging, RPC operations

        Args:
            spans: Sequence of spans to export.

        Returns:
            SpanExportResult indicating success or failure.
        """
        if not spans:
            return SpanExportResult.SUCCESS

        try:
            self._ensure_initialized()

            # Classify and route spans
            genai_rows = []
            span_rows = []

            for span in spans:
                table, category = classify_span(span)

                if table == "genai_spans":
                    genai_rows.append(self._genai_span_to_row(span, category))
                else:
                    span_rows.append(self._span_to_row(span, category))

            # Batch insert to each table
            if genai_rows:
                self._connection.insert_genai_spans(genai_rows)
                logger.debug("Exported %d GenAI spans", len(genai_rows))

            if span_rows:
                self._connection.insert_spans(span_rows)
                logger.debug("Exported %d general spans", len(span_rows))

            return SpanExportResult.SUCCESS
        except Exception as e:
            logger.error("Failed to export spans: %s", e)
            return SpanExportResult.FAILURE

    def _genai_span_to_row(
        self, span: ReadableSpan, operation_type: str
    ) -> dict[str, Any]:
        """Convert OpenTelemetry span to genai_spans table row.

        Args:
            span: OpenTelemetry span.
            operation_type: GenAI operation type (chat, completion, embedding, etc.)

        Returns:
            Dictionary representing a ClickHouse row for genai_spans table.
        """
        # Make copies of attributes to extract from (destructive pops)
        attrs = dict(span.attributes or {})
        resource_attrs = dict(span.resource.attributes) if span.resource else {}

        # Extract structured attributes
        resource_fields = extract_resource_attributes(resource_attrs)
        genai_fields = extract_genai_attributes(attrs)
        agent_fields = extract_agent_attributes(attrs)
        session_fields = extract_session_attributes(attrs)
        error_fields = extract_error_attributes(attrs)

        # Calculate duration in milliseconds
        duration_ms = 0
        if span.end_time and span.start_time:
            duration_ms = int((span.end_time - span.start_time) / 1_000_000)

        # Map operation type to enum value
        op_type_map = {
            "chat": "chat",
            "completion": "completion",
            "text_completion": "completion",
            "embedding": "embedding",
            "embeddings": "embedding",
            "image": "image",
            "image_generation": "image",
            "audio": "audio",
            "speech": "audio",
            "transcription": "audio",
            "rerank": "rerank",
            "tool_call": "tool_call",
            "agent_step": "agent_step",
            "retrieval": "retrieval",
        }
        mapped_op_type = op_type_map.get(operation_type.lower(), "other")

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
            # Session/Workflow context
            "SessionId": session_fields.get("SessionId", ""),
            "WorkflowId": attrs.pop("workflow.id", "")
            or attrs.pop("gen_ai.workflow.id", ""),
            "WorkflowRunId": attrs.pop("workflow.run_id", "")
            or attrs.pop("gen_ai.workflow.run_id", ""),
            # Timing (milliseconds)
            "Timestamp": ns_to_datetime(span.start_time or 0),
            "EndTimestamp": ns_to_datetime(span.end_time or 0),
            "DurationMs": duration_ms,
            # Service info
            "ServiceName": resource_fields.get("ServiceName", "unknown"),
            "ServiceVersion": resource_fields.get("ServiceVersion", ""),
            "DeploymentEnvironment": resource_fields.get(
                "DeploymentEnvironment", ""
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
            # GenAI core
            "OperationType": mapped_op_type,
            "Provider": genai_fields.get("Provider", ""),
            "RequestModel": genai_fields.get("RequestModel", ""),
            "ResponseModel": genai_fields.get("ResponseModel", ""),
            # Token usage
            "InputTokens": genai_fields.get("InputTokens", 0),
            "OutputTokens": genai_fields.get("OutputTokens", 0),
            "TotalTokens": genai_fields.get("TotalTokens", 0),
            # Cost tracking (placeholder - can be computed from token counts)
            "EstimatedCostUsd": 0.0,
            # Agent context
            "AgentName": agent_fields.get("AgentName", ""),
            "AgentType": agent_fields.get("AgentType", ""),
            "AgentStep": agent_fields.get("AgentStep", 0),
            "AgentIteration": agent_fields.get("AgentIteration", 0),
            "ParentAgentSpanId": attrs.pop("agent.parent_span_id", "")
            or attrs.pop("gen_ai.agent.parent_span_id", ""),
            # Response summary
            "FinishReason": genai_fields.get("FinishReason", ""),
            "HasToolCalls": genai_fields.get("HasToolCalls", 0),
            "ToolCallCount": genai_fields.get("ToolCallCount", 0),
            "HasError": error_fields.get("HasError", 0),
            "ErrorType": error_fields.get("ErrorType", ""),
            # User context
            "UserId": session_fields.get("UserId", ""),
            "TenantId": session_fields.get("TenantId", ""),
            # Content (full capture mode)
            "RequestContent": genai_fields.get("RequestContent", ""),
            "ResponseContent": genai_fields.get("ResponseContent", ""),
            "SystemPrompt": genai_fields.get("SystemPrompt", ""),
            # Provider-specific (JSON)
            "RequestParams": genai_fields.get("RequestParams", "{}"),
            "ResponseMeta": genai_fields.get("ResponseMeta", "{}"),
            "TokenDetails": genai_fields.get("TokenDetails", "{}"),
            # Overflow attributes (remaining after extraction)
            "SpanAttributes": safe_json_dumps(attrs),
            "ResourceAttributes": safe_json_dumps(resource_attrs),
        }

        return row

    def _span_to_row(
        self, span: ReadableSpan, category: str
    ) -> dict[str, Any]:
        """Convert OpenTelemetry span to spans table row.

        Extracts typed columns based on semantic conventions for the span category.

        Args:
            span: OpenTelemetry span.
            category: Span category (db, http, messaging, rpc, faas, other).

        Returns:
            Dictionary representing a ClickHouse row for spans table.
        """
        # Make copies of attributes to extract from (destructive pops)
        attrs = dict(span.attributes or {})
        resource_attrs = dict(span.resource.attributes) if span.resource else {}

        # Extract resource attributes first
        resource_fields = extract_resource_attributes(resource_attrs)

        # Extract category-specific attributes
        db_fields = extract_db_attributes(attrs) if category == "db" else {}
        http_fields = extract_http_attributes(attrs) if category == "http" else {}
        messaging_fields = (
            extract_messaging_attributes(attrs) if category == "messaging" else {}
        )
        rpc_fields = extract_rpc_attributes(attrs) if category == "rpc" else {}

        # Always extract network and error attributes
        network_fields = extract_network_attributes(attrs)
        error_fields = extract_error_attributes(attrs)
        session_fields = extract_session_attributes(attrs)
        agent_fields = extract_agent_attributes(attrs)

        # Calculate duration in milliseconds
        duration_ms = 0
        if span.end_time and span.start_time:
            duration_ms = int((span.end_time - span.start_time) / 1_000_000)

        # Build the row
        row = {
            # Core identifiers
            "TraceId": format_trace_id_fixed(span.context.trace_id),
            "SpanId": format_span_id_fixed(span.context.span_id),
            "ParentSpanId": (
                format_span_id_fixed(span.parent.span_id)
                if span.parent
                else "0" * 16
            ),
            "TraceState": (
                str(span.context.trace_state) if span.context.trace_state else ""
            ),
            # Timing (milliseconds)
            "Timestamp": ns_to_datetime(span.start_time or 0),
            "EndTimestamp": ns_to_datetime(span.end_time or 0),
            "DurationMs": duration_ms,
            # Service & Resource
            "ServiceName": resource_fields.get("ServiceName", "unknown"),
            "ServiceVersion": resource_fields.get("ServiceVersion", ""),
            "DeploymentEnvironment": resource_fields.get(
                "DeploymentEnvironment", ""
            ),
            # Span metadata
            "SpanName": span.name,
            "SpanKind": span.kind.name if span.kind else "INTERNAL",
            "StatusCode": (
                span.status.status_code.name
                if span.status and span.status.status_code
                else "UNSET"
            ),
            "StatusMessage": span.status.description if span.status else "",
            "InstrumentationScope": (
                span.instrumentation_scope.name
                if span.instrumentation_scope
                else ""
            ),
            # Span category
            "SpanCategory": category,
            # Database (db.* semantic conventions)
            "DbSystem": db_fields.get("DbSystem", ""),
            "DbName": db_fields.get("DbName", ""),
            "DbStatement": db_fields.get("DbStatement", ""),
            "DbOperation": db_fields.get("DbOperation", ""),
            "DbUser": db_fields.get("DbUser", ""),
            "DbRedisDbIndex": db_fields.get("DbRedisDbIndex", 0),
            "DbMongoCollection": db_fields.get("DbMongoCollection", ""),
            # HTTP (http.* semantic conventions)
            "HttpMethod": http_fields.get("HttpMethod", ""),
            "HttpUrl": http_fields.get("HttpUrl", ""),
            "HttpRoute": http_fields.get("HttpRoute", ""),
            "HttpTarget": http_fields.get("HttpTarget", ""),
            "HttpStatusCode": http_fields.get("HttpStatusCode", 0),
            "HttpRequestBodySize": http_fields.get("HttpRequestBodySize", 0),
            "HttpResponseBodySize": http_fields.get("HttpResponseBodySize", 0),
            "HttpUserAgent": http_fields.get("HttpUserAgent", ""),
            # Messaging (messaging.* semantic conventions)
            "MessagingSystem": messaging_fields.get("MessagingSystem", ""),
            "MessagingDestination": messaging_fields.get(
                "MessagingDestination", ""
            ),
            "MessagingDestinationKind": messaging_fields.get(
                "MessagingDestinationKind", ""
            ),
            "MessagingOperation": messaging_fields.get("MessagingOperation", ""),
            "MessagingMessageId": messaging_fields.get("MessagingMessageId", ""),
            "MessagingKafkaPartition": messaging_fields.get(
                "MessagingKafkaPartition", -1
            ),
            "MessagingKafkaOffset": messaging_fields.get(
                "MessagingKafkaOffset", -1
            ),
            "MessagingKafkaConsumerGroup": messaging_fields.get(
                "MessagingKafkaConsumerGroup", ""
            ),
            # RPC (rpc.* semantic conventions)
            "RpcSystem": rpc_fields.get("RpcSystem", ""),
            "RpcService": rpc_fields.get("RpcService", ""),
            "RpcMethod": rpc_fields.get("RpcMethod", ""),
            "RpcGrpcStatusCode": rpc_fields.get("RpcGrpcStatusCode", -1),
            "CloudRegion": rpc_fields.get("CloudRegion", ""),
            "CloudProvider": rpc_fields.get("CloudProvider", ""),
            "AwsRequestId": rpc_fields.get("AwsRequestId", ""),
            # Network (net.* / network.* / server.*)
            "NetPeerName": network_fields.get("NetPeerName", ""),
            "NetPeerPort": network_fields.get("NetPeerPort", 0),
            "NetTransport": network_fields.get("NetTransport", ""),
            "ServerAddress": network_fields.get("ServerAddress", ""),
            "ServerPort": network_fields.get("ServerPort", 0),
            # Error tracking
            "HasError": error_fields.get("HasError", 0),
            "ErrorType": error_fields.get("ErrorType", ""),
            "ErrorMessage": error_fields.get("ErrorMessage", ""),
            # GenAI correlation
            "SessionId": session_fields.get("SessionId", ""),
            "AgentName": agent_fields.get("AgentName", ""),
            # Extensibility (JSON overflow)
            "Attributes": safe_json_dumps(attrs),
            "ResourceAttributes": safe_json_dumps(resource_attrs),
        }

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
