import os
import time
import unittest
from unittest.mock import patch

from opentelemetry import trace
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
    OTEL_INSTRUMENTATION_GENAI_GENERATOR,
)
from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import (
    InputMessage,
    LLMInvocation,
    OutputMessage,
    Text,
)

STABILITY_EXPERIMENTAL = {
    OTEL_SEMCONV_STABILITY_OPT_IN: "gen_ai_latest_experimental"
}


class TestMetricsEmission(unittest.TestCase):
    def setUp(self):
        # Fresh tracer provider & exporter (do not rely on global replacement each time)
        self.span_exporter = InMemorySpanExporter()
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(
            SimpleSpanProcessor(self.span_exporter)
        )
        # Only set the global tracer provider once (subsequent overrides ignored but harmless)
        trace.set_tracer_provider(tracer_provider)
        self.tracer_provider = tracer_provider
        # Isolated meter provider with in-memory reader (do NOT set global to avoid override warnings)
        self.metric_reader = InMemoryMetricReader()
        self.meter_provider = MeterProvider(
            metric_readers=[self.metric_reader]
        )
        # Reset semconv stability for each test after environment patching
        _OpenTelemetrySemanticConventionStability._initialized = False
        _OpenTelemetrySemanticConventionStability._initialize()
        # Reset handler singleton
        if hasattr(get_telemetry_handler, "_default_handler"):
            delattr(get_telemetry_handler, "_default_handler")

    def _invoke(self, generator: str, capture_mode: str):
        env = {
            **STABILITY_EXPERIMENTAL,
            OTEL_INSTRUMENTATION_GENAI_GENERATOR: generator,
            OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: capture_mode,
        }
        with patch.dict(os.environ, env, clear=False):
            _OpenTelemetrySemanticConventionStability._initialized = False
            _OpenTelemetrySemanticConventionStability._initialize()
            if hasattr(get_telemetry_handler, "_default_handler"):
                delattr(get_telemetry_handler, "_default_handler")
            handler = get_telemetry_handler(
                tracer_provider=self.tracer_provider,
                meter_provider=self.meter_provider,
            )
            inv = LLMInvocation(
                request_model="m",
                provider="prov",
                input_messages=[
                    InputMessage(role="user", parts=[Text(content="hi")])
                ],
            )
            handler.start_llm(inv)
            time.sleep(0.01)  # ensure measurable duration
            inv.output_messages = [
                OutputMessage(
                    role="assistant",
                    parts=[Text(content="ok")],
                    finish_reason="stop",
                )
            ]
            inv.input_tokens = 5
            inv.output_tokens = 7
            handler.stop_llm(inv)
            # Force flush isolated meter provider
            try:
                self.meter_provider.force_flush()  # type: ignore[attr-defined]
            except Exception:
                pass
            time.sleep(0.005)
            try:
                self.metric_reader.collect()
            except Exception:
                pass
        return inv

    def _collect_metrics(self, retries: int = 3, delay: float = 0.01):
        for attempt in range(retries):
            try:
                self.metric_reader.collect()
            except Exception:
                pass
            data = None
            try:
                data = self.metric_reader.get_metrics_data()
            except Exception:
                data = None
            points = []
            if data is not None:
                for rm in getattr(data, "resource_metrics", []) or []:
                    for scope_metrics in (
                        getattr(rm, "scope_metrics", []) or []
                    ):
                        for metric in (
                            getattr(scope_metrics, "metrics", []) or []
                        ):
                            points.append(metric)
            if points or attempt == retries - 1:
                return points
            time.sleep(delay)
        return []

    def test_span_flavor_has_no_metrics(self):
        self._invoke("span", "SPAN_ONLY")
        metrics_list = self._collect_metrics()
        print(
            "[DEBUG span] collected metrics:", [m.name for m in metrics_list]
        )
        names = {m.name for m in metrics_list}
        self.assertNotIn("gen_ai.operation.duration", names)
        self.assertNotIn("gen_ai.token.usage", names)

    def test_span_metric_flavor_emits_metrics(self):
        self._invoke("span_metric", "SPAN_ONLY")
        # Probe metric to validate pipeline
        probe_hist = self.meter_provider.get_meter("probe").create_histogram(
            "probe.metric"
        )
        probe_hist.record(1)
        metrics_list = self._collect_metrics()
        print(
            "[DEBUG span_metric] collected metrics:",
            [m.name for m in metrics_list],
        )
        names = {m.name for m in metrics_list}
        self.assertIn(
            "probe.metric", names, "probe metric missing - pipeline inactive"
        )
        self.assertIn("gen_ai.operation.duration", names)
        self.assertIn("gen_ai.token.usage", names)

    def test_span_metric_event_flavor_emits_metrics(self):
        self._invoke("span_metric_event", "EVENT_ONLY")
        probe_hist = self.meter_provider.get_meter("probe2").create_histogram(
            "probe2.metric"
        )
        probe_hist.record(1)
        metrics_list = self._collect_metrics()
        print(
            "[DEBUG span_metric_event] collected metrics:",
            [m.name for m in metrics_list],
        )
        names = {m.name for m in metrics_list}
        self.assertIn(
            "probe2.metric", names, "probe2 metric missing - pipeline inactive"
        )
        self.assertIn("gen_ai.operation.duration", names)
        self.assertIn("gen_ai.token.usage", names)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
