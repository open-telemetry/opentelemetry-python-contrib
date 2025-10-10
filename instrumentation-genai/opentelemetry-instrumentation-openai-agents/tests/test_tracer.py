from __future__ import annotations

import json
import sys
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent
stub_path = TESTS_ROOT / "stubs"
if str(stub_path) not in sys.path:
    sys.path.insert(0, str(stub_path))

sys.modules.pop("agents", None)
sys.modules.pop("agents.tracing", None)

from agents.tracing import (  # noqa: E402
    function_span,
    generation_span,
    set_trace_processors,
    trace,
)

from opentelemetry.instrumentation.openai_agents import (  # noqa: E402
    OpenAIAgentsInstrumentor,
)
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402

try:  # pragma: no cover - compatibility for older SDK versions
    from opentelemetry.sdk.trace.export import (  # type: ignore[attr-defined]  # noqa: E402
        InMemorySpanExporter,
    )
except ImportError:  # pragma: no cover - fallback for newer SDK layout
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

GEN_AI_INPUT_MESSAGES = getattr(
    GenAI, "GEN_AI_INPUT_MESSAGES", "gen_ai.input.messages"
)
GEN_AI_OUTPUT_MESSAGES = getattr(
    GenAI, "GEN_AI_OUTPUT_MESSAGES", "gen_ai.output.messages"
)
GEN_AI_TOOL_CALL_ARGUMENTS = getattr(
    GenAI, "GEN_AI_TOOL_CALL_ARGUMENTS", "gen_ai.tool.call.arguments"
)
GEN_AI_TOOL_CALL_RESULT = getattr(
    GenAI, "GEN_AI_TOOL_CALL_RESULT", "gen_ai.tool.call.result"
)


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
        client_span = next(
            span for span in spans if span.kind is SpanKind.CLIENT
        )

        assert client_span.attributes[GenAI.GEN_AI_SYSTEM] == "openai"
        assert client_span.attributes[GenAI.GEN_AI_OPERATION_NAME] == "chat"
        assert (
            client_span.attributes[GenAI.GEN_AI_REQUEST_MODEL] == "gpt-4o-mini"
        )
        assert client_span.attributes[GenAI.GEN_AI_USAGE_INPUT_TOKENS] == 12
        assert client_span.attributes[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] == 3
        assert (
            client_span.attributes[ServerAttributes.SERVER_ADDRESS]
            == "api.openai.com"
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

        assert (
            tool_span.attributes[GenAI.GEN_AI_OPERATION_NAME] == "execute_tool"
        )
        assert tool_span.attributes[GenAI.GEN_AI_TOOL_NAME] == "fetch_weather"
        assert tool_span.attributes[GenAI.GEN_AI_TOOL_TYPE] == "function"
        assert tool_span.attributes[GenAI.GEN_AI_SYSTEM] == "openai"
    finally:
        instrumentor.uninstrument()
        exporter.clear()


def test_generation_span_captures_messages_by_default():
    instrumentor, exporter = _instrument_with_provider()

    try:
        with trace("workflow"):
            with generation_span(
                input=[{"role": "user", "content": "hi"}],
                output=[{"role": "assistant", "content": "hello"}],
                model="gpt-4o-mini",
            ):
                pass

        spans = exporter.get_finished_spans()
        client_span = next(
            span for span in spans if span.kind is SpanKind.CLIENT
        )

        prompt = json.loads(client_span.attributes[GEN_AI_INPUT_MESSAGES])
        completion = json.loads(client_span.attributes[GEN_AI_OUTPUT_MESSAGES])

        assert prompt == [
            {
                "role": "user",
                "parts": [{"type": "text", "content": "hi"}],
            }
        ]
        assert completion == [
            {
                "role": "assistant",
                "parts": [{"type": "text", "content": "hello"}],
            }
        ]

        event_names = {event.name for event in client_span.events}
        assert "gen_ai.input" in event_names
        assert "gen_ai.output" in event_names

        input_event = next(
            event
            for event in client_span.events
            if event.name == "gen_ai.input"
        )
        output_event = next(
            event
            for event in client_span.events
            if event.name == "gen_ai.output"
        )

        assert (
            json.loads(input_event.attributes[GEN_AI_INPUT_MESSAGES]) == prompt
        )
        assert (
            json.loads(output_event.attributes[GEN_AI_OUTPUT_MESSAGES])
            == completion
        )
    finally:
        instrumentor.uninstrument()
        exporter.clear()


def test_capture_mode_can_be_disabled():
    instrumentor, exporter = _instrument_with_provider(
        capture_message_content="no_content"
    )

    try:
        with trace("workflow"):
            with generation_span(
                input=[{"role": "user", "content": "hi"}],
                output=[{"role": "assistant", "content": "hello"}],
                model="gpt-4o-mini",
            ):
                pass

        spans = exporter.get_finished_spans()
        client_span = next(
            span for span in spans if span.kind is SpanKind.CLIENT
        )

        assert GEN_AI_INPUT_MESSAGES not in client_span.attributes
        assert GEN_AI_OUTPUT_MESSAGES not in client_span.attributes
        for event in client_span.events:
            assert GEN_AI_INPUT_MESSAGES not in event.attributes
            assert GEN_AI_OUTPUT_MESSAGES not in event.attributes
    finally:
        instrumentor.uninstrument()
        exporter.clear()


def test_function_span_captures_tool_payload():
    instrumentor, exporter = _instrument_with_provider()

    try:
        with trace("workflow"):
            with function_span(
                name="fetch_weather",
                input={"city": "Paris"},
                output={"forecast": "sunny"},
            ):
                pass

        spans = exporter.get_finished_spans()
        tool_span = next(
            span for span in spans if span.kind is SpanKind.INTERNAL
        )

        arguments = json.loads(
            tool_span.attributes[GEN_AI_TOOL_CALL_ARGUMENTS]
        )
        result = json.loads(tool_span.attributes[GEN_AI_TOOL_CALL_RESULT])

        assert arguments == {"city": "Paris"}
        assert result == {"forecast": "sunny"}

        event_names = {event.name for event in tool_span.events}
        assert "gen_ai.tool.arguments" in event_names
        assert "gen_ai.tool.result" in event_names

        args_event = next(
            event
            for event in tool_span.events
            if event.name == "gen_ai.tool.arguments"
        )
        result_event = next(
            event
            for event in tool_span.events
            if event.name == "gen_ai.tool.result"
        )

        assert (
            json.loads(args_event.attributes[GEN_AI_TOOL_CALL_ARGUMENTS])
            == arguments
        )
        assert (
            json.loads(result_event.attributes[GEN_AI_TOOL_CALL_RESULT])
            == result
        )
    finally:
        instrumentor.uninstrument()
        exporter.clear()
