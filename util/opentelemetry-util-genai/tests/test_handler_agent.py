# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import unittest
from unittest.mock import patch

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import server_attributes
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import INVALID_SPAN, SpanKind
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import (
    ContentCapturingMode,
    Error,
    FunctionToolDefinition,
    InputMessage,
    OutputMessage,
    Text,
)


class TestLocalAgentInvocation(unittest.TestCase):
    def setUp(self):
        self.span_exporter = InMemorySpanExporter()
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(
            SimpleSpanProcessor(self.span_exporter)
        )
        self.handler = TelemetryHandler(tracer_provider=tracer_provider)

    def test_start_stop_creates_span(self):
        invocation = self.handler.start_invoke_local_agent(
            "openai",
            request_model="gpt-4",
        )
        invocation.agent_name = "Math Tutor"
        invocation.stop()

        spans = self.span_exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.name == "invoke_agent Math Tutor"
        assert span.attributes[GenAI.GEN_AI_OPERATION_NAME] == "invoke_agent"
        assert span.attributes[GenAI.GEN_AI_AGENT_NAME] == "Math Tutor"
        assert span.attributes[GenAI.GEN_AI_PROVIDER_NAME] == "openai"
        assert span.attributes[GenAI.GEN_AI_REQUEST_MODEL] == "gpt-4"

    def test_span_kind_internal(self):
        invocation = self.handler.start_invoke_local_agent("openai")
        invocation.stop()
        assert (
            self.span_exporter.get_finished_spans()[0].kind
            == SpanKind.INTERNAL
        )

    def test_no_server_attributes(self):
        invocation = self.handler.start_invoke_local_agent("openai")
        invocation.stop()
        attrs = self.span_exporter.get_finished_spans()[0].attributes
        assert server_attributes.SERVER_ADDRESS not in attrs
        assert server_attributes.SERVER_PORT not in attrs

    def test_all_attributes(self):
        invocation = self.handler.start_invoke_local_agent(
            "openai",
            request_model="gpt-4",
        )
        invocation.agent_name = "Full Agent"
        invocation.agent_id = "agent-123"
        invocation.agent_description = "A test agent"
        invocation.agent_version = "1.0.0"
        invocation.conversation_id = "conv-456"
        invocation.data_source_id = "ds-789"
        invocation.output_type = "text"
        invocation.temperature = 0.7
        invocation.top_p = 0.9
        invocation.frequency_penalty = 0.5
        invocation.presence_penalty = 0.3
        invocation.max_tokens = 1000
        invocation.stop_sequences = ["END", "STOP"]
        invocation.seed = 42
        invocation.choice_count = 3
        invocation.finish_reasons = ["stop"]
        invocation.input_tokens = 100
        invocation.output_tokens = 200
        invocation.stop()

        attrs = self.span_exporter.get_finished_spans()[0].attributes
        assert attrs[GenAI.GEN_AI_AGENT_NAME] == "Full Agent"
        assert attrs[GenAI.GEN_AI_AGENT_ID] == "agent-123"
        assert attrs[GenAI.GEN_AI_AGENT_DESCRIPTION] == "A test agent"
        assert attrs[GenAI.GEN_AI_AGENT_VERSION] == "1.0.0"
        assert attrs[GenAI.GEN_AI_USAGE_INPUT_TOKENS] == 100
        assert attrs[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] == 200
        assert attrs[GenAI.GEN_AI_CONVERSATION_ID] == "conv-456"
        assert attrs[GenAI.GEN_AI_DATA_SOURCE_ID] == "ds-789"
        assert attrs[GenAI.GEN_AI_OUTPUT_TYPE] == "text"
        assert attrs[GenAI.GEN_AI_REQUEST_TEMPERATURE] == 0.7
        assert attrs[GenAI.GEN_AI_REQUEST_TOP_P] == 0.9
        assert attrs[GenAI.GEN_AI_REQUEST_FREQUENCY_PENALTY] == 0.5
        assert attrs[GenAI.GEN_AI_REQUEST_PRESENCE_PENALTY] == 0.3
        assert attrs[GenAI.GEN_AI_REQUEST_MAX_TOKENS] == 1000
        assert attrs[GenAI.GEN_AI_REQUEST_STOP_SEQUENCES] == ("END", "STOP")
        assert attrs[GenAI.GEN_AI_REQUEST_SEED] == 42
        assert attrs[GenAI.GEN_AI_REQUEST_CHOICE_COUNT] == 3
        assert attrs[GenAI.GEN_AI_RESPONSE_FINISH_REASONS] == ("stop",)

    def test_finish_reasons_multiple(self):
        invocation = self.handler.start_invoke_local_agent("openai")
        invocation.finish_reasons = ["stop", "length"]
        invocation.stop()
        attrs = self.span_exporter.get_finished_spans()[0].attributes
        assert attrs[GenAI.GEN_AI_RESPONSE_FINISH_REASONS] == (
            "stop",
            "length",
        )

    def test_finish_reasons_empty_list_omitted(self):
        invocation = self.handler.start_invoke_local_agent("openai")
        invocation.finish_reasons = []
        invocation.stop()
        attrs = self.span_exporter.get_finished_spans()[0].attributes
        assert GenAI.GEN_AI_RESPONSE_MODEL not in attrs
        assert GenAI.GEN_AI_RESPONSE_FINISH_REASONS not in attrs

    def test_cache_token_attributes(self):
        invocation = self.handler.start_invoke_local_agent("openai")
        invocation.input_tokens = 100
        invocation.cache_creation_input_tokens = 25
        invocation.cache_read_input_tokens = 50
        invocation.stop()

        attrs = self.span_exporter.get_finished_spans()[0].attributes
        assert attrs[GenAI.GEN_AI_USAGE_INPUT_TOKENS] == 100
        assert attrs[GenAI.GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS] == 25
        assert attrs[GenAI.GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS] == 50

    def test_fail_sets_error_status(self):
        invocation = self.handler.start_invoke_local_agent("openai")
        invocation.fail(RuntimeError("agent crashed"))

        span = self.span_exporter.get_finished_spans()[0]
        assert span.status.description == "agent crashed"
        assert span.attributes.get("error.type") == "RuntimeError"

    def test_context_manager_success(self):
        with self.handler.invoke_local_agent(
            "openai", request_model="gpt-4"
        ) as inv:
            inv.agent_name = "CM Agent"
            inv.input_tokens = 10
            inv.output_tokens = 20

        assert (
            self.span_exporter.get_finished_spans()[0].name
            == "invoke_agent CM Agent"
        )

    def test_context_manager_error(self):
        with self.assertRaises(ValueError):
            with self.handler.invoke_local_agent("openai"):
                raise ValueError("test error")

        assert (
            self.span_exporter.get_finished_spans()[0].attributes.get(
                "error.type"
            )
            == "ValueError"
        )

    def test_context_manager_default_invocation(self):
        with self.handler.invoke_local_agent("openai") as inv:
            inv.agent_name = "Dynamic Agent"
        assert len(self.span_exporter.get_finished_spans()) == 1

    def test_default_values(self):
        invocation = self.handler.start_invoke_local_agent("openai")
        invocation.stop()
        assert invocation._operation_name == "invoke_agent"
        assert invocation.agent_name is None
        assert invocation.provider == "openai"
        assert invocation.request_model is None
        assert not invocation.input_messages
        assert not invocation.output_messages
        assert invocation.tool_definitions is None
        assert invocation.cache_creation_input_tokens is None
        assert invocation.cache_read_input_tokens is None
        assert invocation.span is not INVALID_SPAN
        assert not invocation.attributes

    def test_with_messages(self):
        invocation = self.handler.start_invoke_local_agent("openai")
        invocation.input_messages = [
            InputMessage(role="user", parts=[Text(content="Hello")])
        ]
        invocation.output_messages = [
            OutputMessage(
                role="assistant",
                parts=[Text(content="Hi there!")],
                finish_reason="stop",
            )
        ]
        invocation.stop()
        assert len(invocation.input_messages) == 1
        assert invocation.input_messages[0].role == "user"

    def test_custom_attributes(self):
        invocation = self.handler.start_invoke_local_agent("openai")
        invocation.attributes["custom.key"] = "custom_value"
        invocation.stop()
        spans = self.span_exporter.get_finished_spans()
        assert spans[0].attributes["custom.key"] == "custom_value"

    def test_tool_definitions_type(self):
        tool = FunctionToolDefinition(
            name="get_weather",
            description="Get the weather",
            parameters={"type": "object", "properties": {}},
        )
        invocation = self.handler.start_invoke_local_agent("openai")
        invocation.tool_definitions = [tool]
        invocation.stop()
        assert len(invocation.tool_definitions) == 1
        assert invocation.tool_definitions[0].name == "get_weather"
        assert invocation.tool_definitions[0].type == "function"

    def test_default_lists_are_independent(self):
        inv1 = self.handler.start_invoke_local_agent("openai")
        inv2 = self.handler.start_invoke_local_agent("openai")
        inv1.input_messages.append(InputMessage(role="user", parts=[]))
        assert len(inv2.input_messages) == 0
        inv2.stop()
        inv1.stop()

    def test_default_attributes_are_independent(self):
        inv1 = self.handler.start_invoke_local_agent("openai")
        inv2 = self.handler.start_invoke_local_agent("openai")
        inv1.attributes["foo"] = "bar"
        assert "foo" not in inv2.attributes
        inv2.stop()
        inv1.stop()

    def test_agent_name_set_after_construction(self):
        invocation = self.handler.start_invoke_local_agent("openai")
        invocation.agent_name = "Named Agent"
        invocation.stop()
        span = self.span_exporter.get_finished_spans()[0]
        assert span.name == "invoke_agent Named Agent"
        assert span.attributes[GenAI.GEN_AI_AGENT_NAME] == "Named Agent"


