import pytest

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

    # Two events: input and output
    assert len(logger.emitted) == 2

    # Input event should include original content and attribute gen_ai.input.messages
    input_event = logger.emitted[0]
    body = input_event.body
    assert body["parts"][0]["content"] == "hello user"
    assert "gen_ai.input.messages" in input_event.attributes

    # Output event should include content in message body
    output_event = logger.emitted[1]
    body_out = output_event.body
    msg = body_out.get("message", {})
    assert msg.get("content") == "hello back"


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
