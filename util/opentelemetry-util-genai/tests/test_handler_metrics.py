# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import patch

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.test.test_base import TestBase
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import Error

_DEFAULT_SCHEMA_URL = Schemas.V1_37_0.value

SCOPE = "opentelemetry.util.genai.handler"


class TelemetryHandlerMetricsTest(TestBase):
    def test_stop_llm_records_duration_and_tokens(self) -> None:
        handler = TelemetryHandler(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )
        # Patch default_timer during start to ensure monotonic_start_s
        with patch("timeit.default_timer", return_value=1000.0):
            invocation = handler.start_inference("prov", request_model="model")
        invocation.input_tokens = 5
        invocation.output_tokens = 7

        # Simulate 2 seconds of elapsed monotonic time (seconds)
        with patch(
            "timeit.default_timer",
            return_value=1002.0,
        ):
            invocation.stop()

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

        invocation = handler.start_inference(
            "prov",
            request_model="model",
            server_address="custom.server.com",
            server_port=42,
        )
        invocation.input_tokens = 5
        invocation.output_tokens = 7
        invocation.metric_attributes = {
            "custom.attribute": "custom_value",
        }
        invocation.attributes = {"should not be on metrics": "value"}
        invocation.stop()

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
        # Patch default_timer during start to ensure monotonic_start_s
        with patch("timeit.default_timer", return_value=2000.0):
            invocation = handler.start_inference("", request_model="err-model")
        invocation.input_tokens = 11

        error = Error(message="boom", type=ValueError)
        with patch(
            "timeit.default_timer",
            return_value=2001.0,
        ):
            invocation.fail(error)

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
        metrics = self.get_sorted_metrics()
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

    def test_stop_embedding_records_duration_and_tokens(self) -> None:
        """Verify embedding invocations record duration and input token metrics."""
        handler = TelemetryHandler(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )
        # Patch default_timer during start to ensure monotonic_start_s
        with patch("timeit.default_timer", return_value=1000.0):
            invocation = handler.start_embedding(
                "embed-prov", request_model="embed-model"
            )
        invocation.input_tokens = 100

        # Simulate 1.5 seconds of elapsed monotonic time
        with patch("timeit.default_timer", return_value=1001.5):
            invocation.stop()

        self._assert_metric_scope_schema_urls(_DEFAULT_SCHEMA_URL)
        metrics = self._harvest_metrics()

        # Duration should be recorded
        self.assertIn("gen_ai.client.operation.duration", metrics)
        duration_points = metrics["gen_ai.client.operation.duration"]
        self.assertEqual(len(duration_points), 1)
        duration_point = duration_points[0]
        self.assertEqual(
            duration_point.attributes[GenAI.GEN_AI_OPERATION_NAME],
            GenAI.GenAiOperationNameValues.EMBEDDINGS.value,
        )
        self.assertEqual(
            duration_point.attributes[GenAI.GEN_AI_REQUEST_MODEL],
            "embed-model",
        )
        self.assertEqual(
            duration_point.attributes[GenAI.GEN_AI_PROVIDER_NAME], "embed-prov"
        )
        self.assertAlmostEqual(duration_point.sum, 1.5, places=3)

        # Token metrics should be recorded for embedding (input only)
        self.assertIn("gen_ai.client.token.usage", metrics)
        token_points = metrics["gen_ai.client.token.usage"]
        self.assertEqual(len(token_points), 1)  # Only input tokens
        token_point = token_points[0]
        self.assertEqual(
            token_point.attributes[GenAI.GEN_AI_TOKEN_TYPE],
            GenAI.GenAiTokenTypeValues.INPUT.value,
        )
        self.assertAlmostEqual(token_point.sum, 100.0, places=3)

    def test_stop_embedding_records_duration_with_additional_attributes(
        self,
    ) -> None:
        """Verify embedding metrics include server and custom attributes."""
        handler = TelemetryHandler(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )
        invocation = handler.start_embedding(
            "embed-prov",
            request_model="embed-model",
            server_address="embed.server.com",
            server_port=8080,
        )
        invocation.metric_attributes = {"custom.embed.attr": "embed_value"}
        invocation.response_model_name = "embed-response-model"
        invocation.stop()

        self._assert_metric_scope_schema_urls(_DEFAULT_SCHEMA_URL)
        metrics = self._harvest_metrics()

        self.assertIn("gen_ai.client.operation.duration", metrics)
        duration_points = metrics["gen_ai.client.operation.duration"]
        self.assertEqual(len(duration_points), 1)
        duration_point = duration_points[0]

        self.assertEqual(
            duration_point.attributes["server.address"], "embed.server.com"
        )
        self.assertEqual(duration_point.attributes["server.port"], 8080)
        self.assertEqual(
            duration_point.attributes["custom.embed.attr"], "embed_value"
        )
        self.assertEqual(
            duration_point.attributes[GenAI.GEN_AI_RESPONSE_MODEL],
            "embed-response-model",
        )

    def test_fail_embedding_records_error_and_duration(self) -> None:
        """Verify embedding failure records error type and duration."""
        handler = TelemetryHandler(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )
        with patch("timeit.default_timer", return_value=3000.0):
            invocation = handler.start_embedding(
                "embed-prov", request_model="embed-err-model"
            )

        error = Error(message="embedding failed", type=RuntimeError)
        with patch("timeit.default_timer", return_value=3002.5):
            invocation.fail(error)

        self._assert_metric_scope_schema_urls(_DEFAULT_SCHEMA_URL)
        metrics = self._harvest_metrics()

        self.assertIn("gen_ai.client.operation.duration", metrics)
        duration_points = metrics["gen_ai.client.operation.duration"]
        self.assertEqual(len(duration_points), 1)
        duration_point = duration_points[0]

        self.assertEqual(
            duration_point.attributes.get("error.type"), "RuntimeError"
        )
        self.assertEqual(
            duration_point.attributes.get(GenAI.GEN_AI_REQUEST_MODEL),
            "embed-err-model",
        )
        self.assertAlmostEqual(duration_point.sum, 2.5, places=3)

        # Token metrics should NOT be recorded when input_tokens is not set
        self.assertNotIn("gen_ai.client.token.usage", metrics)

    def test_stop_embedding_without_tokens(self) -> None:
        """Verify embedding without input_tokens does not record token metrics."""
        handler = TelemetryHandler(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )
        invocation = handler.start_embedding(
            "embed-prov", request_model="embed-model"
        )
        # input_tokens is not set
        invocation.stop()

        metrics = self._harvest_metrics()

        # Duration should be recorded
        self.assertIn("gen_ai.client.operation.duration", metrics)

        # Token metrics should NOT be recorded when input_tokens is not set
        self.assertNotIn("gen_ai.client.token.usage", metrics)


