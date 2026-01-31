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

"""Tests for ClickHouse GenAI configuration."""

import os
from unittest.mock import patch

import pytest

from opentelemetry.exporter.clickhouse_genai import ClickHouseGenAIConfig


class TestClickHouseGenAIConfig:
    """Tests for ClickHouseGenAIConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ClickHouseGenAIConfig()

        assert config.endpoint == "localhost:9000"
        assert config.database == "otel_genai"
        assert config.username == "default"
        assert config.password == ""
        assert config.secure is False
        assert config.create_schema is True
        assert config.traces_table == "genai_traces"
        assert config.metrics_table == "genai_metrics"
        assert config.logs_table == "genai_logs"
        assert config.batch_size == 1000
        assert config.ttl_days == 7
        assert config.compression == "lz4"

    def test_custom_config(self):
        """Test custom configuration values."""
        config = ClickHouseGenAIConfig(
            endpoint="custom-host:9001",
            database="custom_db",
            username="custom_user",
            password="secret",
            secure=True,
            create_schema=False,
            ttl_days=30,
            compression="zstd",
        )

        assert config.endpoint == "custom-host:9001"
        assert config.database == "custom_db"
        assert config.username == "custom_user"
        assert config.password == "secret"
        assert config.secure is True
        assert config.create_schema is False
        assert config.ttl_days == 30
        assert config.compression == "zstd"

    def test_config_from_env_vars(self):
        """Test configuration from environment variables."""
        env_vars = {
            "OTEL_EXPORTER_CLICKHOUSE_ENDPOINT": "env-host:9002",
            "OTEL_EXPORTER_CLICKHOUSE_DATABASE": "env_db",
            "OTEL_EXPORTER_CLICKHOUSE_USERNAME": "env_user",
            "OTEL_EXPORTER_CLICKHOUSE_PASSWORD": "env_secret",
            "OTEL_EXPORTER_CLICKHOUSE_SECURE": "true",
            "OTEL_EXPORTER_CLICKHOUSE_CREATE_SCHEMA": "false",
            "OTEL_EXPORTER_CLICKHOUSE_TTL_DAYS": "14",
            "OTEL_EXPORTER_CLICKHOUSE_BATCH_SIZE": "500",
            "OTEL_EXPORTER_CLICKHOUSE_COMPRESSION": "zstd",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            config = ClickHouseGenAIConfig()

            assert config.endpoint == "env-host:9002"
            assert config.database == "env_db"
            assert config.username == "env_user"
            assert config.password == "env_secret"
            assert config.secure is True
            assert config.create_schema is False
            assert config.ttl_days == 14
            assert config.batch_size == 500
            assert config.compression == "zstd"

    def test_invalid_ttl_days(self):
        """Test validation for invalid TTL days."""
        with pytest.raises(ValueError, match="TTL days must be at least 1"):
            ClickHouseGenAIConfig(ttl_days=0)

    def test_invalid_batch_size(self):
        """Test validation for invalid batch size."""
        with pytest.raises(ValueError, match="Batch size must be at least 1"):
            ClickHouseGenAIConfig(batch_size=0)

    def test_invalid_compression(self):
        """Test validation for invalid compression."""
        with pytest.raises(ValueError, match="Invalid compression"):
            ClickHouseGenAIConfig(compression="invalid")

    def test_empty_endpoint(self):
        """Test validation for empty endpoint."""
        with pytest.raises(ValueError, match="endpoint is required"):
            ClickHouseGenAIConfig(endpoint="")
