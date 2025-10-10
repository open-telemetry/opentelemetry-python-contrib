import os
import time
import unittest
from typing import Any, List, Optional, cast
from unittest.mock import patch

from opentelemetry import trace
from opentelemetry.instrumentation._semconv import (
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
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGES,
    OTEL_INSTRUMENTATION_GENAI_EMITTERS,
)
from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import (
    AgentInvocation,
    InputMessage,
    LLMInvocation,
    OutputMessage,
    Text,
)

STABILITY_EXPERIMENTAL: dict[str, str] = {}


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
        # Reset handler singleton
        if hasattr(get_telemetry_handler, "_default_handler"):
            delattr(get_telemetry_handler, "_default_handler")
        # Reset handler singleton
        if hasattr(get_telemetry_handler, "_default_handler"):
            delattr(get_telemetry_handler, "_default_handler")

    def _invoke(
        self,
        generator: str,
        capture_mode: str,
        *,
        agent_name: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> LLMInvocation:
        env = {
            **STABILITY_EXPERIMENTAL,
            OTEL_INSTRUMENTATION_GENAI_EMITTERS: generator,
            OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGES: capture_mode.lower(),
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
                input_messages=[
                    InputMessage(role="user", parts=[Text(content="hi")])
                ],
            )
            inv.provider = "prov"
            # set agent identity post construction if provided
            if agent_name is not None:
                inv.agent_name = agent_name
            if agent_id is not None:
                inv.agent_id = agent_id
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
                self.meter_provider.force_flush()
            except Exception:
                pass
            time.sleep(0.005)
            try:
                self.metric_reader.collect()
            except Exception:
                pass
        return inv

    def _collect_metrics(
        self, retries: int = 3, delay: float = 0.01
    ) -> List[Any]:
        for attempt in range(retries):
            try:
                self.metric_reader.collect()
            except Exception:
                pass
            data: Any = None
            try:
                data = self.metric_reader.get_metrics_data()  # type: ignore[assignment]
            except Exception:
                data = None
            points: List[Any] = []
            if data is not None:
                data_any = cast(Any, data)
                for rm in getattr(data_any, "resource_metrics", []) or []:
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
        self._invoke("span", "span")
        metrics_list = self._collect_metrics()
        print(
            "[DEBUG span] collected metrics:", [m.name for m in metrics_list]
        )
        names = {m.name for m in metrics_list}
        self.assertNotIn("gen_ai.client.operation.duration", names)
        self.assertNotIn("gen_ai.client.token.usage", names)

    def test_span_metric_flavor_emits_metrics(self):
        self._invoke("span_metric", "span")
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
        self.assertIn("gen_ai.client.operation.duration", names)
        self.assertIn("gen_ai.client.token.usage", names)

    def test_span_metric_event_flavor_emits_metrics(self):
        self._invoke("span_metric_event", "events")
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
        self.assertIn("gen_ai.client.operation.duration", names)
        self.assertIn("gen_ai.client.token.usage", names)

    def test_llm_metrics_include_agent_identity_when_present(self):
        self._invoke(
            "span_metric",
            "span",
            agent_name="router_agent",
            agent_id="agent-123",
        )
        metrics_list = self._collect_metrics()
        # Collect token usage and duration datapoints and assert agent attrs present
        # We flatten all datapoints for easier searching
        found_token_agent = False
        found_duration_agent = False
        for metric in metrics_list:
            if metric.name not in (
                "gen_ai.client.token.usage",
                "gen_ai.client.operation.duration",
            ):
                continue
            # metric.data.data_points for Histogram-like metrics
            data = getattr(metric, "data", None)
            if not data:
                continue
            data_points = getattr(data, "data_points", []) or []
            for dp in data_points:
                attrs = getattr(dp, "attributes", {}) or {}
                if (
                    attrs.get("gen_ai.agent.name") == "router_agent"
                    and attrs.get("gen_ai.agent.id") == "agent-123"
                ):
                    if metric.name == "gen_ai.client.token.usage":
                        found_token_agent = True
                    if metric.name == "gen_ai.client.operation.duration":
                        found_duration_agent = True
        self.assertTrue(
            found_token_agent,
            "Expected token usage metric datapoint to include agent.name and agent.id",
        )
        self.assertTrue(
            found_duration_agent,
            "Expected operation duration metric datapoint to include agent.name and agent.id",
        )

    def test_llm_metrics_inherit_agent_identity_from_context(self):
        # Prepare environment to emit metrics
        env = {
            **STABILITY_EXPERIMENTAL,
            OTEL_INSTRUMENTATION_GENAI_EMITTERS: "span_metric",
            OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGES: "span",
        }
        with patch.dict(os.environ, env, clear=False):
            if hasattr(get_telemetry_handler, "_default_handler"):
                delattr(get_telemetry_handler, "_default_handler")
            handler = get_telemetry_handler(
                tracer_provider=self.tracer_provider,
                meter_provider=self.meter_provider,
            )
            # Start an agent (push context)
            agent = AgentInvocation(
                name="context_agent",
                operation="invoke_agent",
                model="model-x",
            )
            handler.start_agent(agent)
            # Start LLM WITHOUT agent_name/id explicitly set
            inv = LLMInvocation(
                request_model="m2",
                input_messages=[
                    InputMessage(role="user", parts=[Text(content="hello")])
                ],
            )
            handler.start_llm(inv)
            time.sleep(0.01)
            inv.output_messages = [
                OutputMessage(
                    role="assistant",
                    parts=[Text(content="hi")],
                    finish_reason="stop",
                )
            ]
            inv.input_tokens = 3
            inv.output_tokens = 4
            handler.stop_llm(inv)
            handler.stop_agent(agent)
            try:
                self.meter_provider.force_flush()
            except Exception:
                pass
            self.metric_reader.collect()

        metrics_list = self._collect_metrics()
        inherited = False
        for metric in metrics_list:
            if metric.name not in (
                "gen_ai.client.token.usage",
                "gen_ai.client.operation.duration",
            ):
                continue
            data = getattr(metric, "data", None)
            if not data:
                continue
            for dp in getattr(data, "data_points", []) or []:
                attrs = getattr(dp, "attributes", {}) or {}
                if attrs.get(
                    "gen_ai.agent.name"
                ) == "context_agent" and attrs.get("gen_ai.agent.id") == str(
                    agent.run_id
                ):
                    inherited = True
                    break
        self.assertTrue(
            inherited,
            "Expected metrics to inherit agent identity from active agent context",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
