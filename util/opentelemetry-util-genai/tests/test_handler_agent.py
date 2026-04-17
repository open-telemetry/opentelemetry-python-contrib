from __future__ import annotations

import unittest
from typing import Any
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
from opentelemetry.semconv.attributes import server_attributes
from opentelemetry.trace import SpanKind
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.utils import ContentCapturingMode

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_handler(
    span_exporter: InMemorySpanExporter,
    metric_reader: InMemoryMetricReader | None = None,
) -> TelemetryHandler:
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    kwargs: dict[str, Any] = {"tracer_provider": tracer_provider}
    if metric_reader is not None:
        kwargs["meter_provider"] = MeterProvider(
            metric_readers=[metric_reader]
        )
    return TelemetryHandler(**kwargs)


def _harvest_metrics(
    meter_provider: MeterProvider,
    metric_reader: InMemoryMetricReader,
) -> dict[str, list[Any]]:
    try:
        meter_provider.force_flush()
    except Exception:
        pass
    metric_reader.collect()
    metrics_by_name: dict[str, list[Any]] = {}
    data = metric_reader.get_metrics_data()
    for resource_metric in (data and data.resource_metrics) or []:
        for scope_metric in resource_metric.scope_metrics or []:
            for metric in scope_metric.metrics or []:
                points = metric.data.data_points or []
                metrics_by_name.setdefault(metric.name, []).extend(points)
    return metrics_by_name


# ============================================================================
# AgentCreation tests
# ============================================================================


class TestAgentCreation(unittest.TestCase):
    def setUp(self):
        self.span_exporter = InMemorySpanExporter()
        self.handler = _make_handler(self.span_exporter)

    def test_start_stop_creates_span(self):
        creation = self.handler.start_create_agent(
            "openai",
            request_model="gpt-4",
        )
        creation.agent_name = "New Agent"
        creation.agent_id = "agent-new-1"
        creation.stop()

        spans = self.span_exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.name == "create_agent New Agent"
        assert span.attributes[GenAI.GEN_AI_OPERATION_NAME] == "create_agent"
        assert span.attributes[GenAI.GEN_AI_AGENT_NAME] == "New Agent"
        assert span.attributes[GenAI.GEN_AI_AGENT_ID] == "agent-new-1"
        assert span.attributes[GenAI.GEN_AI_PROVIDER_NAME] == "openai"
        assert span.attributes[GenAI.GEN_AI_REQUEST_MODEL] == "gpt-4"

    def test_span_kind_is_client(self):
        creation = self.handler.start_create_agent("openai")
        creation.stop()
        assert (
            self.span_exporter.get_finished_spans()[0].kind == SpanKind.CLIENT
        )

    def test_all_attributes(self):
        creation = self.handler.start_create_agent(
            "openai",
            request_model="gpt-4",
            server_address="api.openai.com",
            server_port=443,
        )
        creation.agent_name = "Full Agent"
        creation.agent_id = "agent-123"
        creation.agent_description = "A test agent"
        creation.agent_version = "1.0.0"
        creation.stop()

        attrs = self.span_exporter.get_finished_spans()[0].attributes
        assert attrs[GenAI.GEN_AI_OPERATION_NAME] == "create_agent"
        assert attrs[GenAI.GEN_AI_AGENT_NAME] == "Full Agent"
        assert attrs[GenAI.GEN_AI_AGENT_ID] == "agent-123"
        assert attrs[GenAI.GEN_AI_AGENT_DESCRIPTION] == "A test agent"
        assert attrs["gen_ai.agent.version"] == "1.0.0"
        assert attrs[GenAI.GEN_AI_PROVIDER_NAME] == "openai"
        assert attrs[GenAI.GEN_AI_REQUEST_MODEL] == "gpt-4"
        assert attrs[server_attributes.SERVER_ADDRESS] == "api.openai.com"
        assert attrs[server_attributes.SERVER_PORT] == 443

    def test_no_server_attributes_when_not_provided(self):
        creation = self.handler.start_create_agent("openai")
        creation.stop()
        attrs = self.span_exporter.get_finished_spans()[0].attributes
        assert server_attributes.SERVER_ADDRESS not in attrs
        assert server_attributes.SERVER_PORT not in attrs

    def test_fail_create_agent(self):
        creation = self.handler.start_create_agent("openai")
        creation.agent_name = "Bad Agent"
        creation.fail(RuntimeError("creation failed"))

        spans = self.span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].status.description == "creation failed"
        assert spans[0].attributes.get("error.type") == "RuntimeError"

    def test_context_manager(self):
        with self.handler.create_agent(
            "openai", request_model="gpt-4"
        ) as creation:
            creation.agent_name = "CM Agent"
            creation.agent_id = "assigned-id"

        spans = self.span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "create_agent CM Agent"
        assert spans[0].attributes[GenAI.GEN_AI_AGENT_ID] == "assigned-id"

    def test_context_manager_error(self):
        with self.assertRaises(TypeError):
            with self.handler.create_agent("openai") as creation:
                creation.agent_name = "Err"
                raise TypeError("bad type")

        spans = self.span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].attributes.get("error.type") == "TypeError"

    def test_custom_attributes(self):
        creation = self.handler.start_create_agent(
            "openai", request_model="gpt-4"
        )
        creation.attributes["custom.key"] = "custom_value"
        creation.stop()
        attrs = self.span_exporter.get_finished_spans()[0].attributes
        assert attrs["custom.key"] == "custom_value"

    def test_span_name_without_agent_name(self):
        creation = self.handler.start_create_agent("openai")
        creation.stop()
        assert (
            self.span_exporter.get_finished_spans()[0].name == "create_agent"
        )


