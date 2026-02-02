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

"""Cost analytics API endpoints."""

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

logger = logging.getLogger(__name__)
from opentelemetry.genai.analytics.schemas.common import (
    AnalyticsResponse,
    CostAnalyticsData,
    CostDataPoint,
    CostTotals,
    ModelCostData,
    ProviderCostData,
)

router = APIRouter()


@router.get("/costs", response_model=AnalyticsResponse[CostAnalyticsData])
def get_cost_analytics(
    params: CommonQueryParams = Depends(),
    client: ClickHouseClient = Depends(get_db_client),
    query_builder: QueryBuilder = Depends(get_query_builder),
):
    """Get cost analytics by provider and model.

    Returns cost data nested by provider and model, with time series
    and totals for each dimension.
    """
    start = time.time()

    try:
        # Get time series data
        query, query_params = query_builder.cost_by_dimensions(
            granularity=params.granularity,
            group_by=["Provider", "RequestModel"],
            start_time=params.start_time,
            end_time=params.end_time,
            **params.get_filters(),
        )
        results = client.execute(query, query_params)

        # Get totals
        totals_query, totals_params = query_builder.cost_totals(
            group_by=["Provider", "RequestModel"],
            start_time=params.start_time,
            end_time=params.end_time,
            **params.get_filters(),
        )
        totals_results = client.execute(totals_query, totals_params)
    except ClickHouseError as e:
        logger.error("Failed to query cost analytics: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Build nested response structure
    # Structure: providers -> models -> time_series + totals
    providers_data: dict[str, dict[str, dict]] = defaultdict(
        lambda: defaultdict(lambda: {"time_series": [], "totals": None})
    )

    # Process time series data
    for row in results:
        time_bucket, provider, model, total_cost, request_count, input_tokens, output_tokens = row
        providers_data[provider][model]["time_series"].append(
            CostDataPoint(
                timestamp=time_bucket,
                total_cost=float(total_cost),
                request_count=int(request_count),
                total_input_tokens=int(input_tokens),
                total_output_tokens=int(output_tokens),
            )
        )

    # Process totals data
    model_totals: dict[str, dict[str, CostTotals]] = defaultdict(dict)
    provider_totals: dict[str, CostTotals] = {}

    for row in totals_results:
        provider, model, total_cost, request_count, input_tokens, output_tokens, avg_cost = row
        totals = CostTotals(
            total_cost=float(total_cost),
            request_count=int(request_count),
            total_input_tokens=int(input_tokens),
            total_output_tokens=int(output_tokens),
            avg_cost_per_request=float(avg_cost) if avg_cost else 0.0,
        )
        model_totals[provider][model] = totals
        providers_data[provider][model]["totals"] = totals

    # Calculate provider-level totals
    for provider in providers_data:
        provider_cost = sum(t.total_cost for t in model_totals.get(provider, {}).values())
        provider_requests = sum(t.request_count for t in model_totals.get(provider, {}).values())
        provider_input = sum(t.total_input_tokens for t in model_totals.get(provider, {}).values())
        provider_output = sum(t.total_output_tokens for t in model_totals.get(provider, {}).values())

        provider_totals[provider] = CostTotals(
            total_cost=provider_cost,
            request_count=provider_requests,
            total_input_tokens=provider_input,
            total_output_tokens=provider_output,
            avg_cost_per_request=provider_cost / provider_requests if provider_requests > 0 else 0.0,
        )

    # Build final response
    provider_cost_data = {}
    for provider, models in providers_data.items():
        model_data = {}
        for model, data in models.items():
            model_data[model] = ModelCostData(
                time_series=data["time_series"],
                totals=data["totals"] or CostTotals(
                    total_cost=0, request_count=0, total_input_tokens=0,
                    total_output_tokens=0, avg_cost_per_request=0
                ),
            )
        provider_cost_data[provider] = ProviderCostData(
            models=model_data,
            totals=provider_totals.get(provider, CostTotals(
                total_cost=0, request_count=0, total_input_tokens=0,
                total_output_tokens=0, avg_cost_per_request=0
            )),
        )

    # Calculate overall totals
    overall_cost = sum(t.total_cost for t in provider_totals.values())
    overall_requests = sum(t.request_count for t in provider_totals.values())
    overall_input = sum(t.total_input_tokens for t in provider_totals.values())
    overall_output = sum(t.total_output_tokens for t in provider_totals.values())

    overall_totals = CostTotals(
        total_cost=overall_cost,
        request_count=overall_requests,
        total_input_tokens=overall_input,
        total_output_tokens=overall_output,
        avg_cost_per_request=overall_cost / overall_requests if overall_requests > 0 else 0.0,
    )

    query_time_ms = (time.time() - start) * 1000

    return AnalyticsResponse(
        data=CostAnalyticsData(
            providers=provider_cost_data,
            totals=overall_totals,
        ),
        meta=params.build_meta(query_time_ms=query_time_ms),
    )
