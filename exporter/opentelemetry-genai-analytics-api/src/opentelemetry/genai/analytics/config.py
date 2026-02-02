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

"""Configuration for GenAI Analytics API."""

from dataclasses import dataclass, field
from os import environ
from typing import Optional


def _parse_int_env(key: str, default: int) -> int:
    """Parse an integer environment variable with validation.

    Args:
        key: Environment variable name.
        default: Default value if not set.

    Returns:
        Parsed integer value.

    Raises:
        ValueError: If the value cannot be parsed as an integer.
    """
    value = environ.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"{key} must be an integer, got: {value!r}")


@dataclass
class ClickHouseConfig:
    """ClickHouse connection configuration.

    Reuses the same environment variables as the ClickHouse exporter
    for consistency.
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


@dataclass
class APIConfig:
    """API service configuration.

    Note: The default host "0.0.0.0" binds to all network interfaces.
    For local development only, consider using "127.0.0.1" instead.
    """

    host: str = field(
        default_factory=lambda: environ.get("GENAI_ANALYTICS_HOST", "0.0.0.0")
    )
    port: int = field(
        default_factory=lambda: _parse_int_env("GENAI_ANALYTICS_PORT", 8080)
    )
    workers: int = field(
        default_factory=lambda: _parse_int_env("GENAI_ANALYTICS_WORKERS", 4)
    )
    log_level: str = field(
        default_factory=lambda: environ.get("GENAI_ANALYTICS_LOG_LEVEL", "INFO")
    )
    # Default time range for queries (in hours)
    default_time_range_hours: int = field(
        default_factory=lambda: _parse_int_env(
            "GENAI_ANALYTICS_DEFAULT_TIME_RANGE_HOURS", 24
        )
    )
    # Maximum time range for queries (in days)
    max_time_range_days: int = field(
        default_factory=lambda: _parse_int_env(
            "GENAI_ANALYTICS_MAX_TIME_RANGE_DAYS", 90
        )
    )
    # CORS allowed origins (comma-separated). Use "*" for all origins (development only)
    cors_origins: str = field(
        default_factory=lambda: environ.get("GENAI_ANALYTICS_CORS_ORIGINS", "*")
    )


@dataclass
class Settings:
    """Combined application settings."""

    clickhouse: ClickHouseConfig = field(default_factory=ClickHouseConfig)
    api: APIConfig = field(default_factory=APIConfig)


# Global settings instance
settings = Settings()
