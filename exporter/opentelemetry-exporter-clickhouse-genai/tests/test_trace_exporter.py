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

"""Tests for ClickHouse GenAI span exporter."""

from unittest.mock import MagicMock, patch

import pytest

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult
from opentelemetry.trace import SpanContext, SpanKind
from opentelemetry.trace.status import Status, StatusCode

from opentelemetry.exporter.clickhouse_genai import (
    ClickHouseGenAIConfig,
    ClickHouseGenAISpanExporter,
)
from opentelemetry.exporter.clickhouse_genai.utils import (
    extract_genai_attributes,
    format_span_id_fixed,
    format_trace_id_fixed,
)


class TestFormatFunctions:
    """Tests for ID formatting functions."""

    def test_format_trace_id_fixed(self):
        """Test trace ID formatting."""
        trace_id = 0x1234567890ABCDEF1234567890ABCDEF
        result = format_trace_id_fixed(trace_id)
        assert len(result) == 32
        assert result == "1234567890abcdef1234567890abcdef"

    def test_format_trace_id_fixed_zero(self):
        """Test zero trace ID formatting."""
        result = format_trace_id_fixed(0)
        assert result == "0" * 32

    def test_format_span_id_fixed(self):
        """Test span ID formatting."""
        span_id = 0x1234567890ABCDEF
        result = format_span_id_fixed(span_id)
        assert len(result) == 16
        assert result == "1234567890abcdef"

    def test_format_span_id_fixed_zero(self):
        """Test zero span ID formatting."""
        result = format_span_id_fixed(0)
        assert result == "0" * 16


class TestExtractGenAiAttributes:
    """Tests for GenAI attribute extraction."""

    def test_extract_genai_attributes(self, genai_span_attributes):
        """Test extracting GenAI attributes from span."""
        attrs = genai_span_attributes.copy()
        extracted = extract_genai_attributes(attrs)

        # Check extracted values
        assert extracted["GenAiOperationName"] == "chat"
        assert extracted["GenAiSystem"] == "openai"
        assert extracted["GenAiRequestModel"] == "gpt-4o"
        assert extracted["GenAiResponseModel"] == "gpt-4o-2024-05-13"
        assert extracted["InputTokens"] == 100
        assert extracted["OutputTokens"] == 50
        assert extracted["TotalTokens"] == 150
        assert extracted["Temperature"] == 0.7
        assert extracted["MaxTokens"] == 1000
        assert extracted["IsStreaming"] == 1
        assert extracted["FinishReasons"] == ["stop"]
        assert extracted["AvailableTools"] == ["get_weather", "search"]
        assert extracted["ServerAddress"] == "api.openai.com"
        assert extracted["ServerPort"] == 443

        # Check derived fields
        assert extracted["HasToolCalls"] == 1
        assert extracted["ToolCallCount"] == 2
        assert extracted["HasError"] == 0

        # Check attributes were popped
        assert "gen_ai.operation.name" not in attrs
        assert "gen_ai.system" not in attrs

    def test_extract_genai_attributes_empty(self):
        """Test extracting from empty attributes."""
        attrs = {}
        extracted = extract_genai_attributes(attrs)

        assert extracted["GenAiOperationName"] == ""
        assert extracted["InputTokens"] == 0
        assert extracted["HasError"] == 0

    def test_extract_genai_attributes_with_error(self):
        """Test extracting attributes with error."""
        attrs = {"error.type": "APIConnectionError"}
        extracted = extract_genai_attributes(attrs)

        assert extracted["ErrorType"] == "APIConnectionError"
        assert extracted["HasError"] == 1


