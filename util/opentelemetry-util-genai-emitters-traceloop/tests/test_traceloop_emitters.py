from __future__ import annotations

import pytest

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.util.genai.emitters.spec import EmitterFactoryContext
from opentelemetry.util.genai.emitters.traceloop import (
    TraceloopCompatEmitter,
    traceloop_emitters,
)
from opentelemetry.util.genai.types import (
    ContentCapturingMode,
    Error,
    InputMessage,
    LLMInvocation,
    OutputMessage,
    Text,
)


@pytest.fixture(scope="module", autouse=True)
def _setup_tracer_provider():
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    yield
    exporter.clear()


def _build_context(
    capture_span: bool = False, capture_events: bool = True
) -> EmitterFactoryContext:
    return EmitterFactoryContext(
        tracer=trace.get_tracer(__name__),
        meter=None,
        event_logger=None,
        content_logger=None,
        evaluation_histogram=None,
        capture_span_content=capture_span,
        capture_event_content=capture_events,
    )


def test_traceloop_emitters_spec_factory():
    specs = traceloop_emitters()
    assert len(specs) == 1
    spec = specs[0]
    assert spec.category == "span"
    emitter = spec.factory(_build_context())
    assert isinstance(emitter, TraceloopCompatEmitter)


def test_traceloop_emitter_captures_content():
    tracer = trace.get_tracer(__name__)
    emitter = TraceloopCompatEmitter(tracer=tracer, capture_content=True)
    emitter.set_content_mode(ContentCapturingMode.SPAN_ONLY)
    invocation = LLMInvocation(request_model="gpt-4o")
    invocation.operation = "chat"
    invocation.input_messages = [
        InputMessage(role="user", parts=[Text(content="hi")])
    ]
    invocation.output_messages = [
        OutputMessage(
            role="assistant",
            parts=[Text(content="hello")],
            finish_reason="stop",
        )
    ]
    invocation.input_tokens = 3
    invocation.output_tokens = 7

    emitter.on_start(invocation)
    emitter.on_end(invocation)

    span = getattr(invocation, "traceloop_span", None)
    assert span is not None
    attrs = span.attributes or {}
    assert attrs.get("traceloop.entity.input")
    assert attrs.get("traceloop.entity.output")
    assert attrs.get("gen_ai.prompt.0.content") == "hi"
    assert attrs.get("gen_ai.completion.0.content") == "hello"
    assert attrs.get("llm.usage.total_tokens") == 10
    assert attrs.get("gen_ai.usage.prompt_tokens") == 3
    assert attrs.get("gen_ai.usage.completion_tokens") == 7


def test_traceloop_emitter_handles_error_status():
    tracer = trace.get_tracer(__name__)
    emitter = TraceloopCompatEmitter(tracer=tracer, capture_content=False)
    invocation = LLMInvocation(request_model="gpt-4o")
    invocation.operation = "chat"

    emitter.on_start(invocation)
    emitter.on_error(
        Error(message="boom", type=RuntimeError),
        invocation,
    )

    span = getattr(invocation, "traceloop_span", None)
    assert span is not None
    assert span.status.is_ok is False


def test_traceloop_emitter_whitelists_attributes():
    tracer = trace.get_tracer(__name__)
    emitter = TraceloopCompatEmitter(tracer=tracer, capture_content=False)
    invocation = LLMInvocation(request_model="gpt-4o")
    invocation.operation = "chat"
    invocation.attributes.update(
        {
            "callback.name": "ChatOpenAI",
            "custom": "value",
            "_ls_metadata": {
                "ls_provider": "openai",
                "ls_model_type": "chat",
            },
        }
    )
    invocation.input_tokens = 4
    invocation.output_tokens = 6

    emitter.on_start(invocation)
    emitter.on_end(invocation)

    span = getattr(invocation, "traceloop_span", None)
    assert span is not None
    attrs = span.attributes or {}
    assert (
        attrs.get("traceloop.association.properties.ls_provider") == "openai"
    )
    assert (
        attrs.get("traceloop.association.properties.ls_model_type") == "chat"
    )
    assert "custom" not in attrs
    assert "ls_provider" not in attrs
    assert attrs.get("traceloop.callback.name") == "ChatOpenAI"
    assert attrs.get("llm.usage.total_tokens") == 10
