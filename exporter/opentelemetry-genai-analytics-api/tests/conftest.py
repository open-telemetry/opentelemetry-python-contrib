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

"""Test fixtures for GenAI Analytics API."""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from opentelemetry.genai.analytics.db.connection import ClickHouseClient
from opentelemetry.genai.analytics.main import app


class MockClickHouseClient:
    """Mock ClickHouse client for testing.

    Supports returning different results for different queries by matching
    query patterns or returning results in sequence.
    """

    def __init__(self):
        self.mock_results: list[tuple] = []
        self._result_sequence: list[list[tuple]] = []
        self._call_index: int = 0

    def set_results(self, results: list[tuple]):
        """Set mock results to return for all queries."""
        self.mock_results = results
        self._result_sequence = []
        self._call_index = 0

    def set_result_sequence(self, *results_list: list[tuple]):
        """Set a sequence of results to return for consecutive queries.

        Each call to execute() returns the next result in the sequence.
        """
        self._result_sequence = list(results_list)
        self._call_index = 0

    def execute(self, query: str, params: dict[str, Any] | None = None) -> list[tuple]:
        """Return mock results.

        If a result sequence is set, returns results in sequence.
        Otherwise, returns the default mock_results.
        """
        if self._result_sequence:
            if self._call_index < len(self._result_sequence):
                result = self._result_sequence[self._call_index]
                self._call_index += 1
                return result
            return []
        return self.mock_results

    def ping(self) -> bool:
        """Always return True for tests."""
        return True

    def close(self) -> None:
        """No-op for tests."""
        pass


@pytest.fixture
def mock_client():
    """Create a mock ClickHouse client."""
    return MockClickHouseClient()


@pytest.fixture
def test_client(mock_client):
    """Create a test client with mocked dependencies."""
    from opentelemetry.genai.analytics.api.dependencies import get_db_client

    def mock_get_db_client():
        """Mock dependency that yields the mock client."""
        yield mock_client

    app.dependency_overrides[get_db_client] = mock_get_db_client

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def sample_cost_results():
    """Sample cost query results."""
    now = datetime.now(timezone.utc)
    return [
        # time_bucket, provider, model, total_cost, request_count, input_tokens, output_tokens
        (now, "openai", "gpt-4", 10.50, 100, 50000, 25000),
        (now, "openai", "gpt-3.5-turbo", 2.25, 200, 100000, 50000),
        (now, "anthropic", "claude-3-opus", 15.00, 50, 30000, 15000),
    ]


@pytest.fixture
def sample_cost_totals():
    """Sample cost totals results."""
    return [
        # provider, model, total_cost, request_count, input_tokens, output_tokens, avg_cost
        ("openai", "gpt-4", 10.50, 100, 50000, 25000, 0.105),
        ("openai", "gpt-3.5-turbo", 2.25, 200, 100000, 50000, 0.01125),
        ("anthropic", "claude-3-opus", 15.00, 50, 30000, 15000, 0.30),
    ]


@pytest.fixture
def sample_latency_results():
    """Sample latency query results."""
    return [
        # provider, model, p50, p75, p90, p95, p99, avg, min, max, count
        ("openai", "gpt-4", 500.0, 750.0, 1000.0, 1200.0, 1500.0, 600.0, 100.0, 2000.0, 100),
        ("openai", "gpt-3.5-turbo", 200.0, 300.0, 400.0, 500.0, 600.0, 250.0, 50.0, 800.0, 200),
        ("anthropic", "claude-3-opus", 800.0, 1000.0, 1500.0, 1800.0, 2200.0, 900.0, 200.0, 3000.0, 50),
    ]


@pytest.fixture
def sample_error_rates():
    """Sample error rates results."""
    return [
        # provider, model, total_requests, error_count, error_rate
        ("openai", "gpt-4", 100, 5, 0.05),
        ("openai", "gpt-3.5-turbo", 200, 2, 0.01),
        ("anthropic", "claude-3-opus", 50, 1, 0.02),
    ]


@pytest.fixture
def sample_error_breakdown():
    """Sample error breakdown results."""
    return [
        # provider, model, error_type, status_code, count
        ("openai", "gpt-4", "rate_limit_exceeded", "ERROR", 3),
        ("openai", "gpt-4", "timeout", "ERROR", 2),
        ("openai", "gpt-3.5-turbo", "invalid_request", "ERROR", 2),
    ]