class TestAgentInvocationContent(unittest.TestCase):
    def setUp(self):
        self.span_exporter = InMemorySpanExporter()
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(
            SimpleSpanProcessor(self.span_exporter)
        )
        self.handler = TelemetryHandler(tracer_provider=tracer_provider)

    @patch(
        "opentelemetry.util.genai._invocation.get_content_capturing_mode",
        return_value=ContentCapturingMode.SPAN_AND_EVENT,
    )
    @patch(
        "opentelemetry.util.genai._invocation.is_experimental_mode",
        return_value=True,
    )
    def test_system_instruction_on_span(self, _mock_exp, _mock_cap):
        invocation = self.handler.start_invoke_local_agent("openai")
        invocation.system_instruction = [
            Text(content="You are a helpful assistant."),
        ]
        invocation.stop()

        attrs = self.span_exporter.get_finished_spans()[0].attributes
        assert GenAI.GEN_AI_SYSTEM_INSTRUCTIONS in attrs

    @patch(
        "opentelemetry.util.genai._invocation.get_content_capturing_mode",
        return_value=ContentCapturingMode.SPAN_AND_EVENT,
    )
    @patch(
        "opentelemetry.util.genai._invocation.is_experimental_mode",
        return_value=True,
    )
    def test_tool_definitions_on_span(self, _mock_exp, _mock_cap):
        tool = FunctionToolDefinition(
            name="get_weather",
            description="Get the weather",
            parameters={"type": "object", "properties": {}},
        )
        invocation = self.handler.start_invoke_local_agent("openai")
        invocation.tool_definitions = [tool]
        invocation.stop()

        attrs = self.span_exporter.get_finished_spans()[0].attributes
        assert GenAI.GEN_AI_TOOL_DEFINITIONS in attrs

    @patch(
        "opentelemetry.util.genai._invocation.get_content_capturing_mode",
        return_value=ContentCapturingMode.SPAN_AND_EVENT,
    )
    @patch(
        "opentelemetry.util.genai._invocation.is_experimental_mode",
        return_value=True,
    )
    def test_messages_on_span(self, _mock_exp, _mock_cap):
        invocation = self.handler.start_invoke_local_agent("openai")
        invocation.input_messages = [
            InputMessage(role="user", parts=[Text(content="Hello")])
        ]
        invocation.output_messages = [
            OutputMessage(
                role="assistant",
                parts=[Text(content="Hi!")],
                finish_reason="stop",
            )
        ]
        invocation.stop()

        attrs = self.span_exporter.get_finished_spans()[0].attributes
        assert GenAI.GEN_AI_INPUT_MESSAGES in attrs
        assert GenAI.GEN_AI_OUTPUT_MESSAGES in attrs

    def test_content_not_on_span_by_default(self):
        invocation = self.handler.start_invoke_local_agent("openai")
        invocation.system_instruction = [
            Text(content="You are a helpful assistant."),
        ]
        invocation.input_messages = [
            InputMessage(role="user", parts=[Text(content="Hello")])
        ]
        invocation.stop()

        attrs = self.span_exporter.get_finished_spans()[0].attributes
        assert GenAI.GEN_AI_SYSTEM_INSTRUCTIONS not in attrs
        assert GenAI.GEN_AI_INPUT_MESSAGES not in attrs


