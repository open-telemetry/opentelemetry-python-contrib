import os
from typing import List

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import set_tracer_provider

from opentelemetry.instrumentation.openai_agents import (
    genai_semantic_processor as gsp,
    utils as gutils,
)

GenAISemanticProcessor = gsp.GenAISemanticProcessor


class DummyTrace:
    def __init__(self, trace_id="tX"):
        self.trace_id = trace_id
        self.name = "agent.root"


class BaseSpan:
    def __init__(self, span_id: str, trace_id: str, parent_id=None):
        self.span_id = span_id
        self.trace_id = trace_id
        self.parent_id = parent_id
        self.error = None


class AgentSpanData:
    def __init__(
        self,
        span_id: str,
        trace_id: str,
        parent_id=None,
        description: str | None = None,
        is_creation: bool | None = None,
    ):
        self.span_id = span_id
        self.trace_id = trace_id
        self.parent_id = parent_id
        self.name = f"Agent-{span_id}"
        self.agent_id = f"agent_{span_id}"
        if description:
            self.description = description
        if is_creation is not None:
            self.is_creation = is_creation


class FunctionSpanData:
    def __init__(
        self,
        span_id: str,
        trace_id: str,
        parent_id: str,
        name: str,
        tool_type="function",
        inputs=None,
        output=None,
    ):
        self.span_id = span_id
        self.trace_id = trace_id
        self.parent_id = parent_id
        self.name = name
        self.call_id = f"call_{span_id}"
        self.tool_type = tool_type
        self.input = inputs
        self.output = output


class Choice:
    def __init__(self, finish_reason):
        self.finish_reason = finish_reason


class RespUsage:
    def __init__(self, prompt=10, completion=5):
        self.prompt_tokens = prompt
        self.completion_tokens = completion


class ResponseObj:
    def __init__(self, finish_reasons: List[str]):
        self.id = "resp_1"
        self.model = "gpt-test"
        self.choices = [Choice(fr) for fr in finish_reasons]
        self.usage = RespUsage()


class ResponseSpanData:
    def __init__(
        self,
        span_id: str,
        trace_id: str,
        parent_id: str,
        finish_reasons: List[str],
    ):
        self.span_id = span_id
        self.trace_id = trace_id
        self.parent_id = parent_id
        self.response = ResponseObj(finish_reasons)


class EmbeddingsSpanData:
    def __init__(self, span_id: str, trace_id: str, parent_id: str):
        self.span_id = span_id
        self.trace_id = trace_id
        self.parent_id = parent_id


class DummySpan:
    def __init__(self, data):
        self.span_data = data
        self.span_id = data.span_id
        self.parent_id = getattr(data, "parent_id", None)
        self.trace_id = data.trace_id
        self.error = None


class ListExporter(SpanExporter):
    def __init__(self):
        self.spans = []

    def export(self, spans):  # type: ignore
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self):  # type: ignore
        return None

    def get_finished_spans(self):
        return list(self.spans)


def _mk_provider():
    provider = TracerProvider()
    exporter = ListExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    set_tracer_provider(provider)
    return provider, exporter


def test_operation_naming_create_vs_invoke():
    provider, exporter = _mk_provider()
    processor = GenAISemanticProcessor(tracer=provider.get_tracer(__name__))
    trace = DummyTrace("tA")
    processor.on_trace_start(trace)
    # creation (no parent + description)
    create_data = AgentSpanData("a1", "tA", description="desc")
    create_span = DummySpan(create_data)
    processor.on_span_start(create_span)
    processor.on_span_end(create_span)
    # invocation (has parent)
    invoke_data = AgentSpanData("a2", "tA", parent_id="a1")
    invoke_span = DummySpan(invoke_data)
    processor.on_span_start(invoke_span)
    processor.on_span_end(invoke_span)
    processor.on_trace_end(trace)
    names = {
        s.attributes.get(gsp.OPERATION_NAME)
        for s in exporter.get_finished_spans()
    }
    assert "create_agent" in names
    assert "invoke_agent" in names


def test_tool_io_gating():
    os.environ[
        gutils.OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_TOOL_IO
    ] = "false"
    provider, exporter = _mk_provider()
    processor = GenAISemanticProcessor(tracer=provider.get_tracer(__name__))
    trace = DummyTrace("tB")
    processor.on_trace_start(trace)
    agent = DummySpan(AgentSpanData("a1", "tB", description="d"))
    processor.on_span_start(agent)
    processor.on_span_end(agent)
    func_data = FunctionSpanData(
        "f1",
        "tB",
        parent_id="a1",
        name="tool1",
        inputs={"x": 1},
        output={"y": 2},
    )
    func_span = DummySpan(func_data)
    processor.on_span_start(func_span)
    processor.on_span_end(func_span)
    processor.on_trace_end(trace)
    tool_span = [
        s
        for s in exporter.get_finished_spans()
        if s.attributes.get(gsp.OPERATION_NAME) == "execute_tool"
    ][0]
    assert gsp.TOOL_CALL_ARGS not in tool_span.attributes
    # enable and retry
    os.environ[
        gutils.OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_TOOL_IO
    ] = "true"
    provider2, exporter2 = _mk_provider()
    processor2 = GenAISemanticProcessor(tracer=provider2.get_tracer(__name__))
    trace2 = DummyTrace("tC")
    processor2.on_trace_start(trace2)
    agent2 = DummySpan(AgentSpanData("a2", "tC", description="d"))
    processor2.on_span_start(agent2)
    processor2.on_span_end(agent2)
    func_data2 = FunctionSpanData(
        "f2",
        "tC",
        parent_id="a2",
        name="tool2",
        inputs={"x": 1},
        output={"y": 2},
    )
    func_span2 = DummySpan(func_data2)
    processor2.on_span_start(func_span2)
    processor2.on_span_end(func_span2)
    processor2.on_trace_end(trace2)
    tool_span2 = [
        s
        for s in exporter2.get_finished_spans()
        if s.attributes.get(gsp.OPERATION_NAME) == "execute_tool"
    ][0]
    assert gsp.TOOL_CALL_ARGS in tool_span2.attributes


