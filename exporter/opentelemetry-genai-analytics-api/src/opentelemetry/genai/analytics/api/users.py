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

"""User and tenant analytics API endpoints."""

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
    TenantAnalyticsData,
    TenantStats,
    UserAnalyticsData,
    UserStats,
)

router = APIRouter()


@router.get("/users", response_model=AnalyticsResponse[UserAnalyticsData])
def get_user_analytics(
    params: CommonQueryParams = Depends(),
    limit: int = Query(100, ge=1, le=1000, description="Maximum users to return"),
    client: ClickHouseClient = Depends(get_db_client),
    query_builder: QueryBuilder = Depends(get_query_builder),
):
    """Get per-user analytics.

    Returns usage statistics for each user, sorted by total cost.
    """
    start = time.time()

    try:
        # Get total user count
        count_query, count_params = query_builder.user_count(
            start_time=params.start_time,
            end_time=params.end_time,
            **params.get_filters(),
        )
        count_result = client.execute(count_query, count_params)
        total_users = count_result[0][0] if count_result else 0

        # Get user analytics data
        query, query_params = query_builder.user_analytics(
            start_time=params.start_time,
            end_time=params.end_time,
            limit=limit,
            **params.get_filters(),
        )
        results = client.execute(query, query_params)
    except ClickHouseError as e:
        logger.error("Failed to query user analytics: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Build response
    users = []
    for row in results:
        (
            user_id,
            request_count,
            total_input,
            total_output,
            total_cost,
            avg_latency,
            session_count,
            first_seen,
            last_seen,
        ) = row

        users.append(
            UserStats(
                user_id=str(user_id),
                request_count=int(request_count),
                total_input_tokens=int(total_input),
                total_output_tokens=int(total_output),
                total_cost=float(total_cost),
                avg_latency=float(avg_latency),
                session_count=int(session_count),
                first_seen=first_seen,
                last_seen=last_seen,
            )
        )

    query_time_ms = (time.time() - start) * 1000

    return AnalyticsResponse(
        data=UserAnalyticsData(
            users=users,
            total_users=total_users,
        ),
        meta=params.build_meta(query_time_ms=query_time_ms, include_granularity=False),
    )


@router.get("/tenants", response_model=AnalyticsResponse[TenantAnalyticsData])
def get_tenant_analytics(
    params: CommonQueryParams = Depends(),
    limit: int = Query(100, ge=1, le=1000, description="Maximum tenants to return"),
    client: ClickHouseClient = Depends(get_db_client),
    query_builder: QueryBuilder = Depends(get_query_builder),
):
    """Get per-tenant analytics.

    Returns usage statistics for each tenant, sorted by total cost.
    """
    start = time.time()

    try:
        # Get total tenant count
        count_query, count_params = query_builder.tenant_count(
            start_time=params.start_time,
            end_time=params.end_time,
            **params.get_filters(),
        )
        count_result = client.execute(count_query, count_params)
        total_tenants = count_result[0][0] if count_result else 0

        # Get tenant analytics data
        query, query_params = query_builder.tenant_analytics(
            start_time=params.start_time,
            end_time=params.end_time,
            limit=limit,
            **params.get_filters(),
        )
        results = client.execute(query, query_params)
    except ClickHouseError as e:
        logger.error("Failed to query tenant analytics: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Build response
    tenants = []
    for row in results:
        (
            tenant_id,
            request_count,
            total_input,
            total_output,
            total_cost,
            avg_latency,
            unique_users,
            session_count,
        ) = row

        tenants.append(
            TenantStats(
                tenant_id=str(tenant_id),
                request_count=int(request_count),
                total_input_tokens=int(total_input),
                total_output_tokens=int(total_output),
                total_cost=float(total_cost),
                avg_latency=float(avg_latency),
                unique_users=int(unique_users),
                session_count=int(session_count),
            )
        )

    query_time_ms = (time.time() - start) * 1000

    return AnalyticsResponse(
        data=TenantAnalyticsData(
            tenants=tenants,
            total_tenants=total_tenants,
        ),
        meta=params.build_meta(query_time_ms=query_time_ms, include_granularity=False),
    )
