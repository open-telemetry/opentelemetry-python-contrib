from __future__ import annotations

from typing import Any, Dict, List
from unittest import TestCase
from unittest.mock import patch

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import Error, LLMInvocation


class TelemetryHandlerMetricsTest(TestCase):
    def setUp(self) -> None:
        self.metric_reader = InMemoryMetricReader()
        self.meter_provider = MeterProvider(
            metric_readers=[self.metric_reader]
        )
        self.span_exporter = InMemorySpanExporter()
        self.tracer_provider = TracerProvider()
        self.tracer_provider.add_span_processor(
            SimpleSpanProcessor(self.span_exporter)
        )

    def test_stop_llm_records_duration_and_tokens(self) -> None:
        handler = TelemetryHandler(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )
        invocation = LLMInvocation(request_model="model", provider="prov")
        invocation.input_tokens = 5
        invocation.output_tokens = 7
        handler.start_llm(invocation)
        span = invocation.span
        self.assertIsNotNone(span)
        start_ns = self._get_span_start_time(span)
        self.assertIsNotNone(start_ns)

        with patch(
            "time.time_ns",
            return_value=start_ns + 2_000_000_000,
        ):
            handler.stop_llm(invocation)

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

    def test_fail_llm_records_error_and_available_tokens(self) -> None:
        handler = TelemetryHandler(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )
        invocation = LLMInvocation(request_model="err-model", provider=None)
        invocation.input_tokens = 11
        handler.start_llm(invocation)
        span = invocation.span
        self.assertIsNotNone(span)
        start_ns = self._get_span_start_time(span)
        self.assertIsNotNone(start_ns)

        error = Error(message="boom", type=ValueError)
        with patch(
            "time.time_ns",
            return_value=start_ns + 1_000_000_000,
        ):
            handler.fail_llm(invocation, error)

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

    @staticmethod
    def _get_span_start_time(span) -> int:
        for attr in ("start_time", "_start_time"):
            value = getattr(span, attr, None)
            if isinstance(value, int):
                return value
        raise AssertionError("Span start time not available")

    def _harvest_metrics(self) -> Dict[str, List[Any]]:
        try:
            self.meter_provider.force_flush()
        except Exception:  # pylint: disable=broad-except
            pass
        self.metric_reader.collect()
        metrics_by_name: Dict[str, List[Any]] = {}
        data = self.metric_reader.get_metrics_data()
        for resource_metric in data.resource_metrics or []:
            for scope_metric in resource_metric.scope_metrics or []:
                for metric in getattr(scope_metric, "metrics", []) or []:
                    points = list(
                        getattr(metric.data, "data_points", []) or []
                    )
                    if points:
                        metrics_by_name.setdefault(metric.name, []).extend(
                            points
                        )
        return metrics_by_name
