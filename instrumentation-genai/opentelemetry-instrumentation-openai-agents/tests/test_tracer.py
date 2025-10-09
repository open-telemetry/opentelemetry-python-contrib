from __future__ import annotations

import sys
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent
stub_path = TESTS_ROOT / "stubs"
if str(stub_path) not in sys.path:
    sys.path.insert(0, str(stub_path))

sys.modules.pop("agents", None)
sys.modules.pop("agents.tracing", None)

from agents.tracing import (  # noqa: E402
    agent_span,
    function_span,
    generation_span,
    response_span,
    set_trace_processors,
    trace,
)

from opentelemetry.instrumentation.openai_agents import (  # noqa: E402
    OpenAIAgentsInstrumentor,
)
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402

try:
    from opentelemetry.sdk.trace.export import (  # type: ignore[attr-defined]
        InMemorySpanExporter,
        SimpleSpanProcessor,
    )
except ImportError:  # pragma: no cover - support older/newer SDK layouts
    from opentelemetry.sdk.trace.export import (
        SimpleSpanProcessor,  # noqa: E402
    )
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
        InMemorySpanExporter,
    )
from opentelemetry.semconv._incubating.attributes import (  # noqa: E402
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv._incubating.attributes import (  # noqa: E402
    server_attributes as ServerAttributes,
)
from opentelemetry.trace import SpanKind  # noqa: E402


def _instrument_with_provider(**instrument_kwargs):
    set_trace_processors([])
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    instrumentor = OpenAIAgentsInstrumentor()
    instrumentor.instrument(tracer_provider=provider, **instrument_kwargs)

    return instrumentor, exporter


def test_generation_span_creates_client_span():
    instrumentor, exporter = _instrument_with_provider()

    try:
        with trace("workflow"):
            with generation_span(
                input=[{"role": "user", "content": "hi"}],
                model="gpt-4o-mini",
                model_config={
                    "temperature": 0.2,
                    "base_url": "https://api.openai.com",
                },
                usage={"input_tokens": 12, "output_tokens": 3},
            ):
                pass

        spans = exporter.get_finished_spans()
        client_spans = [span for span in spans if span.kind is SpanKind.CLIENT]
        server_spans = [span for span in spans if span.kind is SpanKind.SERVER]

        assert len(server_spans) == 1
        server_span = server_spans[0]
        assert server_span.name == "workflow"
        assert server_span.attributes["gen_ai.provider.name"] == "openai"
        assert client_spans
        client_span = next(iter(client_spans))

        assert client_span.attributes["gen_ai.provider.name"] == "openai"
        assert client_span.attributes[GenAI.GEN_AI_OPERATION_NAME] == "chat"
        assert (
            client_span.attributes[GenAI.GEN_AI_REQUEST_MODEL] == "gpt-4o-mini"
        )
        assert client_span.name == "chat gpt-4o-mini"
        assert client_span.attributes[GenAI.GEN_AI_USAGE_INPUT_TOKENS] == 12
        assert client_span.attributes[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] == 3
        assert (
            client_span.attributes[ServerAttributes.SERVER_ADDRESS]
            == "api.openai.com"
        )
    finally:
        instrumentor.uninstrument()
        exporter.clear()


def test_generation_span_without_roles_uses_text_completion():
    instrumentor, exporter = _instrument_with_provider()

    try:
        with trace("workflow"):
            with generation_span(
                input=[{"content": "tell me a joke"}],
                model="gpt-4o-mini",
                model_config={"temperature": 0.7},
            ):
                pass

        spans = exporter.get_finished_spans()
        completion_span = next(
            span
            for span in spans
            if span.attributes[GenAI.GEN_AI_OPERATION_NAME]
            == GenAI.GenAiOperationNameValues.TEXT_COMPLETION.value
        )
        assert completion_span.kind is SpanKind.CLIENT
        server_spans = [span for span in spans if span.kind is SpanKind.SERVER]
        assert len(server_spans) == 1
        assert server_spans[0].name == "workflow"
        assert server_spans[0].attributes["gen_ai.provider.name"] == "openai"
        assert [span for span in spans if span.kind is SpanKind.CLIENT]

        assert completion_span.kind is SpanKind.CLIENT
        assert completion_span.name == "text_completion gpt-4o-mini"
        assert (
            completion_span.attributes[GenAI.GEN_AI_REQUEST_MODEL]
            == "gpt-4o-mini"
        )
    finally:
        instrumentor.uninstrument()
        exporter.clear()


def test_function_span_records_tool_attributes():
    instrumentor, exporter = _instrument_with_provider()

    try:
        with trace("workflow"):
            with function_span(
                name="fetch_weather", input='{"city": "Paris"}'
            ):
                pass

        spans = exporter.get_finished_spans()
        tool_span = next(
            span for span in spans if span.kind is SpanKind.INTERNAL
        )

        server_spans = [span for span in spans if span.kind is SpanKind.SERVER]
        assert len(server_spans) == 1
        assert server_spans[0].name == "workflow"
        assert server_spans[0].attributes["gen_ai.provider.name"] == "openai"

        assert (
            tool_span.attributes[GenAI.GEN_AI_OPERATION_NAME] == "execute_tool"
        )
        assert tool_span.attributes[GenAI.GEN_AI_TOOL_NAME] == "fetch_weather"
        assert tool_span.attributes[GenAI.GEN_AI_TOOL_TYPE] == "function"
        assert tool_span.attributes["gen_ai.provider.name"] == "openai"
    finally:
        instrumentor.uninstrument()
        exporter.clear()


def test_agent_create_span_records_attributes():
    instrumentor, exporter = _instrument_with_provider()

    try:
        with trace("workflow"):
            with agent_span(
                operation="create",
                name="support_bot",
                description="Answers support questions",
                agent_id="agt_123",
                model="gpt-4o-mini",
            ):
                pass

        spans = exporter.get_finished_spans()
        create_span = next(
            span
            for span in spans
            if span.attributes[GenAI.GEN_AI_OPERATION_NAME]
            == GenAI.GenAiOperationNameValues.CREATE_AGENT.value
        )
        server_spans = [span for span in spans if span.kind is SpanKind.SERVER]
        assert len(server_spans) == 1
        assert server_spans[0].name == "workflow"
        assert server_spans[0].attributes["gen_ai.provider.name"] == "openai"
        assert [span for span in spans if span.kind is SpanKind.CLIENT]

        assert create_span.kind is SpanKind.CLIENT
        assert create_span.name == "create_agent support_bot"
        assert create_span.attributes["gen_ai.provider.name"] == "openai"
        assert create_span.attributes[GenAI.GEN_AI_AGENT_NAME] == "support_bot"
        assert (
            create_span.attributes[GenAI.GEN_AI_AGENT_DESCRIPTION]
            == "Answers support questions"
        )
        assert create_span.attributes[GenAI.GEN_AI_AGENT_ID] == "agt_123"
        assert (
            create_span.attributes[GenAI.GEN_AI_REQUEST_MODEL] == "gpt-4o-mini"
        )
    finally:
        instrumentor.uninstrument()
        exporter.clear()


def test_agent_name_override_applied_to_agent_spans():
    instrumentor, exporter = _instrument_with_provider(
        agent_name="Travel Concierge"
    )

    try:
        with trace("workflow"):
            with agent_span(operation="invoke", name="support_bot"):
                pass

        spans = exporter.get_finished_spans()
        agent_span_record = next(
            span
            for span in spans
            if span.attributes[GenAI.GEN_AI_OPERATION_NAME]
            == GenAI.GenAiOperationNameValues.INVOKE_AGENT.value
        )
        server_spans = [span for span in spans if span.kind is SpanKind.SERVER]
        assert len(server_spans) == 1
        assert server_spans[0].name == "workflow"
        assert server_spans[0].attributes["gen_ai.provider.name"] == "openai"
        assert [span for span in spans if span.kind is SpanKind.CLIENT]

        assert agent_span_record.kind is SpanKind.CLIENT
        assert agent_span_record.name == "invoke_agent Travel Concierge"
        assert (
            agent_span_record.attributes[GenAI.GEN_AI_AGENT_NAME]
            == "Travel Concierge"
        )
    finally:
        instrumentor.uninstrument()
        exporter.clear()


def test_response_span_records_response_attributes():
    instrumentor, exporter = _instrument_with_provider()

    class _Usage:
        def __init__(self, input_tokens: int, output_tokens: int) -> None:
            self.input_tokens = input_tokens
            self.output_tokens = output_tokens

    class _Response:
        def __init__(self) -> None:
            self.id = "resp-123"
            self.model = "gpt-4o-mini"
            self.usage = _Usage(42, 9)
            self.output = [{"finish_reason": "stop"}]

    try:
        with trace("workflow"):
            with response_span(response=_Response()):
                pass

        spans = exporter.get_finished_spans()
        response = next(
            span
            for span in spans
            if span.attributes[GenAI.GEN_AI_OPERATION_NAME]
            == GenAI.GenAiOperationNameValues.CHAT.value
        )

        assert response.kind is SpanKind.CLIENT
        assert response.name == "chat gpt-4o-mini"
        assert response.attributes["gen_ai.provider.name"] == "openai"
        assert response.attributes[GenAI.GEN_AI_RESPONSE_ID] == "resp-123"
        assert (
            response.attributes[GenAI.GEN_AI_RESPONSE_MODEL] == "gpt-4o-mini"
        )
        assert response.attributes[GenAI.GEN_AI_USAGE_INPUT_TOKENS] == 42
        assert response.attributes[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] == 9
        assert response.attributes[GenAI.GEN_AI_RESPONSE_FINISH_REASONS] == (
            "stop",
        )
        server_spans = [span for span in spans if span.kind is SpanKind.SERVER]
        assert len(server_spans) == 1
        assert server_spans[0].name == "workflow"
        assert server_spans[0].attributes["gen_ai.provider.name"] == "openai"
    finally:
        instrumentor.uninstrument()
        exporter.clear()
