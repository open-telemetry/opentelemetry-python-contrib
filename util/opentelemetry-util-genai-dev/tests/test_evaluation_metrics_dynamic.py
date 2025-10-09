from __future__ import annotations

from typing import Any, Dict, List

from opentelemetry.util.genai.emitters.evaluation import (
    EvaluationMetricsEmitter,
)
from opentelemetry.util.genai.types import EvaluationResult, LLMInvocation


class _RecordingHistogram:
    def __init__(self, name: str) -> None:
        self.name = name
        self.points: List[tuple[float, Dict[str, Any]]] = []

    def record(self, value: float, *, attributes: Dict[str, Any]):
        self.points.append((value, attributes))


class _HistogramFactory:
    def __init__(self) -> None:
        self.created: Dict[str, _RecordingHistogram] = {}

    def __call__(self, metric_name: str):
        # Canonical instruments now: gen_ai.evaluation.<metric>
        full = f"gen_ai.evaluation.{metric_name}"
        if full not in self.created:
            self.created[full] = _RecordingHistogram(full)
        return self.created[full]


def test_dynamic_metric_histograms_created_per_metric():
    factory = _HistogramFactory()
    emitter = EvaluationMetricsEmitter(factory)
    invocation = LLMInvocation(request_model="gpt-test")
    results = [
        EvaluationResult(metric_name="bias", score=0.5),
        EvaluationResult(metric_name="toxicity", score=0.1),
        EvaluationResult(metric_name="bias", score=0.75, label="medium"),
    ]

    emitter.on_evaluation_results(results, invocation)

    # Ensure two canonical histograms were created
    assert set(factory.created.keys()) == {
        "gen_ai.evaluation.bias",
        "gen_ai.evaluation.toxicity",
    }

    bias_hist = factory.created["gen_ai.evaluation.bias"]
    tox_hist = factory.created["gen_ai.evaluation.toxicity"]

    # Bias scores recorded twice
    bias_points = [p[0] for p in bias_hist.points]
    assert bias_points == [0.5, 0.75]

    # Toxicity once
    tox_points = [p[0] for p in tox_hist.points]
    assert tox_points == [0.1]

    # Attribute propagation
    for _, attrs in bias_hist.points + tox_hist.points:
        assert attrs["gen_ai.operation.name"] == "evaluation"
        assert attrs["gen_ai.evaluation.name"] in {"bias", "toxicity"}
    # label only present for second bias result
    labels = [
        attrs.get("gen_ai.evaluation.score.label")
        for _, attrs in bias_hist.points
    ]
    assert labels == [None, "medium"]
    # passed attribute only expected on labeled result (mapped from label 'medium' -> unknown so not set) => ensure first None, second absent or None unless mapping added
    # Units should be set for each point; reasoning only when explanation present (not in this test)
    for _, attrs in bias_hist.points + tox_hist.points:
        assert attrs.get("gen_ai.evaluation.score.units") == "score"
