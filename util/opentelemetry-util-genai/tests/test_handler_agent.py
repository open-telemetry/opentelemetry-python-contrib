from __future__ import annotations

from unittest import TestCase

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.trace import SpanKind
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import (
    AgentInvocation,
    Error,
    InputMessage,
    OutputMessage,
    Text,
)


class _AgentTestBase(TestCase):
    """Shared setUp and helper for agent handler tests."""

    def setUp(self) -> None:
        self.span_exporter = InMemorySpanExporter()
        self.tracer_provider = TracerProvider()
        self.tracer_provider.add_span_processor(
            SimpleSpanProcessor(self.span_exporter)
        )

    def _make_handler(self) -> TelemetryHandler:
        return TelemetryHandler(
            tracer_provider=self.tracer_provider,
        )


class TestAgentInvocationHandler(_AgentTestBase):

    def test_start_stop_creates_span(self) -> None:
        handler = self._make_handler()
        invocation = AgentInvocation(
            agent_name="Math Tutor",
            provider="openai",
            request_model="gpt-4",
        )
        handler.start_agent(invocation)
        handler.stop_agent(invocation)

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "invoke_agent Math Tutor")
        self.assertEqual(
            span.attributes[GenAI.GEN_AI_OPERATION_NAME], "invoke_agent"
        )
        self.assertEqual(
            span.attributes[GenAI.GEN_AI_AGENT_NAME], "Math Tutor"
        )
        self.assertEqual(
            span.attributes[GenAI.GEN_AI_PROVIDER_NAME], "openai"
        )
        self.assertEqual(
            span.attributes[GenAI.GEN_AI_REQUEST_MODEL], "gpt-4"
        )

    def test_span_kind_client_by_default(self) -> None:
        handler = self._make_handler()
        invocation = AgentInvocation(agent_name="Agent", is_remote=True)
        handler.start_agent(invocation)
        handler.stop_agent(invocation)
        self.assertEqual(
            self.span_exporter.get_finished_spans()[0].kind, SpanKind.CLIENT
        )

    def test_span_kind_internal_for_local(self) -> None:
        handler = self._make_handler()
        invocation = AgentInvocation(agent_name="Agent", is_remote=False)
        handler.start_agent(invocation)
        handler.stop_agent(invocation)
        self.assertEqual(
            self.span_exporter.get_finished_spans()[0].kind, SpanKind.INTERNAL
        )

    def test_all_attributes(self) -> None:
        handler = self._make_handler()
        invocation = AgentInvocation(
            agent_name="Full Agent",
            agent_id="agent-123",
            agent_description="A test agent",
            agent_version="1.0.0",
            provider="openai",
            request_model="gpt-4",
            conversation_id="conv-456",
            data_source_id="ds-789",
            output_type="text",
            temperature=0.7,
            top_p=0.9,
            max_tokens=1000,
            seed=42,
            server_address="api.openai.com",
            server_port=443,
        )
        handler.start_agent(invocation)
        invocation.response_model_name = "gpt-4-0613"
        invocation.response_id = "resp-abc"
        invocation.input_tokens = 100
        invocation.output_tokens = 200
        invocation.finish_reasons = ["stop"]
        handler.stop_agent(invocation)

        attrs = self.span_exporter.get_finished_spans()[0].attributes
        self.assertEqual(attrs[GenAI.GEN_AI_AGENT_NAME], "Full Agent")
        self.assertEqual(attrs[GenAI.GEN_AI_AGENT_ID], "agent-123")
        self.assertEqual(
            attrs[GenAI.GEN_AI_AGENT_DESCRIPTION], "A test agent"
        )
        self.assertEqual(attrs[GenAI.GEN_AI_RESPONSE_MODEL], "gpt-4-0613")
        self.assertEqual(attrs[GenAI.GEN_AI_RESPONSE_ID], "resp-abc")
        self.assertEqual(attrs[GenAI.GEN_AI_USAGE_INPUT_TOKENS], 100)
        self.assertEqual(attrs[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS], 200)
        self.assertEqual(
            tuple(attrs[GenAI.GEN_AI_RESPONSE_FINISH_REASONS]), ("stop",)
        )
        self.assertEqual(attrs["gen_ai.agent.version"], "1.0.0")

    def test_cache_token_attributes(self) -> None:
        handler = self._make_handler()
        invocation = AgentInvocation(
            agent_name="Cache Agent", provider="openai"
        )
        handler.start_agent(invocation)
        invocation.input_tokens = 100
        invocation.cache_creation_input_tokens = 25
        invocation.cache_read_input_tokens = 50
        handler.stop_agent(invocation)

        attrs = self.span_exporter.get_finished_spans()[0].attributes
        self.assertEqual(attrs[GenAI.GEN_AI_USAGE_INPUT_TOKENS], 100)
        self.assertEqual(
            attrs[GenAI.GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS], 25
        )
        self.assertEqual(
            attrs[GenAI.GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS], 50
        )

    def test_fail_sets_error_status(self) -> None:
        handler = self._make_handler()
        invocation = AgentInvocation(agent_name="Agent", provider="openai")
        handler.start_agent(invocation)
        handler.fail_agent(
            invocation, Error(message="agent crashed", type=RuntimeError)
        )

        span = self.span_exporter.get_finished_spans()[0]
        self.assertEqual(span.status.description, "agent crashed")
        self.assertEqual(span.attributes.get("error.type"), "RuntimeError")

    def test_context_manager_success(self) -> None:
        handler = self._make_handler()
        invocation = AgentInvocation(
            agent_name="CM Agent", provider="openai", request_model="gpt-4"
        )
        with handler.agent(invocation) as inv:
            inv.input_tokens = 10
            inv.output_tokens = 20

        self.assertEqual(
            self.span_exporter.get_finished_spans()[0].name,
            "invoke_agent CM Agent",
        )

    def test_context_manager_error(self) -> None:
        handler = self._make_handler()
        with self.assertRaises(ValueError):
            with handler.agent(AgentInvocation(agent_name="Agent")):
                raise ValueError("test error")

        self.assertEqual(
            self.span_exporter.get_finished_spans()[0]
            .attributes.get("error.type"),
            "ValueError",
        )

    def test_context_manager_default_invocation(self) -> None:
        handler = self._make_handler()
        with handler.agent() as inv:
            inv.agent_name = "Dynamic Agent"
            inv.provider = "openai"
        self.assertEqual(len(self.span_exporter.get_finished_spans()), 1)

    def test_stop_without_start_is_noop(self) -> None:
        handler = self._make_handler()
        invocation = AgentInvocation(agent_name="Not Started")
        result = handler.stop_agent(invocation)
        self.assertIs(result, invocation)
        self.assertEqual(len(self.span_exporter.get_finished_spans()), 0)

    def test_fail_without_start_is_noop(self) -> None:
        handler = self._make_handler()
        invocation = AgentInvocation(agent_name="Not Started")
        result = handler.fail_agent(
            invocation, Error(message="boom", type=RuntimeError)
        )
        self.assertIs(result, invocation)
        self.assertEqual(len(self.span_exporter.get_finished_spans()), 0)


