from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from types import SimpleNamespace
from typing import Any

import pytest
from agents.tracing import (
    AgentSpanData,
    FunctionSpanData,
    GenerationSpanData,
    ResponseSpanData,
)

import opentelemetry.semconv._incubating.attributes.gen_ai_attributes as _gen_ai_attributes
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as _server_attributes,
)
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import StatusCode


def _ensure_semconv_enums() -> None:
    if not hasattr(_gen_ai_attributes, "GenAiProviderNameValues"):

        class _GenAiProviderNameValues(Enum):
            OPENAI = "openai"
            GCP_GEN_AI = "gcp.gen_ai"
            GCP_VERTEX_AI = "gcp.vertex_ai"
            GCP_GEMINI = "gcp.gemini"
            ANTHROPIC = "anthropic"
            COHERE = "cohere"
            AZURE_AI_INFERENCE = "azure.ai.inference"
            AZURE_AI_OPENAI = "azure.ai.openai"
            IBM_WATSONX_AI = "ibm.watsonx.ai"
            AWS_BEDROCK = "aws.bedrock"
            PERPLEXITY = "perplexity"
            X_AI = "x.ai"
            DEEPSEEK = "deepseek"
            GROQ = "groq"
            MISTRAL_AI = "mistral.ai"

        class _GenAiOperationNameValues(Enum):
            CHAT = "chat"
            GENERATE_CONTENT = "generate_content"
            TEXT_COMPLETION = "text_completion"
            EMBEDDINGS = "embeddings"
            CREATE_AGENT = "create_agent"
            INVOKE_AGENT = "invoke_agent"
            EXECUTE_TOOL = "execute_tool"

        class _GenAiOutputTypeValues(Enum):
            TEXT = "text"
            JSON = "json"
            IMAGE = "image"
            SPEECH = "speech"

        _gen_ai_attributes.GenAiProviderNameValues = _GenAiProviderNameValues
        _gen_ai_attributes.GenAiOperationNameValues = _GenAiOperationNameValues
        _gen_ai_attributes.GenAiOutputTypeValues = _GenAiOutputTypeValues

    if not hasattr(_server_attributes, "SERVER_ADDRESS"):
        _server_attributes.SERVER_ADDRESS = "server.address"
    if not hasattr(_server_attributes, "SERVER_PORT"):
        _server_attributes.SERVER_PORT = "server.port"


_ensure_semconv_enums()

ServerAttributes = _server_attributes

sp = importlib.import_module(
    "opentelemetry.instrumentation.openai_agents.span_processor"
)

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


def _collect(iterator) -> dict[str, Any]:
    return {key: value for key, value in iterator}


@pytest.fixture
def processor_setup():
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer(__name__)
    processor = sp.GenAISemanticProcessor(tracer=tracer, system_name="openai")
    yield processor, exporter
    processor.shutdown()
    exporter.clear()


def test_time_helpers():
    dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert sp._as_utc_nano(dt) == 1704067200 * 1_000_000_000

    class Fallback:
        def __str__(self) -> str:
            return "fallback"

    assert sp.safe_json_dumps({"foo": "bar"}) == '{"foo":"bar"}'
    assert sp.safe_json_dumps(Fallback()) == "fallback"


def test_infer_server_attributes_variants(monkeypatch):
    assert sp._infer_server_attributes(None) == {}
    assert sp._infer_server_attributes(123) == {}

    attrs = sp._infer_server_attributes("https://api.example.com:8080/v1")
    assert attrs[ServerAttributes.SERVER_ADDRESS] == "api.example.com"
    assert attrs[ServerAttributes.SERVER_PORT] == 8080

    def boom(_: str):
        raise ValueError("unparsable url")

    monkeypatch.setattr(sp, "urlparse", boom)
    assert sp._infer_server_attributes("bad") == {}


