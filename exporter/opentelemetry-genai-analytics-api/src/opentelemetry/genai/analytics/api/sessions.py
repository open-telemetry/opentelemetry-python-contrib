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

"""Session analytics API endpoints."""

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
from opentelemetry.genai.analytics.schemas.common import (
    AnalyticsResponse,
    SessionAnalyticsData,
    SessionInfo,
    SessionSummary,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/sessions", response_model=AnalyticsResponse[SessionAnalyticsData])
def get_session_analytics(
    params: CommonQueryParams = Depends(),
    limit: int = Query(100, ge=1, le=1000, description="Maximum sessions to return"),
    client: ClickHouseClient = Depends(get_db_client),
    query_builder: QueryBuilder = Depends(get_query_builder),
):
    """Get session analytics.

    Returns session information and summary statistics.
    """
    start = time.time()

    try:
        # Get session list
        sessions_query, sessions_params = query_builder.session_analytics(
            start_time=params.start_time,
            end_time=params.end_time,
            limit=limit,
            user_id=params.user_id,
            tenant_id=params.tenant_id,
        )
        sessions_results = client.execute(sessions_query, sessions_params)

        # Get session summary
        summary_query, summary_params = query_builder.session_summary(
            start_time=params.start_time,
            end_time=params.end_time,
            user_id=params.user_id,
            tenant_id=params.tenant_id,
        )
        summary_results = client.execute(summary_query, summary_params)
    except ClickHouseError as e:
        logger.error("Failed to query session analytics: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Build sessions list
    sessions = []
    for row in sessions_results:
        (
            session_id,
            user_id,
            tenant_id,
            start_time_val,
            end_time_val,
            duration_ms,
            turn_count,
            message_count,
            total_input,
            total_output,
            total_cost,
            tool_call_count,
            status,
            final_outcome,
            primary_agent,
        ) = row

        sessions.append(
            SessionInfo(
                session_id=str(session_id),
                user_id=str(user_id) if user_id else "",
                tenant_id=str(tenant_id) if tenant_id else "",
                start_time=start_time_val,
                end_time=end_time_val,
                duration_ms=int(duration_ms),
                turn_count=int(turn_count),
                message_count=int(message_count),
                total_input_tokens=int(total_input),
                total_output_tokens=int(total_output),
                total_cost=float(total_cost),
                tool_call_count=int(tool_call_count),
                status=str(status),
                final_outcome=str(final_outcome) if final_outcome else "",
                primary_agent=str(primary_agent) if primary_agent else "",
            )
        )

    # Build summary
    summary = SessionSummary(
        total_sessions=0,
        avg_turns=0,
        avg_messages=0,
        avg_duration_ms=0,
        total_cost=0,
        avg_cost_per_session=0,
        completed_sessions=0,
        abandoned_sessions=0,
        error_sessions=0,
    )

    if summary_results:
        row = summary_results[0]
        (
            total_sessions,
            avg_turns,
            avg_messages,
            avg_duration,
            total_cost,
            avg_cost,
            completed,
            abandoned,
            errors,
        ) = row

        summary = SessionSummary(
            total_sessions=int(total_sessions),
            avg_turns=float(avg_turns) if avg_turns else 0,
            avg_messages=float(avg_messages) if avg_messages else 0,
            avg_duration_ms=float(avg_duration) if avg_duration else 0,
            total_cost=float(total_cost) if total_cost else 0,
            avg_cost_per_session=float(avg_cost) if avg_cost else 0,
            completed_sessions=int(completed),
            abandoned_sessions=int(abandoned),
            error_sessions=int(errors),
        )

    query_time_ms = (time.time() - start) * 1000

    return AnalyticsResponse(
        data=SessionAnalyticsData(
            sessions=sessions,
            summary=summary,
        ),
        meta=params.build_meta(query_time_ms=query_time_ms, include_granularity=False),
    )
