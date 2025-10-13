from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

import opentelemetry.instrumentation.openai_agents.span_processor as sp
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import StatusCode

try:
    from opentelemetry.sdk.trace.export import (  # type: ignore[attr-defined]
        InMemorySpanExporter,
        SimpleSpanProcessor,
    )
except ImportError:  # pragma: no cover
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )


@pytest.fixture
def processor_setup():
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer(__name__)
    processor = sp._OpenAIAgentsSpanProcessor(tracer=tracer, system="openai")
    yield processor, exporter
    processor.shutdown()
    exporter.clear()


def test_parse_iso8601_variants():
    assert sp._parse_iso8601(None) is None
    assert sp._parse_iso8601("bad-value") is None
    assert (
        sp._parse_iso8601("2024-01-01T00:00:00Z") == 1704067200 * 1_000_000_000
    )


def test_extract_server_attributes_variants(monkeypatch):
    assert sp._extract_server_attributes(None) == {}
    assert sp._extract_server_attributes({"base_url": 123}) == {}

    attrs = sp._extract_server_attributes(
        {"base_url": "https://api.example.com:8080/v1"}
    )
    assert attrs[ServerAttributes.SERVER_ADDRESS] == "api.example.com"
    assert attrs[ServerAttributes.SERVER_PORT] == 8080

    def boom(_: str):
        raise ValueError("unparsable url")

    monkeypatch.setattr(sp, "urlparse", boom)
    assert sp._extract_server_attributes({"base_url": "bad"}) == {}


def test_chat_helpers_cover_edges():
    assert not sp._looks_like_chat(None)
    assert not sp._looks_like_chat([{"content": "only text"}])
    assert sp._looks_like_chat([{"role": "user", "content": "hi"}])

    reasons = sp._collect_finish_reasons(
        [
            {"finish_reason": "stop"},
            {"stop_reason": "length"},
            SimpleNamespace(finish_reason="done"),
        ]
    )
    assert reasons == ["stop", "length", "done"]

    assert sp._clean_stop_sequences(None) is None
    assert sp._clean_stop_sequences("stop") == ["stop"]
    assert sp._clean_stop_sequences([None]) is None
    assert sp._clean_stop_sequences(["foo", None, 42]) == ["foo", "42"]
    assert sp._clean_stop_sequences(123) is None


def test_operation_and_span_naming(processor_setup):
    processor, _ = processor_setup

    generation = SimpleNamespace(
        type=sp.SPAN_TYPE_GENERATION, input=[{"role": "user"}]
    )
    assert (
        processor._operation_name(generation)
        == GenAI.GenAiOperationNameValues.CHAT.value
    )

    agent_create = SimpleNamespace(
        type=sp.SPAN_TYPE_AGENT, operation=" CREATE "
    )
    assert (
        processor._operation_name(agent_create)
        == GenAI.GenAiOperationNameValues.CREATE_AGENT.value
    )

    agent_invoke = SimpleNamespace(
        type=sp.SPAN_TYPE_AGENT, operation="invoke_agent"
    )
    assert (
        processor._operation_name(agent_invoke)
        == GenAI.GenAiOperationNameValues.INVOKE_AGENT.value
    )

    agent_default = SimpleNamespace(type=sp.SPAN_TYPE_AGENT, operation=None)
    assert (
        processor._operation_name(agent_default)
        == GenAI.GenAiOperationNameValues.INVOKE_AGENT.value
    )

    function_data = SimpleNamespace(type=sp.SPAN_TYPE_FUNCTION)
    assert (
        processor._operation_name(function_data)
        == GenAI.GenAiOperationNameValues.EXECUTE_TOOL.value
    )

    response_data = SimpleNamespace(type=sp.SPAN_TYPE_RESPONSE)
    assert (
        processor._operation_name(response_data)
        == GenAI.GenAiOperationNameValues.CHAT.value
    )

    unknown = SimpleNamespace(type=None)
    assert processor._operation_name(unknown) == "operation"

    agent_creation = SimpleNamespace(type=sp.SPAN_TYPE_AGENT_CREATION)
    assert (
        processor._operation_name(agent_creation)
        == GenAI.GenAiOperationNameValues.CREATE_AGENT.value
    )

    assert (
        processor._span_kind(SimpleNamespace(type=sp.SPAN_TYPE_GENERATION))
        == SpanKind.CLIENT
    )
    assert (
        processor._span_kind(SimpleNamespace(type="internal"))
        is SpanKind.INTERNAL
    )

    attrs = {GenAI.GEN_AI_REQUEST_MODEL: "gpt-4o"}
    assert (
        processor._span_name(GenAI.GenAiOperationNameValues.CHAT.value, attrs)
        == "chat gpt-4o"
    )
    assert (
        processor._span_name(
            GenAI.GenAiOperationNameValues.EXECUTE_TOOL.value,
            {GenAI.GEN_AI_TOOL_NAME: "weather"},
        )
        == "execute_tool weather"
    )
    assert (
        processor._span_name(
            GenAI.GenAiOperationNameValues.INVOKE_AGENT.value, {}
        )
        == "invoke_agent"
    )
    assert (
        processor._span_name(
            GenAI.GenAiOperationNameValues.CREATE_AGENT.value, {}
        )
        == "create_agent"
    )
    assert processor._span_name("custom_operation", {}) == "custom_operation"


