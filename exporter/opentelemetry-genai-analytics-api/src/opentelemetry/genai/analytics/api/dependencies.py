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

"""FastAPI dependencies for GenAI Analytics API."""

from datetime import datetime, timedelta, timezone
from typing import Generator, Optional

from fastapi import HTTPException, Query

from opentelemetry.genai.analytics.config import settings
from opentelemetry.genai.analytics.db.connection import (
    ClickHouseClient,
    _connection_pool,
)
from opentelemetry.genai.analytics.db.queries import Granularity, QueryBuilder
from opentelemetry.genai.analytics.schemas.common import ResponseMeta, TimeRange


def get_db_client() -> Generator[ClickHouseClient, None, None]:
    """Dependency to get ClickHouse client from connection pool.

    This is a generator dependency that acquires a connection from the pool
    and automatically releases it back when the request completes.
    """
    client = _connection_pool.acquire()
    try:
        yield client
    finally:
        _connection_pool.release(client)


def get_query_builder() -> QueryBuilder:
    """Dependency to get query builder."""
    return QueryBuilder()


class CommonQueryParams:
    """Common query parameters for all analytics endpoints."""

    def __init__(
        self,
        start_time: Optional[datetime] = Query(
            None,
            description="Start of time range (ISO8601). Defaults to 24 hours ago.",
        ),
        end_time: Optional[datetime] = Query(
            None,
            description="End of time range (ISO8601). Defaults to now.",
        ),
        granularity: Granularity = Query(
            Granularity.HOUR,
            description="Time granularity for aggregations.",
        ),
        service_name: Optional[str] = Query(
            None,
            description="Filter by service name.",
        ),
        provider: Optional[str] = Query(
            None,
            description="Filter by provider (openai, anthropic, etc.).",
        ),
        model: Optional[str] = Query(
            None,
            description="Filter by model name.",
        ),
        tenant_id: Optional[str] = Query(
            None,
            description="Filter by tenant ID.",
        ),
        user_id: Optional[str] = Query(
            None,
            description="Filter by user ID.",
        ),
    ):
        # Set default time range if not provided
        now = datetime.now(timezone.utc)
        default_start = now - timedelta(hours=settings.api.default_time_range_hours)

        self.start_time = start_time or default_start
        self.end_time = end_time or now
        self.granularity = granularity
        self.service_name = service_name
        self.provider = provider
        self.model = model
        self.tenant_id = tenant_id
        self.user_id = user_id

        # Validate time range
        max_range = timedelta(days=settings.api.max_time_range_days)
        if (self.end_time - self.start_time) > max_range:
            raise HTTPException(
                status_code=400,
                detail=f"Time range exceeds maximum of {settings.api.max_time_range_days} days"
            )
        if self.start_time > self.end_time:
            raise HTTPException(
                status_code=400,
                detail="start_time must be before end_time"
            )

    def get_filters(self) -> dict:
        """Get filter parameters as dict for query builder."""
        filters = {}
        if self.service_name:
            filters["service_name"] = self.service_name
        if self.provider:
            filters["provider"] = self.provider
        if self.model:
            filters["model"] = self.model
        if self.tenant_id:
            filters["tenant_id"] = self.tenant_id
        if self.user_id:
            filters["user_id"] = self.user_id
        return filters

    def build_meta(
        self,
        query_time_ms: Optional[float] = None,
        include_granularity: bool = True,
    ) -> ResponseMeta:
        """Build response metadata."""
        return ResponseMeta(
            time_range=TimeRange(start=self.start_time, end=self.end_time),
            granularity=self.granularity if include_granularity else None,
            filters_applied=self.get_filters(),
            query_time_ms=query_time_ms,
        )
