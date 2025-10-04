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
"""NLTK-based sentiment evaluator plug-in."""

from __future__ import annotations

from typing import Iterable, List, Mapping, Sequence

from opentelemetry.util.genai.evaluators.base import Evaluator
from opentelemetry.util.genai.evaluators.registry import (
    EvaluatorRegistration,
    register_evaluator,
)
from opentelemetry.util.genai.types import (
    Error,
    EvaluationResult,
    LLMInvocation,
    Text,
)


def _extract_text(invocation: LLMInvocation) -> str:
    parts: List[str] = []
    for message in invocation.output_messages:
        for part in getattr(message, "parts", []):
            if isinstance(part, Text):
                parts.append(part.content)
    return "\n".join(part for part in parts if part).strip()


class NLTKSentimentEvaluator(Evaluator):
    """Evaluator that scores sentiment using NLTK's VADER analyser."""

    def default_metrics(self) -> Sequence[str]:  # pragma: no cover - trivial
        return ("sentiment",)

    def evaluate_llm(
        self, invocation: LLMInvocation
    ) -> Sequence[EvaluationResult]:  # type: ignore[override]
        metric_name = self.metrics[0] if self.metrics else "sentiment"
        try:
            from nltk.sentiment import SentimentIntensityAnalyzer
        except Exception as exc:  # pragma: no cover - defensive fallback
            return [
                EvaluationResult(
                    metric_name=metric_name,
                    error=Error(
                        message="nltk (vader) not installed",
                        type=type(exc),
                    ),
                )
            ]
        content = _extract_text(invocation)
        if not content:
            return [
                EvaluationResult(
                    metric_name=metric_name,
                    score=0.0,
                    label="neutral",
                )
            ]
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
        return [
            EvaluationResult(
                metric_name=metric_name,
                score=score,
                label=label,
                explanation=f"compound={compound}",
            )
        ]


def _factory(
    metrics: Iterable[str] | None = None,
    invocation_type: str | None = None,
    options: Mapping[str, Mapping[str, str]] | None = None,
) -> NLTKSentimentEvaluator:
    return NLTKSentimentEvaluator(
        metrics,
        invocation_type=invocation_type,
        options=options,
    )


_REGISTRATION = EvaluatorRegistration(
    factory=_factory,
    default_metrics_factory=lambda: {"LLMInvocation": ("sentiment",)},
)


def registration() -> EvaluatorRegistration:
    return _REGISTRATION


def register() -> None:
    register_evaluator(
        "nltk_sentiment",
        _REGISTRATION.factory,
        default_metrics=_REGISTRATION.default_metrics_factory,
    )


__all__ = [
    "NLTKSentimentEvaluator",
    "registration",
    "register",
]
