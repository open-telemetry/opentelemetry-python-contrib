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

"""Tests for GenAI Analytics API endpoints."""

from datetime import datetime, timedelta, timezone

import pytest


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_check(self, test_client):
        """Test health check returns healthy status."""
        response = test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert data["clickhouse"]["status"] == "connected"

    def test_root_endpoint(self, test_client):
        """Test root endpoint returns API info."""
        response = test_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "OpenTelemetry GenAI Analytics API"
        assert "version" in data
        assert data["docs"] == "/docs"


class TestCostAnalytics:
    """Tests for cost analytics endpoint."""

    def test_cost_analytics_empty(self, test_client, mock_client):
        """Test cost analytics with no data."""
        mock_client.set_results([])

        response = test_client.get("/api/v1/analytics/costs")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "meta" in data

    def test_cost_analytics_with_filters(self, test_client, mock_client):
        """Test cost analytics with query filters."""
        mock_client.set_results([])

        response = test_client.get(
            "/api/v1/analytics/costs",
            params={
                "provider": "openai",
                "granularity": "hour",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["filters_applied"]["provider"] == "openai"
        assert data["meta"]["granularity"] == "hour"

    def test_cost_analytics_with_data(
        self, test_client, mock_client, sample_cost_results, sample_cost_totals
    ):
        """Test cost analytics correctly transforms and nests data."""
        # Set up sequence: first call returns time series, second returns totals
        mock_client.set_result_sequence(sample_cost_results, sample_cost_totals)

        response = test_client.get("/api/v1/analytics/costs")
        assert response.status_code == 200
        data = response.json()

        # Verify provider nesting
        assert "openai" in data["data"]["providers"]
        assert "anthropic" in data["data"]["providers"]

        # Verify model nesting within providers
        openai_data = data["data"]["providers"]["openai"]
        assert "gpt-4" in openai_data["models"]
        assert "gpt-3.5-turbo" in openai_data["models"]

        # Verify totals are calculated correctly
        assert data["data"]["totals"]["total_cost"] == pytest.approx(27.75, rel=0.01)
        assert data["data"]["totals"]["request_count"] == 350

        # Verify provider totals
        assert openai_data["totals"]["total_cost"] == pytest.approx(12.75, rel=0.01)
        assert openai_data["totals"]["request_count"] == 300


class TestTokenAnalytics:
    """Tests for token analytics endpoint."""

    def test_token_analytics_empty(self, test_client, mock_client):
        """Test token analytics with no data."""
        mock_client.set_results([])

        response = test_client.get("/api/v1/analytics/tokens")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert data["data"]["totals"]["total_tokens"] == 0


class TestLatencyAnalytics:
    """Tests for latency analytics endpoint."""

    def test_latency_analytics_empty(self, test_client, mock_client):
        """Test latency analytics with no data."""
        mock_client.set_results([])

        response = test_client.get("/api/v1/analytics/latency")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_latency_with_time_series(self, test_client, mock_client):
        """Test latency analytics with time series enabled."""
        mock_client.set_results([])

        response = test_client.get(
            "/api/v1/analytics/latency",
            params={"include_time_series": True},
        )
        assert response.status_code == 200

    def test_latency_analytics_with_data(
        self, test_client, mock_client, sample_latency_results
    ):
        """Test latency analytics correctly transforms data."""
        mock_client.set_results(sample_latency_results)

        response = test_client.get("/api/v1/analytics/latency")
        assert response.status_code == 200
        data = response.json()

        # Verify provider nesting
        assert "openai" in data["data"]["providers"]
        assert "anthropic" in data["data"]["providers"]

        # Verify model latency data
        gpt4_latency = data["data"]["providers"]["openai"]["models"]["gpt-4"]["percentiles"]
        assert gpt4_latency["p50"] == 500.0
        assert gpt4_latency["p95"] == 1200.0
        assert gpt4_latency["p99"] == 1500.0
        assert gpt4_latency["avg"] == 600.0
        assert gpt4_latency["request_count"] == 100


class TestErrorAnalytics:
    """Tests for error analytics endpoint."""

    def test_error_analytics_empty(self, test_client, mock_client):
        """Test error analytics with no data."""
        mock_client.set_results([])

        response = test_client.get("/api/v1/analytics/errors")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["total_requests"] == 0
        assert data["data"]["overall_error_rate"] == 0


class TestModelAnalytics:
    """Tests for model analytics endpoint."""

    def test_model_analytics_empty(self, test_client, mock_client):
        """Test model analytics with no data."""
        mock_client.set_results([])

        response = test_client.get("/api/v1/analytics/models")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["total_requests"] == 0
        assert data["data"]["unique_models"] == 0


class TestUserAnalytics:
    """Tests for user analytics endpoint."""

    def test_user_analytics_empty(self, test_client, mock_client):
        """Test user analytics with no data."""
        mock_client.set_results([])

        response = test_client.get("/api/v1/analytics/users")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["total_users"] == 0

    def test_user_analytics_with_limit(self, test_client, mock_client):
        """Test user analytics with limit parameter."""
        mock_client.set_results([])

        response = test_client.get(
            "/api/v1/analytics/users",
            params={"limit": 50},
        )
        assert response.status_code == 200


class TestTenantAnalytics:
    """Tests for tenant analytics endpoint."""

    def test_tenant_analytics_empty(self, test_client, mock_client):
        """Test tenant analytics with no data."""
        mock_client.set_results([])

        response = test_client.get("/api/v1/analytics/tenants")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["total_tenants"] == 0


class TestSessionAnalytics:
    """Tests for session analytics endpoint."""

    def test_session_analytics_empty(self, test_client, mock_client):
        """Test session analytics with no data."""
        mock_client.set_results([])

        response = test_client.get("/api/v1/analytics/sessions")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["summary"]["total_sessions"] == 0


class TestToolAnalytics:
    """Tests for tool analytics endpoint."""

    def test_tool_analytics_empty(self, test_client, mock_client):
        """Test tool analytics with no data."""
        mock_client.set_results([])

        response = test_client.get("/api/v1/analytics/tools")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["total_invocations"] == 0


class TestProviderComparison:
    """Tests for provider comparison endpoint."""

    def test_provider_comparison_empty(self, test_client, mock_client):
        """Test provider comparison with no data."""
        mock_client.set_results([])

        response = test_client.get("/api/v1/analytics/providers/compare")
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]["providers"]) == 0


