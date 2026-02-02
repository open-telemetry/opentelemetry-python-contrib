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

"""ClickHouse schema definitions for GenAI observability.

Schema design principles:
1. Millisecond precision (DateTime64(3)) - sufficient for LLM observability
2. Modern inverted indexes for text search
3. Separate tables for different data types (spans, tools, retrievals, sessions)
4. Smart span routing: GenAI spans vs general spans
5. JSON overflow for extensibility
"""

# =============================================================================
# GENAI_SPANS - Core LLM/AI Interactions
# =============================================================================
GENAI_SPANS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {database}.{table} (
    -- IDENTIFIERS
    TraceId FixedString(32) CODEC(ZSTD(1)),
    SpanId FixedString(16) CODEC(ZSTD(1)),
    ParentSpanId FixedString(16) CODEC(ZSTD(1)),

    -- SESSION/WORKFLOW CONTEXT
    SessionId String DEFAULT '' CODEC(ZSTD(1)),
    WorkflowId String DEFAULT '' CODEC(ZSTD(1)),
    WorkflowRunId String DEFAULT '' CODEC(ZSTD(1)),

    -- TIMING (milliseconds)
    Timestamp DateTime64(3) CODEC(Delta, ZSTD(1)),
    EndTimestamp DateTime64(3) CODEC(Delta, ZSTD(1)),
    DurationMs UInt32 CODEC(Delta, ZSTD(1)),

    -- SERVICE INFO
    ServiceName LowCardinality(String) CODEC(ZSTD(1)),
    ServiceVersion String DEFAULT '' CODEC(ZSTD(1)),
    DeploymentEnvironment LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),

    -- SPAN INFO
    SpanName LowCardinality(String) CODEC(ZSTD(1)),
    SpanKind Enum8('INTERNAL'=0, 'SERVER'=1, 'CLIENT'=2, 'PRODUCER'=3, 'CONSUMER'=4) DEFAULT 'CLIENT' CODEC(ZSTD(1)),
    StatusCode Enum8('UNSET'=0, 'OK'=1, 'ERROR'=2) DEFAULT 'UNSET' CODEC(ZSTD(1)),
    StatusMessage String DEFAULT '' CODEC(ZSTD(1)),
    InstrumentationScope LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),

    -- GENAI CORE
    OperationType LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    Provider LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    RequestModel LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    ResponseModel LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    ResponseId String DEFAULT '' CODEC(ZSTD(1)),

    -- TOKEN USAGE
    InputTokens UInt32 DEFAULT 0 CODEC(Delta, ZSTD(1)),
    OutputTokens UInt32 DEFAULT 0 CODEC(Delta, ZSTD(1)),
    TotalTokens UInt32 DEFAULT 0 CODEC(Delta, ZSTD(1)),

    -- COST TRACKING
    EstimatedCostUsd Float32 DEFAULT 0 CODEC(ZSTD(1)),

    -- AGENT CONTEXT
    AgentName LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    AgentType LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    AgentStep UInt16 DEFAULT 0,
    AgentIteration UInt8 DEFAULT 0,
    ParentAgentSpanId FixedString(16) DEFAULT '' CODEC(ZSTD(1)),

    -- RESPONSE SUMMARY
    FinishReason LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    HasToolCalls UInt8 DEFAULT 0,
    ToolCallCount UInt8 DEFAULT 0,
    HasError UInt8 DEFAULT 0,
    ErrorType LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),

    -- USER CONTEXT
    UserId String DEFAULT '' CODEC(ZSTD(1)),
    TenantId String DEFAULT '' CODEC(ZSTD(1)),

    -- CONTENT (full capture mode)
    RequestContent String DEFAULT '' CODEC(ZSTD(1)),
    ResponseContent String DEFAULT '' CODEC(ZSTD(1)),
    SystemPrompt String DEFAULT '' CODEC(ZSTD(1)),

    -- PROVIDER-SPECIFIC (JSON for sparse/varying fields)
    RequestParams String DEFAULT '{{}}' CODEC(ZSTD(1)),
    ResponseMeta String DEFAULT '{{}}' CODEC(ZSTD(1)),
    TokenDetails String DEFAULT '{{}}' CODEC(ZSTD(1)),

    -- OVERFLOW
    SpanAttributes String DEFAULT '{{}}' CODEC(ZSTD(1)),
    ResourceAttributes String DEFAULT '{{}}' CODEC(ZSTD(1)),

    -- INVERTED INDEXES (modern full-text)
    INDEX idx_request_content RequestContent TYPE full_text GRANULARITY 1,
    INDEX idx_response_content ResponseContent TYPE full_text GRANULARITY 1,
    INDEX idx_system_prompt SystemPrompt TYPE full_text GRANULARITY 1,
    INDEX idx_span_name SpanName TYPE full_text GRANULARITY 1,

    -- BLOOM FILTERS (for exact ID lookups)
    INDEX idx_trace_id TraceId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_span_id SpanId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_session_id SessionId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_workflow_id WorkflowId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_user_id UserId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_provider Provider TYPE bloom_filter GRANULARITY 1,
    INDEX idx_model RequestModel TYPE bloom_filter GRANULARITY 1,

    -- MINMAX for range queries
    INDEX idx_duration DurationMs TYPE minmax GRANULARITY 1,
    INDEX idx_tokens InputTokens TYPE minmax GRANULARITY 1,
    INDEX idx_cost EstimatedCostUsd TYPE minmax GRANULARITY 1,
    INDEX idx_timestamp Timestamp TYPE minmax GRANULARITY 1,

    -- SET for enums/flags
    INDEX idx_has_error HasError TYPE set(2) GRANULARITY 1,
    INDEX idx_has_tools HasToolCalls TYPE set(2) GRANULARITY 1
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(Timestamp)
ORDER BY (ServiceName, Provider, OperationType, RequestModel, toUnixTimestamp(Timestamp), TraceId, SpanId)
TTL toDateTime(Timestamp) + INTERVAL {ttl_days} DAY
SETTINGS index_granularity = 8192
"""

# =============================================================================
# SPANS - General Purpose Span Table (All Non-LLM Spans)
# =============================================================================
SPANS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {database}.{table} (
    -- CORE IDENTIFIERS
    TraceId FixedString(32) CODEC(ZSTD(1)),
    SpanId FixedString(16) CODEC(ZSTD(1)),
    ParentSpanId FixedString(16) CODEC(ZSTD(1)),
    TraceState String DEFAULT '' CODEC(ZSTD(1)),

    -- TIMING (milliseconds)
    Timestamp DateTime64(3) CODEC(Delta, ZSTD(1)),
    EndTimestamp DateTime64(3) CODEC(Delta, ZSTD(1)),
    DurationMs UInt32 CODEC(Delta, ZSTD(1)),

    -- SERVICE & RESOURCE
    ServiceName LowCardinality(String) CODEC(ZSTD(1)),
    ServiceVersion String DEFAULT '' CODEC(ZSTD(1)),
    DeploymentEnvironment LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),

    -- SPAN METADATA
    SpanName String CODEC(ZSTD(1)),
    SpanKind Enum8('INTERNAL'=0, 'SERVER'=1, 'CLIENT'=2, 'PRODUCER'=3, 'CONSUMER'=4) DEFAULT 'INTERNAL' CODEC(ZSTD(1)),
    StatusCode Enum8('UNSET'=0, 'OK'=1, 'ERROR'=2) DEFAULT 'UNSET' CODEC(ZSTD(1)),
    StatusMessage String DEFAULT '' CODEC(ZSTD(1)),
    InstrumentationScope LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),

    -- SPAN CATEGORY (for routing queries)
    SpanCategory LowCardinality(String) CODEC(ZSTD(1)),

    -- DATABASE (db.* semantic conventions)
    DbSystem LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    DbName String DEFAULT '' CODEC(ZSTD(1)),
    DbStatement String DEFAULT '' CODEC(ZSTD(1)),
    DbOperation LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    DbUser String DEFAULT '' CODEC(ZSTD(1)),
    DbRedisDbIndex UInt8 DEFAULT 0,
    DbMongoCollection String DEFAULT '' CODEC(ZSTD(1)),

    -- HTTP (http.* semantic conventions)
    HttpMethod LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    HttpUrl String DEFAULT '' CODEC(ZSTD(1)),
    HttpRoute String DEFAULT '' CODEC(ZSTD(1)),
    HttpTarget String DEFAULT '' CODEC(ZSTD(1)),
    HttpStatusCode UInt16 DEFAULT 0,
    HttpRequestBodySize UInt32 DEFAULT 0,
    HttpResponseBodySize UInt32 DEFAULT 0,
    HttpUserAgent String DEFAULT '' CODEC(ZSTD(1)),

    -- MESSAGING (messaging.* semantic conventions)
    MessagingSystem LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    MessagingDestination String DEFAULT '' CODEC(ZSTD(1)),
    MessagingDestinationKind LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    MessagingOperation LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    MessagingMessageId String DEFAULT '' CODEC(ZSTD(1)),
    MessagingKafkaPartition Int32 DEFAULT -1,
    MessagingKafkaOffset Int64 DEFAULT -1,
    MessagingKafkaConsumerGroup String DEFAULT '' CODEC(ZSTD(1)),

    -- RPC (rpc.* semantic conventions)
    RpcSystem LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    RpcService String DEFAULT '' CODEC(ZSTD(1)),
    RpcMethod String DEFAULT '' CODEC(ZSTD(1)),
    RpcGrpcStatusCode Int8 DEFAULT -1,

    -- CLOUD (cloud.* semantic conventions)
    CloudRegion LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    CloudProvider LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    AwsRequestId String DEFAULT '' CODEC(ZSTD(1)),

    -- NETWORK (net.* / network.* / server.* semantic conventions)
    NetPeerName String DEFAULT '' CODEC(ZSTD(1)),
    NetPeerPort UInt16 DEFAULT 0,
    NetTransport LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    ServerAddress String DEFAULT '' CODEC(ZSTD(1)),
    ServerPort UInt16 DEFAULT 0,

    -- ERROR TRACKING
    HasError UInt8 DEFAULT 0,
    ErrorType LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    ErrorMessage String DEFAULT '' CODEC(ZSTD(1)),

    -- GENAI CORRELATION
    SessionId String DEFAULT '' CODEC(ZSTD(1)),
    AgentName LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),

    -- EXTENSIBILITY (JSON overflow)
    Attributes String DEFAULT '{{}}' CODEC(ZSTD(1)),
    ResourceAttributes String DEFAULT '{{}}' CODEC(ZSTD(1)),

    -- INDEXES
    INDEX idx_trace_id TraceId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_span_id SpanId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_parent_span_id ParentSpanId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_session_id SessionId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_category SpanCategory TYPE bloom_filter GRANULARITY 1,
    INDEX idx_db_system DbSystem TYPE bloom_filter GRANULARITY 1,
    INDEX idx_http_method HttpMethod TYPE bloom_filter GRANULARITY 1,
    INDEX idx_messaging_system MessagingSystem TYPE bloom_filter GRANULARITY 1,
    INDEX idx_rpc_system RpcSystem TYPE bloom_filter GRANULARITY 1,

    INDEX idx_db_statement DbStatement TYPE full_text GRANULARITY 1,
    INDEX idx_http_url HttpUrl TYPE full_text GRANULARITY 1,
    INDEX idx_span_name SpanName TYPE full_text GRANULARITY 1,
    INDEX idx_error_message ErrorMessage TYPE full_text GRANULARITY 1,

    INDEX idx_duration DurationMs TYPE minmax GRANULARITY 1,
    INDEX idx_http_status HttpStatusCode TYPE minmax GRANULARITY 1,
    INDEX idx_timestamp Timestamp TYPE minmax GRANULARITY 1,

    INDEX idx_has_error HasError TYPE set(2) GRANULARITY 1
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(Timestamp)
ORDER BY (ServiceName, SpanCategory, toUnixTimestamp(Timestamp), TraceId, SpanId)
TTL toDateTime(Timestamp) + INTERVAL {ttl_days} DAY
SETTINGS index_granularity = 8192
"""