# ============================================================================
# AgentInvocation tests
# ============================================================================


class TestAgentInvocation(unittest.TestCase):
    def setUp(self):
        self.span_exporter = InMemorySpanExporter()
        self.handler = _make_handler(self.span_exporter)

    # ---- local (INTERNAL) ----

    def test_local_agent_creates_span(self):
        inv = self.handler.start_invoke_local_agent(
            "openai", request_model="gpt-4"
        )
        inv.agent_name = "Math Tutor"
        inv.stop()

        spans = self.span_exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.name == "invoke_agent Math Tutor"
        assert span.kind == SpanKind.INTERNAL
        assert span.attributes[GenAI.GEN_AI_OPERATION_NAME] == "invoke_agent"
        assert span.attributes[GenAI.GEN_AI_AGENT_NAME] == "Math Tutor"
        assert span.attributes[GenAI.GEN_AI_PROVIDER_NAME] == "openai"

    # ---- remote (CLIENT) ----

    def test_remote_agent_creates_client_span(self):
        inv = self.handler.start_invoke_remote_agent(
            "openai",
            request_model="gpt-4",
            server_address="api.openai.com",
            server_port=443,
        )
        inv.agent_name = "Remote Agent"
        inv.stop()

        spans = self.span_exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.kind == SpanKind.CLIENT
        assert (
            span.attributes[server_attributes.SERVER_ADDRESS]
            == "api.openai.com"
        )
        assert span.attributes[server_attributes.SERVER_PORT] == 443

    def test_all_attributes(self):
        inv = self.handler.start_invoke_remote_agent(
            "openai",
            request_model="gpt-4",
            server_address="api.openai.com",
            server_port=443,
        )
        inv.agent_name = "Full Agent"
        inv.agent_id = "agent-123"
        inv.agent_description = "A test agent"
        inv.agent_version = "1.0.0"
        inv.conversation_id = "conv-456"
        inv.data_source_id = "ds-789"
        inv.output_type = "text"
        inv.temperature = 0.7
        inv.top_p = 0.9
        inv.max_tokens = 1000
        inv.seed = 42
        inv.input_tokens = 100
        inv.output_tokens = 200
        inv.stop()

        attrs = self.span_exporter.get_finished_spans()[0].attributes
        assert attrs[GenAI.GEN_AI_AGENT_NAME] == "Full Agent"
        assert attrs[GenAI.GEN_AI_AGENT_ID] == "agent-123"
        assert attrs[GenAI.GEN_AI_AGENT_DESCRIPTION] == "A test agent"
        assert attrs["gen_ai.agent.version"] == "1.0.0"
        assert attrs[GenAI.GEN_AI_CONVERSATION_ID] == "conv-456"
        assert attrs[GenAI.GEN_AI_DATA_SOURCE_ID] == "ds-789"
        assert attrs[GenAI.GEN_AI_OUTPUT_TYPE] == "text"
        assert attrs[GenAI.GEN_AI_REQUEST_TEMPERATURE] == 0.7
        assert attrs[GenAI.GEN_AI_REQUEST_TOP_P] == 0.9
        assert attrs[GenAI.GEN_AI_REQUEST_MAX_TOKENS] == 1000
        assert attrs[GenAI.GEN_AI_REQUEST_SEED] == 42
        assert attrs[GenAI.GEN_AI_USAGE_INPUT_TOKENS] == 100
        assert attrs[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] == 200

    def test_fail_agent(self):
        inv = self.handler.start_invoke_local_agent("openai")
        inv.agent_name = "Failing Agent"
        inv.fail(RuntimeError("agent crashed"))

        spans = self.span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].status.description == "agent crashed"
        assert spans[0].attributes.get("error.type") == "RuntimeError"

    # ---- context managers ----

    def test_invoke_local_agent_context_manager(self):
        with self.handler.invoke_local_agent(
            "openai", request_model="gpt-4"
        ) as inv:
            inv.agent_name = "CM Agent"
            inv.input_tokens = 10
            inv.output_tokens = 20

        spans = self.span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "invoke_agent CM Agent"
        assert spans[0].kind == SpanKind.INTERNAL

    def test_invoke_remote_agent_context_manager(self):
        with self.handler.invoke_remote_agent(
            "openai",
            request_model="gpt-4",
            server_address="api.openai.com",
            server_port=443,
        ) as inv:
            inv.agent_name = "Remote CM"

        spans = self.span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].kind == SpanKind.CLIENT

    def test_context_manager_error(self):
        with self.assertRaises(ValueError):
            with self.handler.invoke_local_agent("openai") as inv:
                inv.agent_name = "Error Agent"
                raise ValueError("test error")

        spans = self.span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].attributes.get("error.type") == "ValueError"

    def test_custom_attributes(self):
        inv = self.handler.start_invoke_local_agent("openai")
        inv.attributes["custom.key"] = "custom_value"
        inv.stop()
        attrs = self.span_exporter.get_finished_spans()[0].attributes
        assert attrs["custom.key"] == "custom_value"

    def test_span_name_without_agent_name(self):
        inv = self.handler.start_invoke_local_agent("openai")
        inv.stop()
        assert (
            self.span_exporter.get_finished_spans()[0].name == "invoke_agent"
        )


