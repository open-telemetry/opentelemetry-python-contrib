# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Builtin evaluators.

Lightweight reference evaluators that demonstrate the interface.
Heavy / optional dependencies are imported lazily. If the dependency is not
available, the evaluator returns an EvaluationResult with an error field set.
"""

from __future__ import annotations

from typing import List

from opentelemetry.util.genai.evaluators.base import Evaluator
from opentelemetry.util.genai.evaluators.registry import register_evaluator
from opentelemetry.util.genai.types import (
    Error,
    EvaluationResult,
    LLMInvocation,
    Text,
)


def _extract_text(invocation: LLMInvocation) -> str:
    text_parts: List[str] = []
    for msg in invocation.output_messages:
        for part in msg.parts:
            if isinstance(part, Text):  # simple content aggregation
                text_parts.append(part.content)
    return "\n".join(text_parts).strip()


class LengthEvaluator(Evaluator):
    """Simple evaluator producing a score based on response length.

    Score: normalized length = len / (len + 50) in [0,1).
    Label tiers: short (<50 chars), medium (50-200), long (>200).
    """

    def evaluate_invocation(
        self, invocation: LLMInvocation
    ) -> EvaluationResult:  # renamed method
        content = _extract_text(invocation)
        length = len(content)
        if length == 0:
            return EvaluationResult(
                metric_name="length", score=0.0, label="empty"
            )
        score = length / (length + 50)
        if length < 50:
            label = "short"
        elif length <= 200:
            label = "medium"
        else:
            label = "long"
        return EvaluationResult(
            metric_name="length",
            score=score,
            label=label,
            explanation=f"Length characters: {length}",
            attributes={"gen_ai.evaluation.length.chars": length},
        )


class DeepevalEvaluator(Evaluator):
    """Placeholder Deepeval evaluator.

    Attempts to import deepeval. If unavailable, returns error. A future
    integration may map multiple metrics; for now this returns a single
    placeholder result when the dependency is present.
    """

    def evaluate_invocation(self, invocation: LLMInvocation):  # type: ignore[override]
        try:
            import deepeval  # noqa: F401
        except Exception as exc:  # pragma: no cover - environment dependent
            return EvaluationResult(
                metric_name="deepeval",
                error=Error(message="deepeval not installed", type=type(exc)),
            )
        return EvaluationResult(
            metric_name="deepeval",
            score=None,
            label=None,
            explanation="Deepeval integration placeholder (no metrics recorded)",
        )


class SentimentEvaluator(Evaluator):
    """Simple sentiment evaluator using nltk's VADER analyzer if available."""

    def evaluate_invocation(self, invocation: LLMInvocation):  # type: ignore[override]
        try:
            from nltk.sentiment import (
                SentimentIntensityAnalyzer,  # type: ignore
            )
        except Exception as exc:  # pragma: no cover - dependency optional
            return EvaluationResult(
                metric_name="sentiment",
                error=Error(
                    message="nltk (vader) not installed", type=type(exc)
                ),
            )
        content = _extract_text(invocation)
        if not content:
            return EvaluationResult(
                metric_name="sentiment", score=0.0, label="neutral"
            )
        analyzer = SentimentIntensityAnalyzer()
        scores = analyzer.polarity_scores(content)
        compound = scores.get("compound", 0.0)
        score = (compound + 1) / 2
        if compound >= 0.2:
            label = "positive"
        elif compound <= -0.2:
            label = "negative"
        else:
            label = "neutral"
        return EvaluationResult(
            metric_name="sentiment",
            score=score,
            label=label,
            explanation=f"compound={compound}",
        )


# Auto-register builtin evaluators (names stable lowercase)
register_evaluator("length", lambda: LengthEvaluator())
register_evaluator("deepeval", lambda: DeepevalEvaluator())
register_evaluator("sentiment", lambda: SentimentEvaluator())

__all__ = [
    "LengthEvaluator",
    "DeepevalEvaluator",
    "SentimentEvaluator",
]