# =============================================================================
# GENAI_TOOL_CALLS - Detailed Tool/Function Executions
# =============================================================================
TOOL_CALLS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {database}.{table} (
    -- IDENTIFIERS
    Id UUID DEFAULT generateUUIDv4() CODEC(ZSTD(1)),
    TraceId FixedString(32) CODEC(ZSTD(1)),
    SpanId FixedString(16) CODEC(ZSTD(1)),
    ToolCallId String CODEC(ZSTD(1)),

    -- TIMING
    Timestamp DateTime64(3) CODEC(Delta, ZSTD(1)),
    DurationMs UInt32 DEFAULT 0 CODEC(Delta, ZSTD(1)),

    -- TOOL IDENTITY
    ToolName LowCardinality(String) CODEC(ZSTD(1)),
    ToolType LowCardinality(String) DEFAULT 'function' CODEC(ZSTD(1)),
    ToolSource LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),

    -- EXECUTION
    ToolInput String DEFAULT '' CODEC(ZSTD(1)),
    ToolOutput String DEFAULT '' CODEC(ZSTD(1)),
    ToolError String DEFAULT '' CODEC(ZSTD(1)),

    -- STATUS
    Status LowCardinality(String) DEFAULT 'pending' CODEC(ZSTD(1)),

    -- CONTEXT
    SessionId String DEFAULT '' CODEC(ZSTD(1)),
    AgentName LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    AgentStep UInt16 DEFAULT 0,

    -- INDEXES
    INDEX idx_trace_id TraceId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_span_id SpanId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_tool_name ToolName TYPE bloom_filter GRANULARITY 1,
    INDEX idx_session_id SessionId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_tool_input ToolInput TYPE full_text GRANULARITY 1,
    INDEX idx_tool_output ToolOutput TYPE full_text GRANULARITY 1,
    INDEX idx_duration DurationMs TYPE minmax GRANULARITY 1
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(Timestamp)
ORDER BY (ToolName, toUnixTimestamp(Timestamp), TraceId)
TTL toDateTime(Timestamp) + INTERVAL {ttl_days} DAY
SETTINGS index_granularity = 8192
"""

# =============================================================================
# GENAI_RETRIEVALS - RAG/Vector DB Queries
# =============================================================================
RETRIEVALS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {database}.{table} (
    -- IDENTIFIERS
    Id UUID DEFAULT generateUUIDv4() CODEC(ZSTD(1)),
    TraceId FixedString(32) CODEC(ZSTD(1)),
    SpanId FixedString(16) CODEC(ZSTD(1)),

    -- TIMING
    Timestamp DateTime64(3) CODEC(Delta, ZSTD(1)),
    DurationMs UInt32 DEFAULT 0 CODEC(Delta, ZSTD(1)),

    -- RETRIEVAL SOURCE
    SourceType LowCardinality(String) DEFAULT 'vector_db' CODEC(ZSTD(1)),
    SourceName LowCardinality(String) CODEC(ZSTD(1)),
    CollectionName String DEFAULT '' CODEC(ZSTD(1)),

    -- QUERY
    QueryText String DEFAULT '' CODEC(ZSTD(1)),
    QueryVector Array(Float32) DEFAULT [] CODEC(ZSTD(1)),
    QueryType LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),

    -- RESULTS
    ResultCount UInt16 DEFAULT 0,
    TopK UInt16 DEFAULT 0,
    Results String DEFAULT '[]' CODEC(ZSTD(1)),

    -- RELEVANCE METRICS
    MaxScore Float32 DEFAULT 0 CODEC(ZSTD(1)),
    MinScore Float32 DEFAULT 0 CODEC(ZSTD(1)),
    AvgScore Float32 DEFAULT 0 CODEC(ZSTD(1)),

    -- CONTEXT USAGE
    TokensUsed UInt32 DEFAULT 0,
    ContextTruncated UInt8 DEFAULT 0,

    -- CONTEXT
    SessionId String DEFAULT '' CODEC(ZSTD(1)),
    AgentName LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),

    -- INDEXES
    INDEX idx_trace_id TraceId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_source SourceName TYPE bloom_filter GRANULARITY 1,
    INDEX idx_session_id SessionId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_query QueryText TYPE full_text GRANULARITY 1,
    INDEX idx_duration DurationMs TYPE minmax GRANULARITY 1,
    INDEX idx_score MaxScore TYPE minmax GRANULARITY 1
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(Timestamp)
ORDER BY (SourceName, toUnixTimestamp(Timestamp), TraceId)
TTL toDateTime(Timestamp) + INTERVAL {ttl_days} DAY
SETTINGS index_granularity = 8192
"""

