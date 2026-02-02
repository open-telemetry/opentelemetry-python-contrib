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

"""Common Pydantic schemas for GenAI Analytics API."""

from datetime import datetime
from enum import Enum
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field


class Granularity(str, Enum):
    """Time granularity for aggregations."""

    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class TimeRange(BaseModel):
    """Time range for queries."""

    start: datetime
    end: datetime


class ResponseMeta(BaseModel):
    """Metadata for API responses."""

    time_range: TimeRange
    granularity: Optional[Granularity] = None
    filters_applied: dict[str, Any] = Field(default_factory=dict)
    query_time_ms: Optional[float] = None


T = TypeVar("T")


class AnalyticsResponse(BaseModel, Generic[T]):
    """Generic analytics response wrapper."""

    data: T
    meta: ResponseMeta


# =========================================================================
# Cost Schemas
# =========================================================================


class CostDataPoint(BaseModel):
    """Single cost data point in time series."""

    timestamp: datetime
    total_cost: float
    request_count: int
    total_input_tokens: int
    total_output_tokens: int


class CostTotals(BaseModel):
    """Aggregated cost totals."""

    total_cost: float
    request_count: int
    total_input_tokens: int
    total_output_tokens: int
    avg_cost_per_request: float


class ModelCostData(BaseModel):
    """Cost data for a specific model."""

    time_series: list[CostDataPoint]
    totals: CostTotals


class ProviderCostData(BaseModel):
    """Cost data grouped by model within a provider."""

    models: dict[str, ModelCostData] = Field(default_factory=dict)
    totals: CostTotals


class CostAnalyticsData(BaseModel):
    """Nested cost analytics data by provider and model."""

    providers: dict[str, ProviderCostData] = Field(default_factory=dict)
    totals: CostTotals


# =========================================================================
# Token Schemas
# =========================================================================


class TokenDataPoint(BaseModel):
    """Single token usage data point."""

    timestamp: datetime
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    avg_input_tokens: float
    avg_output_tokens: float
    request_count: int


class TokenTotals(BaseModel):
    """Aggregated token totals."""

    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    avg_input_tokens: float
    avg_output_tokens: float
    request_count: int


class ProviderTokenData(BaseModel):
    """Token data for a provider."""

    time_series: list[TokenDataPoint]
    totals: TokenTotals


class TokenAnalyticsData(BaseModel):
    """Nested token analytics data by provider."""

    providers: dict[str, ProviderTokenData] = Field(default_factory=dict)
    totals: TokenTotals


# =========================================================================
# Latency Schemas
# =========================================================================


class LatencyPercentiles(BaseModel):
    """Latency percentile values."""

    p50: float
    p75: float
    p90: float
    p95: float
    p99: float
    avg: float
    min: float
    max: float
    request_count: int


class LatencyDataPoint(BaseModel):
    """Single latency data point in time series."""

    timestamp: datetime
    p50: float
    p95: float
    p99: float
    avg: float
    request_count: int


class ModelLatencyData(BaseModel):
    """Latency data for a specific model."""

    percentiles: LatencyPercentiles
    time_series: list[LatencyDataPoint] = Field(default_factory=list)


class ProviderLatencyData(BaseModel):
    """Latency data grouped by model within a provider."""

    models: dict[str, ModelLatencyData] = Field(default_factory=dict)


class LatencyAnalyticsData(BaseModel):
    """Nested latency analytics data by provider and model."""

    providers: dict[str, ProviderLatencyData] = Field(default_factory=dict)


# =========================================================================
# Error Schemas
# =========================================================================


class ErrorBreakdown(BaseModel):
    """Error breakdown by type."""

    error_type: str
    status_code: str
    count: int


class ErrorDataPoint(BaseModel):
    """Single error data point in time series."""

    timestamp: datetime
    total_requests: int
    error_count: int
    error_rate: float


class ModelErrorData(BaseModel):
    """Error data for a specific model."""

    total_requests: int
    error_count: int
    error_rate: float
    breakdown: list[ErrorBreakdown] = Field(default_factory=list)


class ProviderErrorData(BaseModel):
    """Error data grouped by model within a provider."""

    models: dict[str, ModelErrorData] = Field(default_factory=dict)
    total_requests: int
    error_count: int
    error_rate: float


class ErrorAnalyticsData(BaseModel):
    """Nested error analytics data by provider."""

    providers: dict[str, ProviderErrorData] = Field(default_factory=dict)
    time_series: list[ErrorDataPoint] = Field(default_factory=list)
    total_requests: int
    total_errors: int
    overall_error_rate: float


# =========================================================================
# Model Usage Schemas
# =========================================================================


class ModelUsageStats(BaseModel):
    """Usage statistics for a model."""

    request_count: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost: float
    avg_latency: float
    error_rate: float


