from __future__ import annotations

import unittest

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import server_attributes
from opentelemetry.trace import INVALID_SPAN, SpanKind
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import (
    FunctionToolDefinition,
    InputMessage,
    OutputMessage,
    Text,
)


class TestAgentInvocation(unittest.TestCase):
    def setUp(self):
        self.span_exporter = InMemorySpanExporter()
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(
            SimpleSpanProcessor(self.span_exporter)
        )
        self.handler = TelemetryHandler(tracer_provider=tracer_provider)

    def test_start_stop_creates_span(self):
        invocation = self.handler.start_agent(
            provider="openai",
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

    def test_span_kind_client(self):
        invocation = self.handler.start_agent(provider="openai")
        invocation.stop()
        assert (
            self.span_exporter.get_finished_spans()[0].kind == SpanKind.CLIENT
        )

    def test_all_attributes(self):
        invocation = self.handler.start_agent(
            provider="openai",
            request_model="gpt-4",
            server_address="api.openai.com",
            server_port=443,
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
        invocation.max_tokens = 1000
        invocation.seed = 42
        invocation.input_tokens = 100
        invocation.output_tokens = 200
        invocation.finish_reasons = ["stop"]
        invocation.stop()

        attrs = self.span_exporter.get_finished_spans()[0].attributes
        assert attrs[GenAI.GEN_AI_AGENT_NAME] == "Full Agent"
        assert attrs[GenAI.GEN_AI_AGENT_ID] == "agent-123"
        assert attrs[GenAI.GEN_AI_AGENT_DESCRIPTION] == "A test agent"
        assert attrs[GenAI.GEN_AI_AGENT_VERSION] == "1.0.0"
        assert attrs[GenAI.GEN_AI_USAGE_INPUT_TOKENS] == 100
        assert attrs[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] == 200
        assert tuple(attrs[GenAI.GEN_AI_RESPONSE_FINISH_REASONS]) == ("stop",)
        assert attrs[server_attributes.SERVER_ADDRESS] == "api.openai.com"
        assert attrs[server_attributes.SERVER_PORT] == 443
        assert attrs[GenAI.GEN_AI_CONVERSATION_ID] == "conv-456"
        assert attrs[GenAI.GEN_AI_DATA_SOURCE_ID] == "ds-789"
        assert attrs[GenAI.GEN_AI_OUTPUT_TYPE] == "text"
        assert attrs[GenAI.GEN_AI_REQUEST_TEMPERATURE] == 0.7
        assert attrs[GenAI.GEN_AI_REQUEST_TOP_P] == 0.9
        assert attrs[GenAI.GEN_AI_REQUEST_MAX_TOKENS] == 1000
        assert attrs[GenAI.GEN_AI_REQUEST_SEED] == 42

    def test_cache_token_attributes(self):
        invocation = self.handler.start_agent(provider="openai")
        invocation.input_tokens = 100
        invocation.cache_creation_input_tokens = 25
        invocation.cache_read_input_tokens = 50
        invocation.stop()

        attrs = self.span_exporter.get_finished_spans()[0].attributes
        assert attrs[GenAI.GEN_AI_USAGE_INPUT_TOKENS] == 100
        assert attrs[GenAI.GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS] == 25
        assert attrs[GenAI.GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS] == 50

    def test_fail_sets_error_status(self):
        invocation = self.handler.start_agent(provider="openai")
        invocation.fail(RuntimeError("agent crashed"))

        span = self.span_exporter.get_finished_spans()[0]
        assert span.status.description == "agent crashed"
        assert span.attributes.get("error.type") == "RuntimeError"

    def test_context_manager_success(self):
        with self.handler.invoke_agent(
            provider="openai", request_model="gpt-4"
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
            with self.handler.invoke_agent(provider="openai"):
                raise ValueError("test error")

        assert (
            self.span_exporter.get_finished_spans()[0].attributes.get(
                "error.type"
            )
            == "ValueError"
        )

    def test_context_manager_default_invocation(self):
        with self.handler.invoke_agent() as inv:
            inv.agent_name = "Dynamic Agent"
            inv.provider = "openai"
        assert len(self.span_exporter.get_finished_spans()) == 1

    def test_default_values(self):
        invocation = self.handler.start_agent()
        invocation.stop()
        assert invocation._operation_name == "invoke_agent"
        assert invocation.agent_name is None
        assert invocation.provider is None
        assert invocation.request_model is None
        assert invocation.input_messages == []
        assert invocation.output_messages == []
        assert invocation.tool_definitions is None
        assert invocation.cache_creation_input_tokens is None
        assert invocation.cache_read_input_tokens is None
        assert invocation.span is not INVALID_SPAN
        assert not invocation.attributes

    def test_with_messages(self):
        invocation = self.handler.start_agent(provider="openai")
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
        invocation = self.handler.start_agent(provider="openai")
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
        invocation = self.handler.start_agent(provider="openai")
        invocation.tool_definitions = [tool]
        invocation.stop()
        assert len(invocation.tool_definitions) == 1
        assert invocation.tool_definitions[0].name == "get_weather"
        assert invocation.tool_definitions[0].type == "function"

    def test_default_lists_are_independent(self):
        inv1 = self.handler.start_agent()
        inv2 = self.handler.start_agent()
        inv1.input_messages.append(InputMessage(role="user", parts=[]))
        assert len(inv2.input_messages) == 0
        inv2.stop()
        inv1.stop()

    def test_default_attributes_are_independent(self):
        inv1 = self.handler.start_agent()
        inv2 = self.handler.start_agent()
        inv1.attributes["foo"] = "bar"
        assert "foo" not in inv2.attributes
        inv2.stop()
        inv1.stop()

    def test_agent_name_in_constructor(self):
        invocation = self.handler.start_agent(agent_name="Named Agent")
        invocation.stop()
        span = self.span_exporter.get_finished_spans()[0]
        assert span.name == "invoke_agent Named Agent"
        assert span.attributes[GenAI.GEN_AI_AGENT_NAME] == "Named Agent"
