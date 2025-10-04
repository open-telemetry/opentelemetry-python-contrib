import sys
import types

import pytest

from opentelemetry.util.evaluator.nltk import (
    NLTKSentimentEvaluator,
    registration,
)
from opentelemetry.util.genai.types import (
    LLMInvocation,
    OutputMessage,
    Text,
)


def _install_stub_analyzer(compound: float = 0.5):
    sentiment_module = types.ModuleType("nltk.sentiment")

    class _Analyzer:
        def polarity_scores(self, text):  # pragma: no cover - simple stub
            return {"compound": compound}

    sentiment_module.SentimentIntensityAnalyzer = _Analyzer
    nltk_module = types.ModuleType("nltk")
    nltk_module.sentiment = sentiment_module
    sys.modules["nltk"] = nltk_module
    sys.modules["nltk.sentiment"] = sentiment_module
    return lambda: (
        sys.modules.pop("nltk", None),
        sys.modules.pop("nltk.sentiment", None),
    )


def _build_invocation(text: str) -> LLMInvocation:
    invocation = LLMInvocation(request_model="demo-model")
    invocation.output_messages.append(
        OutputMessage(
            role="assistant",
            parts=[Text(content=text)],
            finish_reason="stop",
        )
    )
    return invocation


def test_registration_factory_emits_scores():
    cleanup = _install_stub_analyzer(compound=0.9)
    try:
        reg = registration()
        evaluator = reg.factory(
            metrics=None, invocation_type=None, options=None
        )
        results = evaluator.evaluate_llm(_build_invocation("Great work!"))
        assert results
        result = results[0]
        assert result.metric_name == "sentiment"
        assert pytest.approx(result.score or 0.0, rel=1e-6) == (0.9 + 1) / 2
        assert result.label == "positive"
    finally:
        cleanup()


def test_evaluator_reports_missing_dependency():
    sys.modules.pop("nltk", None)
    sys.modules.pop("nltk.sentiment", None)
    evaluator = NLTKSentimentEvaluator()
    results = evaluator.evaluate_llm(_build_invocation("Needs nltk"))
    assert results
    assert results[0].error is not None
    assert results[0].score is None