def test_operation_and_span_naming(processor_setup):
    processor, _ = processor_setup

    generation = GenerationSpanData(input=[{"role": "user"}], model="gpt-4o")
    assert (
        processor._get_operation_name(generation) == sp.GenAIOperationName.CHAT
    )

    completion = GenerationSpanData(input=[])
    assert (
        processor._get_operation_name(completion)
        == sp.GenAIOperationName.TEXT_COMPLETION
    )

    embeddings = GenerationSpanData(input=None)
    setattr(embeddings, "embedding_dimension", 128)
    assert (
        processor._get_operation_name(embeddings)
        == sp.GenAIOperationName.EMBEDDINGS
    )

    agent_create = AgentSpanData(operation=" CREATE ")
    assert (
        processor._get_operation_name(agent_create)
        == sp.GenAIOperationName.CREATE_AGENT
    )

    agent_invoke = AgentSpanData(operation="invoke_agent")
    assert (
        processor._get_operation_name(agent_invoke)
        == sp.GenAIOperationName.INVOKE_AGENT
    )

    agent_default = AgentSpanData(operation=None)
    assert (
        processor._get_operation_name(agent_default)
        == sp.GenAIOperationName.INVOKE_AGENT
    )

    function_data = FunctionSpanData()
    assert (
        processor._get_operation_name(function_data)
        == sp.GenAIOperationName.EXECUTE_TOOL
    )

    response_data = ResponseSpanData()
    assert (
        processor._get_operation_name(response_data)
        == sp.GenAIOperationName.CHAT
    )

    class UnknownSpanData:
        pass

    unknown = UnknownSpanData()
    assert processor._get_operation_name(unknown) == "unknown"

    assert processor._get_span_kind(GenerationSpanData()) is SpanKind.CLIENT
    assert processor._get_span_kind(FunctionSpanData()) is SpanKind.INTERNAL

    assert (
        sp.get_span_name(sp.GenAIOperationName.CHAT, model="gpt-4o")
        == "chat gpt-4o"
    )
    assert (
        sp.get_span_name(
            sp.GenAIOperationName.EXECUTE_TOOL, tool_name="weather"
        )
        == "execute_tool weather"
    )
    assert (
        sp.get_span_name(sp.GenAIOperationName.INVOKE_AGENT, agent_name=None)
        == "invoke_agent"
    )
    assert (
        sp.get_span_name(sp.GenAIOperationName.CREATE_AGENT, agent_name=None)
        == "create_agent"
    )


