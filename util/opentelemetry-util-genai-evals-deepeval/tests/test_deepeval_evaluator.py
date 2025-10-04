import importlib
import sys
from unittest.mock import patch

import pytest
from deepeval.evaluate.types import EvaluationResult as DeeEvaluationResult
from deepeval.evaluate.types import MetricData, TestResult

from opentelemetry.util.evaluator import deepeval as plugin
from opentelemetry.util.genai.evaluators.registry import (
    clear_registry,
    get_evaluator,
    list_evaluators,
)
from opentelemetry.util.genai.types import (
    InputMessage,
    LLMInvocation,
    OutputMessage,
    Text,
)


@pytest.fixture(autouse=True)
def _reset_registry():
    clear_registry()
    importlib.reload(plugin)
    plugin.register()
    yield
    clear_registry()


def _build_invocation() -> LLMInvocation:
    invocation = LLMInvocation(request_model="test-model")
    invocation.input_messages.append(
        InputMessage(role="user", parts=[Text(content="hello")])
    )
    invocation.output_messages.append(
        OutputMessage(
            role="assistant",
            parts=[Text(content="hi there")],
            finish_reason="stop",
        )
    )
    return invocation


def test_registration_adds_deepeval() -> None:
    names = list_evaluators()
    assert "deepeval" in names


def test_default_metrics_covered() -> None:
    evaluator = get_evaluator("deepeval")
    assert set(m.lower() for m in evaluator.metrics) == {
        "bias",
        "toxicity",
        "answer_relevancy",
        "faithfulness",
    }


def test_evaluator_converts_results(monkeypatch):
    invocation = _build_invocation()
    evaluator = get_evaluator(
        "deepeval",
        ("bias",),
        invocation_type="LLMInvocation",
    )

    fake_result = DeeEvaluationResult(
        test_results=[
            TestResult(
                name="case",
                success=True,
                metrics_data=[
                    MetricData(
                        name="bias",
                        threshold=0.7,
                        success=True,
                        score=0.8,
                        reason="looks good",
                        evaluation_model="gpt-4o-mini",
                        evaluation_cost=0.01,
                    )
                ],
                conversational=False,
            )
        ],
        confident_link=None,
    )

    monkeypatch.setattr(
        plugin.DeepevalEvaluator,
        "_instantiate_metrics",
        lambda self, specs, test_case: ([object()], []),
    )
    monkeypatch.setattr(
        plugin.DeepevalEvaluator,
        "_run_deepeval",
        lambda self, case, metrics: fake_result,
    )

    results = evaluator.evaluate(invocation)
    assert len(results) == 1
    result = results[0]
    assert result.metric_name == "bias"
    assert result.score == 0.8
    assert result.label == "pass"
    assert result.explanation == "looks good"
    assert result.attributes["deepeval.threshold"] == 0.7
    assert result.attributes["deepeval.success"] is True


def test_metric_options_coercion(monkeypatch):
    invocation = _build_invocation()
    evaluator = plugin.DeepevalEvaluator(
        ("bias",),
        invocation_type="LLMInvocation",
        options={"bias": {"threshold": "0.9", "strict_mode": "true"}},
    )

    captured = {}

    def fake_instantiate(self, specs, test_case):
        captured.update(specs[0].options)
        return [object()], []

    fake_result = DeeEvaluationResult(
        test_results=[
            TestResult(
                name="case",
                success=False,
                metrics_data=[
                    MetricData(
                        name="bias",
                        threshold=0.9,
                        success=False,
                        score=0.1,
                        reason="too biased",
                    )
                ],
                conversational=False,
            )
        ],
        confident_link=None,
    )

    monkeypatch.setattr(
        plugin.DeepevalEvaluator,
        "_instantiate_metrics",
        fake_instantiate,
    )
    monkeypatch.setattr(
        plugin.DeepevalEvaluator,
        "_run_deepeval",
        lambda self, case, metrics: fake_result,
    )

    results = evaluator.evaluate(invocation)
    assert captured["threshold"] == 0.9
    assert captured["strict_mode"] is True
    assert captured.get("model", evaluator._default_model()) == "gpt-4o-mini"
    assert results[0].label == "fail"


def test_evaluator_handles_instantiation_error(monkeypatch):
    invocation = _build_invocation()
    evaluator = plugin.DeepevalEvaluator(
        ("bias",), invocation_type="LLMInvocation"
    )

    def boom(self, specs, test_case):
        raise RuntimeError("boom")

    monkeypatch.setattr(plugin.DeepevalEvaluator, "_instantiate_metrics", boom)

    results = evaluator.evaluate(invocation)
    assert len(results) == 1
    assert results[0].error is not None
    assert "boom" in results[0].error.message


def test_evaluator_missing_output(monkeypatch):
    invocation = LLMInvocation(request_model="abc")
    evaluator = plugin.DeepevalEvaluator(
        ("bias",), invocation_type="LLMInvocation"
    )
    results = evaluator.evaluate(invocation)
    assert len(results) == 1
    assert results[0].error is not None


def test_dependency_missing(monkeypatch):
    invocation = _build_invocation()
    evaluator = plugin.DeepevalEvaluator(
        ("bias",), invocation_type="LLMInvocation"
    )
    with patch.dict(sys.modules, {"deepeval": None}):
        results = evaluator.evaluate(invocation)
    assert len(results) == 1
    assert results[0].error is not None


def test_faithfulness_skipped_without_retrieval_context():
    invocation = _build_invocation()
    evaluator = plugin.DeepevalEvaluator(
        ("faithfulness",),
        invocation_type="LLMInvocation",
    )
    results = evaluator.evaluate(invocation)
    assert len(results) == 1
    result = results[0]
    assert result.label == "skipped"
    assert result.error is not None
    assert "retrieval_context" in (result.explanation or "")
    assert result.attributes.get("deepeval.skipped") is True


def test_retrieval_context_extracted_from_attributes(monkeypatch):
    invocation = _build_invocation()
    invocation.attributes["retrieval_context"] = [
        {"content": "doc1"},
        "doc2",
    ]
    evaluator = plugin.DeepevalEvaluator(
        ("faithfulness",),
        invocation_type="LLMInvocation",
    )

    captured = {}

    def fake_instantiate(self, specs, test_case):
        captured["retrieval_context"] = getattr(
            test_case, "retrieval_context", None
        )
        return ([object()], [])

    fake_result = DeeEvaluationResult(
        test_results=[
            TestResult(
                name="case",
                success=True,
                metrics_data=[
                    MetricData(
                        name="faithfulness",
                        threshold=0.5,
                        success=True,
                        score=0.95,
                        reason="faithful",
                    )
                ],
                conversational=False,
            )
        ],
        confident_link=None,
    )

    monkeypatch.setattr(
        plugin.DeepevalEvaluator, "_instantiate_metrics", fake_instantiate
    )
    monkeypatch.setattr(
        plugin.DeepevalEvaluator,
        "_run_deepeval",
        lambda self, case, metrics: fake_result,
    )

    results = evaluator.evaluate(invocation)
    assert captured["retrieval_context"] == ["doc1", "doc2"]
    assert results[0].metric_name == "faithfulness"
