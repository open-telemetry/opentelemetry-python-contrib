import pytest

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.util.genai.emitters.composite import CompositeGenerator
from opentelemetry.util.genai.emitters.content_events import (
    ContentEventsEmitter,
)
from opentelemetry.util.genai.emitters.span import SpanEmitter
from opentelemetry.util.genai.types import (
    InputMessage,
    LLMInvocation,
    OutputMessage,
    Text,
)


class DummyLogger:
    def __init__(self):
        self.emitted = []

    def emit(self, record):
        self.emitted.append(record)


def _build_composite(logger: DummyLogger, capture_content: bool):
    span = SpanEmitter(
        tracer=None, capture_content=False
    )  # span kept lean for event mode
    content = ContentEventsEmitter(
        logger=logger, capture_content=capture_content
    )
    return CompositeGenerator([span, content])


def test_events_without_content_capture(sample_invocation):
    logger = DummyLogger()
    gen = _build_composite(logger, capture_content=False)
    # Start and finish to emit events
    gen.start(sample_invocation)
    gen.finish(sample_invocation)

    # No events should be emitted when capture_content=False
    assert len(logger.emitted) == 0


def test_events_with_content_capture(sample_invocation, monkeypatch):
    logger = DummyLogger()
    gen = _build_composite(logger, capture_content=True)
    gen.start(sample_invocation)
    gen.finish(sample_invocation)

    # Single event should include both input and output payloads
    assert len(logger.emitted) == 1

    event = logger.emitted[0]
    body = event.body or {}
    inputs = body.get("gen_ai.input.messages") or []
    outputs = body.get("gen_ai.output.messages") or []

    assert inputs and inputs[0]["parts"][0]["content"] == "hello user"
    assert outputs and outputs[0]["parts"][0]["content"] == "hello back"


@pytest.fixture
def sample_invocation():
    input_msg = InputMessage(role="user", parts=[Text(content="hello user")])
    output_msg = OutputMessage(
        role="assistant",
        parts=[Text(content="hello back")],
        finish_reason="stop",
    )
    inv = LLMInvocation(request_model="test-model")
    inv.input_messages = [input_msg]
    inv.output_messages = [output_msg]
    return inv


"""
Removed tests that depended on environment variable gating. Emission now controlled solely by capture_content flag.
"""


def test_span_emitter_filters_non_gen_ai_attributes():
    provider = TracerProvider()
    emitter = SpanEmitter(
        tracer=provider.get_tracer(__name__), capture_content=False
    )
    invocation = LLMInvocation(request_model="example-model")
    invocation.provider = "example-provider"
    invocation.framework = "langchain"
    invocation.agent_id = "agent-123"
    invocation.attributes.update(
        {
            "request_top_p": 0.42,
            "custom": "value",
            "gen_ai.request.id": "req-789",
        }
    )

    emitter.start(invocation)
    invocation.response_model_name = "example-model-v2"
    invocation.response_id = "resp-456"
    invocation.input_tokens = 10
    invocation.output_tokens = 5
    invocation.attributes["gen_ai.response.finish_reasons"] = ["stop"]

    emitter.finish(invocation)

    span = invocation.span
    assert span is not None
    attrs = getattr(span, "attributes", None) or getattr(
        span, "_attributes", {}
    )

    assert attrs.get("gen_ai.agent.id") == "agent-123"
    assert attrs.get("gen_ai.request.id") == "req-789"
    assert "request_top_p" not in attrs
    assert "custom" not in attrs
    assert any(key.startswith("gen_ai.") for key in attrs)
