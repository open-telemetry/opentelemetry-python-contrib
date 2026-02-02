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

"""Provider comparison analytics API endpoints."""

import logging
import time

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
    ProviderComparisonData,
    ProviderStats,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/providers/compare", response_model=AnalyticsResponse[ProviderComparisonData])
def get_provider_comparison(
    params: CommonQueryParams = Depends(),
    client: ClickHouseClient = Depends(get_db_client),
    query_builder: QueryBuilder = Depends(get_query_builder),
):
    """Compare providers across multiple metrics.

    Returns comprehensive statistics for each provider including
    cost, latency, error rates, and usage.
    """
    start = time.time()

    try:
        # Get provider comparison data
        query, query_params = query_builder.provider_comparison(
            start_time=params.start_time,
            end_time=params.end_time,
            **params.get_filters(),
        )
        results = client.execute(query, query_params)
    except ClickHouseError as e:
        logger.error("Failed to query provider comparison: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Build providers list
    providers = []
    for row in results:
        (
            provider,
            request_count,
            total_cost,
            avg_cost,
            total_input,
            total_output,
            avg_latency,
            p50_latency,
            p95_latency,
            p99_latency,
            error_count,
            error_rate,
            models_used,
        ) = row

        providers.append(
            ProviderStats(
                provider=str(provider),
                request_count=int(request_count),
                total_cost=float(total_cost),
                avg_cost_per_request=float(avg_cost),
                total_input_tokens=int(total_input),
                total_output_tokens=int(total_output),
                avg_latency=float(avg_latency),
                p50_latency=float(p50_latency),
                p95_latency=float(p95_latency),
                p99_latency=float(p99_latency),
                error_count=int(error_count),
                error_rate=float(error_rate),
                models_used=int(models_used),
            )
        )

    query_time_ms = (time.time() - start) * 1000

    return AnalyticsResponse(
        data=ProviderComparisonData(providers=providers),
        meta=params.build_meta(query_time_ms=query_time_ms, include_granularity=False),
    )
