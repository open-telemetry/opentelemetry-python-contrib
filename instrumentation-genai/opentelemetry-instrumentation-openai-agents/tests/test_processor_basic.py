from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import set_tracer_provider

from opentelemetry.instrumentation.openai_agents import (
    genai_semantic_processor as gsp,
)
GenAISemanticProcessor = gsp.GenAISemanticProcessor
OPERATION_NAME = gsp.OPERATION_NAME
AGENT_NAME = gsp.AGENT_NAME
AGENT_ID = gsp.AGENT_ID


class DummyAgentSpanData:
    def __init__(self):
        self.name = "Math Tutor"
        self.agent_id = "asst_123"
        self.description = "Helps with math problems"
        self.span_id = "child1"
        self.parent_id = None  # creation (no parent + description)
        self.trace_id = "t1"
        self.tools = [{"name": "multiply", "type": "function"}]
        self.input = [
            {"role": "user", "content": "What is 2*3?"},
        ]
        self.output = [
            {"role": "assistant", "content": "It is 6"},
        ]


class DummySpan:
    def __init__(self):
        self.span_id = "child1"
        self.parent_id = None
        self.trace_id = "t1"
        self.span_data = DummyAgentSpanData()
        self.error = None


class DummyTrace:
    def __init__(self):
        self.trace_id = "t1"
        self.name = "agent.root"


def test_agent_span_attributes():
    provider = TracerProvider()
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

    exporter = ListExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    set_tracer_provider(provider)

    processor = GenAISemanticProcessor(
        tracer=provider.get_tracer(__name__),
        include_sensitive_data=True,
    )

    # simulate lifecycle
    trace = DummyTrace()
    processor.on_trace_start(trace)
    span = DummySpan()
    processor.on_span_start(span)
    processor.on_span_end(span)
    processor.on_trace_end(trace)

    finished = exporter.get_finished_spans()
    # Expect two spans: root + agent (creation)
    assert len(finished) == 2
    agent_span = [s for s in finished if s.name.startswith("create_agent")][0]
    assert agent_span.attributes[OPERATION_NAME] == "create_agent"
    assert agent_span.attributes[AGENT_NAME] == "Math Tutor"
    assert agent_span.attributes[AGENT_ID] == "asst_123"
