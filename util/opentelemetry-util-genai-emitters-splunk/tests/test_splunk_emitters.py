from __future__ import annotations

from types import SimpleNamespace

from opentelemetry import metrics
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


def test_splunk_emitters_bundle_replaces_defaults() -> None:
    bundle = splunk_emitters(
        tracer=None,
        meter=metrics.get_meter(__name__),
        event_logger=_CapturingLogger(),
        settings=SimpleNamespace(
            capture_content_span=False,
            capture_content_events=True,
        ),
    )
    assert bundle.replace_default_emitters is True
    assert len(bundle.emitters) == 3


def test_conversation_event_emission() -> None:
    logger = _CapturingLogger()
    emitter = SplunkConversationEventsEmitter(logger, capture_content=True)
    invocation = LLMInvocation(request_model="gpt-test")
    invocation.input_messages = [
        InputMessage(role="user", parts=[Text(content="Hello")])
    ]
    invocation.output_messages = [
        OutputMessage(
            role="assistant", parts=[Text(content="Hi")], finish_reason="stop"
        )
    ]

    emitter.finish(invocation)

    assert logger.records
    record = logger.records[0]
    assert record.attributes["event.name"] == "gen_ai.splunk.conversation"
    assert record.body["conversation"]["inputs"][0]["role"] == "user"
    assert record.body["conversation"]["outputs"][0]["role"] == "assistant"
