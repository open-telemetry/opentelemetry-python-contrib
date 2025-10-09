from __future__ import annotations

from typing import Any

from opentelemetry.util.genai.emitters.evaluation import (
    EvaluationEventsEmitter,
)
from opentelemetry.util.genai.types import (
    Error,
    EvaluationResult,
    LLMInvocation,
)


class _RecordingEventLogger:
    def __init__(self) -> None:
        self.records: list[Any] = []

    def emit(self, event: Any) -> None:
        self.records.append(event)


def _build_invocation() -> LLMInvocation:
    invocation = LLMInvocation(request_model="gpt-test")
    invocation.provider = "openai"
    invocation.response_id = "resp-123"
    return invocation


def test_spec_event_emission_uses_semconv_attributes() -> None:
    logger = _RecordingEventLogger()
    emitter = EvaluationEventsEmitter(logger)
    invocation = _build_invocation()
    result = EvaluationResult(
        metric_name="bias",
        score=0.75,
        label="medium",
        explanation="Detected mild bias",
        attributes={"judge_model": "gpt-4", 1: "int-key"},
        error=Error(message="timeout", type=TimeoutError),
    )

    emitter.on_evaluation_results([result], invocation)

    assert len(logger.records) == 1
    event = logger.records[0]
    assert event.name == "gen_ai.evaluation.result"
    attrs = event.attributes
    assert attrs["gen_ai.evaluation.name"] == "bias"
    assert attrs["gen_ai.evaluation.score.value"] == 0.75
    assert attrs["gen_ai.evaluation.explanation"] == "Detected mild bias"
    assert attrs["gen_ai.evaluation.attributes.judge_model"] == "gpt-4"
    assert attrs["gen_ai.evaluation.attributes.1"] == "int-key"
    assert attrs["gen_ai.evaluation.attributes.error.message"] == "timeout"
    assert "error.message" not in attrs
    assert event.body is None


def test_legacy_event_emission_when_flag_enabled() -> None:
    logger = _RecordingEventLogger()
    emitter = EvaluationEventsEmitter(logger, emit_legacy_event=True)
    invocation = _build_invocation()
    result = EvaluationResult(
        metric_name="toxicity",
        explanation="All clear",
        attributes={"detail": "sample"},
        error=Error(message="failure", type=RuntimeError),
    )

    emitter.on_evaluation_results([result], invocation)

    assert len(logger.records) == 2
    new_event, legacy_event = logger.records
    assert new_event.name == "gen_ai.evaluation.result"
    assert legacy_event.name == "gen_ai.evaluation"
    assert legacy_event.body == {
        "gen_ai.evaluation.explanation": "All clear",
        "gen_ai.evaluation.attributes": {"detail": "sample"},
    }
    assert legacy_event.attributes["error.message"] == "failure"