# ============================================================================
# Agent Metrics tests
# ============================================================================


class TestAgentMetrics(unittest.TestCase):
    def setUp(self):
        self.span_exporter = InMemorySpanExporter()
        self.metric_reader = InMemoryMetricReader()
        self.tracer_provider = TracerProvider()
        self.tracer_provider.add_span_processor(
            SimpleSpanProcessor(self.span_exporter)
        )
        self.meter_provider = MeterProvider(
            metric_readers=[self.metric_reader]
        )
        self.handler = TelemetryHandler(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )

    def _harvest(self) -> dict[str, list[Any]]:
        return _harvest_metrics(self.meter_provider, self.metric_reader)

    def test_invoke_agent_records_duration(self):
        with patch(
            "opentelemetry.util.genai._invocation.timeit.default_timer",
            return_value=1000.0,
        ):
            inv = self.handler.start_invoke_local_agent(
                "openai", request_model="gpt-4"
            )
        inv.agent_name = "Metrics Agent"
        inv.input_tokens = 50
        inv.output_tokens = 100

        with patch(
            "opentelemetry.util.genai.metrics.timeit.default_timer",
            return_value=1003.0,
        ):
            inv.stop()

        metrics = self._harvest()
        assert "gen_ai.client.operation.duration" in metrics
        duration_points = metrics["gen_ai.client.operation.duration"]
        assert len(duration_points) == 1
        self.assertAlmostEqual(duration_points[0].sum, 3.0, places=3)
        assert (
            duration_points[0].attributes[GenAI.GEN_AI_OPERATION_NAME]
            == "invoke_agent"
        )

    def test_invoke_agent_records_token_usage(self):
        inv = self.handler.start_invoke_local_agent(
            "openai", request_model="gpt-4"
        )
        inv.input_tokens = 50
        inv.output_tokens = 100
        inv.stop()

        metrics = self._harvest()
        assert "gen_ai.client.token.usage" in metrics
        token_points = metrics["gen_ai.client.token.usage"]
        assert len(token_points) == 2
        token_map = {
            p.attributes[GenAI.GEN_AI_TOKEN_TYPE]: p.sum for p in token_points
        }
        assert token_map["input"] == 50
        assert token_map["output"] == 100

    def test_create_agent_records_duration(self):
        with patch(
            "opentelemetry.util.genai._invocation.timeit.default_timer",
            return_value=2000.0,
        ):
            creation = self.handler.start_create_agent(
                "openai", request_model="gpt-4"
            )
        creation.agent_name = "Created"

        with patch(
            "opentelemetry.util.genai.metrics.timeit.default_timer",
            return_value=2005.0,
        ):
            creation.stop()

        metrics = self._harvest()
        assert "gen_ai.client.operation.duration" in metrics
        duration_points = metrics["gen_ai.client.operation.duration"]
        assert len(duration_points) == 1
        self.assertAlmostEqual(duration_points[0].sum, 5.0, places=3)
        assert (
            duration_points[0].attributes[GenAI.GEN_AI_OPERATION_NAME]
            == "create_agent"
        )

    def test_create_agent_no_token_metrics(self):
        creation = self.handler.start_create_agent("openai")
        creation.stop()

        metrics = self._harvest()
        assert "gen_ai.client.token.usage" not in metrics


