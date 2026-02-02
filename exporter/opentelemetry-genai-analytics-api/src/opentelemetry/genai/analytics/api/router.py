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

"""Main API router for GenAI Analytics."""

from fastapi import APIRouter

from opentelemetry.genai.analytics.api.audit import router as audit_router
from opentelemetry.genai.analytics.api.costs import router as costs_router
from opentelemetry.genai.analytics.api.errors import router as errors_router
from opentelemetry.genai.analytics.api.latency import router as latency_router
from opentelemetry.genai.analytics.api.models import router as models_router
from opentelemetry.genai.analytics.api.providers import router as providers_router
from opentelemetry.genai.analytics.api.sessions import router as sessions_router
from opentelemetry.genai.analytics.api.tokens import router as tokens_router
from opentelemetry.genai.analytics.api.tools import router as tools_router
from opentelemetry.genai.analytics.api.users import router as users_router

api_router = APIRouter(prefix="/api/v1")

# Include all routers
api_router.include_router(costs_router, prefix="/analytics", tags=["Cost Analytics"])
api_router.include_router(tokens_router, prefix="/analytics", tags=["Token Analytics"])
api_router.include_router(latency_router, prefix="/analytics", tags=["Latency Analytics"])
api_router.include_router(errors_router, prefix="/analytics", tags=["Error Analytics"])
api_router.include_router(models_router, prefix="/analytics", tags=["Model Analytics"])
api_router.include_router(users_router, prefix="/analytics", tags=["User Analytics"])
api_router.include_router(sessions_router, prefix="/analytics", tags=["Session Analytics"])
api_router.include_router(tools_router, prefix="/analytics", tags=["Tool Analytics"])
api_router.include_router(providers_router, prefix="/analytics", tags=["Provider Analytics"])
api_router.include_router(audit_router, prefix="/audit", tags=["Audit Trail"])