def test_attribute_builders(processor_setup):
    processor, _ = processor_setup

    payload = sp.ContentPayload(
        input_messages=[
            {
                "role": "user",
                "parts": [{"type": "text", "content": "hi"}],
            }
        ],
        output_messages=[
            {
                "role": "assistant",
                "parts": [{"type": "text", "content": "hello"}],
            }
        ],
        system_instructions=[{"type": "text", "content": "be helpful"}],
    )
    model_config = {
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
    }
    generation_span = GenerationSpanData(
        input=[{"role": "user"}],
        output=[{"finish_reason": "stop"}],
        model="gpt-4o",
        model_config=model_config,
        usage={
            "prompt_tokens": 10,
            "completion_tokens": 3,
            "total_tokens": 13,
        },
    )
    gen_attrs = _collect(
        processor._get_attributes_from_generation_span_data(
            generation_span, payload
        )
    )
    assert gen_attrs[sp.GEN_AI_REQUEST_MODEL] == "gpt-4o"
    assert gen_attrs[sp.GEN_AI_REQUEST_MAX_TOKENS] == 128
    assert gen_attrs[sp.GEN_AI_REQUEST_STOP_SEQUENCES] == [
        "foo",
        None,
        "bar",
    ]
    assert gen_attrs[ServerAttributes.SERVER_ADDRESS] == "api.openai.com"
    assert gen_attrs[ServerAttributes.SERVER_PORT] == 443
    assert gen_attrs[sp.GEN_AI_USAGE_INPUT_TOKENS] == 10
    assert gen_attrs[sp.GEN_AI_USAGE_OUTPUT_TOKENS] == 3
    assert gen_attrs[sp.GEN_AI_RESPONSE_FINISH_REASONS] == ["stop"]
    assert json.loads(gen_attrs[sp.GEN_AI_INPUT_MESSAGES])[0]["role"] == "user"
    assert (
        json.loads(gen_attrs[sp.GEN_AI_OUTPUT_MESSAGES])[0]["role"]
        == "assistant"
    )
    assert (
        json.loads(gen_attrs[sp.GEN_AI_SYSTEM_INSTRUCTIONS])[0]["content"]
        == "be helpful"
    )
    assert gen_attrs[sp.GEN_AI_OUTPUT_TYPE] == sp.GenAIOutputType.TEXT

    class _Usage:
        def __init__(self) -> None:
            self.input_tokens = None
            self.prompt_tokens = 7
            self.output_tokens = None
            self.completion_tokens = 2
            self.total_tokens = 9

    class _Response:
        def __init__(self) -> None:
            self.id = "resp-1"
            self.model = "gpt-4o"
            self.usage = _Usage()
            self.output = [{"finish_reason": "stop"}]

    response_span = ResponseSpanData(response=_Response())
    response_attrs = _collect(
        processor._get_attributes_from_response_span_data(
            response_span, sp.ContentPayload()
        )
    )
    assert response_attrs[sp.GEN_AI_RESPONSE_ID] == "resp-1"
    assert response_attrs[sp.GEN_AI_RESPONSE_MODEL] == "gpt-4o"
    assert response_attrs[sp.GEN_AI_RESPONSE_FINISH_REASONS] == ["stop"]
    assert response_attrs[sp.GEN_AI_USAGE_INPUT_TOKENS] == 7
    assert response_attrs[sp.GEN_AI_USAGE_OUTPUT_TOKENS] == 2
    assert response_attrs[sp.GEN_AI_OUTPUT_TYPE] == sp.GenAIOutputType.TEXT

    agent_span = AgentSpanData(
        name="helper",
        output_type="json",
        description="desc",
        agent_id="agent-123",
        model="model-x",
        operation="invoke_agent",
    )
    agent_attrs = _collect(
        processor._get_attributes_from_agent_span_data(agent_span, None)
    )
    assert agent_attrs[sp.GEN_AI_AGENT_NAME] == "helper"
    assert agent_attrs[sp.GEN_AI_AGENT_ID] == "agent-123"
    assert agent_attrs[sp.GEN_AI_REQUEST_MODEL] == "model-x"
    assert agent_attrs[sp.GEN_AI_OUTPUT_TYPE] == sp.GenAIOutputType.TEXT

    # Fallback to aggregated model when span data lacks it
    agent_span_no_model = AgentSpanData(
        name="helper-2",
        output_type="json",
        description="desc",
        agent_id="agent-456",
        operation="invoke_agent",
    )
    agent_content = {
        "input_messages": [],
        "output_messages": [],
        "system_instructions": [],
        "request_model": "gpt-fallback",
    }
    agent_attrs_fallback = _collect(
        processor._get_attributes_from_agent_span_data(
            agent_span_no_model, agent_content
        )
    )
    assert agent_attrs_fallback[sp.GEN_AI_REQUEST_MODEL] == "gpt-fallback"

    function_span = FunctionSpanData(name="lookup_weather")
    function_span.tool_type = "extension"
    function_span.call_id = "call-42"
    function_span.description = "desc"
    function_payload = sp.ContentPayload(
        tool_arguments={"city": "seattle"},
        tool_result={"temperature": 70},
    )
    function_attrs = _collect(
        processor._get_attributes_from_function_span_data(
            function_span, function_payload
        )
    )
    assert function_attrs[sp.GEN_AI_TOOL_NAME] == "lookup_weather"
    assert function_attrs[sp.GEN_AI_TOOL_TYPE] == "extension"
    assert function_attrs[sp.GEN_AI_TOOL_CALL_ID] == "call-42"
    assert function_attrs[sp.GEN_AI_TOOL_DESCRIPTION] == "desc"
    assert function_attrs[sp.GEN_AI_TOOL_CALL_ARGUMENTS] == {"city": "seattle"}
    assert function_attrs[sp.GEN_AI_TOOL_CALL_RESULT] == {"temperature": 70}
    assert function_attrs[sp.GEN_AI_OUTPUT_TYPE] == sp.GenAIOutputType.JSON