def test_attribute_builders(processor_setup):
    processor, _ = processor_setup

    generation_span = SimpleNamespace(
        type=sp.SPAN_TYPE_GENERATION,
        input=[{"role": "user"}],
        model="gpt-4o",
        output=[{"finish_reason": "stop"}],
        model_config={
            "base_url": "https://api.openai.com:443/v1",
            "temperature": 0.2,
            "top_p": 0.9,
            "top_k": 3,
            "frequency_penalty": 0.1,
            "presence_penalty": 0.4,
            "seed": 1234,
            "n": 2,
            "max_tokens": 128,
            "stop": ["foo", None, "bar"],
        },
        usage={"prompt_tokens": 10, "completion_tokens": 3},
    )
    gen_attrs = processor._attributes_from_generation(generation_span)
    assert gen_attrs[GenAI.GEN_AI_REQUEST_MODEL] == "gpt-4o"
    assert gen_attrs[GenAI.GEN_AI_REQUEST_MAX_TOKENS] == 128
    assert gen_attrs[GenAI.GEN_AI_REQUEST_STOP_SEQUENCES] == ["foo", "bar"]
    assert gen_attrs[ServerAttributes.SERVER_ADDRESS] == "api.openai.com"
    assert gen_attrs[ServerAttributes.SERVER_PORT] == 443
    assert gen_attrs[GenAI.GEN_AI_USAGE_INPUT_TOKENS] == 10
    assert gen_attrs[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] == 3

    empty_response_span = SimpleNamespace(
        type=sp.SPAN_TYPE_RESPONSE, response=None
    )
    empty_attrs = processor._attributes_from_response(empty_response_span)
    assert empty_attrs[GenAI.GEN_AI_OPERATION_NAME] == "chat"
    assert empty_attrs[sp._GEN_AI_PROVIDER_NAME] == "openai"

    class _Usage:
        def __init__(self) -> None:
            self.input_tokens = None
            self.prompt_tokens = 7
            self.output_tokens = None
            self.completion_tokens = 2

    class _Response:
        def __init__(self) -> None:
            self.id = "resp-1"
            self.model = "gpt-4o"
            self.usage = _Usage()
            self.output = [{"finish_reason": "stop"}]

    response_span = SimpleNamespace(
        type=sp.SPAN_TYPE_RESPONSE, response=_Response()
    )
    response_attrs = processor._attributes_from_response(response_span)
    assert response_attrs[GenAI.GEN_AI_RESPONSE_ID] == "resp-1"
    assert response_attrs[GenAI.GEN_AI_RESPONSE_MODEL] == "gpt-4o"
    assert response_attrs[GenAI.GEN_AI_USAGE_INPUT_TOKENS] == 7
    assert response_attrs[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] == 2

    agent_span = SimpleNamespace(
        type=sp.SPAN_TYPE_AGENT, name="helper", output_type="json"
    )
    agent_attrs = processor._attributes_from_agent(agent_span)
    assert agent_attrs[GenAI.GEN_AI_AGENT_NAME] == "helper"
    assert agent_attrs[GenAI.GEN_AI_OUTPUT_TYPE] == "json"

    agent_creation_span = SimpleNamespace(
        type=sp.SPAN_TYPE_AGENT_CREATION,
        name="builder",
        description="desc",
        agent_id=None,
        id="agent-123",
        model="model-x",
    )
    creation_attrs = processor._attributes_from_agent_creation(
        agent_creation_span
    )
    assert creation_attrs[GenAI.GEN_AI_AGENT_ID] == "agent-123"
    assert creation_attrs[GenAI.GEN_AI_REQUEST_MODEL] == "model-x"

    function_span = SimpleNamespace(
        type=sp.SPAN_TYPE_FUNCTION, name="lookup_weather"
    )
    function_attrs = processor._attributes_from_function(function_span)
    assert function_attrs[GenAI.GEN_AI_TOOL_NAME] == "lookup_weather"
    assert function_attrs[GenAI.GEN_AI_TOOL_TYPE] == "function"

    generic_span = SimpleNamespace(type="custom")
    generic_attrs = processor._attributes_from_generic(generic_span)
    assert generic_attrs[GenAI.GEN_AI_OPERATION_NAME] == "custom"


