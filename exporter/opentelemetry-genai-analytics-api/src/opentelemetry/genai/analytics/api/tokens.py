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

"""Token usage analytics API endpoints."""

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
    ProviderTokenData,
    TokenAnalyticsData,
    TokenDataPoint,
    TokenTotals,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/tokens", response_model=AnalyticsResponse[TokenAnalyticsData])
def get_token_analytics(
    params: CommonQueryParams = Depends(),
    client: ClickHouseClient = Depends(get_db_client),
    query_builder: QueryBuilder = Depends(get_query_builder),
):
    """Get token usage analytics by provider.

    Returns token usage data nested by provider, with time series
    and totals for each provider.
    """
    start = time.time()

    try:
        # Get time series data grouped by provider
        query, query_params = query_builder.token_usage(
            granularity=params.granularity,
            group_by=["Provider"],
            start_time=params.start_time,
            end_time=params.end_time,
            **params.get_filters(),
        )
        results = client.execute(query, query_params)
    except ClickHouseError as e:
        logger.error("Failed to query token analytics: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Build nested response structure
    providers_data: dict[str, dict] = defaultdict(
        lambda: {"time_series": [], "totals": None}
    )

    # Process time series data and accumulate totals
    provider_accum: dict[str, dict] = defaultdict(
        lambda: {
            "total_input": 0,
            "total_output": 0,
            "total": 0,
            "request_count": 0,
            "avg_input_sum": 0,
            "avg_output_sum": 0,
        }
    )

    for row in results:
        (
            time_bucket,
            provider,
            total_input,
            total_output,
            total_tokens,
            avg_input,
            avg_output,
            request_count,
        ) = row

        providers_data[provider]["time_series"].append(
            TokenDataPoint(
                timestamp=time_bucket,
                total_input_tokens=int(total_input),
                total_output_tokens=int(total_output),
                total_tokens=int(total_tokens),
                avg_input_tokens=float(avg_input),
                avg_output_tokens=float(avg_output),
                request_count=int(request_count),
            )
        )

        # Accumulate for totals
        provider_accum[provider]["total_input"] += int(total_input)
        provider_accum[provider]["total_output"] += int(total_output)
        provider_accum[provider]["total"] += int(total_tokens)
        provider_accum[provider]["request_count"] += int(request_count)

    # Calculate provider totals
    for provider, accum in provider_accum.items():
        request_count = accum["request_count"]
        providers_data[provider]["totals"] = TokenTotals(
            total_input_tokens=accum["total_input"],
            total_output_tokens=accum["total_output"],
            total_tokens=accum["total"],
            avg_input_tokens=accum["total_input"] / request_count if request_count > 0 else 0,
            avg_output_tokens=accum["total_output"] / request_count if request_count > 0 else 0,
            request_count=request_count,
        )

    # Build final response
    provider_token_data = {}
    for provider, data in providers_data.items():
        provider_token_data[provider] = ProviderTokenData(
            time_series=data["time_series"],
            totals=data["totals"] or TokenTotals(
                total_input_tokens=0, total_output_tokens=0, total_tokens=0,
                avg_input_tokens=0, avg_output_tokens=0, request_count=0
            ),
        )

    # Calculate overall totals
    overall_input = sum(a["total_input"] for a in provider_accum.values())
    overall_output = sum(a["total_output"] for a in provider_accum.values())
    overall_total = sum(a["total"] for a in provider_accum.values())
    overall_requests = sum(a["request_count"] for a in provider_accum.values())

    overall_totals = TokenTotals(
        total_input_tokens=overall_input,
        total_output_tokens=overall_output,
        total_tokens=overall_total,
        avg_input_tokens=overall_input / overall_requests if overall_requests > 0 else 0,
        avg_output_tokens=overall_output / overall_requests if overall_requests > 0 else 0,
        request_count=overall_requests,
    )

    query_time_ms = (time.time() - start) * 1000

    return AnalyticsResponse(
        data=TokenAnalyticsData(
            providers=provider_token_data,
            totals=overall_totals,
        ),
        meta=params.build_meta(query_time_ms=query_time_ms),
    )
