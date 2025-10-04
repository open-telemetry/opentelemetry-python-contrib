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

These evaluators implement lightweight reference behaviour to exercise the
pluggable evaluation infrastructure. Heavy / optional dependencies are
imported lazily. When a dependency is not available the evaluator returns an
``EvaluationResult`` with the ``error`` field populated.
"""

from __future__ import annotations

from typing import List, Sequence

from opentelemetry.util.genai.evaluators.base import Evaluator
from opentelemetry.util.genai.evaluators.registry import register_evaluator
from opentelemetry.util.genai.types import (
    EvaluationResult,
    LLMInvocation,
    Text,
)


def _extract_text(invocation: LLMInvocation) -> str:
    text_parts: List[str] = []
    for msg in invocation.output_messages:
        for part in msg.parts:
            if isinstance(part, Text):
                text_parts.append(part.content)
    return "\n".join(text_parts).strip()


class LengthEvaluator(Evaluator):
    """Simple evaluator producing a score based on response length."""

    def default_metrics(self) -> Sequence[str]:  # pragma: no cover - trivial
        return ("length",)

    def evaluate_llm(
        self, invocation: LLMInvocation
    ) -> Sequence[EvaluationResult]:
        content = _extract_text(invocation)
        length = len(content)
        metric_name = self.metrics[0] if self.metrics else "length"
        if length == 0:
            return [
                EvaluationResult(
                    metric_name=metric_name, score=0.0, label="empty"
                )
            ]
        score = length / (length + 50)
        if length < 50:
            label = "short"
        elif length <= 200:
            label = "medium"
        else:
            label = "long"
        return [
            EvaluationResult(
                metric_name=metric_name,
                score=score,
                label=label,
                explanation=f"Length characters: {length}",
                attributes={"gen_ai.evaluation.length.chars": length},
            )
        ]


def _wrap_factory(cls):
    def _factory(
        metrics=None,
        invocation_type=None,
        options=None,
    ):
        return cls(
            metrics,
            invocation_type=invocation_type,
            options=options,
        )

    return _factory


# Auto-register builtin evaluators (names stable lowercase)
register_evaluator(
    "length",
    _wrap_factory(LengthEvaluator),
    default_metrics=lambda: {"LLMInvocation": ("length",)},
)

__all__ = [
    "LengthEvaluator",
]
