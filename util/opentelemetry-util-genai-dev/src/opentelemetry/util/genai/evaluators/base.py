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

from __future__ import annotations

from abc import ABC
from typing import Iterable, Sequence

from opentelemetry.util.genai.types import (
    AgentInvocation,
    EvaluationResult,
    GenAI,
    LLMInvocation,
)


class Evaluator(ABC):
    """Base evaluator contract for GenAI artifacts.

    Evaluators may specialise for different invocation types (LLM, Agent, etc.).
    Subclasses override the type-specific ``evaluate_*`` methods. The top-level
    ``evaluate`` method performs dynamic dispatch and guarantees a list return type.
    """

    def __init__(self, metrics: Iterable[str] | None = None) -> None:
        self._metrics = tuple(metrics or self.default_metrics())

    # ---- Metrics ------------------------------------------------------
    def default_metrics(self) -> Sequence[str]:  # pragma: no cover - trivial
        """Return the default metric identifiers produced by this evaluator."""

        return ()

    @property
    def metrics(self) -> Sequence[str]:  # pragma: no cover - trivial
        """Metric identifiers advertised by this evaluator instance."""

        return self._metrics

    # ---- Evaluation dispatch -----------------------------------------
    def evaluate(self, item: GenAI) -> list[EvaluationResult]:
        """Evaluate any GenAI telemetry entity and return results."""

        if isinstance(item, LLMInvocation):
            return list(self.evaluate_llm(item))
        if isinstance(item, AgentInvocation):
            return list(self.evaluate_agent(item))
        return []

    # ---- Type-specific hooks -----------------------------------------
    def evaluate_llm(
        self, invocation: LLMInvocation
    ) -> Sequence[EvaluationResult]:
        """Evaluate an LLM invocation. Override in subclasses."""

        return []

    def evaluate_agent(
        self, invocation: AgentInvocation
    ) -> Sequence[EvaluationResult]:
        """Evaluate an agent invocation. Override in subclasses."""

        return []


__all__ = ["Evaluator"]
