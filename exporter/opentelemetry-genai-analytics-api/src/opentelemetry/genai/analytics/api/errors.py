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

"""Error monitoring analytics API endpoints."""

import logging
import time
from collections import defaultdict

from clickhouse_driver.errors import Error as ClickHouseError
from fastapi import APIRouter, Depends, HTTPException

from opentelemetry.genai.analytics.api.dependencies import (
    CommonQueryParams,
    get_db_client,
    get_query_builder,
)
from opentelemetry.genai.analytics.db.connection import ClickHouseClient
from opentelemetry.genai.analytics.db.queries import QueryBuilder
from opentelemetry.genai.analytics.schemas.common import (
    AnalyticsResponse,
    ErrorAnalyticsData,
    ErrorBreakdown,
    ErrorDataPoint,
    ModelErrorData,
    ProviderErrorData,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/errors", response_model=AnalyticsResponse[ErrorAnalyticsData])
def get_error_analytics(
    params: CommonQueryParams = Depends(),
    client: ClickHouseClient = Depends(get_db_client),
    query_builder: QueryBuilder = Depends(get_query_builder),
):
    """Get error rate analytics by provider and model.

    Returns error rates and breakdown by error type, nested by
    provider and model.
    """
    start = time.time()

    try:
        # Get error rates by provider and model
        rates_query, rates_params = query_builder.error_rates(
            group_by=["Provider", "RequestModel"],
            start_time=params.start_time,
            end_time=params.end_time,
            **params.get_filters(),
        )
        rates_results = client.execute(rates_query, rates_params)

        # Get error breakdown
        breakdown_query, breakdown_params = query_builder.error_breakdown(
            start_time=params.start_time,
            end_time=params.end_time,
            **params.get_filters(),
        )
        breakdown_results = client.execute(breakdown_query, breakdown_params)

        # Get error time series
        ts_query, ts_params = query_builder.error_time_series(
            granularity=params.granularity,
            start_time=params.start_time,
            end_time=params.end_time,
            **params.get_filters(),
        )
        ts_results = client.execute(ts_query, ts_params)
    except ClickHouseError as e:
        logger.error("Failed to query error analytics: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Build breakdown lookup
    breakdown_lookup: dict[str, dict[str, list[ErrorBreakdown]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in breakdown_results:
        provider, model, error_type, status_code, error_count = row
        breakdown_lookup[provider][model].append(
            ErrorBreakdown(
                error_type=str(error_type) if error_type else "unknown",
                status_code=str(status_code),
                count=int(error_count),
            )
        )

    # Build nested response structure
    providers_data: dict[str, dict[str, ModelErrorData]] = defaultdict(dict)
    provider_totals: dict[str, dict] = defaultdict(
        lambda: {"total_requests": 0, "error_count": 0}
    )

    for row in rates_results:
        provider, model, total_requests, error_count, error_rate = row

        providers_data[provider][model] = ModelErrorData(
            total_requests=int(total_requests),
            error_count=int(error_count),
            error_rate=float(error_rate),
            breakdown=breakdown_lookup.get(provider, {}).get(model, []),
        )

        provider_totals[provider]["total_requests"] += int(total_requests)
        provider_totals[provider]["error_count"] += int(error_count)

    # Build time series
    time_series = []
    for row in ts_results:
        time_bucket, total_requests, error_count, error_rate = row
        time_series.append(
            ErrorDataPoint(
                timestamp=time_bucket,
                total_requests=int(total_requests),
                error_count=int(error_count),
                error_rate=float(error_rate),
            )
        )

    # Build final response
    provider_error_data = {}
    for provider, models in providers_data.items():
        totals = provider_totals[provider]
        provider_error_data[provider] = ProviderErrorData(
            models=models,
            total_requests=totals["total_requests"],
            error_count=totals["error_count"],
            error_rate=(
                totals["error_count"] / totals["total_requests"]
                if totals["total_requests"] > 0
                else 0.0
            ),
        )

    # Calculate overall totals
    overall_requests = sum(t["total_requests"] for t in provider_totals.values())
    overall_errors = sum(t["error_count"] for t in provider_totals.values())

    query_time_ms = (time.time() - start) * 1000

    return AnalyticsResponse(
        data=ErrorAnalyticsData(
            providers=provider_error_data,
            time_series=time_series,
            total_requests=overall_requests,
            total_errors=overall_errors,
            overall_error_rate=(
                overall_errors / overall_requests if overall_requests > 0 else 0.0
            ),
        ),
        meta=params.build_meta(query_time_ms=query_time_ms),
    )