# =============================================================================
# GENAI_SESSIONS - Session/Conversation Tracking
# =============================================================================
SESSIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {database}.{table} (
    -- IDENTIFIERS
    SessionId String CODEC(ZSTD(1)),

    -- TIMING
    StartTime DateTime64(3) CODEC(Delta, ZSTD(1)),
    EndTime DateTime64(3) CODEC(Delta, ZSTD(1)),
    DurationMs UInt64 DEFAULT 0 CODEC(Delta, ZSTD(1)),
    LastActivityTime DateTime64(3) CODEC(Delta, ZSTD(1)),

    -- USER CONTEXT
    UserId String DEFAULT '' CODEC(ZSTD(1)),
    TenantId String DEFAULT '' CODEC(ZSTD(1)),

    -- SESSION METRICS
    TurnCount UInt16 DEFAULT 0,
    MessageCount UInt16 DEFAULT 0,
    TotalInputTokens UInt32 DEFAULT 0,
    TotalOutputTokens UInt32 DEFAULT 0,
    TotalCostUsd Float32 DEFAULT 0,

    -- AGENT CONTEXT
    PrimaryAgentName LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    AgentsUsed Array(LowCardinality(String)) DEFAULT [] CODEC(ZSTD(1)),

    -- MODELS USED
    ModelsUsed Array(LowCardinality(String)) DEFAULT [] CODEC(ZSTD(1)),
    ProvidersUsed Array(LowCardinality(String)) DEFAULT [] CODEC(ZSTD(1)),

    -- TOOL USAGE
    ToolCallCount UInt16 DEFAULT 0,
    ToolsUsed Array(LowCardinality(String)) DEFAULT [] CODEC(ZSTD(1)),

    -- OUTCOME
    Status LowCardinality(String) DEFAULT 'active' CODEC(ZSTD(1)),
    FinalOutcome LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),

    -- METADATA
    SessionMetadata String DEFAULT '{{}}' CODEC(ZSTD(1)),

    -- INDEXES
    INDEX idx_session_id SessionId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_user_id UserId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_start_time StartTime TYPE minmax GRANULARITY 1,
    INDEX idx_cost TotalCostUsd TYPE minmax GRANULARITY 1
)
ENGINE = ReplacingMergeTree(LastActivityTime)
PARTITION BY toYYYYMM(StartTime)
ORDER BY (SessionId)
TTL toDateTime(StartTime) + INTERVAL {ttl_days} DAY
SETTINGS index_granularity = 8192
"""

# =============================================================================
# GENAI_MESSAGES - Message-Level Tracking
# =============================================================================
MESSAGES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {database}.{table} (
    -- IDENTIFIERS
    TraceId FixedString(32) CODEC(ZSTD(1)),
    SpanId FixedString(16) CODEC(ZSTD(1)),
    MessageIndex UInt8 CODEC(ZSTD(1)),

    -- TIMING
    Timestamp DateTime64(3) CODEC(Delta, ZSTD(1)),

    -- MESSAGE CONTENT
    Role LowCardinality(String) CODEC(ZSTD(1)),
    Content String CODEC(ZSTD(1)),

    -- TOOL CALL CONTEXT
    ToolCalls String DEFAULT '[]' CODEC(ZSTD(1)),

    -- TOOL RESPONSE CONTEXT
    ToolCallId String DEFAULT '' CODEC(ZSTD(1)),
    ToolName LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),

    -- METADATA
    TokenCount UInt16 DEFAULT 0,

    -- SESSION CONTEXT
    SessionId String DEFAULT '' CODEC(ZSTD(1)),
    TurnIndex UInt16 DEFAULT 0,

    -- INDEXES
    INDEX idx_trace_id TraceId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_session_id SessionId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_content Content TYPE full_text GRANULARITY 1
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(Timestamp)
ORDER BY (TraceId, SpanId, MessageIndex)
TTL toDateTime(Timestamp) + INTERVAL {ttl_days} DAY
SETTINGS index_granularity = 8192
"""

