import pytest

from opentelemetry.util.genai.generators.span_metric_event_generator import (
    _ENV_VAR,
    SpanMetricEventGenerator,
)
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


@pytest.fixture
def sample_invocation():
    # Create a simple invocation with one input and one output message
    input_msg = InputMessage(role="user", parts=[Text(content="hello user")])
    output_msg = OutputMessage(
        role="assistant",
        parts=[Text(content="hello back")],
        finish_reason="stop",
    )
    invocation = LLMInvocation(request_model="test-model")
    invocation.input_messages = [input_msg]
    invocation.output_messages = [output_msg]
    return invocation


def test_events_without_content_capture(sample_invocation, monkeypatch):
    # Enable events via env var
    monkeypatch.setenv(_ENV_VAR, "true")
    logger = DummyLogger()
    gen = SpanMetricEventGenerator(logger=logger, capture_content=False)
    # Start and finish to emit events
    gen.start(sample_invocation)
    gen.finish(sample_invocation)

    # Expect two events: one for input, one for output
    assert len(logger.emitted) == 2

    # Check input message event
    input_event = logger.emitted[0]
    # Body should have parts with empty content and no input.messages attribute
    body = input_event.body
    assert body["parts"][0]["content"] == ""
    assert "gen_ai.input.messages" not in input_event.attributes

    # Check output message event
    output_event = logger.emitted[1]
    body_out = output_event.body
    msg = body_out.get("message", {})
    # 'content' should not be present when capture_content=False
    assert "content" not in msg


def test_events_with_content_capture(sample_invocation, monkeypatch):
    # Enable events via env var
    monkeypatch.setenv(_ENV_VAR, "true")
    logger = DummyLogger()
    gen = SpanMetricEventGenerator(logger=logger, capture_content=True)
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


def test_no_events_without_env_var(sample_invocation, monkeypatch):
    # Ensure env var is not set
    monkeypatch.delenv(_ENV_VAR, raising=False)
    logger = DummyLogger()
    gen = SpanMetricEventGenerator(logger=logger, capture_content=True)
    gen.start(sample_invocation)
    gen.finish(sample_invocation)
    # No events should be emitted when env var is not set
    assert len(logger.emitted) == 0


def test_events_with_env_var_set(sample_invocation, monkeypatch):
    # Ensure env var is set to enable events
    monkeypatch.setenv(_ENV_VAR, "true")
    logger = DummyLogger()
    gen = SpanMetricEventGenerator(logger=logger, capture_content=False)
    gen.start(sample_invocation)
    gen.finish(sample_invocation)
    # Events should be emitted regardless of capture_content if env var enabled
    assert len(logger.emitted) == 2