class TestRemoteAgentInvocation(unittest.TestCase):
    def setUp(self):
        self.span_exporter = InMemorySpanExporter()
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(
            SimpleSpanProcessor(self.span_exporter)
        )
        self.handler = TelemetryHandler(tracer_provider=tracer_provider)

    def test_span_kind_client(self):
        invocation = self.handler.start_invoke_remote_agent("openai")
        invocation.stop()
        assert (
            self.span_exporter.get_finished_spans()[0].kind == SpanKind.CLIENT
        )

    def test_server_attributes(self):
        invocation = self.handler.start_invoke_remote_agent(
            "openai",
            server_address="api.openai.com",
            server_port=443,
        )
        invocation.stop()
        attrs = self.span_exporter.get_finished_spans()[0].attributes
        assert attrs[server_attributes.SERVER_ADDRESS] == "api.openai.com"
        assert attrs[server_attributes.SERVER_PORT] == 443

    def test_all_attributes(self):
        invocation = self.handler.start_invoke_remote_agent(
            "openai",
            request_model="gpt-4",
            server_address="api.openai.com",
            server_port=443,
        )
        invocation.agent_name = "Remote Agent"
        invocation.agent_id = "agent-123"
        invocation.agent_description = "A remote test agent"
        invocation.agent_version = "1.0.0"
        invocation.input_tokens = 100
        invocation.output_tokens = 200
        invocation.stop()

        attrs = self.span_exporter.get_finished_spans()[0].attributes
        assert attrs[GenAI.GEN_AI_AGENT_NAME] == "Remote Agent"
        assert attrs[GenAI.GEN_AI_AGENT_ID] == "agent-123"
        assert attrs[GenAI.GEN_AI_AGENT_DESCRIPTION] == "A remote test agent"
        assert attrs[GenAI.GEN_AI_AGENT_VERSION] == "1.0.0"
        assert attrs[GenAI.GEN_AI_USAGE_INPUT_TOKENS] == 100
        assert attrs[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] == 200
        assert attrs[GenAI.GEN_AI_REQUEST_MODEL] == "gpt-4"

    def test_fail_sets_error_status(self):
        invocation = self.handler.start_invoke_remote_agent("openai")
        invocation.fail(RuntimeError("remote agent crashed"))

        span = self.span_exporter.get_finished_spans()[0]
        assert span.status.description == "remote agent crashed"
        assert span.attributes.get("error.type") == "RuntimeError"

    def test_context_manager_success(self):
        with self.handler.invoke_remote_agent(
            "openai",
            request_model="gpt-4",
            server_address="api.openai.com",
        ) as inv:
            inv.agent_name = "CM Remote Agent"

        span = self.span_exporter.get_finished_spans()[0]
        assert span.name == "invoke_agent CM Remote Agent"
        assert span.kind == SpanKind.CLIENT

    def test_context_manager_error(self):
        with self.assertRaises(ValueError):
            with self.handler.invoke_remote_agent("openai"):
                raise ValueError("remote error")

        assert (
            self.span_exporter.get_finished_spans()[0].attributes.get(
                "error.type"
            )
            == "ValueError"
        )