class TestClickHouseGenAISpanExporter:
    """Tests for ClickHouseGenAISpanExporter."""

    @patch(
        "opentelemetry.exporter.clickhouse_genai.trace_exporter.ClickHouseConnection"
    )
    def test_export_empty_spans(self, mock_connection_class, config):
        """Test exporting empty span list."""
        exporter = ClickHouseGenAISpanExporter(config)
        result = exporter.export([])
        assert result == SpanExportResult.SUCCESS

    @patch(
        "opentelemetry.exporter.clickhouse_genai.trace_exporter.ClickHouseConnection"
    )
    def test_export_spans(self, mock_connection_class, config, genai_span_attributes):
        """Test exporting spans."""
        mock_connection = MagicMock()
        mock_connection_class.return_value = mock_connection

        exporter = ClickHouseGenAISpanExporter(config)
        exporter._initialized = True  # Skip initialization

        # Create a mock span
        span = MagicMock(spec=ReadableSpan)
        span.context = MagicMock()
        span.context.trace_id = 0x1234567890ABCDEF1234567890ABCDEF
        span.context.span_id = 0x1234567890ABCDEF
        span.context.trace_state = None
        span.parent = None
        span.name = "chat gpt-4o"
        span.kind = SpanKind.CLIENT
        span.start_time = 1700000000000000000
        span.end_time = 1700000001000000000
        span.status = Status(StatusCode.OK)
        span.attributes = genai_span_attributes
        span.events = []
        span.links = []
        span.resource = Resource.create({"service.name": "test-service"})
        span.instrumentation_scope = MagicMock()
        span.instrumentation_scope.name = "opentelemetry.instrumentation.openai"
        span.instrumentation_scope.version = "0.1.0"

        result = exporter.export([span])

        assert result == SpanExportResult.SUCCESS
        mock_connection.insert_traces.assert_called_once()

        # Verify the row structure
        rows = mock_connection.insert_traces.call_args[0][0]
        assert len(rows) == 1
        row = rows[0]

        assert row["TraceId"] == "1234567890abcdef1234567890abcdef"
        assert row["SpanId"] == "1234567890abcdef"
        assert row["SpanName"] == "chat gpt-4o"
        assert row["GenAiSystem"] == "openai"
        assert row["GenAiRequestModel"] == "gpt-4o"
        assert row["InputTokens"] == 100
        assert row["OutputTokens"] == 50

    @patch(
        "opentelemetry.exporter.clickhouse_genai.trace_exporter.ClickHouseConnection"
    )
    def test_export_failure(self, mock_connection_class, config):
        """Test export failure handling."""
        mock_connection = MagicMock()
        mock_connection.insert_traces.side_effect = Exception("Connection failed")
        mock_connection_class.return_value = mock_connection

        exporter = ClickHouseGenAISpanExporter(config)
        exporter._initialized = True

        span = MagicMock(spec=ReadableSpan)
        span.context = MagicMock()
        span.context.trace_id = 0x1234567890ABCDEF1234567890ABCDEF
        span.context.span_id = 0x1234567890ABCDEF
        span.context.trace_state = None
        span.parent = None
        span.name = "test"
        span.kind = SpanKind.CLIENT
        span.start_time = 1700000000000000000
        span.end_time = 1700000001000000000
        span.status = Status(StatusCode.OK)
        span.attributes = {}
        span.events = []
        span.links = []
        span.resource = Resource.create({})
        span.instrumentation_scope = None

        result = exporter.export([span])
        assert result == SpanExportResult.FAILURE

    @patch(
        "opentelemetry.exporter.clickhouse_genai.trace_exporter.ClickHouseConnection"
    )
    def test_shutdown(self, mock_connection_class, config):
        """Test exporter shutdown."""
        mock_connection = MagicMock()
        mock_connection_class.return_value = mock_connection

        exporter = ClickHouseGenAISpanExporter(config)
        exporter.shutdown()

        mock_connection.close.assert_called_once()

    @patch(
        "opentelemetry.exporter.clickhouse_genai.trace_exporter.ClickHouseConnection"
    )
    def test_force_flush(self, mock_connection_class, config):
        """Test force flush."""
        exporter = ClickHouseGenAISpanExporter(config)
        result = exporter.force_flush()
        assert result is True
