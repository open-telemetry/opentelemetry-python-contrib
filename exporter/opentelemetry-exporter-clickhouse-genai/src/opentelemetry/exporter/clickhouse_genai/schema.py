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

"""ClickHouse schema definitions for GenAI observability."""

# Traces table - maximally columnar for LLM interaction tracking
TRACES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {database}.{table} (
    -- IDENTIFIERS
    TraceId FixedString(32) CODEC(ZSTD(1)),
    SpanId FixedString(16) CODEC(ZSTD(1)),
    ParentSpanId FixedString(16) CODEC(ZSTD(1)),
    TraceState String DEFAULT '' CODEC(ZSTD(1)),

    -- TIMING (nanosecond precision for latency analysis)
    Timestamp DateTime64(9) CODEC(Delta, ZSTD(1)),
    EndTimestamp DateTime64(9) CODEC(Delta, ZSTD(1)),
    DurationNs Int64 CODEC(Delta, ZSTD(1)),

    -- SERVICE & RESOURCE INFO
    ServiceName LowCardinality(String) CODEC(ZSTD(1)),
    ServiceVersion String DEFAULT '' CODEC(ZSTD(1)),
    ServiceNamespace LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    DeploymentEnvironment LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    HostName String DEFAULT '' CODEC(ZSTD(1)),
    ProcessPid UInt32 DEFAULT 0,
    TelemetrySdkName LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    TelemetrySdkVersion String DEFAULT '' CODEC(ZSTD(1)),

    -- SPAN INFO
    SpanName LowCardinality(String) CODEC(ZSTD(1)),
    SpanKind LowCardinality(String) CODEC(ZSTD(1)),
    StatusCode LowCardinality(String) CODEC(ZSTD(1)),
    StatusMessage String DEFAULT '' CODEC(ZSTD(1)),
    InstrumentationScopeName LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    InstrumentationScopeVersion String DEFAULT '' CODEC(ZSTD(1)),

    -- GENAI CORE ATTRIBUTES (gen_ai.* namespace)
    GenAiOperationName LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    GenAiSystem LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    GenAiRequestModel LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    GenAiResponseModel LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    GenAiResponseId String DEFAULT '' CODEC(ZSTD(1)),

    -- TOKEN USAGE (critical for cost tracking & optimization)
    InputTokens UInt32 DEFAULT 0 CODEC(Delta, ZSTD(1)),
    OutputTokens UInt32 DEFAULT 0 CODEC(Delta, ZSTD(1)),
    TotalTokens UInt32 DEFAULT 0 CODEC(Delta, ZSTD(1)),
    CachedInputTokens UInt32 DEFAULT 0 CODEC(Delta, ZSTD(1)),
    ReasoningTokens UInt32 DEFAULT 0 CODEC(Delta, ZSTD(1)),
    EmbeddingDimensions UInt16 DEFAULT 0,

    -- REQUEST PARAMETERS
    Temperature Float32 DEFAULT 0 CODEC(ZSTD(1)),
    TopP Float32 DEFAULT 0 CODEC(ZSTD(1)),
    MaxTokens UInt32 DEFAULT 0 CODEC(ZSTD(1)),
    FrequencyPenalty Float32 DEFAULT 0 CODEC(ZSTD(1)),
    PresencePenalty Float32 DEFAULT 0 CODEC(ZSTD(1)),
    Seed Int64 DEFAULT 0 CODEC(ZSTD(1)),
    ChoiceCount UInt8 DEFAULT 1 CODEC(ZSTD(1)),
    IsStreaming UInt8 DEFAULT 0 CODEC(ZSTD(1)),
    StopSequences Array(String) DEFAULT [] CODEC(ZSTD(1)),
    ReasoningEffort LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),

    -- RESPONSE INFO
    FinishReasons Array(LowCardinality(String)) DEFAULT [] CODEC(ZSTD(1)),
    ResponseFormatType LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    ServiceTier LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    SystemFingerprint String DEFAULT '' CODEC(ZSTD(1)),

    -- SERVER & NETWORK INFO
    ServerAddress LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    ServerPort UInt16 DEFAULT 0 CODEC(ZSTD(1)),
    ApiBaseUrl String DEFAULT '' CODEC(ZSTD(1)),
    ApiVersion String DEFAULT '' CODEC(ZSTD(1)),

    -- TOOL/FUNCTION CALLING
    AvailableTools Array(String) DEFAULT [] CODEC(ZSTD(1)),
    ToolCallCount UInt8 DEFAULT 0 CODEC(ZSTD(1)),
    HasToolCalls UInt8 DEFAULT 0 CODEC(ZSTD(1)),

    -- ERROR INFO
    ErrorType LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    HasError UInt8 DEFAULT 0 CODEC(ZSTD(1)),

    -- USER CONTEXT
    UserId String DEFAULT '' CODEC(ZSTD(1)),

    -- CONTENT (populated in ALL capture mode)
    RequestMessages String DEFAULT '' CODEC(ZSTD(1)),
    ResponseContent String DEFAULT '' CODEC(ZSTD(1)),
    RequestPrompt String DEFAULT '' CODEC(ZSTD(1)),
    RequestInput String DEFAULT '' CODEC(ZSTD(1)),
    StructuredOutputSchema String DEFAULT '' CODEC(ZSTD(1)),

    -- EVENTS (parallel arrays for span events)
    `Events.Timestamp` Array(DateTime64(9)) DEFAULT [] CODEC(ZSTD(1)),
    `Events.Name` Array(LowCardinality(String)) DEFAULT [] CODEC(ZSTD(1)),
    `Events.Attributes` Array(String) DEFAULT [] CODEC(ZSTD(1)),
    EventCount UInt8 DEFAULT 0 CODEC(ZSTD(1)),

    -- LINKS (trace links to other spans)
    `Links.TraceId` Array(FixedString(32)) DEFAULT [] CODEC(ZSTD(1)),
    `Links.SpanId` Array(FixedString(16)) DEFAULT [] CODEC(ZSTD(1)),
    `Links.TraceState` Array(String) DEFAULT [] CODEC(ZSTD(1)),
    `Links.Attributes` Array(String) DEFAULT [] CODEC(ZSTD(1)),

    -- OVERFLOW (for any attributes not in dedicated columns)
    SpanAttributesJson String DEFAULT '{{}}' CODEC(ZSTD(1)),
    ResourceAttributesJson String DEFAULT '{{}}' CODEC(ZSTD(1)),

    -- COMPREHENSIVE INDEXES (optimize for all query patterns)

    -- Bloom filters for exact lookups
    INDEX idx_trace_id TraceId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_span_id SpanId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_parent_span_id ParentSpanId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_response_id GenAiResponseId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_user_id UserId TYPE bloom_filter GRANULARITY 1,

    -- Bloom filters for categorical lookups
    INDEX idx_service_name ServiceName TYPE bloom_filter GRANULARITY 1,
    INDEX idx_operation GenAiOperationName TYPE bloom_filter GRANULARITY 1,
    INDEX idx_system GenAiSystem TYPE bloom_filter GRANULARITY 1,
    INDEX idx_request_model GenAiRequestModel TYPE bloom_filter GRANULARITY 1,
    INDEX idx_response_model GenAiResponseModel TYPE bloom_filter GRANULARITY 1,
    INDEX idx_span_kind SpanKind TYPE bloom_filter GRANULARITY 1,
    INDEX idx_status_code StatusCode TYPE bloom_filter GRANULARITY 1,
    INDEX idx_error_type ErrorType TYPE bloom_filter GRANULARITY 1,
    INDEX idx_server_address ServerAddress TYPE bloom_filter GRANULARITY 1,
    INDEX idx_environment DeploymentEnvironment TYPE bloom_filter GRANULARITY 1,
    INDEX idx_finish_reasons FinishReasons TYPE bloom_filter GRANULARITY 1,

    -- MinMax indexes for range queries
    INDEX idx_duration_range DurationNs TYPE minmax GRANULARITY 1,
    INDEX idx_input_tokens_range InputTokens TYPE minmax GRANULARITY 1,
    INDEX idx_output_tokens_range OutputTokens TYPE minmax GRANULARITY 1,
    INDEX idx_total_tokens_range TotalTokens TYPE minmax GRANULARITY 1,
    INDEX idx_temperature_range Temperature TYPE minmax GRANULARITY 1,
    INDEX idx_timestamp_range Timestamp TYPE minmax GRANULARITY 1,

    -- Set indexes for boolean/flag columns
    INDEX idx_has_error HasError TYPE set(2) GRANULARITY 1,
    INDEX idx_has_tool_calls HasToolCalls TYPE set(2) GRANULARITY 1,
    INDEX idx_is_streaming IsStreaming TYPE set(2) GRANULARITY 1,

    -- NGram bloom filter for text search in content
    INDEX idx_request_messages RequestMessages TYPE ngrambf_v1(4, 1024, 2, 0) GRANULARITY 1,
    INDEX idx_response_content ResponseContent TYPE ngrambf_v1(4, 1024, 2, 0) GRANULARITY 1,
    INDEX idx_span_name SpanName TYPE ngrambf_v1(3, 512, 2, 0) GRANULARITY 1
)
ENGINE = MergeTree()
PARTITION BY toDate(Timestamp)
ORDER BY (ServiceName, GenAiSystem, GenAiOperationName, GenAiRequestModel, toUnixTimestamp(Timestamp), TraceId, SpanId)
TTL toDateTime(Timestamp) + INTERVAL {ttl_days} DAY
SETTINGS index_granularity = 8192,
         ttl_only_drop_parts = 1
