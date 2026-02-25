from __future__ import annotations

import json
import os
from typing import Any, Dict, List
from unittest import TestCase
from unittest.mock import patch

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import error_attributes
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import StatusCode
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import Error, LLMInvocation, ToolCall

_DEFAULT_SCHEMA_URL = Schemas.V1_37_0.value

SCOPE = "opentelemetry.util.genai.handler"


class TelemetryHandlerMetricsTest(TestBase):
    def test_stop_llm_records_duration_and_tokens(self) -> None:
        handler = TelemetryHandler(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )
        invocation = LLMInvocation(request_model="model", provider="prov")
        invocation.input_tokens = 5
        invocation.output_tokens = 7
        # Patch default_timer during start to ensure monotonic_start_s
        with patch("timeit.default_timer", return_value=1000.0):
            handler.start_llm(invocation)

        # Simulate 2 seconds of elapsed monotonic time (seconds)
        with patch(
            "timeit.default_timer",
            return_value=1002.0,
        ):
            handler.stop_llm(invocation)

        self._assert_metric_scope_schema_urls(_DEFAULT_SCHEMA_URL)
        metrics = self._harvest_metrics()
        self.assertIn("gen_ai.client.operation.duration", metrics)
        duration_points = metrics["gen_ai.client.operation.duration"]
        self.assertEqual(len(duration_points), 1)
        duration_point = duration_points[0]
        self.assertEqual(
            duration_point.attributes[GenAI.GEN_AI_OPERATION_NAME],
            GenAI.GenAiOperationNameValues.CHAT.value,
        )
        self.assertEqual(
            duration_point.attributes[GenAI.GEN_AI_REQUEST_MODEL], "model"
        )
        self.assertEqual(
            duration_point.attributes[GenAI.GEN_AI_PROVIDER_NAME], "prov"
        )
        self.assertAlmostEqual(duration_point.sum, 2.0, places=3)

        self.assertIn("gen_ai.client.token.usage", metrics)
        token_points = metrics["gen_ai.client.token.usage"]
        token_by_type = {
            point.attributes[GenAI.GEN_AI_TOKEN_TYPE]: point
            for point in token_points
        }
        self.assertEqual(len(token_by_type), 2)
        self.assertAlmostEqual(
            token_by_type[GenAI.GenAiTokenTypeValues.INPUT.value].sum,
            5.0,
            places=3,
        )
        self.assertAlmostEqual(
            token_by_type[GenAI.GenAiTokenTypeValues.COMPLETION.value].sum,
            7.0,
            places=3,
        )

    def test_stop_llm_records_duration_and_tokens_with_additional_attributes(
        self,
    ) -> None:
        handler = TelemetryHandler(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )

        invocation = LLMInvocation(request_model="model", provider="prov")
        invocation.input_tokens = 5
        invocation.output_tokens = 7
        invocation.server_address = "custom.server.com"
        invocation.server_port = 42
        handler.start_llm(invocation)
        invocation.metric_attributes = {
            "custom.attribute": "custom_value",
        }
        invocation.attributes = {"should not be on metrics": "value"}
        handler.stop_llm(invocation)

        self._assert_metric_scope_schema_urls(_DEFAULT_SCHEMA_URL)
        metrics = self._harvest_metrics()
        self.assertIn("gen_ai.client.operation.duration", metrics)
        duration_points = metrics["gen_ai.client.operation.duration"]
        self.assertIn("gen_ai.client.token.usage", metrics)
        token_points = metrics["gen_ai.client.token.usage"]
        points = duration_points + token_points

        for point in points:
            self.assertEqual(
                point.attributes["server.address"], "custom.server.com"
            )
            self.assertEqual(point.attributes["server.port"], 42)
            self.assertEqual(
                point.attributes["custom.attribute"], "custom_value"
            )
            self.assertIsNone(point.attributes.get("should not be on metrics"))

    def test_fail_llm_records_error_and_available_tokens(self) -> None:
        handler = TelemetryHandler(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )
        invocation = LLMInvocation(request_model="err-model", provider=None)
        invocation.input_tokens = 11
        # Patch default_timer during start to ensure monotonic_start_s
        with patch("timeit.default_timer", return_value=2000.0):
            handler.start_llm(invocation)

        error = Error(message="boom", type=ValueError)
        with patch(
            "timeit.default_timer",
            return_value=2001.0,
        ):
            handler.fail_llm(invocation, error)

        self._assert_metric_scope_schema_urls(_DEFAULT_SCHEMA_URL)
        metrics = self._harvest_metrics()
        self.assertIn("gen_ai.client.operation.duration", metrics)
        duration_points = metrics["gen_ai.client.operation.duration"]
        self.assertEqual(len(duration_points), 1)
        duration_point = duration_points[0]
        self.assertEqual(
            duration_point.attributes.get("error.type"), "ValueError"
        )
        self.assertEqual(
            duration_point.attributes.get(GenAI.GEN_AI_REQUEST_MODEL),
            "err-model",
        )
        self.assertAlmostEqual(duration_point.sum, 1.0, places=3)

        self.assertIn("gen_ai.client.token.usage", metrics)
        token_points = metrics["gen_ai.client.token.usage"]
        self.assertEqual(len(token_points), 1)
        token_point = token_points[0]
        self.assertEqual(
            token_point.attributes[GenAI.GEN_AI_TOKEN_TYPE],
            GenAI.GenAiTokenTypeValues.INPUT.value,
        )
        self.assertAlmostEqual(token_point.sum, 11.0, places=3)

    def _harvest_metrics(
        self,
    ) -> Dict[str, List[Any]]:
        """Returns (metrics_by_name, resource_metrics).

        metrics_by_name maps metric name to list of data points.
        resource_metrics is the raw ResourceMetrics list for scope-level
        assertions (e.g. schema_url).
        """
        metrics = self.get_sorted_metrics(SCOPE)
        metrics_by_name: Dict[str, List[Any]] = {}
        for metric in metrics or []:
            points = metric.data.data_points or []
            metrics_by_name.setdefault(metric.name, []).extend(points)
        return metrics_by_name

    def _assert_metric_scope_schema_urls(
        self, expected_schema_url: str
    ) -> None:
        for (
            resource_metric
        ) in self.memory_metrics_reader.get_metrics_data().resource_metrics:
            for scope_metric in resource_metric.scope_metrics:
                if scope_metric.scope.name != SCOPE:
                    continue
                self.assertEqual(
                    scope_metric.scope.schema_url, expected_schema_url
                )


