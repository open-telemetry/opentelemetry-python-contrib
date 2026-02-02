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

"""Tool usage analytics API endpoints."""

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
    ToolAnalyticsData,
    ToolDataPoint,
    ToolStats,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/tools", response_model=AnalyticsResponse[ToolAnalyticsData])
def get_tool_analytics(
    params: CommonQueryParams = Depends(),
    limit: int = Query(100, ge=1, le=1000, description="Maximum tools to return"),
    include_time_series: bool = Query(
        False, description="Include time series data"
    ),
    tool_name: str | None = Query(
        None, description="Filter by specific tool name"
    ),
    client: ClickHouseClient = Depends(get_db_client),
    query_builder: QueryBuilder = Depends(get_query_builder),
):
    """Get tool usage analytics.

    Returns usage statistics for each tool including success rates
    and latency percentiles.
    """
    start = time.time()

    try:
        # Get tool usage data
        query, query_params = query_builder.tool_usage(
            start_time=params.start_time,
            end_time=params.end_time,
            limit=limit,
            tool_name=tool_name,
        )
        results = client.execute(query, query_params)
    except ClickHouseError as e:
        logger.error("Failed to query tool analytics: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Build tools list
    tools = []
    total_invocations = 0

    for row in results:
        (
            name,
            tool_type,
            invocation_count,
            success_count,
            error_count,
            success_rate,
            avg_duration,
            p50_duration,
            p95_duration,
            p99_duration,
        ) = row

        tools.append(
            ToolStats(
                tool_name=str(name),
                tool_type=str(tool_type),
                invocation_count=int(invocation_count),
                success_count=int(success_count),
                error_count=int(error_count),
                success_rate=float(success_rate),
                avg_duration=float(avg_duration),
                p50_duration=float(p50_duration),
                p95_duration=float(p95_duration),
                p99_duration=float(p99_duration),
            )
        )
        total_invocations += int(invocation_count)

    # Optionally get time series data
    time_series = []
    if include_time_series:
        try:
            ts_query, ts_params = query_builder.tool_time_series(
                granularity=params.granularity,
                start_time=params.start_time,
                end_time=params.end_time,
                tool_name=tool_name,
            )
            ts_results = client.execute(ts_query, ts_params)
        except ClickHouseError as e:
            logger.error("Failed to query tool time series: %s", e)
            raise HTTPException(status_code=503, detail="Database unavailable")

        for row in ts_results:
            time_bucket, name, invocation_count, success_rate, avg_duration = row
            time_series.append(
                ToolDataPoint(
                    timestamp=time_bucket,
                    tool_name=str(name),
                    invocation_count=int(invocation_count),
                    success_rate=float(success_rate),
                    avg_duration=float(avg_duration),
                )
            )

    query_time_ms = (time.time() - start) * 1000

    return AnalyticsResponse(
        data=ToolAnalyticsData(
            tools=tools,
            time_series=time_series,
            total_invocations=total_invocations,
        ),
        meta=params.build_meta(
            query_time_ms=query_time_ms,
            include_granularity=include_time_series,
        ),
    )