def test_extract_genai_attributes_unknown_type(processor_setup):
    processor, _ = processor_setup

    class UnknownSpanData:
        pass

    class StubSpan:
        def __init__(self) -> None:
            self.span_data = UnknownSpanData()

    attrs = _collect(
        processor._extract_genai_attributes(
            StubSpan(), sp.ContentPayload(), None
        )
    )
    assert attrs[sp.GEN_AI_PROVIDER_NAME] == "openai"
    assert attrs[sp.GEN_AI_SYSTEM_KEY] == "openai"
    assert sp.GEN_AI_OPERATION_NAME not in attrs


def test_span_status_helper():
    status = sp._get_span_status(
        SimpleNamespace(error={"message": "boom", "data": "bad"})
    )
    assert status.status_code is StatusCode.ERROR
    assert status.description == "boom: bad"

    ok_status = sp._get_span_status(SimpleNamespace(error=None))
    assert ok_status.status_code is StatusCode.OK


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
        span_data=AgentSpanData(
            operation="invoke", name="agent", model="gpt-4o"
        ),
        started_at="2024-01-01T00:00:00Z",
        ended_at="2024-01-01T00:00:02Z",
    )
    processor.on_span_start(parent_span)

    missing_span = FakeSpan(
        trace_id="trace-1",
        span_id="missing",
        span_data=FunctionSpanData(name="lookup"),
        started_at="2024-01-01T00:00:01Z",
        ended_at="2024-01-01T00:00:02Z",
    )
    processor.on_span_end(missing_span)

    child_span = FakeSpan(
        trace_id="trace-1",
        span_id="span-2",
        parent_id="span-1",
        span_data=FunctionSpanData(name="lookup"),
        started_at="2024-01-01T00:00:02Z",
        ended_at="2024-01-01T00:00:03Z",
        error={"message": "boom", "data": "bad"},
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
        span_data=AgentSpanData(operation=None),
        started_at="2024-01-01T00:00:06Z",
    )
    processor.on_span_start(linger_span)

    assert processor.force_flush() is None
    processor.shutdown()

    finished = exporter.get_finished_spans()
    statuses = {span.name: span.status for span in finished}

    assert (
        statuses["execute_tool lookup"].status_code is StatusCode.ERROR
        and statuses["execute_tool lookup"].description == "boom: bad"
    )
    assert statuses["invoke_agent agent"].status_code is StatusCode.OK
    assert statuses["workflow"].status_code is StatusCode.OK
    assert (
        statuses["invoke_agent"].status_code is StatusCode.ERROR
        and statuses["invoke_agent"].description == "Application shutdown"
    )
    assert (
        statuses["linger"].status_code is StatusCode.ERROR
        and statuses["linger"].description == "Application shutdown"
    )
    workflow_span = next(span for span in finished if span.name == "workflow")
    assert (
        workflow_span.attributes[sp.GEN_AI_OPERATION_NAME]
        == sp.GenAIOperationName.INVOKE_AGENT
    )


def test_chat_span_renamed_with_model(processor_setup):
    processor, exporter = processor_setup

    trace = FakeTrace(name="workflow", trace_id="trace-rename")
    processor.on_trace_start(trace)

    agent = FakeSpan(
        trace_id=trace.trace_id,
        span_id="agent-span",
        span_data=AgentSpanData(
            operation="invoke_agent",
            name="Agent",
        ),
        started_at="2025-01-01T00:00:00Z",
        ended_at="2025-01-01T00:00:02Z",
    )
    processor.on_span_start(agent)

    generation_data = GenerationSpanData(
        input=[{"role": "user", "content": "question"}],
        output=[{"finish_reason": "stop"}],
        usage={"prompt_tokens": 1, "completion_tokens": 1},
    )
    generation_span = FakeSpan(
        trace_id=trace.trace_id,
        span_id="child-span",
        parent_id=agent.span_id,
        span_data=generation_data,
        started_at="2025-01-01T00:00:00Z",
        ended_at="2025-01-01T00:00:01Z",
    )
    processor.on_span_start(generation_span)

    # Model becomes available before span end (e.g., once response arrives)
    generation_data.model = "gpt-4o"

    processor.on_span_end(generation_span)
    processor.on_span_end(agent)
    processor.on_trace_end(trace)

    span_names = {span.name for span in exporter.get_finished_spans()}
    assert "chat gpt-4o" in span_names