class TelemetryHandlerToolTest(TestCase):
    """Tests for tool call lifecycle methods"""

    def setUp(self) -> None:
        self.span_exporter = InMemorySpanExporter()
        self.tracer_provider = TracerProvider()
        self.tracer_provider.add_span_processor(
            SimpleSpanProcessor(self.span_exporter)
        )
        self.handler = TelemetryHandler(tracer_provider=self.tracer_provider)

    def test_start_tool_call_creates_span(self):
        """Test start_tool_call creates span with correct name and kind"""
        tool = ToolCall(
            name="get_weather",
            arguments={"location": "Paris"},
            id="call_123",
        )
        self.handler.start_tool_call(tool)

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)  # Span not finished yet

        self.assertIsNotNone(tool.span)
        self.assertIsNotNone(tool.context_token)
        self.assertEqual(tool.span.name, "execute_tool get_weather")
        # Check kind is INTERNAL (value 1)
        self.assertEqual(tool.span.kind, SpanKind.INTERNAL)

    def test_stop_tool_call_ends_span(self):
        """Test stop_tool_call ends span successfully"""
        tool = ToolCall(
            name="get_weather",
            arguments={"location": "Paris"},
            id="call_123",
            tool_type="function",
            tool_description="Get current weather",
        )
        self.handler.start_tool_call(tool)
        tool.tool_result = {"temp": 20, "condition": "sunny"}
        self.handler.stop_tool_call(tool)

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertEqual(span.name, "execute_tool get_weather")
        self.assertEqual(span.kind, SpanKind.INTERNAL)

        # Check required attributes
        self.assertEqual(
            span.attributes[GenAI.GEN_AI_OPERATION_NAME],
            "execute_tool",
        )
        # Check recommended attributes
        self.assertEqual(
            span.attributes[GenAI.GEN_AI_TOOL_NAME], "get_weather"
        )
        self.assertEqual(
            span.attributes[GenAI.GEN_AI_TOOL_CALL_ID], "call_123"
        )
        self.assertEqual(span.attributes[GenAI.GEN_AI_TOOL_TYPE], "function")
        self.assertEqual(
            span.attributes[GenAI.GEN_AI_TOOL_DESCRIPTION],
            "Get current weather",
        )

        # Check status is OK
        self.assertEqual(span.status.status_code, StatusCode.OK)

    def test_stop_tool_call_without_start(self):
        """Test stop_tool_call without prior start is a no-op"""
        tool = ToolCall(name="test", arguments={}, id=None)
        # Don't call start_tool_call
        self.handler.stop_tool_call(tool)

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_fail_tool_call_sets_error_status(self):
        """Test fail_tool_call sets error status and attributes"""
        tool = ToolCall(name="failing_tool", arguments={}, id="call_456")
        self.handler.start_tool_call(tool)

        error = Error(message="Tool execution failed", type=ValueError)
        self.handler.fail_tool_call(tool, error)

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertEqual(span.name, "execute_tool failing_tool")
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(
            span.attributes[error_attributes.ERROR_TYPE], "ValueError"
        )

    @patch.dict(
        os.environ,
        {
            OTEL_SEMCONV_STABILITY_OPT_IN: "gen_ai_latest_experimental",
            OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "SPAN_ONLY",
        },
    )
    def test_tool_call_with_content_capture(self):
        """Test tool call captures arguments and results when SPAN_ONLY mode"""
        # Reset semconv state after patching env
        _OpenTelemetrySemanticConventionStability._initialized = False
        _OpenTelemetrySemanticConventionStability._initialize()

        tool = ToolCall(
            name="get_weather",
            arguments={"location": "Paris"},
            id="call_123",
        )
        self.handler.start_tool_call(tool)
        tool.tool_result = {"temp": 20, "condition": "sunny"}
        self.handler.stop_tool_call(tool)

        spans = self.span_exporter.get_finished_spans()
        span = spans[0]

        # Check that arguments and result are captured
        self.assertIn(GenAI.GEN_AI_TOOL_CALL_ARGUMENTS, span.attributes)
        self.assertIn(GenAI.GEN_AI_TOOL_CALL_RESULT, span.attributes)

        # Verify JSON serialization
        args = json.loads(span.attributes[GenAI.GEN_AI_TOOL_CALL_ARGUMENTS])
        self.assertEqual(args["location"], "Paris")

        result = json.loads(span.attributes[GenAI.GEN_AI_TOOL_CALL_RESULT])
        self.assertEqual(result["temp"], 20)

    def test_tool_call_context_manager_success(self):
        """Test tool_call context manager successfully"""
        tool = ToolCall(
            name="calculate_sum",
            arguments={"a": 5, "b": 3},
            id="call_789",
            tool_type="function",
        )

        with self.handler.tool_call(tool) as tc:
            # Simulate tool execution
            tc.tool_result = {"sum": 8}

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertEqual(span.name, "execute_tool calculate_sum")
        self.assertEqual(span.status.status_code, StatusCode.OK)
        self.assertEqual(
            span.attributes[GenAI.GEN_AI_TOOL_NAME], "calculate_sum"
        )

    def test_tool_call_context_manager_with_exception(self):
        """Test tool_call context manager handles exceptions"""
        tool = ToolCall(name="failing_operation", arguments={}, id="call_999")

        class ToolExecutionError(RuntimeError):
            pass

        with self.assertRaises(ToolExecutionError):
            with self.handler.tool_call(tool):
                raise ToolExecutionError("Tool execution failed")

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

        span = spans[0]
        self.assertEqual(span.name, "execute_tool failing_operation")
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        # Error type includes full qualified name for local classes
        self.assertIn(
            "ToolExecutionError",
            span.attributes[error_attributes.ERROR_TYPE],
        )
