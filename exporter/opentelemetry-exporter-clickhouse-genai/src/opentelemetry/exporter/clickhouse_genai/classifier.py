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

"""Span classification based on OpenTelemetry semantic conventions.

Routes spans to appropriate ClickHouse tables:
- genai_spans: LLM/AI interactions (gen_ai.* attributes)
- spans: All other spans (db.*, http.*, messaging.*, rpc.*, etc.)
"""

from typing import Tuple

from opentelemetry.sdk.trace import ReadableSpan

# Known GenAI instrumentation scopes
GENAI_SCOPES = frozenset([
    "opentelemetry.instrumentation.openai",
    "opentelemetry.instrumentation.openai_v2",
    "opentelemetry.instrumentation.anthropic",
    "opentelemetry.instrumentation.bedrock",
    "opentelemetry.instrumentation.cohere",
    "opentelemetry.instrumentation.groq",
    "opentelemetry.instrumentation.mistral",
    "opentelemetry.instrumentation.vertexai",
    "opentelemetry.instrumentation.google_genai",
    "opentelemetry.instrumentation.langchain",
    "opentelemetry.instrumentation.langgraph",
    "opentelemetry.instrumentation.llamaindex",
    "opentelemetry.instrumentation.haystack",
    "opentelemetry.instrumentation.crewai",
    "opentelemetry.instrumentation.chromadb",
    "opentelemetry.instrumentation.pinecone",
    "opentelemetry.instrumentation.milvus",
    "opentelemetry.instrumentation.qdrant",
    "opentelemetry.instrumentation.weaviate",
    "opentelemetry.instrumentation.mcp",
])

# Database instrumentation scopes
DB_SCOPES = frozenset([
    "opentelemetry.instrumentation.psycopg",
    "opentelemetry.instrumentation.psycopg2",
    "opentelemetry.instrumentation.aiopg",
    "opentelemetry.instrumentation.asyncpg",
    "opentelemetry.instrumentation.sqlalchemy",
    "opentelemetry.instrumentation.redis",
    "opentelemetry.instrumentation.pymongo",
    "opentelemetry.instrumentation.pymemcache",
    "opentelemetry.instrumentation.elasticsearch",
    "opentelemetry.instrumentation.mysql",
    "opentelemetry.instrumentation.mysqlclient",
    "opentelemetry.instrumentation.pymysql",
    "opentelemetry.instrumentation.sqlite3",
    "opentelemetry.instrumentation.cassandra",
    "opentelemetry.instrumentation.pymssql",
    "opentelemetry.instrumentation.dbapi",
    "opentelemetry.instrumentation.tortoiseorm",
])

# HTTP instrumentation scopes
HTTP_SCOPES = frozenset([
    "opentelemetry.instrumentation.requests",
    "opentelemetry.instrumentation.httpx",
    "opentelemetry.instrumentation.urllib",
    "opentelemetry.instrumentation.urllib3",
    "opentelemetry.instrumentation.aiohttp_client",
    "opentelemetry.instrumentation.flask",
    "opentelemetry.instrumentation.django",
    "opentelemetry.instrumentation.fastapi",
    "opentelemetry.instrumentation.starlette",
    "opentelemetry.instrumentation.tornado",
    "opentelemetry.instrumentation.pyramid",
    "opentelemetry.instrumentation.falcon",
    "opentelemetry.instrumentation.asgi",
    "opentelemetry.instrumentation.wsgi",
    "opentelemetry.instrumentation.aiohttp_server",
])

# Messaging instrumentation scopes
MESSAGING_SCOPES = frozenset([
    "opentelemetry.instrumentation.kafka",
    "opentelemetry.instrumentation.kafka_python",
    "opentelemetry.instrumentation.aiokafka",
    "opentelemetry.instrumentation.confluent_kafka",
    "opentelemetry.instrumentation.pika",
    "opentelemetry.instrumentation.aio_pika",
    "opentelemetry.instrumentation.celery",
    "opentelemetry.instrumentation.boto3sqs",
    "opentelemetry.instrumentation.remoulade",
])

# RPC instrumentation scopes
RPC_SCOPES = frozenset([
    "opentelemetry.instrumentation.grpc",
    "opentelemetry.instrumentation.botocore",
    "opentelemetry.instrumentation.boto",
    "opentelemetry.instrumentation.aws_lambda",
])


def classify_span(span: ReadableSpan) -> Tuple[str, str]:
    """
    Classify span into (target_table, category).

    Args:
        span: OpenTelemetry ReadableSpan to classify

    Returns:
        Tuple of (target_table, category) where:
        - target_table: 'genai_spans' or 'spans'
        - category: operation type or span category (e.g., 'chat', 'db', 'http')
    """
    # Get instrumentation scope name
    scope = ""
    if span.instrumentation_scope:
        scope = span.instrumentation_scope.name or ""

    # Get span attributes as dict
    attrs = dict(span.attributes) if span.attributes else {}

    # 1. GenAI spans → genai_spans table
    # Check for gen_ai.* attributes (highest priority)
    if "gen_ai.system" in attrs:
        op_type = attrs.get("gen_ai.operation.name", "other")
        return ("genai_spans", str(op_type))

    # Check instrumentation scope
    if scope in GENAI_SCOPES:
        op_type = attrs.get("gen_ai.operation.name", "other")
        return ("genai_spans", str(op_type))

    # 2. Database spans (db.* attributes)
    if "db.system" in attrs or scope in DB_SCOPES:
        return ("spans", "db")

    # 3. HTTP spans (http.* attributes)
    if (
        "http.method" in attrs
        or "http.request.method" in attrs
        or scope in HTTP_SCOPES
    ):
        return ("spans", "http")

    # 4. Messaging spans (messaging.* attributes)
    if "messaging.system" in attrs or scope in MESSAGING_SCOPES:
        return ("spans", "messaging")

    # 5. RPC spans (rpc.* attributes) - includes gRPC, AWS API
    if "rpc.system" in attrs or scope in RPC_SCOPES:
        return ("spans", "rpc")

    # 6. FaaS spans (AWS Lambda, etc.)
    if "faas.trigger" in attrs or "faas.invoked_name" in attrs:
        return ("spans", "faas")

    # 7. Default - unknown category
    return ("spans", "other")


def is_genai_span(span: ReadableSpan) -> bool:
    """Check if a span is a GenAI span."""
    table, _ = classify_span(span)
    return table == "genai_spans"


def get_span_category(span: ReadableSpan) -> str:
    """Get the category of a span (db, http, messaging, rpc, faas, other)."""
    _, category = classify_span(span)
    return category
