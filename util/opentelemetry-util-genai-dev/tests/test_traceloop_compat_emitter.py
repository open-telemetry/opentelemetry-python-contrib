import os

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.semconv._incubating.attributes.gen_ai_attributes import (
    GEN_AI_RESPONSE_ID,
)
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT_MODE,
    OTEL_INSTRUMENTATION_GENAI_EMITTERS,
)
from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import (
    InputMessage,
    LLMInvocation,
    OutputMessage,
    Text,
)


def _reset_handler_singleton():
    if hasattr(get_telemetry_handler, "_default_handler"):
        delattr(get_telemetry_handler, "_default_handler")


def _build_invocation():
    inv = LLMInvocation(request_model="m-test")
    inv.input_messages = [
        InputMessage(role="user", parts=[Text(content="hello world")])
    ]
    inv.output_messages = [
        OutputMessage(
            role="assistant",
            parts=[Text(content="hi back")],
            finish_reason="stop",
        )
    ]
    inv.response_id = "resp-123"
    inv.attributes["traceloop.callback_name"] = "MyChain"
    return inv


def test_traceloop_compat_only():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    # Environment: only traceloop compat + capture content on span
    os.environ[OTEL_INSTRUMENTATION_GENAI_EMITTERS] = "traceloop_compat"
    os.environ[OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT] = "true"
    os.environ[OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT_MODE] = (
        "SPAN_ONLY"
    )

    _reset_handler_singleton()
    handler = get_telemetry_handler(tracer_provider=provider)

    inv = _build_invocation()
    handler.start_llm(inv)
    handler.stop_llm(inv)

    spans = exporter.get_finished_spans()
    # Expect exactly one span produced (compat only)
    assert len(spans) == 1, f"Expected 1 span, got {len(spans)}"
    span = spans[0]
    assert span.name == "MyChain.chat"
    assert span.attributes.get("traceloop.span.kind") == "llm"
    # Content captured
    assert "traceloop.entity.input" in span.attributes
    assert "traceloop.entity.output" in span.attributes
    assert span.attributes.get(GEN_AI_RESPONSE_ID) == "resp-123"


def test_traceloop_compat_combined_with_span():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    os.environ[OTEL_INSTRUMENTATION_GENAI_EMITTERS] = "span,traceloop_compat"
    os.environ[OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT] = "true"
    os.environ[OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT_MODE] = (
        "SPAN_ONLY"
    )

    _reset_handler_singleton()
    handler = get_telemetry_handler(tracer_provider=provider)

    inv = _build_invocation()
    handler.start_llm(inv)
    handler.stop_llm(inv)

    spans = exporter.get_finished_spans()
    # Expect two spans: semconv span + traceloop compat span
    assert len(spans) == 2, f"Expected 2 spans, got {len(spans)}"
    names = {s.name for s in spans}
    assert any(n == "MyChain.chat" for n in names), names
    assert any(n.startswith("chat ") for n in names), names
    compat = next(s for s in spans if s.name == "MyChain.chat")
    semconv = next(s for s in spans if s.name.startswith("chat "))
    assert compat.attributes.get("traceloop.span.kind") == "llm"
    # Ensure traceloop.* attributes are not present on semconv span
    assert all(
        not k.startswith("traceloop.") for k in semconv.attributes.keys()
    ), semconv.attributes


def teardown_module():  # cleanup env
    for k in (
        OTEL_INSTRUMENTATION_GENAI_EMITTERS,
        OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
        OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT_MODE,
    ):
        os.environ.pop(k, None)
    _reset_handler_singleton()