class TestAuditTrail:
    """Tests for audit trail endpoint."""

    def test_audit_traces_empty(self, test_client, mock_client):
        """Test audit traces with no data."""
        mock_client.set_results([])

        response = test_client.get("/api/v1/audit/traces")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["total_count"] == 0

    def test_audit_traces_pagination(self, test_client, mock_client):
        """Test audit traces with pagination."""
        mock_client.set_results([])

        response = test_client.get(
            "/api/v1/audit/traces",
            params={"page": 2, "page_size": 50},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["page"] == 2
        assert data["data"]["page_size"] == 50


class TestTimeRangeValidation:
    """Tests for time range validation."""

    def test_time_range_exceeds_maximum(self, test_client, mock_client):
        """Test that time ranges exceeding max_time_range_days are rejected."""
        mock_client.set_results([])

        # Request 100 days, which exceeds the default 90-day max
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=100)

        response = test_client.get(
            "/api/v1/analytics/costs",
            params={
                "start_time": start.isoformat(),
                "end_time": now.isoformat(),
            },
        )
        assert response.status_code == 400
        assert "exceeds maximum" in response.json()["detail"]

    def test_start_time_after_end_time(self, test_client, mock_client):
        """Test that start_time > end_time is rejected."""
        mock_client.set_results([])

        now = datetime.now(timezone.utc)
        start = now + timedelta(days=1)  # Start is after now (end)

        response = test_client.get(
            "/api/v1/analytics/costs",
            params={
                "start_time": start.isoformat(),
                "end_time": now.isoformat(),
            },
        )
        assert response.status_code == 400
        assert "before" in response.json()["detail"]

    def test_valid_time_range(self, test_client, mock_client):
        """Test that valid time ranges are accepted."""
        mock_client.set_results([])

        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)

        response = test_client.get(
            "/api/v1/analytics/costs",
            params={
                "start_time": start.isoformat(),
                "end_time": now.isoformat(),
            },
        )
        assert response.status_code == 200


class TestErrorHandling:
    """Tests for error handling."""

    def test_error_analytics_with_data(
        self, test_client, mock_client, sample_error_rates
    ):
        """Test error analytics correctly transforms data."""
        # Set up sequence: error rates, breakdown, time series
        mock_client.set_result_sequence(
            sample_error_rates,  # error rates
            [],  # breakdown (empty for simplicity)
            [],  # time series (empty for simplicity)
        )

        response = test_client.get("/api/v1/analytics/errors")
        assert response.status_code == 200
        data = response.json()

        # Verify provider nesting
        assert "openai" in data["data"]["providers"]
        assert "anthropic" in data["data"]["providers"]

        # Verify totals
        assert data["data"]["total_requests"] == 350
        assert data["data"]["total_errors"] == 8
        # 8/350 ≈ 0.0229
        assert data["data"]["overall_error_rate"] == pytest.approx(0.0229, rel=0.01)


class TestQueryBuilderValidation:
    """Tests for QueryBuilder SQL injection protection."""

    def test_valid_group_by_columns(self):
        """Test that valid group_by columns are accepted."""
        from opentelemetry.genai.analytics.db.queries import QueryBuilder

        builder = QueryBuilder(database="test_db")
        # Should not raise
        builder._validate_group_by(["Provider", "RequestModel"])

    def test_invalid_group_by_column_rejected(self):
        """Test that invalid group_by columns raise ValueError."""
        from opentelemetry.genai.analytics.db.queries import QueryBuilder

        builder = QueryBuilder(database="test_db")
        with pytest.raises(ValueError, match="Invalid group_by column"):
            builder._validate_group_by(["Provider", "MaliciousColumn; DROP TABLE users;--"])

    def test_sql_injection_attempt_blocked(self):
        """Test that SQL injection attempts via group_by are blocked."""
        from opentelemetry.genai.analytics.db.queries import QueryBuilder

        builder = QueryBuilder(database="test_db")
        malicious_inputs = [
            "Provider; DROP TABLE genai_spans;--",
            "1=1; DELETE FROM genai_spans;",
            "Provider UNION SELECT * FROM users",
            "Provider' OR '1'='1",
        ]
        for malicious in malicious_inputs:
            with pytest.raises(ValueError, match="Invalid group_by column"):
                builder._validate_group_by([malicious])