class TestAgentInvocationType(TestCase):

    def test_defaults(self) -> None:
        inv = AgentInvocation()
        self.assertEqual(inv.operation_name, "invoke_agent")
        self.assertIsNone(inv.agent_name)
        self.assertIsNone(inv.provider)
        self.assertIsNone(inv.request_model)
        self.assertTrue(inv.is_remote)
        self.assertEqual(inv.input_messages, [])
        self.assertEqual(inv.output_messages, [])
        self.assertIsNone(inv.tool_definitions)
        self.assertIsNone(inv.cache_creation_input_tokens)
        self.assertIsNone(inv.cache_read_input_tokens)

    def test_with_messages(self) -> None:
        inv = AgentInvocation(
            agent_name="Test",
            input_messages=[
                InputMessage(role="user", parts=[Text(content="Hello")])
            ],
            output_messages=[
                OutputMessage(
                    role="assistant",
                    parts=[Text(content="Hi there!")],
                    finish_reason="stop",
                )
            ],
        )
        self.assertEqual(len(inv.input_messages), 1)
        self.assertEqual(inv.input_messages[0].role, "user")

    def test_custom_attributes(self) -> None:
        inv = AgentInvocation(
            agent_name="Custom",
            attributes={"custom.key": "custom_value"},
        )
        self.assertEqual(inv.attributes["custom.key"], "custom_value")
