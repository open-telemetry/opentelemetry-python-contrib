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


@dataclass
class CollectorConfig(ClickHouseGenAIConfig):
    """Configuration for OTLP Collector with ClickHouse export.

    Extends ClickHouseGenAIConfig with receiver settings for running
    as an OTLP collector service.

    Attributes:
        grpc_endpoint: gRPC receiver endpoint (host:port).
        http_endpoint: HTTP receiver endpoint (host:port).
        enable_grpc: Whether to enable gRPC receiver.
        enable_http: Whether to enable HTTP receiver.
        grpc_max_workers: Maximum worker threads for gRPC server.
        batch_timeout_ms: Timeout before flushing incomplete batch (ms).
        max_queue_size: Maximum items in processing queue before dropping.
    """

    grpc_endpoint: str = field(
        default_factory=lambda: environ.get(
            "OTEL_COLLECTOR_GRPC_ENDPOINT", "0.0.0.0:4317"
        )
    )
    http_endpoint: str = field(
        default_factory=lambda: environ.get(
            "OTEL_COLLECTOR_HTTP_ENDPOINT", "0.0.0.0:4318"
        )
    )
    enable_grpc: bool = field(
        default_factory=lambda: environ.get(
            "OTEL_COLLECTOR_ENABLE_GRPC", "true"
        ).lower()
        == "true"
    )
    enable_http: bool = field(
        default_factory=lambda: environ.get(
            "OTEL_COLLECTOR_ENABLE_HTTP", "true"
        ).lower()
        == "true"
    )
    grpc_max_workers: int = field(
        default_factory=lambda: int(
            environ.get("OTEL_COLLECTOR_GRPC_MAX_WORKERS", "10")
        )
    )
    batch_timeout_ms: int = field(
        default_factory=lambda: int(
            environ.get("OTEL_COLLECTOR_BATCH_TIMEOUT_MS", "5000")
        )
    )
    max_queue_size: int = field(
        default_factory=lambda: int(
            environ.get("OTEL_COLLECTOR_MAX_QUEUE_SIZE", "10000")
        )
    )

    def __post_init__(self):
        """Validate configuration after initialization."""
        super().__post_init__()
        if not self.enable_grpc and not self.enable_http:
            raise ValueError(
                "At least one receiver (gRPC or HTTP) must be enabled"
            )
        if self.grpc_max_workers < 1:
            raise ValueError("gRPC max workers must be at least 1")
        if self.batch_timeout_ms < 100:
            raise ValueError("Batch timeout must be at least 100ms")
        if self.max_queue_size < 100:
            raise ValueError("Max queue size must be at least 100")
