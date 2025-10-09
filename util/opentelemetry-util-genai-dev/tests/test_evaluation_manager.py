from __future__ import annotations

from opentelemetry.util.genai.evaluators.manager import Manager
from opentelemetry.util.genai.types import EvaluationResult, LLMInvocation


class _StubHandler:
    def __init__(self) -> None:
        self.calls: list[tuple[LLMInvocation, list[EvaluationResult]]] = []

    def evaluation_results(
        self, invocation: LLMInvocation, results: list[EvaluationResult]
    ) -> None:
        self.calls.append((invocation, list(results)))


def _make_manager(
    monkeypatch, aggregate: bool
) -> tuple[Manager, _StubHandler]:
    monkeypatch.setenv("OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS", "none")
    if aggregate:
        monkeypatch.setenv(
            "OTEL_INSTRUMENTATION_GENAI_EVALS_RESULTS_AGGREGATION", "true"
        )
    else:
        monkeypatch.delenv(
            "OTEL_INSTRUMENTATION_GENAI_EVALS_RESULTS_AGGREGATION",
            raising=False,
        )
    handler = _StubHandler()
    manager = Manager(handler)
    manager._evaluators = {"LLMInvocation": []}
    manager._aggregate_results = aggregate
    return manager, handler


def test_manager_emits_single_batch_when_aggregation_enabled(monkeypatch):
    manager, handler = _make_manager(monkeypatch, aggregate=True)
    invocation = LLMInvocation(request_model="agg-model")
    buckets = [
        [EvaluationResult(metric_name="bias", score=0.1)],
        [EvaluationResult(metric_name="toxicity", score=0.2)],
    ]

    flattened = manager._emit_results(invocation, buckets)

    assert len(handler.calls) == 1
    emitted = handler.calls[0][1]
    assert [res.metric_name for res in emitted] == ["bias", "toxicity"]
    assert flattened == emitted


def test_manager_emits_per_bucket_when_aggregation_disabled(monkeypatch):
    manager, handler = _make_manager(monkeypatch, aggregate=False)
    invocation = LLMInvocation(request_model="no-agg-model")
    buckets = [
        [EvaluationResult(metric_name="bias", score=0.1)],
        [EvaluationResult(metric_name="toxicity", score=0.2)],
    ]

    flattened = manager._emit_results(invocation, buckets)

    calls = handler.calls
    assert len(calls) == 2
    assert [res.metric_name for res in calls[0][1]] == ["bias"]
    assert [res.metric_name for res in calls[1][1]] == ["toxicity"]
    assert flattened == [item for bucket in buckets for item in bucket]
