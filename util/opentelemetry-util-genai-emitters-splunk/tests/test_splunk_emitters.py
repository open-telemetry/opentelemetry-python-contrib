from __future__ import annotations

from opentelemetry import metrics
from opentelemetry.util.genai.emitters.spec import EmitterFactoryContext
from opentelemetry.util.genai.emitters.splunk import (
    SplunkConversationEventsEmitter,
    splunk_emitters,
)
from opentelemetry.util.genai.types import (
    InputMessage,
    LLMInvocation,
    OutputMessage,
    Text,
)


class _CapturingLogger:
    def __init__(self) -> None:
        self.records = []

    def emit(self, record) -> None:
        self.records.append(record)


def test_splunk_emitters_specs() -> None:
    specs = splunk_emitters()
    assert len(specs) == 1
    spec = specs[0]
    assert spec.category == "content_events"
    assert spec.mode == "replace-category"
    context = EmitterFactoryContext(
        tracer=None,
        meter=metrics.get_meter(__name__),
        event_logger=_CapturingLogger(),
        content_logger=None,
        evaluation_histogram=None,
        capture_span_content=False,
        capture_event_content=True,
    )
    emitter = spec.factory(context)
    assert isinstance(emitter, SplunkConversationEventsEmitter)


def test_conversation_event_emission() -> None:
    logger = _CapturingLogger()
    spec = splunk_emitters()[0]
    context = EmitterFactoryContext(
        tracer=None,
        meter=metrics.get_meter(__name__),
        event_logger=logger,
        content_logger=None,
        evaluation_histogram=None,
        capture_span_content=False,
        capture_event_content=True,
    )
    emitter = spec.factory(context)
    invocation = LLMInvocation(request_model="gpt-test")
    invocation.input_messages = [
        InputMessage(role="user", parts=[Text(content="Hello")])
    ]
    invocation.output_messages = [
        OutputMessage(
            role="assistant", parts=[Text(content="Hi")], finish_reason="stop"
        )
    ]

    emitter.on_end(invocation)

    assert logger.records
    record = logger.records[0]
    assert record.attributes["event.name"] == "gen_ai.splunk.conversation"
    assert record.body["conversation"]["inputs"][0]["role"] == "user"
    assert record.body["conversation"]["outputs"][0]["role"] == "assistant"
