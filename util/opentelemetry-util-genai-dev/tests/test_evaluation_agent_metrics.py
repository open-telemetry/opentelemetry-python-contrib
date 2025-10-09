from __future__ import annotations

from typing import Any, Dict, List, Tuple

from opentelemetry.util.genai.emitters.evaluation import (
    EvaluationMetricsEmitter,
)
from opentelemetry.util.genai.types import AgentInvocation, EvaluationResult


class _RecordingHistogram:
    def __init__(self) -> None:
        self.records: List[Tuple[float, Dict[str, Any]]] = []

    def record(self, value: float, attributes=None):  # type: ignore[override]
        attrs: Dict[str, Any] = {}
        if isinstance(attributes, dict):
            from typing import cast

            attrs.update(cast(Dict[str, Any], attributes))
        self.records.append((value, attrs))


def test_agent_evaluation_metric_includes_agent_identity():
    hist = _RecordingHistogram()
    emitter = EvaluationMetricsEmitter(hist)
    agent = AgentInvocation(name="router", operation="invoke_agent")
    agent.agent_name = "router"  # identity fields reused for emission
    agent.agent_id = str(agent.run_id)
    agent.model = "gpt-agent"
    res = EvaluationResult(metric_name="bias", score=0.9, label="pass")

    emitter.on_evaluation_results([res], agent)

    assert hist.records, "Expected one histogram record"
    value, attrs = hist.records[0]
    assert value == 0.9
    # core evaluation attrs
    assert attrs["gen_ai.evaluation.name"] == "bias"
    # agent identity propagated
    assert attrs["gen_ai.agent.name"] == "router"
    assert attrs["gen_ai.agent.id"] == agent.agent_id
