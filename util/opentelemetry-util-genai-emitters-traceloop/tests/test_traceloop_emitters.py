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

    emitter.on_start(invocation)
    emitter.on_end(invocation)

    span = getattr(invocation, "traceloop_span", None)
    assert span is not None
    attrs = span.attributes or {}
    assert attrs.get("traceloop.entity.input")
    assert attrs.get("traceloop.entity.output")


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