def test_finish_reasons_aggregation():
    provider, exporter = _mk_provider()
    processor = GenAISemanticProcessor(tracer=provider.get_tracer(__name__))
    trace = DummyTrace("tD")
    processor.on_trace_start(trace)
    agent = DummySpan(AgentSpanData("a1", "tD", description="d"))
    processor.on_span_start(agent)
    processor.on_span_end(agent)
    resp_data = ResponseSpanData(
        "r1", "tD", parent_id="a1", finish_reasons=["stop", "length"]
    )
    resp_span = DummySpan(resp_data)
    processor.on_span_start(resp_span)
    processor.on_span_end(resp_span)
    processor.on_trace_end(trace)
    resp_finished = [
        s
        for s in exporter.get_finished_spans()
        if s.attributes.get(gsp.OPERATION_NAME) == "chat"
    ][0]
    assert set(
        resp_finished.attributes.get(gsp.RESPONSE_FINISH_REASONS, [])
    ) == {"stop", "length"}


def test_truncation_and_tool_definitions():
    os.environ[
        gutils.OTEL_INSTRUMENTATION_OPENAI_AGENTS_MAX_VALUE_LENGTH
    ] = "40"
    os.environ[
        gutils.OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_TOOL_DEFINITIONS
    ] = "true"
    provider, exporter = _mk_provider()
    processor = GenAISemanticProcessor(
        tracer=provider.get_tracer(__name__), include_sensitive_data=True
    )
    trace = DummyTrace("tE")
    processor.on_trace_start(trace)
    data = AgentSpanData("a1", "tE", description="d")
    data.tools = [
        {
            "name": "tool",
            "description": "".join(["x" for _ in range(100)]),
        }
    ]
    span = DummySpan(data)
    processor.on_span_start(span)
    processor.on_span_end(span)
    processor.on_trace_end(trace)
    agent_span = [
        s
        for s in exporter.get_finished_spans()
        if s.attributes.get(gsp.OPERATION_NAME) == "create_agent"
    ][0]
    td = agent_span.attributes.get(gsp.TOOL_DEFINITIONS)
    assert isinstance(td, str) or (isinstance(td, list) and len(str(td)) > 0)


def test_metrics_toggle_off():
    os.environ[
        gutils.OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_METRICS
    ] = "false"
    provider, _ = _mk_provider()
    processor = GenAISemanticProcessor(tracer=provider.get_tracer(__name__))
    assert processor._meter is None


def test_error_attribute_and_status():
    provider, exporter = _mk_provider()
    processor = GenAISemanticProcessor(tracer=provider.get_tracer(__name__))
    trace = DummyTrace("tF")
    processor.on_trace_start(trace)
    data = AgentSpanData("a1", "tF", description="d")
    span = DummySpan(data)
    processor.on_span_start(span)
    span.error = {"message": "Boom", "type": "Failure"}
    processor.on_span_end(span)
    processor.on_trace_end(trace)
    finished = [
        s
        for s in exporter.get_finished_spans()
        if s.attributes.get(gsp.OPERATION_NAME) == "create_agent"
    ][0]
    assert finished.status.status_code.name == "ERROR"
    assert finished.attributes[gsp.ERROR_TYPE] == "Failure"


def test_deactivation():
    provider, exporter = _mk_provider()
    processor = GenAISemanticProcessor(tracer=provider.get_tracer(__name__))
    trace = DummyTrace("tG")
    processor.on_trace_start(trace)
    # Start and end first span BEFORE shutdown (should be recorded)
    first = DummySpan(AgentSpanData("a1", "tG", description="d"))
    processor.on_span_start(first)
    processor.on_span_end(first)
    # Shutdown then attempt second span (should be ignored)
    processor.shutdown()
    second = DummySpan(AgentSpanData("a2", "tG", description="d"))
    processor.on_span_start(second)
    processor.on_span_end(second)
    processor.on_trace_end(trace)
    ops = [
        s.attributes.get(gsp.OPERATION_NAME)
        for s in exporter.get_finished_spans()
    ]
    assert ops.count("create_agent") == 1


def test_additional_operation_names():
    provider, exporter = _mk_provider()
    processor = GenAISemanticProcessor(tracer=provider.get_tracer(__name__))
    trace = DummyTrace("tH")
    processor.on_trace_start(trace)
    agent = DummySpan(AgentSpanData("a1", "tH", description="d"))
    processor.on_span_start(agent)
    processor.on_span_end(agent)
    emb = DummySpan(EmbeddingsSpanData("e1", "tH", "a1"))
    processor.on_span_start(emb)
    processor.on_span_end(emb)
    processor.on_trace_end(trace)
    names = {
        s.attributes.get(gsp.OPERATION_NAME)
        for s in exporter.get_finished_spans()
    }
    assert "embeddings" in names
    assert "create_agent" in names
