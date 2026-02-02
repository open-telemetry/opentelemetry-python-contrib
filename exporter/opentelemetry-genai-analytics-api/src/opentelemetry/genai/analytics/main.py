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

"""FastAPI application entry point for GenAI Analytics API."""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from opentelemetry.genai.analytics.api import api_router
from opentelemetry.genai.analytics.config import settings
from opentelemetry.genai.analytics.db.connection import _connection_pool
from opentelemetry.genai.analytics.version import __version__

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("Starting GenAI Analytics API v%s", __version__)
    logger.info(
        "ClickHouse: %s/%s",
        settings.clickhouse.endpoint,
        settings.clickhouse.database,
    )

    # Test ClickHouse connection via pool
    if _connection_pool.ping():
        logger.info("ClickHouse connection verified")
    else:
        logger.warning("ClickHouse connection failed - service may not work correctly")

    yield

    # Shutdown - close all pooled connections
    logger.info("Shutting down GenAI Analytics API")
    _connection_pool.close_all()


app = FastAPI(
    title="OpenTelemetry GenAI Analytics API",
    description="""
Analytics API for querying LLM observability data stored in ClickHouse.

## Features

- **Cost Analytics**: Track spending by provider, model, tenant, user
- **Token Usage**: Monitor input/output token consumption
- **Latency Tracking**: P50/P95/P99 percentiles by provider/model
- **Error Monitoring**: Error rates and breakdown by type
- **Model Usage**: Distribution and trends across models
- **User/Tenant Analytics**: Per-user and per-tenant metrics
- **Session Analytics**: Conversation metrics and outcomes
- **Tool Usage**: Function/tool invocation statistics
- **Provider Comparison**: Compare providers across all metrics
- **Audit Trail**: Full trace history with filtering

## Authentication

This service is designed for internal use and does not include authentication.
Deploy behind an API gateway or service mesh for production use.
    """,
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Add CORS middleware (configurable via GENAI_ANALYTICS_CORS_ORIGINS)
# Use "*" for development, specific origins for production
_cors_origins = (
    ["*"] if settings.api.cors_origins == "*"
    else [o.strip() for o in settings.api.cors_origins.split(",") if o.strip()]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router)


@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint."""
    clickhouse_ok = _connection_pool.ping()

    return {
        "status": "healthy" if clickhouse_ok else "degraded",
        "version": __version__,
        "clickhouse": {
            "status": "connected" if clickhouse_ok else "disconnected",
            "endpoint": settings.clickhouse.endpoint,
            "database": settings.clickhouse.database,
        },
    }


@app.get("/", tags=["Root"])
def root():
    """Root endpoint with API information."""
    return {
        "name": "OpenTelemetry GenAI Analytics API",
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
    }


def run():
    """Run the application with uvicorn."""
    logging.basicConfig(
        level=getattr(logging, settings.api.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    uvicorn.run(
        "opentelemetry.genai.analytics.main:app",
        host=settings.api.host,
        port=settings.api.port,
        workers=settings.api.workers,
        log_level=settings.api.log_level.lower(),
    )


if __name__ == "__main__":
    run()
