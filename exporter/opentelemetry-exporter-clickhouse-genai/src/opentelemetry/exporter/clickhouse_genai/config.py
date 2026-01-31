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

"""Configuration for ClickHouse GenAI exporter."""

from dataclasses import dataclass, field
from os import environ
from typing import Optional


@dataclass
class ClickHouseGenAIConfig:
    """Configuration for ClickHouse GenAI exporter.

    Attributes:
        endpoint: ClickHouse server endpoint (tcp://host:port or host:port).
        database: Database name for GenAI observability data.
        username: ClickHouse username.
        password: ClickHouse password.
        secure: Whether to use TLS for connection.
        ca_cert: Path to CA certificate file for TLS.
        create_schema: Whether to auto-create tables on startup.
        traces_table: Name of the traces table.
        metrics_table: Name of the metrics table.
        logs_table: Name of the logs table.
        batch_size: Number of records per insert batch.
        flush_interval_ms: Interval between flushes in milliseconds.
        ttl_days: Data retention period in days.
        compression: Compression algorithm (lz4, zstd, none).
    """

    endpoint: str = field(
        default_factory=lambda: environ.get(
            "OTEL_EXPORTER_CLICKHOUSE_ENDPOINT", "localhost:9000"
        )
    )
    database: str = field(
        default_factory=lambda: environ.get(
            "OTEL_EXPORTER_CLICKHOUSE_DATABASE", "otel_genai"
        )
    )
    username: str = field(
        default_factory=lambda: environ.get(
            "OTEL_EXPORTER_CLICKHOUSE_USERNAME", "default"
        )
    )
    password: str = field(
        default_factory=lambda: environ.get(
            "OTEL_EXPORTER_CLICKHOUSE_PASSWORD", ""
        )
    )
    secure: bool = field(
        default_factory=lambda: environ.get(
            "OTEL_EXPORTER_CLICKHOUSE_SECURE", "false"
        ).lower()
        == "true"
    )
    ca_cert: Optional[str] = field(
        default_factory=lambda: environ.get("OTEL_EXPORTER_CLICKHOUSE_CA_CERT")
    )
    create_schema: bool = field(
        default_factory=lambda: environ.get(
            "OTEL_EXPORTER_CLICKHOUSE_CREATE_SCHEMA", "true"
        ).lower()
        == "true"
    )
    traces_table: str = "genai_traces"
    metrics_table: str = "genai_metrics"
    logs_table: str = "genai_logs"
    batch_size: int = field(
        default_factory=lambda: int(
            environ.get("OTEL_EXPORTER_CLICKHOUSE_BATCH_SIZE", "1000")
        )
    )
    flush_interval_ms: int = 5000
    ttl_days: int = field(
        default_factory=lambda: int(
            environ.get("OTEL_EXPORTER_CLICKHOUSE_TTL_DAYS", "7")
        )
    )
    compression: str = field(
        default_factory=lambda: environ.get(
            "OTEL_EXPORTER_CLICKHOUSE_COMPRESSION", "lz4"
        )
    )

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.endpoint:
            raise ValueError("ClickHouse endpoint is required")
        if self.ttl_days < 1:
            raise ValueError("TTL days must be at least 1")
        if self.batch_size < 1:
            raise ValueError("Batch size must be at least 1")
        if self.compression not in ("lz4", "zstd", "none", ""):
            raise ValueError(
                f"Invalid compression: {self.compression}. "
                "Must be one of: lz4, zstd, none"
            )
