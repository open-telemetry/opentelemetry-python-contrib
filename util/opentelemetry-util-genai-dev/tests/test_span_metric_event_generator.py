import pytest

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.util.genai.emitters.composite import CompositeEmitter
from opentelemetry.util.genai.emitters.content_events import (
    ContentEventsEmitter,
)
from opentelemetry.util.genai.emitters.span import SpanEmitter
from opentelemetry.util.genai.types import (
    EvaluationResult,
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
    return CompositeEmitter(
        span_emitters=[span],
        metrics_emitters=[],
        content_event_emitters=[content],
        evaluation_emitters=[],
    )


def test_events_without_content_capture(sample_invocation):
    logger = DummyLogger()
    gen = _build_composite(logger, capture_content=False)
    # Start and finish to emit events
    gen.on_start(sample_invocation)
    gen.on_end(sample_invocation)

    # No events should be emitted when capture_content=False
    assert len(logger.emitted) == 0


def test_events_with_content_capture(sample_invocation, monkeypatch):
    logger = DummyLogger()
    gen = _build_composite(logger, capture_content=True)
    gen.on_start(sample_invocation)
    gen.on_end(sample_invocation)

    # Single event should include both input and output payloads
    assert len(logger.emitted) == 1

    event = logger.emitted[0]
    body = event.body or {}
    inputs = body.get("gen_ai.input.messages") or []
    outputs = body.get("gen_ai.output.messages") or []

    assert inputs and inputs[0]["parts"][0]["content"] == "hello user"
    assert outputs and outputs[0]["parts"][0]["content"] == "hello back"


class _RecordingEvaluationEmitter:
    role = "evaluation"

    def __init__(self) -> None:
        self.call_log = []

    def on_evaluation_results(self, results, obj=None):
        self.call_log.append(("results", list(results)))

    def on_end(self, obj):
        self.call_log.append(("end", obj))

    def on_error(self, error, obj):
        self.call_log.append(("error", error))


def test_evaluation_emitters_receive_lifecycle_callbacks():
    emitter = _RecordingEvaluationEmitter()
    composite = CompositeEmitter(
        span_emitters=[],
        metrics_emitters=[],
        content_event_emitters=[],
        evaluation_emitters=[emitter],
    )
    invocation = LLMInvocation(request_model="eval-model")
    result = EvaluationResult(metric_name="bias", score=0.1)

    composite.on_evaluation_results([result], invocation)
    composite.on_end(invocation)
    composite.on_error(RuntimeError("boom"), invocation)

    assert ("results", [result]) in emitter.call_log
    assert any(entry[0] == "end" for entry in emitter.call_log)
    assert any(entry[0] == "error" for entry in emitter.call_log)


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
            "ls_temperature": 0.55,
        }
    )

    emitter.on_start(invocation)
    invocation.response_model_name = "example-model-v2"
    invocation.response_id = "resp-456"
    invocation.input_tokens = 10
    invocation.output_tokens = 5
    invocation.attributes["gen_ai.response.finish_reasons"] = ["stop"]

    emitter.on_end(invocation)

    span = invocation.span
    assert span is not None
    attrs = getattr(span, "attributes", None) or getattr(
        span, "_attributes", {}
    )

    assert attrs.get("gen_ai.agent.id") == "agent-123"
    assert attrs.get("gen_ai.request.id") == "req-789"
    assert "request_top_p" not in attrs
    assert "custom" not in attrs
    assert "ls_temperature" not in attrs
    assert "traceloop.association.properties.ls_temperature" not in attrs
    assert all(not key.startswith("traceloop.") for key in attrs.keys())
    assert any(key.startswith("gen_ai.") for key in attrs)
