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
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import (
    AgentCreation,
    AgentInvocation,
    Error,
    InputMessage,
    OutputMessage,
    Text,
)


class TestAgentInvocationHandler(TestCase):
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

    # ---- start/stop agent ----

    def test_start_stop_agent_creates_span(self) -> None:
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

    def test_agent_span_kind_client_by_default(self) -> None:
        handler = self._make_handler()
        invocation = AgentInvocation(agent_name="Remote Agent", is_remote=True)
        handler.start_agent(invocation)
        handler.stop_agent(invocation)

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        from opentelemetry.trace import SpanKind

        self.assertEqual(spans[0].kind, SpanKind.CLIENT)

    def test_agent_span_kind_internal_for_local(self) -> None:
        handler = self._make_handler()
        invocation = AgentInvocation(
            agent_name="Local Agent", is_remote=False
        )
        handler.start_agent(invocation)
        handler.stop_agent(invocation)

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        from opentelemetry.trace import SpanKind

        self.assertEqual(spans[0].kind, SpanKind.INTERNAL)

    def test_agent_with_all_attributes(self) -> None:
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

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        attrs = spans[0].attributes
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

    # ---- fail agent ----

    def test_fail_agent_sets_error_status(self) -> None:
        handler = self._make_handler()
        invocation = AgentInvocation(
            agent_name="Failing Agent", provider="openai"
        )
        handler.start_agent(invocation)
        error = Error(message="agent crashed", type=RuntimeError)
        handler.fail_agent(invocation, error)

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.status.description, "agent crashed")
        self.assertEqual(span.attributes.get("error.type"), "RuntimeError")

    # ---- context manager ----

    def test_agent_context_manager_success(self) -> None:
        handler = self._make_handler()
        invocation = AgentInvocation(
            agent_name="CM Agent", provider="openai", request_model="gpt-4"
        )
        with handler.agent(invocation) as inv:
            inv.input_tokens = 10
            inv.output_tokens = 20

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "invoke_agent CM Agent")

    def test_agent_context_manager_error(self) -> None:
        handler = self._make_handler()
        invocation = AgentInvocation(agent_name="Error Agent")
        with self.assertRaises(ValueError):
            with handler.agent(invocation):
                raise ValueError("test error")

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].attributes.get("error.type"), "ValueError")

    def test_agent_context_manager_default_invocation(self) -> None:
        handler = self._make_handler()
        with handler.agent() as inv:
            inv.agent_name = "Dynamic Agent"
            inv.provider = "openai"

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

    # ---- not started ----

    def test_stop_agent_without_start_is_noop(self) -> None:
        handler = self._make_handler()
        invocation = AgentInvocation(agent_name="Not Started")
        result = handler.stop_agent(invocation)
        self.assertIs(result, invocation)
        self.assertEqual(len(self.span_exporter.get_finished_spans()), 0)

    def test_fail_agent_without_start_is_noop(self) -> None:
        handler = self._make_handler()
        invocation = AgentInvocation(agent_name="Not Started")
        error = Error(message="boom", type=RuntimeError)
        result = handler.fail_agent(invocation, error)
        self.assertIs(result, invocation)
        self.assertEqual(len(self.span_exporter.get_finished_spans()), 0)


