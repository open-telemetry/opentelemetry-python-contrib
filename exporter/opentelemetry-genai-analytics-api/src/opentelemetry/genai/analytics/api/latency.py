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

"""Latency analytics API endpoints."""

import logging
import time
from collections import defaultdict

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
    LatencyAnalyticsData,
    LatencyDataPoint,
    LatencyPercentiles,
    ModelLatencyData,
    ProviderLatencyData,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/latency", response_model=AnalyticsResponse[LatencyAnalyticsData])
def get_latency_analytics(
    params: CommonQueryParams = Depends(),
    include_time_series: bool = Query(
        False, description="Include time series data (more expensive query)"
    ),
    client: ClickHouseClient = Depends(get_db_client),
    query_builder: QueryBuilder = Depends(get_query_builder),
):
    """Get latency analytics by provider and model.

    Returns latency percentiles (P50, P75, P90, P95, P99) nested by
    provider and model.
    """
    start = time.time()

    try:
        # Get percentiles grouped by provider and model
        query, query_params = query_builder.latency_percentiles(
            group_by=["Provider", "RequestModel"],
            start_time=params.start_time,
            end_time=params.end_time,
            **params.get_filters(),
        )
        results = client.execute(query, query_params)
    except ClickHouseError as e:
        logger.error("Failed to query latency analytics: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Build nested response structure
    providers_data: dict[str, dict[str, ModelLatencyData]] = defaultdict(dict)

    for row in results:
        (
            provider,
            model,
            p50,
            p75,
            p90,
            p95,
            p99,
            avg_latency,
            min_latency,
            max_latency,
            request_count,
        ) = row

        percentiles = LatencyPercentiles(
            p50=float(p50),
            p75=float(p75),
            p90=float(p90),
            p95=float(p95),
            p99=float(p99),
            avg=float(avg_latency),
            min=float(min_latency),
            max=float(max_latency),
            request_count=int(request_count),
        )

        providers_data[provider][model] = ModelLatencyData(
            percentiles=percentiles,
            time_series=[],
        )

    # Optionally get time series data
    if include_time_series:
        try:
            ts_query, ts_params = query_builder.latency_time_series(
                granularity=params.granularity,
                group_by=["Provider", "RequestModel"],
                start_time=params.start_time,
                end_time=params.end_time,
                **params.get_filters(),
            )
            ts_results = client.execute(ts_query, ts_params)
        except ClickHouseError as e:
            logger.error("Failed to query latency time series: %s", e)
            raise HTTPException(status_code=503, detail="Database unavailable")

        for row in ts_results:
            time_bucket, provider, model, p50, p95, p99, avg_latency, request_count = row

            if provider in providers_data and model in providers_data[provider]:
                providers_data[provider][model].time_series.append(
                    LatencyDataPoint(
                        timestamp=time_bucket,
                        p50=float(p50),
                        p95=float(p95),
                        p99=float(p99),
                        avg=float(avg_latency),
                        request_count=int(request_count),
                    )
                )

    # Build final response
    provider_latency_data = {}
    for provider, models in providers_data.items():
        provider_latency_data[provider] = ProviderLatencyData(models=models)

    query_time_ms = (time.time() - start) * 1000

    return AnalyticsResponse(
        data=LatencyAnalyticsData(providers=provider_latency_data),
        meta=params.build_meta(
            query_time_ms=query_time_ms,
            include_granularity=include_time_series,
        ),
    )
