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

"""Audit trail API endpoints."""

import logging
import time

from clickhouse_driver.errors import Error as ClickHouseError
from fastapi import APIRouter, Depends, HTTPException, Query

from opentelemetry.genai.analytics.api.dependencies import (
    CommonQueryParams,
    get_db_client,
    get_query_builder,
)
from opentelemetry.genai.analytics.db.connection import ClickHouseClient
from opentelemetry.genai.analytics.db.queries import QueryBuilder

logger = logging.getLogger(__name__)
from opentelemetry.genai.analytics.schemas.common import (
    AnalyticsResponse,
    AuditAnalyticsData,
    AuditMessage,
    AuditSpan,
    AuditToolCall,
    TraceDetail,
)

router = APIRouter()


@router.get("/traces", response_model=AnalyticsResponse[AuditAnalyticsData])
def get_audit_traces(
    params: CommonQueryParams = Depends(),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=1000, description="Items per page"),
    client: ClickHouseClient = Depends(get_db_client),
    query_builder: QueryBuilder = Depends(get_query_builder),
):
    """Get audit trail of LLM interactions.

    Returns a paginated list of spans with filtering support.
    """
    start = time.time()
    offset = (page - 1) * page_size

    try:
        # Get total count for pagination
        count_query, count_params = query_builder.audit_traces_count(
            start_time=params.start_time,
            end_time=params.end_time,
            **params.get_filters(),
        )
        count_result = client.execute(count_query, count_params)
        total_count = count_result[0][0] if count_result else 0

        # Get audit traces
        query, query_params = query_builder.audit_traces(
            start_time=params.start_time,
            end_time=params.end_time,
            limit=page_size,
            offset=offset,
            **params.get_filters(),
        )
        results = client.execute(query, query_params)
    except ClickHouseError as e:
        logger.error("Failed to query audit traces: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Build spans list
    spans = []
    for row in results:
        (
            trace_id,
            span_id,
            parent_span_id,
            session_id,
            timestamp,
            end_timestamp,
            duration_ms,
            service_name,
            span_name,
            operation_type,
            provider,
            request_model,
            response_model,
            input_tokens,
            output_tokens,
            estimated_cost,
            finish_reason,
            has_error,
            error_type,
            status_message,
            user_id,
            tenant_id,
            agent_name,
        ) = row

        spans.append(
            AuditSpan(
                trace_id=str(trace_id),
                span_id=str(span_id),
                parent_span_id=str(parent_span_id) if parent_span_id else "",
                session_id=str(session_id) if session_id else "",
                timestamp=timestamp,
                end_timestamp=end_timestamp,
                duration_ms=int(duration_ms),
                service_name=str(service_name),
                span_name=str(span_name),
                operation_type=str(operation_type) if operation_type else "",
                provider=str(provider) if provider else "",
                request_model=str(request_model) if request_model else "",
                response_model=str(response_model) if response_model else "",
                input_tokens=int(input_tokens),
                output_tokens=int(output_tokens),
                estimated_cost=float(estimated_cost),
                finish_reason=str(finish_reason) if finish_reason else "",
                has_error=bool(has_error),
                error_type=str(error_type) if error_type else "",
                status_message=str(status_message) if status_message else "",
                user_id=str(user_id) if user_id else "",
                tenant_id=str(tenant_id) if tenant_id else "",
                agent_name=str(agent_name) if agent_name else "",
            )
        )

    query_time_ms = (time.time() - start) * 1000

    return AnalyticsResponse(
        data=AuditAnalyticsData(
            spans=spans,
            total_count=total_count,
            page=page,
            page_size=page_size,
        ),
        meta=params.build_meta(query_time_ms=query_time_ms, include_granularity=False),
    )


@router.get("/traces/{trace_id}", response_model=TraceDetail)
def get_trace_detail(
    trace_id: str,
    span_id: str | None = Query(None, description="Filter to specific span"),
    client: ClickHouseClient = Depends(get_db_client),
    query_builder: QueryBuilder = Depends(get_query_builder),
):
    """Get detailed information for a specific trace.

    Returns the span along with its messages and tool calls.
    """
    try:
        # Build extra filters including span_id if provided
        extra_filters = {"TraceId": trace_id}
        if span_id:
            extra_filters["SpanId"] = span_id

        # Get the span
        span_query, span_params = query_builder.audit_traces(
            limit=1,
            extra_filters=extra_filters,
        )
        span_results = client.execute(span_query, span_params)
    except ClickHouseError as e:
        logger.error("Failed to query trace detail: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")

    if not span_results:
        raise HTTPException(status_code=404, detail="Trace not found")

    row = span_results[0]
    span = AuditSpan(
        trace_id=str(row[0]),
        span_id=str(row[1]),
        parent_span_id=str(row[2]) if row[2] else "",
        session_id=str(row[3]) if row[3] else "",
        timestamp=row[4],
        end_timestamp=row[5],
        duration_ms=int(row[6]),
        service_name=str(row[7]),
        span_name=str(row[8]),
        operation_type=str(row[9]) if row[9] else "",
        provider=str(row[10]) if row[10] else "",
        request_model=str(row[11]) if row[11] else "",
        response_model=str(row[12]) if row[12] else "",
        input_tokens=int(row[13]),
        output_tokens=int(row[14]),
        estimated_cost=float(row[15]),
        finish_reason=str(row[16]) if row[16] else "",
        has_error=bool(row[17]),
        error_type=str(row[18]) if row[18] else "",
        status_message=str(row[19]) if row[19] else "",
        user_id=str(row[20]) if row[20] else "",
        tenant_id=str(row[21]) if row[21] else "",
        agent_name=str(row[22]) if row[22] else "",
    )

    # Get messages
    msg_query, msg_params = query_builder.trace_messages(trace_id, span_id)
    msg_results = client.execute(msg_query, msg_params)

    messages = []
    for row in msg_results:
        messages.append(
            AuditMessage(
                trace_id=str(row[0]),
                span_id=str(row[1]),
                message_index=int(row[2]),
                timestamp=row[3],
                role=str(row[4]),
                content=str(row[5]),
                tool_calls=str(row[6]) if row[6] else "[]",
                tool_call_id=str(row[7]) if row[7] else "",
                tool_name=str(row[8]) if row[8] else "",
                token_count=int(row[9]),
            )
        )

    # Get tool calls
    tool_query, tool_params = query_builder.trace_tool_calls(trace_id, span_id)
    tool_results = client.execute(tool_query, tool_params)

    tool_calls = []
    for row in tool_results:
        tool_calls.append(
            AuditToolCall(
                id=str(row[0]),
                trace_id=str(row[1]),
                span_id=str(row[2]),
                tool_call_id=str(row[3]) if row[3] else "",
                timestamp=row[4],
                duration_ms=int(row[5]),
                tool_name=str(row[6]),
                tool_type=str(row[7]),
                tool_input=str(row[8]) if row[8] else "",
                tool_output=str(row[9]) if row[9] else "",
                tool_error=str(row[10]) if row[10] else "",
                status=str(row[11]),
            )
        )

    return TraceDetail(
        span=span,
        messages=messages,
        tool_calls=tool_calls,
    )
