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

"""Model usage analytics API endpoints."""

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
    ModelAnalyticsData,
    ModelUsageStats,
    ProviderModelUsage,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/models", response_model=AnalyticsResponse[ModelAnalyticsData])
def get_model_analytics(
    params: CommonQueryParams = Depends(),
    client: ClickHouseClient = Depends(get_db_client),
    query_builder: QueryBuilder = Depends(get_query_builder),
):
    """Get model usage distribution analytics.

    Returns usage statistics for each model, nested by provider.
    """
    start = time.time()

    try:
        # Get model usage data
        query, query_params = query_builder.model_usage(
            start_time=params.start_time,
            end_time=params.end_time,
            **params.get_filters(),
        )
        results = client.execute(query, query_params)
    except ClickHouseError as e:
        logger.error("Failed to query model analytics: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Build nested response structure
    providers_data: dict[str, dict[str, ModelUsageStats]] = defaultdict(dict)
    unique_models = set()

    for row in results:
        (
            provider,
            model,
            request_count,
            total_input,
            total_output,
            total_cost,
            avg_latency,
            error_rate,
        ) = row

        providers_data[provider][model] = ModelUsageStats(
            request_count=int(request_count),
            total_input_tokens=int(total_input),
            total_output_tokens=int(total_output),
            total_cost=float(total_cost),
            avg_latency=float(avg_latency),
            error_rate=float(error_rate),
        )
        unique_models.add(model)

    # Build final response
    provider_model_usage = {}
    total_requests = 0

    for provider, models in providers_data.items():
        provider_requests = sum(m.request_count for m in models.values())
        total_requests += provider_requests

        provider_model_usage[provider] = ProviderModelUsage(
            models=models,
            total_requests=provider_requests,
        )

    query_time_ms = (time.time() - start) * 1000

    return AnalyticsResponse(
        data=ModelAnalyticsData(
            providers=provider_model_usage,
            total_requests=total_requests,
            unique_models=len(unique_models),
        ),
        meta=params.build_meta(query_time_ms=query_time_ms, include_granularity=False),
    )