"""

# Metrics table
METRICS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {database}.{table} (
    -- TIMING
    Timestamp DateTime64(3) CODEC(Delta, ZSTD(1)),
    StartTimeUnixNano UInt64 DEFAULT 0 CODEC(Delta, ZSTD(1)),
    EndTimeUnixNano UInt64 DEFAULT 0 CODEC(Delta, ZSTD(1)),

    -- METRIC IDENTITY
    MetricName LowCardinality(String) CODEC(ZSTD(1)),
    MetricDescription String DEFAULT '' CODEC(ZSTD(1)),
    MetricUnit LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    MetricType LowCardinality(String) CODEC(ZSTD(1)),

    -- SERVICE & RESOURCE INFO
    ServiceName LowCardinality(String) CODEC(ZSTD(1)),
    ServiceVersion String DEFAULT '' CODEC(ZSTD(1)),
    DeploymentEnvironment LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    InstrumentationScopeName LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    InstrumentationScopeVersion String DEFAULT '' CODEC(ZSTD(1)),

    -- GENAI DIMENSIONS (extracted from attributes)
    GenAiOperationName LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    GenAiSystem LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    GenAiRequestModel LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    GenAiResponseModel LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    GenAiTokenType LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    ServerAddress LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    ServerPort UInt16 DEFAULT 0,
    ErrorType LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    ServiceTier LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),

    -- GAUGE/SUM VALUES
    Value Float64 DEFAULT 0 CODEC(ZSTD(1)),
    IntValue Int64 DEFAULT 0 CODEC(ZSTD(1)),
    IsMonotonic UInt8 DEFAULT 0,
    AggregationTemporality LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),

    -- HISTOGRAM VALUES
    HistogramCount UInt64 DEFAULT 0 CODEC(ZSTD(1)),
    HistogramSum Float64 DEFAULT 0 CODEC(ZSTD(1)),
    HistogramMin Float64 DEFAULT 0 CODEC(ZSTD(1)),
    HistogramMax Float64 DEFAULT 0 CODEC(ZSTD(1)),
    BucketCounts Array(UInt64) DEFAULT [] CODEC(ZSTD(1)),
    ExplicitBounds Array(Float64) DEFAULT [] CODEC(ZSTD(1)),

    -- EXEMPLARS (for linking to traces)
    `Exemplars.TraceId` Array(FixedString(32)) DEFAULT [] CODEC(ZSTD(1)),
    `Exemplars.SpanId` Array(FixedString(16)) DEFAULT [] CODEC(ZSTD(1)),
    `Exemplars.Value` Array(Float64) DEFAULT [] CODEC(ZSTD(1)),
    `Exemplars.Timestamp` Array(DateTime64(9)) DEFAULT [] CODEC(ZSTD(1)),

    -- OVERFLOW ATTRIBUTES
    AttributesJson String DEFAULT '{{}}' CODEC(ZSTD(1)),
    ResourceAttributesJson String DEFAULT '{{}}' CODEC(ZSTD(1)),

    -- COMPREHENSIVE INDEXES
    INDEX idx_metric_name MetricName TYPE bloom_filter GRANULARITY 1,
    INDEX idx_service_name ServiceName TYPE bloom_filter GRANULARITY 1,
    INDEX idx_operation GenAiOperationName TYPE bloom_filter GRANULARITY 1,
    INDEX idx_system GenAiSystem TYPE bloom_filter GRANULARITY 1,
    INDEX idx_request_model GenAiRequestModel TYPE bloom_filter GRANULARITY 1,
    INDEX idx_token_type GenAiTokenType TYPE bloom_filter GRANULARITY 1,
    INDEX idx_error_type ErrorType TYPE bloom_filter GRANULARITY 1,
    INDEX idx_metric_type MetricType TYPE bloom_filter GRANULARITY 1,

    INDEX idx_value_range Value TYPE minmax GRANULARITY 1,
    INDEX idx_histogram_sum_range HistogramSum TYPE minmax GRANULARITY 1,
    INDEX idx_histogram_count_range HistogramCount TYPE minmax GRANULARITY 1,
    INDEX idx_timestamp_range Timestamp TYPE minmax GRANULARITY 1
)
ENGINE = MergeTree()
PARTITION BY toDate(Timestamp)
ORDER BY (ServiceName, MetricName, GenAiSystem, GenAiRequestModel, toUnixTimestamp(Timestamp))
TTL toDateTime(Timestamp) + INTERVAL {ttl_days} DAY
SETTINGS index_granularity = 8192,
         ttl_only_drop_parts = 1
"""

