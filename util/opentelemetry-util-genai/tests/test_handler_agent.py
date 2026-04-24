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
from opentelemetry.trace import SpanKind
from opentelemetry.util.genai.handler import TelemetryHandler


class TestAgentCreation(unittest.TestCase):
    def setUp(self):
        self.span_exporter = InMemorySpanExporter()
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(
            SimpleSpanProcessor(self.span_exporter)
        )
        self.handler = TelemetryHandler(tracer_provider=tracer_provider)

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

        spans = self.span_exporter.get_finished_spans()
        assert len(spans) == 1
        attrs = spans[0].attributes
        assert attrs[GenAI.GEN_AI_OPERATION_NAME] == "create_agent"
        assert attrs[GenAI.GEN_AI_AGENT_NAME] == "Full Agent"
        assert attrs[GenAI.GEN_AI_AGENT_ID] == "agent-123"
        assert attrs[GenAI.GEN_AI_AGENT_DESCRIPTION] == "A test agent"
        assert attrs[GenAI.GEN_AI_AGENT_VERSION] == "1.0.0"
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