# =============================================================================
# GENAI_METRICS - Aggregated Metrics
# =============================================================================
METRICS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {database}.{table} (
    -- TIMING
    Timestamp DateTime64(3) CODEC(Delta, ZSTD(1)),

    -- METRIC IDENTITY
    MetricName LowCardinality(String) CODEC(ZSTD(1)),
    MetricType LowCardinality(String) DEFAULT 'gauge' CODEC(ZSTD(1)),
    MetricUnit LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),

    -- DIMENSIONS
    ServiceName LowCardinality(String) CODEC(ZSTD(1)),
    Provider LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    Model LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    OperationType LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    AgentName LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),

    -- VALUES
    Value Float64 DEFAULT 0 CODEC(ZSTD(1)),
    IntValue Int64 DEFAULT 0 CODEC(ZSTD(1)),

    -- HISTOGRAM (if applicable)
    HistogramBuckets Array(Float64) DEFAULT [] CODEC(ZSTD(1)),
    HistogramCounts Array(UInt64) DEFAULT [] CODEC(ZSTD(1)),
    HistogramSum Float64 DEFAULT 0 CODEC(ZSTD(1)),
    HistogramCount UInt64 DEFAULT 0 CODEC(ZSTD(1)),

    -- EXEMPLAR (link to trace)
    ExemplarTraceId FixedString(32) DEFAULT '' CODEC(ZSTD(1)),
    ExemplarSpanId FixedString(16) DEFAULT '' CODEC(ZSTD(1)),

    -- OVERFLOW
    Attributes String DEFAULT '{{}}' CODEC(ZSTD(1)),
    ResourceAttributes String DEFAULT '{{}}' CODEC(ZSTD(1)),

    -- INDEXES
    INDEX idx_metric MetricName TYPE bloom_filter GRANULARITY 1,
    INDEX idx_service ServiceName TYPE bloom_filter GRANULARITY 1,
    INDEX idx_provider Provider TYPE bloom_filter GRANULARITY 1,
    INDEX idx_model Model TYPE bloom_filter GRANULARITY 1,
    INDEX idx_value Value TYPE minmax GRANULARITY 1,
    INDEX idx_timestamp Timestamp TYPE minmax GRANULARITY 1
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(Timestamp)
ORDER BY (ServiceName, MetricName, Provider, Model, toUnixTimestamp(Timestamp))
TTL toDateTime(Timestamp) + INTERVAL {ttl_days} DAY
SETTINGS index_granularity = 8192
"""

# Database creation
CREATE_DATABASE_SQL = "CREATE DATABASE IF NOT EXISTS {database}"

# Table name constants
GENAI_SPANS_TABLE = "genai_spans"
SPANS_TABLE = "spans"
TOOL_CALLS_TABLE = "genai_tool_calls"
RETRIEVALS_TABLE = "genai_retrievals"
SESSIONS_TABLE = "genai_sessions"
MESSAGES_TABLE = "genai_messages"
METRICS_TABLE = "genai_metrics"

# Legacy alias for backward compatibility
TRACES_TABLE_SQL = GENAI_SPANS_TABLE_SQL
LOGS_TABLE_SQL = MESSAGES_TABLE_SQL

# Column sets for each table (used for filtering rows before insertion)
GENAI_SPANS_COLUMNS = frozenset([
    "TraceId", "SpanId", "ParentSpanId",
    "SessionId", "WorkflowId", "WorkflowRunId",
    "Timestamp", "EndTimestamp", "DurationMs",
    "ServiceName", "ServiceVersion", "DeploymentEnvironment",
    "SpanName", "SpanKind", "StatusCode", "StatusMessage", "InstrumentationScope",
    "OperationType", "Provider", "RequestModel", "ResponseModel", "ResponseId",
    "InputTokens", "OutputTokens", "TotalTokens", "EstimatedCostUsd",
    "AgentName", "AgentType", "AgentStep", "AgentIteration", "ParentAgentSpanId",
    "FinishReason", "HasToolCalls", "ToolCallCount", "HasError", "ErrorType",
    "UserId", "TenantId",
    "RequestContent", "ResponseContent", "SystemPrompt",
    "RequestParams", "ResponseMeta", "TokenDetails",
    "SpanAttributes", "ResourceAttributes",
])

SPANS_COLUMNS = frozenset([
    "TraceId", "SpanId", "ParentSpanId", "TraceState",
    "Timestamp", "EndTimestamp", "DurationMs",
    "ServiceName", "ServiceVersion", "DeploymentEnvironment",
    "SpanName", "SpanKind", "StatusCode", "StatusMessage", "InstrumentationScope",
    "SpanCategory",
    "DbSystem", "DbName", "DbStatement", "DbOperation", "DbUser",
    "DbRedisDbIndex", "DbMongoCollection",
    "HttpMethod", "HttpUrl", "HttpRoute", "HttpTarget", "HttpStatusCode",
    "HttpRequestBodySize", "HttpResponseBodySize", "HttpUserAgent",
    "MessagingSystem", "MessagingDestination", "MessagingDestinationKind",
    "MessagingOperation", "MessagingMessageId",
    "MessagingKafkaPartition", "MessagingKafkaOffset", "MessagingKafkaConsumerGroup",
    "RpcSystem", "RpcService", "RpcMethod", "RpcGrpcStatusCode",
    "CloudRegion", "CloudProvider", "AwsRequestId",
    "NetPeerName", "NetPeerPort", "NetTransport", "ServerAddress", "ServerPort",
    "HasError", "ErrorType", "ErrorMessage",
    "SessionId", "AgentName",
    "Attributes", "ResourceAttributes",
])