# Logs table
LOGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {database}.{table} (
    -- TIMING
    Timestamp DateTime64(9) CODEC(Delta, ZSTD(1)),
    ObservedTimestamp DateTime64(9) CODEC(Delta, ZSTD(1)),

    -- TRACE CONTEXT (links logs to spans)
    TraceId FixedString(32) CODEC(ZSTD(1)),
    SpanId FixedString(16) CODEC(ZSTD(1)),
    TraceFlags UInt8 DEFAULT 0,

    -- SERVICE & RESOURCE INFO
    ServiceName LowCardinality(String) CODEC(ZSTD(1)),
    ServiceVersion String DEFAULT '' CODEC(ZSTD(1)),
    DeploymentEnvironment LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    InstrumentationScopeName LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),

    -- LOG RECORD
    SeverityText LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    SeverityNumber UInt8 DEFAULT 0,

    -- GENAI EVENT INFO (for structured GenAI log events)
    EventName LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    GenAiSystem LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),

    -- MESSAGE CONTENT (columnar for fast queries)
    MessageRole LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    MessageContent String DEFAULT '' CODEC(ZSTD(1)),
    ToolCallId String DEFAULT '' CODEC(ZSTD(1)),

    -- For gen_ai.choice events
    ChoiceIndex UInt8 DEFAULT 0,
    FinishReason LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    ChoiceMessageRole LowCardinality(String) DEFAULT '' CODEC(ZSTD(1)),
    ChoiceMessageContent String DEFAULT '' CODEC(ZSTD(1)),

    -- Tool calls in choices (flattened)
    ToolCallsJson String DEFAULT '[]' CODEC(ZSTD(1)),
    HasToolCalls UInt8 DEFAULT 0,

    -- RAW BODY (for non-structured logs)
    Body String DEFAULT '' CODEC(ZSTD(1)),
    BodyJson String DEFAULT '{{}}' CODEC(ZSTD(1)),

    -- OVERFLOW ATTRIBUTES
    LogAttributesJson String DEFAULT '{{}}' CODEC(ZSTD(1)),
    ResourceAttributesJson String DEFAULT '{{}}' CODEC(ZSTD(1)),

    -- COMPREHENSIVE INDEXES
    INDEX idx_trace_id TraceId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_span_id SpanId TYPE bloom_filter GRANULARITY 1,
    INDEX idx_event_name EventName TYPE bloom_filter GRANULARITY 1,
    INDEX idx_service_name ServiceName TYPE bloom_filter GRANULARITY 1,
    INDEX idx_system GenAiSystem TYPE bloom_filter GRANULARITY 1,
    INDEX idx_message_role MessageRole TYPE bloom_filter GRANULARITY 1,
    INDEX idx_finish_reason FinishReason TYPE bloom_filter GRANULARITY 1,
    INDEX idx_severity SeverityText TYPE bloom_filter GRANULARITY 1,
    INDEX idx_has_tool_calls HasToolCalls TYPE set(2) GRANULARITY 1,

    -- Text search
    INDEX idx_message_content MessageContent TYPE ngrambf_v1(4, 1024, 2, 0) GRANULARITY 1,
    INDEX idx_choice_content ChoiceMessageContent TYPE ngrambf_v1(4, 1024, 2, 0) GRANULARITY 1,
    INDEX idx_body Body TYPE ngrambf_v1(4, 1024, 2, 0) GRANULARITY 1,

    INDEX idx_timestamp_range Timestamp TYPE minmax GRANULARITY 1
)
ENGINE = MergeTree()
PARTITION BY toDate(Timestamp)
ORDER BY (ServiceName, EventName, MessageRole, toUnixTimestamp(Timestamp), TraceId, SpanId)
TTL toDateTime(Timestamp) + INTERVAL {ttl_days} DAY
SETTINGS index_granularity = 8192,
         ttl_only_drop_parts = 1
"""

# Database creation
CREATE_DATABASE_SQL = "CREATE DATABASE IF NOT EXISTS {database}"
