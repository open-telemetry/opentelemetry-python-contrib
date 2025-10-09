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
        full = f"gen_ai.evaluation.score.{metric_name}"
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

    # Ensure two histograms were created
    assert set(factory.created.keys()) == {
        "gen_ai.evaluation.score.bias",
        "gen_ai.evaluation.score.toxicity",
    }

    bias_hist = factory.created["gen_ai.evaluation.score.bias"]
    tox_hist = factory.created["gen_ai.evaluation.score.toxicity"]

    # Bias scores recorded twice
    bias_points = [p[0] for p in bias_hist.points]
    assert bias_points == [0.5, 0.75]

    # Toxicity once
    tox_points = [p[0] for p in tox_hist.points]
    assert tox_points == [0.1]

    # Attribute propagation
    for _, attrs in bias_hist.points + tox_hist.points:
        assert attrs["gen_ai.operation.name"] == "evaluation"
        assert "gen_ai.evaluation.name" in attrs
    # label only present for second bias result
    labels = [
        attrs.get("gen_ai.evaluation.score.label")
        for _, attrs in bias_hist.points
    ]
    assert labels == [None, "medium"]