class TestAgentCreationHandler(TestCase):
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

    def test_start_stop_create_agent(self) -> None:
        handler = self._make_handler()
        creation = AgentCreation(
            agent_name="New Agent",
            agent_id="agent-new-1",
            provider="openai",
            request_model="gpt-4",
        )
        handler.start_create_agent(creation)
        handler.stop_create_agent(creation)

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "create_agent New Agent")
        self.assertEqual(
            span.attributes[GenAI.GEN_AI_OPERATION_NAME], "create_agent"
        )
        self.assertEqual(
            span.attributes[GenAI.GEN_AI_AGENT_NAME], "New Agent"
        )

    def test_create_agent_span_kind_is_client(self) -> None:
        handler = self._make_handler()
        creation = AgentCreation(agent_name="Client Agent")
        handler.start_create_agent(creation)
        handler.stop_create_agent(creation)

        spans = self.span_exporter.get_finished_spans()
        from opentelemetry.trace import SpanKind

        self.assertEqual(spans[0].kind, SpanKind.CLIENT)

    def test_create_agent_with_all_base_attributes(self) -> None:
        handler = self._make_handler()
        creation = AgentCreation(
            agent_name="Full Agent",
            agent_id="agent-123",
            agent_description="A test agent",
            agent_version="1.0.0",
            provider="openai",
            request_model="gpt-4",
            server_address="api.openai.com",
            server_port=443,
        )
        handler.start_create_agent(creation)
        handler.stop_create_agent(creation)

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        attrs = spans[0].attributes
        self.assertEqual(attrs[GenAI.GEN_AI_OPERATION_NAME], "create_agent")
        self.assertEqual(attrs[GenAI.GEN_AI_AGENT_NAME], "Full Agent")
        self.assertEqual(attrs[GenAI.GEN_AI_AGENT_ID], "agent-123")
        self.assertEqual(
            attrs[GenAI.GEN_AI_AGENT_DESCRIPTION], "A test agent"
        )
        self.assertEqual(attrs[GenAI.GEN_AI_AGENT_VERSION], "1.0.0")
        self.assertEqual(attrs[GenAI.GEN_AI_PROVIDER_NAME], "openai")
        self.assertEqual(attrs[GenAI.GEN_AI_REQUEST_MODEL], "gpt-4")

    def test_fail_create_agent(self) -> None:
        handler = self._make_handler()
        creation = AgentCreation(agent_name="Bad Agent")
        handler.start_create_agent(creation)
        error = Error(message="creation failed", type=RuntimeError)
        handler.fail_create_agent(creation, error)

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].status.description, "creation failed")
        self.assertEqual(spans[0].attributes.get("error.type"), "RuntimeError")

    def test_create_agent_context_manager(self) -> None:
        handler = self._make_handler()
        creation = AgentCreation(
            agent_name="CM Agent",
            provider="openai",
        )
        with handler.create_agent(creation) as cr:
            cr.agent_id = "assigned-id"

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "create_agent CM Agent")

    def test_create_agent_context_manager_error(self) -> None:
        handler = self._make_handler()
        with self.assertRaises(TypeError):
            with handler.create_agent(AgentCreation(agent_name="Err")):
                raise TypeError("bad type")

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].attributes.get("error.type"), "TypeError")

    def test_create_agent_context_manager_default(self) -> None:
        handler = self._make_handler()
        with handler.create_agent() as cr:
            cr.agent_name = "Dynamic Agent"
            cr.provider = "openai"

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

    def test_stop_create_agent_without_start_is_noop(self) -> None:
        handler = self._make_handler()
        creation = AgentCreation(agent_name="Not Started")
        result = handler.stop_create_agent(creation)
        self.assertIs(result, creation)
        self.assertEqual(len(self.span_exporter.get_finished_spans()), 0)

    def test_fail_create_agent_without_start_is_noop(self) -> None:
        handler = self._make_handler()
        creation = AgentCreation(agent_name="Not Started")
        error = Error(message="boom", type=RuntimeError)
        result = handler.fail_create_agent(creation, error)
        self.assertIs(result, creation)
        self.assertEqual(len(self.span_exporter.get_finished_spans()), 0)


class TestAgentTypes(TestCase):
    """Unit tests for the AgentInvocation and AgentCreation dataclasses."""

    def test_agent_invocation_defaults(self) -> None:
        inv = AgentInvocation()
        self.assertEqual(inv.operation_name, "invoke_agent")
        self.assertIsNone(inv.agent_name)
        self.assertIsNone(inv.agent_id)
        self.assertIsNone(inv.provider)
        self.assertIsNone(inv.request_model)
        self.assertTrue(inv.is_remote)
        self.assertEqual(inv.input_messages, [])
        self.assertEqual(inv.output_messages, [])
        self.assertEqual(inv.system_instruction, [])
        self.assertIsNone(inv.tool_definitions)
        self.assertIsNone(inv.span)
        self.assertIsNone(inv.context_token)

    def test_agent_creation_defaults(self) -> None:
        creation = AgentCreation()
        self.assertEqual(creation.operation_name, "create_agent")
        self.assertIsNone(creation.agent_name)
        self.assertIsNone(creation.agent_id)
        self.assertIsNone(creation.agent_description)
        self.assertIsNone(creation.agent_version)
        self.assertIsNone(creation.provider)
        self.assertIsNone(creation.request_model)
        self.assertEqual(creation.system_instruction, [])
        self.assertIsNone(creation.server_address)
        self.assertIsNone(creation.server_port)
        self.assertIsNone(creation.span)
        self.assertIsNone(creation.context_token)

    def test_agent_invocation_with_messages(self) -> None:
        inv = AgentInvocation(
            agent_name="Test",
            input_messages=[
                InputMessage(
                    role="user", parts=[Text(content="Hello")]
                )
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
        self.assertEqual(len(inv.output_messages), 1)
        self.assertEqual(inv.input_messages[0].role, "user")

    def test_agent_invocation_custom_attributes(self) -> None:
        inv = AgentInvocation(
            agent_name="Custom",
            attributes={"custom.key": "custom_value"},
        )
        self.assertEqual(inv.attributes["custom.key"], "custom_value")

    def test_agent_creation_custom_attributes(self) -> None:
        creation = AgentCreation(
            agent_name="Custom",
            attributes={"custom.key": "custom_value"},
        )
        self.assertEqual(creation.attributes["custom.key"], "custom_value")