class ProviderModelUsage(BaseModel):
    """Model usage grouped by provider."""

    models: dict[str, ModelUsageStats] = Field(default_factory=dict)
    total_requests: int


class ModelAnalyticsData(BaseModel):
    """Model usage analytics data."""

    providers: dict[str, ProviderModelUsage] = Field(default_factory=dict)
    total_requests: int
    unique_models: int


# =========================================================================
# User/Tenant Schemas
# =========================================================================


class UserStats(BaseModel):
    """Statistics for a single user."""

    user_id: str
    request_count: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost: float
    avg_latency: float
    session_count: int
    first_seen: datetime
    last_seen: datetime


class UserAnalyticsData(BaseModel):
    """User analytics data."""

    users: list[UserStats]
    total_users: int


class TenantStats(BaseModel):
    """Statistics for a single tenant."""

    tenant_id: str
    request_count: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost: float
    avg_latency: float
    unique_users: int
    session_count: int


class TenantAnalyticsData(BaseModel):
    """Tenant analytics data."""

    tenants: list[TenantStats]
    total_tenants: int


# =========================================================================
# Session Schemas
# =========================================================================


class SessionInfo(BaseModel):
    """Information about a single session."""

    session_id: str
    user_id: str
    tenant_id: str
    start_time: datetime
    end_time: Optional[datetime]
    duration_ms: int
    turn_count: int
    message_count: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost: float
    tool_call_count: int
    status: str
    final_outcome: str
    primary_agent: str


class SessionSummary(BaseModel):
    """Summary statistics for sessions."""

    total_sessions: int
    avg_turns: float
    avg_messages: float
    avg_duration_ms: float
    total_cost: float
    avg_cost_per_session: float
    completed_sessions: int
    abandoned_sessions: int
    error_sessions: int


class SessionAnalyticsData(BaseModel):
    """Session analytics data."""

    sessions: list[SessionInfo]
    summary: SessionSummary


# =========================================================================
# Tool Schemas
# =========================================================================


class ToolStats(BaseModel):
    """Statistics for a single tool."""

    tool_name: str
    tool_type: str
    invocation_count: int
    success_count: int
    error_count: int
    success_rate: float
    avg_duration: float
    p50_duration: float
    p95_duration: float
    p99_duration: float


class ToolDataPoint(BaseModel):
    """Tool usage data point in time series."""

    timestamp: datetime
    tool_name: str
    invocation_count: int
    success_rate: float
    avg_duration: float


class ToolAnalyticsData(BaseModel):
    """Tool analytics data."""

    tools: list[ToolStats]
    time_series: list[ToolDataPoint] = Field(default_factory=list)
    total_invocations: int


# =========================================================================
# Provider Comparison Schemas
# =========================================================================


class ProviderStats(BaseModel):
    """Comprehensive statistics for a provider."""

    provider: str
    request_count: int
    total_cost: float
    avg_cost_per_request: float
    total_input_tokens: int
    total_output_tokens: int
    avg_latency: float
    p50_latency: float
    p95_latency: float
    p99_latency: float
    error_count: int
    error_rate: float
    models_used: int


class ProviderComparisonData(BaseModel):
    """Provider comparison analytics data."""

    providers: list[ProviderStats]


# =========================================================================
# Audit Schemas
# =========================================================================


class AuditSpan(BaseModel):
    """Audit trail span information."""

    trace_id: str
    span_id: str
    parent_span_id: str
    session_id: str
    timestamp: datetime
    end_timestamp: datetime
    duration_ms: int
    service_name: str
    span_name: str
    operation_type: str
    provider: str
    request_model: str
    response_model: str
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    finish_reason: str
    has_error: bool
    error_type: str
    status_message: str
    user_id: str
    tenant_id: str
    agent_name: str


class AuditMessage(BaseModel):
    """Audit trail message."""

    trace_id: str
    span_id: str
    message_index: int
    timestamp: datetime
    role: str
    content: str
    tool_calls: str
    tool_call_id: str
    tool_name: str
    token_count: int


class AuditToolCall(BaseModel):
    """Audit trail tool call."""

    id: str
    trace_id: str
    span_id: str
    tool_call_id: str
    timestamp: datetime
    duration_ms: int
    tool_name: str
    tool_type: str
    tool_input: str
    tool_output: str
    tool_error: str
    status: str


class TraceDetail(BaseModel):
    """Detailed trace information with messages and tool calls."""

    span: AuditSpan
    messages: list[AuditMessage] = Field(default_factory=list)
    tool_calls: list[AuditToolCall] = Field(default_factory=list)


class AuditAnalyticsData(BaseModel):
    """Audit analytics data."""

    spans: list[AuditSpan]
    total_count: int
    page: int
    page_size: int
