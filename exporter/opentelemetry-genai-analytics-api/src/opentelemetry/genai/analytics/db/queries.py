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

"""SQL query builder for GenAI Analytics."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from opentelemetry.genai.analytics.config import settings
from opentelemetry.genai.analytics.schemas.common import Granularity


class Table(str, Enum):
    """ClickHouse table names."""

    GENAI_SPANS = "genai_spans"
    SPANS = "spans"
    TOOL_CALLS = "genai_tool_calls"
    RETRIEVALS = "genai_retrievals"
    SESSIONS = "genai_sessions"
    MESSAGES = "genai_messages"
    METRICS = "genai_metrics"


# Allowlist of valid column names for filtering to prevent SQL injection
ALLOWED_FILTER_COLUMNS = frozenset({
    "TraceId",
    "SpanId",
    "ParentSpanId",
    "SessionId",
    "ServiceName",
    "SpanName",
    "OperationType",
    "Provider",
    "RequestModel",
    "ResponseModel",
    "FinishReason",
    "HasError",
    "ErrorType",
    "StatusCode",
    "StatusMessage",
    "UserId",
    "TenantId",
    "AgentName",
    "ToolName",
    "ToolType",
    "Status",
})

# Allowlist of valid column names for GROUP BY clauses to prevent SQL injection
ALLOWED_GROUP_BY_COLUMNS = frozenset({
    "Provider",
    "RequestModel",
    "ResponseModel",
    "ServiceName",
    "UserId",
    "TenantId",
    "SessionId",
    "AgentName",
    "OperationType",
    "FinishReason",
    "ErrorType",
    "StatusCode",
    "ToolName",
    "ToolType",
})


GRANULARITY_FUNCTIONS = {
    Granularity.MINUTE: "toStartOfMinute",
    Granularity.HOUR: "toStartOfHour",
    Granularity.DAY: "toStartOfDay",
    Granularity.WEEK: "toStartOfWeek",
    Granularity.MONTH: "toStartOfMonth",
}


class QueryBuilder:
    """SQL query builder for analytics queries."""

    def __init__(self, database: Optional[str] = None):
        """Initialize query builder.

        Args:
            database: Database name. Uses settings if not provided.
        """
        self.database = database or settings.clickhouse.database

    def _table(self, table: Table) -> str:
        """Get fully qualified table name."""
        return f"{self.database}.{table.value}"

    def _validate_group_by(self, group_by: list[str]) -> None:
        """Validate group_by columns against allowlist.

        Args:
            group_by: List of column names to validate.

        Raises:
            ValueError: If any column is not in the allowlist.
        """
        for col in group_by:
            if col not in ALLOWED_GROUP_BY_COLUMNS:
                raise ValueError(f"Invalid group_by column: {col}")

    def _time_bucket(self, granularity: Granularity, column: str = "Timestamp") -> str:
        """Get time bucket expression."""
        func = GRANULARITY_FUNCTIONS[granularity]
        return f"{func}({column})"

    def _build_filters(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        service_name: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        has_error: Optional[bool] = None,
        extra_filters: Optional[dict[str, Any]] = None,
    ) -> tuple[list[str], dict[str, Any]]:
        """Build WHERE clause filters.

        Returns:
            Tuple of (filter_clauses, params).
        """
        filters = []
        params = {}

        if start_time:
            filters.append("Timestamp >= %(start_time)s")
            params["start_time"] = start_time

        if end_time:
            filters.append("Timestamp <= %(end_time)s")
            params["end_time"] = end_time

        if service_name:
            filters.append("ServiceName = %(service_name)s")
            params["service_name"] = service_name

        if provider:
            filters.append("Provider = %(provider)s")
            params["provider"] = provider

        if model:
            filters.append("RequestModel = %(model)s")
            params["model"] = model

        if tenant_id:
            filters.append("TenantId = %(tenant_id)s")
            params["tenant_id"] = tenant_id

        if user_id:
            filters.append("UserId = %(user_id)s")
            params["user_id"] = user_id

        if session_id:
            filters.append("SessionId = %(session_id)s")
            params["session_id"] = session_id

        if has_error is not None:
            filters.append("HasError = %(has_error)s")
            params["has_error"] = 1 if has_error else 0

        if extra_filters:
            for key, value in extra_filters.items():
                # Validate column name to prevent SQL injection
                if key not in ALLOWED_FILTER_COLUMNS:
                    raise ValueError(f"Invalid filter column: {key}")
                filters.append(f"{key} = %({key})s")
                params[key] = value

        return filters, params

    def _where_clause(self, filters: list[str]) -> str:
        """Build WHERE clause from filters."""
        if not filters:
            return ""
        return "WHERE " + " AND ".join(filters)

    # =========================================================================
    # Cost Analytics Queries
    # =========================================================================

    def cost_by_dimensions(
        self,
        granularity: Granularity,
        group_by: list[str],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        **filters,
    ) -> tuple[str, dict[str, Any]]:
        """Build cost analytics query.

        Args:
            granularity: Time granularity.
            group_by: Columns to group by (e.g., ["Provider", "RequestModel"]).
            start_time: Start of time range.
            end_time: End of time range.
            **filters: Additional filters.

        Returns:
            Tuple of (query, params).
        """
        self._validate_group_by(group_by)
        filter_clauses, params = self._build_filters(
            start_time=start_time, end_time=end_time, **filters
        )

        time_bucket = self._time_bucket(granularity)
        group_cols = ", ".join(group_by)
        select_cols = ", ".join(group_by)

        query = f"""
        SELECT
            {time_bucket} AS time_bucket,
            {select_cols},
            sum(EstimatedCostUsd) AS total_cost,
            count() AS request_count,
            sum(InputTokens) AS total_input_tokens,
            sum(OutputTokens) AS total_output_tokens
        FROM {self._table(Table.GENAI_SPANS)}
        {self._where_clause(filter_clauses)}
        GROUP BY time_bucket, {group_cols}
        ORDER BY time_bucket, {group_cols}
        """

        return query, params

    def cost_totals(
        self,
        group_by: list[str],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        **filters,
    ) -> tuple[str, dict[str, Any]]:
        """Build cost totals query (no time series)."""
        self._validate_group_by(group_by)
        filter_clauses, params = self._build_filters(
            start_time=start_time, end_time=end_time, **filters
        )

        group_cols = ", ".join(group_by)
        select_cols = ", ".join(group_by)

        query = f"""
        SELECT
            {select_cols},
            sum(EstimatedCostUsd) AS total_cost,
            count() AS request_count,
            sum(InputTokens) AS total_input_tokens,
            sum(OutputTokens) AS total_output_tokens,
            avg(EstimatedCostUsd) AS avg_cost_per_request
        FROM {self._table(Table.GENAI_SPANS)}
        {self._where_clause(filter_clauses)}
        GROUP BY {group_cols}
        ORDER BY total_cost DESC
        """

        return query, params

    # =========================================================================
    # Token Analytics Queries
    # =========================================================================

    def token_usage(
        self,
        granularity: Granularity,
        group_by: list[str],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        **filters,
    ) -> tuple[str, dict[str, Any]]:
        """Build token usage query."""
        if group_by:
            self._validate_group_by(group_by)
        filter_clauses, params = self._build_filters(
            start_time=start_time, end_time=end_time, **filters
        )

        time_bucket = self._time_bucket(granularity)
        group_cols = ", ".join(group_by) if group_by else ""
        select_cols = ", ".join(group_by) if group_by else ""

        group_clause = f"time_bucket, {group_cols}" if group_cols else "time_bucket"
        select_part = f"{select_cols}," if select_cols else ""

        query = f"""
        SELECT
            {time_bucket} AS time_bucket,
            {select_part}
            sum(InputTokens) AS total_input_tokens,
            sum(OutputTokens) AS total_output_tokens,
            sum(TotalTokens) AS total_tokens,
            avg(InputTokens) AS avg_input_tokens,
            avg(OutputTokens) AS avg_output_tokens,
            count() AS request_count
        FROM {self._table(Table.GENAI_SPANS)}
        {self._where_clause(filter_clauses)}
        GROUP BY {group_clause}
        ORDER BY time_bucket
        """

        return query, params

    # =========================================================================
    # Latency Analytics Queries
    # =========================================================================

    def latency_percentiles(
        self,
        group_by: list[str],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        **filters,
    ) -> tuple[str, dict[str, Any]]:
        """Build latency percentiles query."""
        self._validate_group_by(group_by)
        filter_clauses, params = self._build_filters(
            start_time=start_time, end_time=end_time, **filters
        )

        group_cols = ", ".join(group_by)
        select_cols = ", ".join(group_by)

        query = f"""
        SELECT
            {select_cols},
            quantile(0.50)(DurationMs) AS p50,
            quantile(0.75)(DurationMs) AS p75,
            quantile(0.90)(DurationMs) AS p90,
            quantile(0.95)(DurationMs) AS p95,
            quantile(0.99)(DurationMs) AS p99,
            avg(DurationMs) AS avg_latency,
            min(DurationMs) AS min_latency,
            max(DurationMs) AS max_latency,
            count() AS request_count
        FROM {self._table(Table.GENAI_SPANS)}
        {self._where_clause(filter_clauses)}
        GROUP BY {group_cols}
        ORDER BY request_count DESC
        """

        return query, params

    def latency_time_series(
        self,
        granularity: Granularity,
        group_by: list[str],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        **filters,
    ) -> tuple[str, dict[str, Any]]:
        """Build latency time series query."""
        if group_by:
            self._validate_group_by(group_by)
        filter_clauses, params = self._build_filters(
            start_time=start_time, end_time=end_time, **filters
        )

        time_bucket = self._time_bucket(granularity)
        group_cols = ", ".join(group_by) if group_by else ""
        select_cols = ", ".join(group_by) if group_by else ""

        group_clause = f"time_bucket, {group_cols}" if group_cols else "time_bucket"
        select_part = f"{select_cols}," if select_cols else ""

        query = f"""
        SELECT
            {time_bucket} AS time_bucket,
            {select_part}
            quantile(0.50)(DurationMs) AS p50,
            quantile(0.95)(DurationMs) AS p95,
            quantile(0.99)(DurationMs) AS p99,
            avg(DurationMs) AS avg_latency,
            count() AS request_count
        FROM {self._table(Table.GENAI_SPANS)}
        {self._where_clause(filter_clauses)}
        GROUP BY {group_clause}
        ORDER BY time_bucket
        """

        return query, params

    # =========================================================================
    # Error Analytics Queries
    # =========================================================================

    def error_rates(
        self,
        group_by: list[str],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        **filters,
    ) -> tuple[str, dict[str, Any]]:
        """Build error rates query."""
        self._validate_group_by(group_by)
        filter_clauses, params = self._build_filters(
            start_time=start_time, end_time=end_time, **filters
        )

        group_cols = ", ".join(group_by)
        select_cols = ", ".join(group_by)

        query = f"""
        SELECT
            {select_cols},
            count() AS total_requests,
            countIf(HasError = 1) AS error_count,
            countIf(HasError = 1) / count() AS error_rate
        FROM {self._table(Table.GENAI_SPANS)}
        {self._where_clause(filter_clauses)}
        GROUP BY {group_cols}
        ORDER BY error_count DESC
        """

        return query, params

    def error_breakdown(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        **filters,
    ) -> tuple[str, dict[str, Any]]:
        """Build error breakdown by type query."""
        filter_clauses, params = self._build_filters(
            start_time=start_time, end_time=end_time, has_error=True, **filters
        )

        query = f"""
        SELECT
            Provider,
            RequestModel,
            ErrorType,
            StatusCode,
            count() AS error_count
        FROM {self._table(Table.GENAI_SPANS)}
        {self._where_clause(filter_clauses)}
        GROUP BY Provider, RequestModel, ErrorType, StatusCode
        ORDER BY error_count DESC
        """

        return query, params

    def error_time_series(
        self,
        granularity: Granularity,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        **filters,
    ) -> tuple[str, dict[str, Any]]:
        """Build error time series query."""
        filter_clauses, params = self._build_filters(
            start_time=start_time, end_time=end_time, **filters
        )

        time_bucket = self._time_bucket(granularity)

        query = f"""
        SELECT
            {time_bucket} AS time_bucket,
            count() AS total_requests,
            countIf(HasError = 1) AS error_count,
            countIf(HasError = 1) / count() AS error_rate
        FROM {self._table(Table.GENAI_SPANS)}
        {self._where_clause(filter_clauses)}
        GROUP BY time_bucket
        ORDER BY time_bucket
        """

        return query, params

    # =========================================================================
    # Model Analytics Queries
    # =========================================================================

    def model_usage(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        **filters,
    ) -> tuple[str, dict[str, Any]]:
        """Build model usage distribution query."""
        filter_clauses, params = self._build_filters(
            start_time=start_time, end_time=end_time, **filters
        )

        query = f"""
        SELECT
            Provider,
            RequestModel,
            count() AS request_count,
            sum(InputTokens) AS total_input_tokens,
            sum(OutputTokens) AS total_output_tokens,
            sum(EstimatedCostUsd) AS total_cost,
            avg(DurationMs) AS avg_latency,
            countIf(HasError = 1) / count() AS error_rate
        FROM {self._table(Table.GENAI_SPANS)}
        {self._where_clause(filter_clauses)}
        GROUP BY Provider, RequestModel
        ORDER BY request_count DESC
        """

        return query, params

    # =========================================================================
    # User/Tenant Analytics Queries
    # =========================================================================

    def user_analytics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        **filters,
    ) -> tuple[str, dict[str, Any]]:
        """Build user analytics query."""
        filter_clauses, params = self._build_filters(
            start_time=start_time, end_time=end_time, **filters
        )
        # Filter out empty user IDs
        filter_clauses.append("UserId != ''")
        params["limit"] = limit

        query = f"""
        SELECT
            UserId,
            count() AS request_count,
            sum(InputTokens) AS total_input_tokens,
            sum(OutputTokens) AS total_output_tokens,
            sum(EstimatedCostUsd) AS total_cost,
            avg(DurationMs) AS avg_latency,
            uniqExact(SessionId) AS session_count,
            min(Timestamp) AS first_seen,
            max(Timestamp) AS last_seen
        FROM {self._table(Table.GENAI_SPANS)}
        {self._where_clause(filter_clauses)}
        GROUP BY UserId
        ORDER BY total_cost DESC
        LIMIT %(limit)s
        """

        return query, params

    def tenant_analytics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        **filters,
    ) -> tuple[str, dict[str, Any]]:
        """Build tenant analytics query."""
        filter_clauses, params = self._build_filters(
            start_time=start_time, end_time=end_time, **filters
        )
        # Filter out empty tenant IDs
        filter_clauses.append("TenantId != ''")
        params["limit"] = limit

        query = f"""
        SELECT
            TenantId,
            count() AS request_count,
            sum(InputTokens) AS total_input_tokens,
            sum(OutputTokens) AS total_output_tokens,
            sum(EstimatedCostUsd) AS total_cost,
            avg(DurationMs) AS avg_latency,
            uniqExact(UserId) AS unique_users,
            uniqExact(SessionId) AS session_count
        FROM {self._table(Table.GENAI_SPANS)}
        {self._where_clause(filter_clauses)}
        GROUP BY TenantId
        ORDER BY total_cost DESC
        LIMIT %(limit)s
        """

        return query, params

    # =========================================================================
    # Session Analytics Queries
    # =========================================================================

    def session_analytics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        **filters,
    ) -> tuple[str, dict[str, Any]]:
        """Build session analytics query from sessions table."""
        params = {"limit": limit}

        filter_clauses = []
        if start_time:
            filter_clauses.append("StartTime >= %(start_time)s")
            params["start_time"] = start_time
        if end_time:
            filter_clauses.append("StartTime <= %(end_time)s")
            params["end_time"] = end_time
        if user_id:
            filter_clauses.append("UserId = %(user_id)s")
            params["user_id"] = user_id
        if tenant_id:
            filter_clauses.append("TenantId = %(tenant_id)s")
            params["tenant_id"] = tenant_id

        query = f"""
        SELECT
            SessionId,
            UserId,
            TenantId,
            StartTime,
            EndTime,
            DurationMs,
            TurnCount,
            MessageCount,
            TotalInputTokens,
            TotalOutputTokens,
            TotalCostUsd,
            ToolCallCount,
            Status,
            FinalOutcome,
            PrimaryAgentName
        FROM {self._table(Table.SESSIONS)}
        {self._where_clause(filter_clauses)}
        ORDER BY StartTime DESC
        LIMIT %(limit)s
        """

        return query, params

    def session_summary(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        **filters,
    ) -> tuple[str, dict[str, Any]]:
        """Build session summary statistics query."""
        params = {}

        filter_clauses = []
        if start_time:
            filter_clauses.append("StartTime >= %(start_time)s")
            params["start_time"] = start_time
        if end_time:
            filter_clauses.append("StartTime <= %(end_time)s")
            params["end_time"] = end_time
        if user_id:
            filter_clauses.append("UserId = %(user_id)s")
            params["user_id"] = user_id
        if tenant_id:
            filter_clauses.append("TenantId = %(tenant_id)s")
            params["tenant_id"] = tenant_id

        query = f"""
        SELECT
            count() AS total_sessions,
            avg(TurnCount) AS avg_turns,
            avg(MessageCount) AS avg_messages,
            avg(DurationMs) AS avg_duration_ms,
            sum(TotalCostUsd) AS total_cost,
            avg(TotalCostUsd) AS avg_cost_per_session,
            countIf(Status = 'completed') AS completed_sessions,
            countIf(Status = 'abandoned') AS abandoned_sessions,
            countIf(Status = 'error') AS error_sessions
        FROM {self._table(Table.SESSIONS)}
        {self._where_clause(filter_clauses)}
        """

        return query, params

    # =========================================================================
    # Tool Analytics Queries
    # =========================================================================

    def tool_usage(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        tool_name: Optional[str] = None,
        **filters,
    ) -> tuple[str, dict[str, Any]]:
        """Build tool usage analytics query."""
        params = {"limit": limit}

        filter_clauses = []
        if start_time:
            filter_clauses.append("Timestamp >= %(start_time)s")
            params["start_time"] = start_time
        if end_time:
            filter_clauses.append("Timestamp <= %(end_time)s")
            params["end_time"] = end_time
        if tool_name:
            filter_clauses.append("ToolName = %(tool_name)s")
            params["tool_name"] = tool_name

        query = f"""
        SELECT
            ToolName,
            ToolType,
            count() AS invocation_count,
            countIf(Status = 'success') AS success_count,
            countIf(Status = 'error') AS error_count,
            countIf(Status = 'success') / count() AS success_rate,
            avg(DurationMs) AS avg_duration,
            quantile(0.50)(DurationMs) AS p50_duration,
            quantile(0.95)(DurationMs) AS p95_duration,
            quantile(0.99)(DurationMs) AS p99_duration
        FROM {self._table(Table.TOOL_CALLS)}
        {self._where_clause(filter_clauses)}
        GROUP BY ToolName, ToolType
        ORDER BY invocation_count DESC
        LIMIT %(limit)s
        """

        return query, params

    def tool_time_series(
        self,
        granularity: Granularity,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        tool_name: Optional[str] = None,
        **filters,
    ) -> tuple[str, dict[str, Any]]:
        """Build tool usage time series query."""
        params = {}

        filter_clauses = []
        if start_time:
            filter_clauses.append("Timestamp >= %(start_time)s")
            params["start_time"] = start_time
        if end_time:
            filter_clauses.append("Timestamp <= %(end_time)s")
            params["end_time"] = end_time
        if tool_name:
            filter_clauses.append("ToolName = %(tool_name)s")
            params["tool_name"] = tool_name

        time_bucket = self._time_bucket(granularity)

        query = f"""
        SELECT
            {time_bucket} AS time_bucket,
            ToolName,
            count() AS invocation_count,
            countIf(Status = 'success') / count() AS success_rate,
            avg(DurationMs) AS avg_duration
        FROM {self._table(Table.TOOL_CALLS)}
        {self._where_clause(filter_clauses)}
        GROUP BY time_bucket, ToolName
        ORDER BY time_bucket, invocation_count DESC
        """

        return query, params

    # =========================================================================
    # Provider Comparison Queries
    # =========================================================================

    def provider_comparison(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        **filters,
    ) -> tuple[str, dict[str, Any]]:
        """Build provider comparison query."""
        filter_clauses, params = self._build_filters(
            start_time=start_time, end_time=end_time, **filters
        )

        query = f"""
        SELECT
            Provider,
            count() AS request_count,
            sum(EstimatedCostUsd) AS total_cost,
            avg(EstimatedCostUsd) AS avg_cost_per_request,
            sum(InputTokens) AS total_input_tokens,
            sum(OutputTokens) AS total_output_tokens,
            avg(DurationMs) AS avg_latency,
            quantile(0.50)(DurationMs) AS p50_latency,
            quantile(0.95)(DurationMs) AS p95_latency,
            quantile(0.99)(DurationMs) AS p99_latency,
            countIf(HasError = 1) AS error_count,
            countIf(HasError = 1) / count() AS error_rate,
            uniqExact(RequestModel) AS models_used
        FROM {self._table(Table.GENAI_SPANS)}
        {self._where_clause(filter_clauses)}
        GROUP BY Provider
        ORDER BY request_count DESC
        """

        return query, params

    # =========================================================================
    # Audit Trail Queries
    # =========================================================================

    def audit_traces(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
        **filters,
    ) -> tuple[str, dict[str, Any]]:
        """Build audit trail query."""
        filter_clauses, params = self._build_filters(
            start_time=start_time, end_time=end_time, **filters
        )
        params["limit"] = limit
        params["offset"] = offset

        query = f"""
        SELECT
            TraceId,
            SpanId,
            ParentSpanId,
            SessionId,
            Timestamp,
            EndTimestamp,
            DurationMs,
            ServiceName,
            SpanName,
            OperationType,
            Provider,
            RequestModel,
            ResponseModel,
            InputTokens,
            OutputTokens,
            EstimatedCostUsd,
            FinishReason,
            HasError,
            ErrorType,
            StatusMessage,
            UserId,
            TenantId,
            AgentName
        FROM {self._table(Table.GENAI_SPANS)}
        {self._where_clause(filter_clauses)}
        ORDER BY Timestamp DESC
        LIMIT %(limit)s
        OFFSET %(offset)s
        """

        return query, params

    def audit_traces_count(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        **filters,
    ) -> tuple[str, dict[str, Any]]:
        """Build audit trail count query for pagination."""
        filter_clauses, params = self._build_filters(
            start_time=start_time, end_time=end_time, **filters
        )

        query = f"""
        SELECT count() AS total_count
        FROM {self._table(Table.GENAI_SPANS)}
        {self._where_clause(filter_clauses)}
        """

        return query, params

    def user_count(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        **filters,
    ) -> tuple[str, dict[str, Any]]:
        """Build user count query for pagination."""
        filter_clauses, params = self._build_filters(
            start_time=start_time, end_time=end_time, **filters
        )
        filter_clauses.append("UserId != ''")

        query = f"""
        SELECT uniqExact(UserId) AS total_count
        FROM {self._table(Table.GENAI_SPANS)}
        {self._where_clause(filter_clauses)}
        """

        return query, params

    def tenant_count(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        **filters,
    ) -> tuple[str, dict[str, Any]]:
        """Build tenant count query for pagination."""
        filter_clauses, params = self._build_filters(
            start_time=start_time, end_time=end_time, **filters
        )
        filter_clauses.append("TenantId != ''")

        query = f"""
        SELECT uniqExact(TenantId) AS total_count
        FROM {self._table(Table.GENAI_SPANS)}
        {self._where_clause(filter_clauses)}
        """

        return query, params

    def trace_messages(
        self, trace_id: str, span_id: Optional[str] = None
    ) -> tuple[str, dict[str, Any]]:
        """Get messages for a specific trace."""
        params = {"trace_id": trace_id}

        filters = ["TraceId = %(trace_id)s"]
        if span_id:
            filters.append("SpanId = %(span_id)s")
            params["span_id"] = span_id

        query = f"""
        SELECT
            TraceId,
            SpanId,
            MessageIndex,
            Timestamp,
            Role,
            Content,
            ToolCalls,
            ToolCallId,
            ToolName,
            TokenCount
        FROM {self._table(Table.MESSAGES)}
        {self._where_clause(filters)}
        ORDER BY Timestamp, MessageIndex
        """

        return query, params

    def trace_tool_calls(
        self, trace_id: str, span_id: Optional[str] = None
    ) -> tuple[str, dict[str, Any]]:
        """Get tool calls for a specific trace."""
        params = {"trace_id": trace_id}

        filters = ["TraceId = %(trace_id)s"]
        if span_id:
            filters.append("SpanId = %(span_id)s")
            params["span_id"] = span_id

        query = f"""
        SELECT
            Id,
            TraceId,
            SpanId,
            ToolCallId,
            Timestamp,
            DurationMs,
            ToolName,
            ToolType,
            ToolInput,
            ToolOutput,
            ToolError,
            Status
        FROM {self._table(Table.TOOL_CALLS)}
        {self._where_clause(filters)}
        ORDER BY Timestamp
        """

        return query, params
