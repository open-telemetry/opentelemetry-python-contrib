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

"""
OpenTelemetry ClickHouse GenAI Exporter
=======================================

This package provides exporters for sending OpenTelemetry traces, metrics, and
logs to ClickHouse, with schemas optimized for GenAI/LLM observability.

Features:
- Maximally columnar schema design for fast LLM analytics
- Dedicated columns for GenAI attributes (tokens, models, operations)
- Comprehensive indexing for all query patterns
- Native TCP protocol for best performance
- Auto-schema creation with configurable TTL

Installation:
    pip install opentelemetry-exporter-clickhouse-genai

Basic usage for traces:

    >>> from opentelemetry import trace
    >>> from opentelemetry.sdk.trace import TracerProvider
    >>> from opentelemetry.sdk.trace.export import BatchSpanProcessor
    >>> from opentelemetry.exporter.clickhouse_genai import (
    ...     ClickHouseGenAISpanExporter,
    ...     ClickHouseGenAIConfig,
    ... )
    >>>
    >>> config = ClickHouseGenAIConfig(
    ...     endpoint="localhost:9000",
    ...     database="otel_genai",
    ...     ttl_days=7,
    ... )
    >>> exporter = ClickHouseGenAISpanExporter(config)
    >>> provider = TracerProvider()
    >>> provider.add_span_processor(BatchSpanProcessor(exporter))
    >>> trace.set_tracer_provider(provider)

Configuration via environment variables:
    - OTEL_EXPORTER_CLICKHOUSE_ENDPOINT: ClickHouse endpoint (default: localhost:9000)
    - OTEL_EXPORTER_CLICKHOUSE_DATABASE: Database name (default: otel_genai)
    - OTEL_EXPORTER_CLICKHOUSE_USERNAME: Username (default: default)
    - OTEL_EXPORTER_CLICKHOUSE_PASSWORD: Password (default: empty)
    - OTEL_EXPORTER_CLICKHOUSE_TTL_DAYS: Data retention in days (default: 7)
    - OTEL_EXPORTER_CLICKHOUSE_CREATE_SCHEMA: Auto-create tables (default: true)
"""

from opentelemetry.exporter.clickhouse_genai.config import ClickHouseGenAIConfig
from opentelemetry.exporter.clickhouse_genai.connection import ClickHouseConnection
from opentelemetry.exporter.clickhouse_genai.logs_exporter import (
    ClickHouseGenAILogsExporter,
)
from opentelemetry.exporter.clickhouse_genai.metrics_exporter import (
    ClickHouseGenAIMetricsExporter,
)
from opentelemetry.exporter.clickhouse_genai.trace_exporter import (
    ClickHouseGenAISpanExporter,
)
from opentelemetry.exporter.clickhouse_genai.version import __version__

__all__ = [
    "ClickHouseGenAIConfig",
    "ClickHouseGenAISpanExporter",
    "ClickHouseGenAIMetricsExporter",
    "ClickHouseGenAILogsExporter",
    "ClickHouseConnection",
    "__version__",
]