class TelemetryHandlerToolMetricsTest(TestBase):
    def _harvest_metrics(self) -> Dict[str, List[Any]]:
        metrics = self.get_sorted_metrics()
        metrics_by_name: Dict[str, List[Any]] = {}
        for metric in metrics or []:
            points = metric.data.data_points or []
            metrics_by_name.setdefault(metric.name, []).extend(points)
        return metrics_by_name

    def test_stop_tool_records_duration(self) -> None:
        handler = TelemetryHandler(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )
        with patch("timeit.default_timer", return_value=1000.0):
            invocation = handler.start_tool("get_weather")
        invocation.metric_attributes = {"custom.key": "custom_value"}

        with patch("timeit.default_timer", return_value=1002.5):
            invocation.stop()

        metrics = self._harvest_metrics()
        self.assertIn("gen_ai.client.operation.duration", metrics)
        duration_points = metrics["gen_ai.client.operation.duration"]
        self.assertEqual(len(duration_points), 1)
        duration_point = duration_points[0]

        self.assertEqual(
            duration_point.attributes[GenAI.GEN_AI_OPERATION_NAME],
            "execute_tool",
        )
        self.assertEqual(
            duration_point.attributes["custom.key"], "custom_value"
        )
        self.assertAlmostEqual(duration_point.sum, 2.5, places=3)
        self.assertNotIn("gen_ai.client.token.usage", metrics)

    def test_fail_tool_records_duration_with_error(self) -> None:
        handler = TelemetryHandler(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )
        with patch("timeit.default_timer", return_value=500.0):
            invocation = handler.start_tool("failing_tool")

        error = Error(message="Tool execution failed", type=RuntimeError)
        with patch("timeit.default_timer", return_value=501.5):
            invocation.fail(error)

        metrics = self._harvest_metrics()
        self.assertIn("gen_ai.client.operation.duration", metrics)
        duration_points = metrics["gen_ai.client.operation.duration"]
        self.assertEqual(len(duration_points), 1)
        duration_point = duration_points[0]

        self.assertEqual(
            duration_point.attributes["error.type"], "RuntimeError"
        )
        self.assertEqual(
            duration_point.attributes[GenAI.GEN_AI_OPERATION_NAME],
            "execute_tool",
        )
        self.assertAlmostEqual(duration_point.sum, 1.5, places=3)
        self.assertNotIn("gen_ai.client.token.usage", metrics)