class TestAgentInvocationMetrics(TestBase):
    def test_local_agent_records_duration_and_tokens(self) -> None:
        handler = TelemetryHandler(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )
        with patch("timeit.default_timer", return_value=1000.0):
            invocation = handler.start_invoke_local_agent(
                "prov", request_model="model"
            )
        invocation.input_tokens = 5
        invocation.output_tokens = 7

        with patch("timeit.default_timer", return_value=1002.0):
            invocation.stop()

        metrics = self._harvest_metrics()
        self.assertIn("gen_ai.client.operation.duration", metrics)
        duration_points = metrics["gen_ai.client.operation.duration"]
        self.assertEqual(len(duration_points), 1)
        duration_point = duration_points[0]
        self.assertEqual(
            duration_point.attributes[GenAI.GEN_AI_OPERATION_NAME],
            GenAI.GenAiOperationNameValues.INVOKE_AGENT.value,
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
            token_by_type[GenAI.GenAiTokenTypeValues.OUTPUT.value].sum,
            7.0,
            places=3,
        )

    def test_remote_agent_records_duration_with_server_attrs(self) -> None:
        handler = TelemetryHandler(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )
        invocation = handler.start_invoke_remote_agent(
            "prov",
            request_model="model",
            server_address="agent.example.com",
            server_port=443,
        )
        invocation.input_tokens = 10
        invocation.stop()

        metrics = self._harvest_metrics()
        self.assertIn("gen_ai.client.operation.duration", metrics)
        duration_point = metrics["gen_ai.client.operation.duration"][0]
        self.assertEqual(
            duration_point.attributes["server.address"], "agent.example.com"
        )
        self.assertEqual(duration_point.attributes["server.port"], 443)

    def test_fail_agent_records_error_metric(self) -> None:
        handler = TelemetryHandler(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
        )
        with patch("timeit.default_timer", return_value=2000.0):
            invocation = handler.start_invoke_local_agent(
                "", request_model="err-model"
            )
        invocation.input_tokens = 11

        error = Error(message="boom", type=ValueError)
        with patch("timeit.default_timer", return_value=2001.0):
            invocation.fail(error)

        metrics = self._harvest_metrics()
        self.assertIn("gen_ai.client.operation.duration", metrics)
        duration_point = metrics["gen_ai.client.operation.duration"][0]
        self.assertEqual(
            duration_point.attributes.get("error.type"), "ValueError"
        )
        self.assertAlmostEqual(duration_point.sum, 1.0, places=3)

    def _harvest_metrics(self):
        metrics = self.get_sorted_metrics()
        metrics_by_name = {}
        for metric in metrics or []:
            points = metric.data.data_points or []
            metrics_by_name.setdefault(metric.name, []).extend(points)
        return metrics_by_name
