from __future__ import annotations

from opentelemetry import metrics
from opentelemetry.util.genai.emitters.spec import EmitterFactoryContext
from opentelemetry.util.genai.emitters.splunk import (
    SplunkConversationEventsEmitter,
    SplunkEvaluationResultsEmitter,
    splunk_emitters,
)
from opentelemetry.util.genai.types import (
    EvaluationResult,
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


class _FakeHistogram:
    def __init__(self, name: str) -> None:
        self.name = name
        self.records = []

    def record(self, value, attributes=None) -> None:
        self.records.append((value, attributes or {}))


class _FakeMeter:
    def __init__(self) -> None:
        self.histograms: dict[str, _FakeHistogram] = {}

    def create_histogram(self, name, unit=None, description=None):
        histogram = _FakeHistogram(name)
        self.histograms[name] = histogram
        return histogram


def _build_invocation() -> LLMInvocation:
    invocation = LLMInvocation(request_model="gpt-test")
    invocation.provider = "openai"
    invocation.input_messages = [
        InputMessage(role="user", parts=[Text(content="Hello")])
    ]
    invocation.output_messages = [
        OutputMessage(
            role="assistant",
            parts=[Text(content="Hi")],
            finish_reason="stop",
        )
    ]
    invocation.attributes["system_instruction"] = ["be nice"]
    return invocation


def test_splunk_emitters_specs() -> None:
    specs = splunk_emitters()
    categories = {spec.category for spec in specs}
    assert categories == {"content_events", "evaluation"}

    conversation_spec = next(
        spec for spec in specs if spec.category == "content_events"
    )
    evaluation_spec = next(
        spec for spec in specs if spec.category == "evaluation"
    )

    conversation_context = EmitterFactoryContext(
        tracer=None,
        meter=metrics.get_meter(__name__),
        event_logger=_CapturingLogger(),
        content_logger=None,
        evaluation_histogram=None,
        capture_span_content=False,
        capture_event_content=True,
    )
    conversation_emitter = conversation_spec.factory(conversation_context)
    assert isinstance(conversation_emitter, SplunkConversationEventsEmitter)

    evaluation_context = EmitterFactoryContext(
        tracer=None,
        meter=_FakeMeter(),
        event_logger=_CapturingLogger(),
        content_logger=None,
        evaluation_histogram=None,
        capture_span_content=False,
        capture_event_content=True,
    )
    evaluation_emitter = evaluation_spec.factory(evaluation_context)
    assert isinstance(evaluation_emitter, SplunkEvaluationResultsEmitter)


def test_conversation_event_emission() -> None:
    logger = _CapturingLogger()
    specs = splunk_emitters()
    conversation_spec = next(
        spec for spec in specs if spec.category == "content_events"
    )
    context = EmitterFactoryContext(
        tracer=None,
        meter=metrics.get_meter(__name__),
        event_logger=logger,
        content_logger=None,
        evaluation_histogram=None,
        capture_span_content=False,
        capture_event_content=True,
    )
    emitter = conversation_spec.factory(context)
    invocation = _build_invocation()

    emitter.on_end(invocation)

    assert logger.records
    record = logger.records[0]
    assert record.attributes["event.name"] == "gen_ai.splunk.conversation"
    assert record.body["conversation"]["inputs"][0]["role"] == "user"
    assert record.body["conversation"]["outputs"][0]["role"] == "assistant"


def test_evaluation_results_aggregation_and_metrics() -> None:
    logger = _CapturingLogger()
    meter = _FakeMeter()
    specs = splunk_emitters()
    evaluation_spec = next(
        spec for spec in specs if spec.category == "evaluation"
    )
    context = EmitterFactoryContext(
        tracer=None,
        meter=meter,
        event_logger=logger,
        content_logger=None,
        evaluation_histogram=None,
        capture_span_content=False,
        capture_event_content=True,
    )
    emitter = evaluation_spec.factory(context)
    invocation = _build_invocation()

    results = [
        EvaluationResult(
            metric_name="accuracy",
            score=3.0,
            label="medium",
            explanation="Normalized via range",
            attributes={"range": [0, 4], "judge_model": "llama3"},
        ),
        EvaluationResult(
            metric_name="toxicity/v1",
            score=0.2,
            label="low",
        ),
        EvaluationResult(
            metric_name="readability",
            score=5.0,
            label="high",
        ),
    ]

    emitter.on_evaluation_results(results, invocation)

    assert "gen_ai.evaluation.result.accuracy" in meter.histograms
    assert (
        meter.histograms["gen_ai.evaluation.result.accuracy"].records[0][0]
        == 0.75
    )
    assert "gen_ai.evaluation.result.toxicity_v1" in meter.histograms
    assert (
        meter.histograms["gen_ai.evaluation.result.toxicity_v1"].records[0][0]
        == 0.2
    )
    assert "gen_ai.evaluation.result.readability" not in meter.histograms

    emitter.on_end(invocation)

    assert len(logger.records) == 1
    record = logger.records[0]
    assert record.event_name == "gen_ai.splunk.evaluations"
    evaluations = record.body["evaluations"]
    assert len(evaluations) == 3

    accuracy_entry = next(e for e in evaluations if e["name"] == "accuracy")
    assert accuracy_entry["normalized_score"] == 0.75
    assert accuracy_entry["range"] == "[0.0,4.0]"
    assert accuracy_entry["attributes"]["judge_model"] == "llama3"

    toxicity_entry = next(e for e in evaluations if e["name"] == "toxicity/v1")
    assert toxicity_entry["normalized_score"] == 0.2
    assert toxicity_entry["range"] == "[0,1]"

    readability_entry = next(
        e for e in evaluations if e["name"] == "readability"
    )
    assert "normalized_score" not in readability_entry

    conversation = record.body["conversation"]
    assert conversation["inputs"][0]["parts"][0]["content"] == "Hello"
    assert conversation["system_instructions"] == ["be nice"]

    assert record.attributes["event.name"] == "gen_ai.splunk.evaluations"
    assert record.attributes["gen_ai.request.model"] == "gpt-test"
    assert record.attributes["gen_ai.provider.name"] == "openai"
