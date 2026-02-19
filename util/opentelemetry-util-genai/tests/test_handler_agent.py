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
    AgentCreation,
    Error,
)


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
            name="New Agent",
            agent_id="agent-new-1",
            provider="openai",
            model="gpt-4",
        )
        handler.start_agent(creation)
        handler.stop_agent(creation)

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "create_agent New Agent")
        self.assertEqual(
            span.attributes[GenAI.GEN_AI_OPERATION_NAME], "create_agent"
        )
        self.assertEqual(span.attributes[GenAI.GEN_AI_AGENT_NAME], "New Agent")

    def test_create_agent_span_kind_is_client(self) -> None:
        handler = self._make_handler()
        creation = AgentCreation(name="Client Agent")
        handler.start_agent(creation)
        handler.stop_agent(creation)

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(spans[0].kind, SpanKind.CLIENT)

    def test_create_agent_with_all_base_attributes(self) -> None:
        handler = self._make_handler()
        creation = AgentCreation(
            name="Full Agent",
            agent_id="agent-123",
            description="A test agent",
            version="1.0.0",
            provider="openai",
            model="gpt-4",
            server_address="api.openai.com",
            server_port=443,
        )
        handler.start_agent(creation)
        handler.stop_agent(creation)

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        attrs = spans[0].attributes
        self.assertEqual(attrs[GenAI.GEN_AI_OPERATION_NAME], "create_agent")
        self.assertEqual(attrs[GenAI.GEN_AI_AGENT_NAME], "Full Agent")
        self.assertEqual(attrs[GenAI.GEN_AI_AGENT_ID], "agent-123")
        self.assertEqual(attrs[GenAI.GEN_AI_AGENT_DESCRIPTION], "A test agent")
        self.assertEqual(attrs["gen_ai.agent.version"], "1.0.0")
        self.assertEqual(attrs[GenAI.GEN_AI_PROVIDER_NAME], "openai")
        self.assertEqual(attrs[GenAI.GEN_AI_REQUEST_MODEL], "gpt-4")

    def test_fail_create_agent(self) -> None:
        handler = self._make_handler()
        creation = AgentCreation(name="Bad Agent")
        handler.start_agent(creation)
        error = Error(message="creation failed", type=RuntimeError)
        handler.fail_agent(creation, error)

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].status.description, "creation failed")
        self.assertEqual(spans[0].attributes.get("error.type"), "RuntimeError")

    def test_create_agent_context_manager(self) -> None:
        handler = self._make_handler()
        creation = AgentCreation(
            name="CM Agent",
            provider="openai",
        )
        with handler.create_agent(creation) as c:
            c.agent_id = "assigned-id"

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "create_agent CM Agent")

    def test_create_agent_context_manager_error(self) -> None:
        handler = self._make_handler()
        with self.assertRaises(TypeError):
            with handler.create_agent(AgentCreation(name="Err")):
                raise TypeError("bad type")

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].attributes.get("error.type"), "TypeError")

    def test_create_agent_context_manager_default(self) -> None:
        handler = self._make_handler()
        with handler.create_agent() as c:
            c.name = "Dynamic Agent"
            c.provider = "openai"

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

    def test_stop_agent_without_start_is_noop(self) -> None:
        handler = self._make_handler()
        creation = AgentCreation(name="Not Started")
        result = handler.stop_agent(creation)
        self.assertIs(result, creation)
        self.assertEqual(len(self.span_exporter.get_finished_spans()), 0)

    def test_fail_agent_without_start_is_noop(self) -> None:
        handler = self._make_handler()
        creation = AgentCreation(name="Not Started")
        error = Error(message="boom", type=RuntimeError)
        result = handler.fail_agent(creation, error)
        self.assertIs(result, creation)
        self.assertEqual(len(self.span_exporter.get_finished_spans()), 0)


class TestAgentCreationTypes(TestCase):
    """Unit tests for the _BaseAgent and AgentCreation dataclasses."""

    def test_agent_creation_defaults(self) -> None:
        creation = AgentCreation()
        self.assertEqual(creation.operation_name, "create_agent")
        self.assertIsNone(creation.name)
        self.assertIsNone(creation.agent_id)
        self.assertIsNone(creation.description)
        self.assertIsNone(creation.version)
        self.assertIsNone(creation.provider)
        self.assertIsNone(creation.model)
        self.assertEqual(creation.system_instructions, [])
        self.assertIsNone(creation.server_address)
        self.assertIsNone(creation.server_port)
        self.assertIsNone(creation.span)
        self.assertIsNone(creation.context_token)

    def test_agent_creation_custom_attributes(self) -> None:
        creation = AgentCreation(
            name="Custom",
            attributes={"custom.key": "custom_value"},
        )
        self.assertEqual(creation.attributes["custom.key"], "custom_value")
