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
    function_span,
    generation_span,
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


def _instrument_with_provider():
    set_trace_processors([])
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    instrumentor = OpenAIAgentsInstrumentor()
    instrumentor.instrument(tracer_provider=provider)

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

        assert client_span.attributes["gen_ai.provider.name"] == "openai"
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
        assert tool_span.attributes["gen_ai.provider.name"] == "openai"
    finally:
        instrumentor.uninstrument()
        exporter.clear()