def test_attributes_for_span_dispatch(processor_setup):
    processor, _ = processor_setup

    generation_span = SimpleNamespace(
        type=sp.SPAN_TYPE_GENERATION,
        model="gpt",
        input=[{"role": "user"}],
        output=[],
    )
    assert GenAI.GEN_AI_OPERATION_NAME in processor._attributes_for_span(
        generation_span
    )

    response_span = SimpleNamespace(
        type=sp.SPAN_TYPE_RESPONSE, response=SimpleNamespace()
    )
    assert (
        processor._attributes_for_span(response_span)[
            GenAI.GEN_AI_OPERATION_NAME
        ]
        == "chat"
    )

    agent_create_span = SimpleNamespace(
        type=sp.SPAN_TYPE_AGENT, operation="create"
    )
    assert (
        processor._attributes_for_span(agent_create_span)[
            GenAI.GEN_AI_OPERATION_NAME
        ]
        == "create_agent"
    )

    agent_invoke_span = SimpleNamespace(
        type=sp.SPAN_TYPE_AGENT, operation="invoke"
    )
    assert (
        processor._attributes_for_span(agent_invoke_span)[
            GenAI.GEN_AI_OPERATION_NAME
        ]
        == "invoke_agent"
    )

    agent_creation_span = SimpleNamespace(type=sp.SPAN_TYPE_AGENT_CREATION)
    assert (
        processor._attributes_for_span(agent_creation_span)[
            GenAI.GEN_AI_OPERATION_NAME
        ]
        == "create_agent"
    )

    function_span = SimpleNamespace(type=sp.SPAN_TYPE_FUNCTION)
    assert (
        processor._attributes_for_span(function_span)[GenAI.GEN_AI_TOOL_TYPE]
        == "function"
    )

    guardrail_span = SimpleNamespace(type=sp.SPAN_TYPE_GUARDRAIL)
    assert (
        processor._attributes_for_span(guardrail_span)[
            GenAI.GEN_AI_OPERATION_NAME
        ]
        == sp.SPAN_TYPE_GUARDRAIL
    )

    unknown_span = SimpleNamespace(type="unknown")
    assert processor._attributes_for_span(unknown_span) == {
        sp._GEN_AI_PROVIDER_NAME: "openai"
    }


@dataclass
class FakeTrace:
    name: str
    trace_id: str
    started_at: str | None = None
    ended_at: str | None = None


@dataclass
class FakeSpan:
    trace_id: str
    span_id: str
    span_data: Any
    parent_id: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    error: dict[str, Any] | None = None


def test_span_lifecycle_and_shutdown(processor_setup):
    processor, exporter = processor_setup

    trace = FakeTrace(
        name="workflow",
        trace_id="trace-1",
        started_at="not-a-timestamp",
        ended_at="2024-01-01T00:00:05Z",
    )
    processor.on_trace_start(trace)

    parent_span = FakeSpan(
        trace_id="trace-1",
        span_id="span-1",
        span_data=SimpleNamespace(
            type=sp.SPAN_TYPE_AGENT, operation="invoke", name="agent"
        ),
        started_at="2024-01-01T00:00:00Z",
        ended_at="2024-01-01T00:00:02Z",
    )
    processor.on_span_start(parent_span)

    missing_span = FakeSpan(
        trace_id="trace-1",
        span_id="missing",
        span_data=SimpleNamespace(type=sp.SPAN_TYPE_FUNCTION),
        started_at="2024-01-01T00:00:01Z",
        ended_at="2024-01-01T00:00:02Z",
    )
    processor.on_span_end(missing_span)

    child_span = FakeSpan(
        trace_id="trace-1",
        span_id="span-2",
        parent_id="span-1",
        span_data=SimpleNamespace(type=sp.SPAN_TYPE_FUNCTION, name="lookup"),
        started_at="2024-01-01T00:00:02Z",
        ended_at="2024-01-01T00:00:03Z",
        error={"message": "boom"},
    )
    processor.on_span_start(child_span)
    processor.on_span_end(child_span)

    processor.on_span_end(parent_span)
    processor.on_trace_end(trace)

    linger_trace = FakeTrace(
        name="linger",
        trace_id="trace-2",
        started_at="2024-01-01T00:00:06Z",
    )
    processor.on_trace_start(linger_trace)
    linger_span = FakeSpan(
        trace_id="trace-2",
        span_id="span-3",
        span_data=SimpleNamespace(type=sp.SPAN_TYPE_AGENT, operation=None),
        started_at="2024-01-01T00:00:06Z",
    )
    processor.on_span_start(linger_span)

    assert processor.force_flush() is None
    processor.shutdown()

    finished = exporter.get_finished_spans()
    statuses = {span.name: span.status for span in finished}

    assert any(
        status.status_code is StatusCode.ERROR and status.description == "boom"
        for status in statuses.values()
    )
    assert any(
        status.status_code is StatusCode.OK for status in statuses.values()
    )
    assert any(
        status.status_code is StatusCode.ERROR
        and status.description == "shutdown"
        for status in statuses.values()
    )