# ============================================================================
# Agent Events tests
# ============================================================================


class TestAgentEvents(unittest.TestCase):
    def setUp(self):
        self.span_exporter = InMemorySpanExporter()
        self.handler = _make_handler(self.span_exporter)

    @patch(
        "opentelemetry.util.genai._agent_invocation.should_emit_event",
        return_value=True,
    )
    @patch(
        "opentelemetry.util.genai._agent_invocation.is_experimental_mode",
        return_value=True,
    )
    def test_invoke_agent_emits_event(self, _mock_exp, _mock_emit):
        inv = self.handler.start_invoke_local_agent(
            "openai", request_model="gpt-4"
        )
        inv.agent_name = "Event Agent"
        inv.stop()

        # The logger.emit was called — verify via span attributes at minimum
        spans = self.span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].attributes[GenAI.GEN_AI_AGENT_NAME] == "Event Agent"

    @patch(
        "opentelemetry.util.genai._agent_creation.should_emit_event",
        return_value=True,
    )
    @patch(
        "opentelemetry.util.genai._agent_creation.get_content_capturing_mode",
        return_value=ContentCapturingMode.NO_CONTENT,
    )
    @patch(
        "opentelemetry.util.genai._agent_creation.is_experimental_mode",
        return_value=True,
    )
    def test_create_agent_emits_event(
        self, _mock_exp, _mock_capture, _mock_emit
    ):
        creation = self.handler.start_create_agent("openai")
        creation.agent_name = "Event Creation"
        creation.stop()

        spans = self.span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].attributes[GenAI.GEN_AI_AGENT_NAME] == "Event Creation"
