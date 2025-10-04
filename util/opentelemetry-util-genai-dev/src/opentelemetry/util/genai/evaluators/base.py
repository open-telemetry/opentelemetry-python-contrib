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
from typing import Iterable, Mapping, Sequence

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

    def __init__(
        self,
        metrics: Iterable[str] | None = None,
        *,
        invocation_type: str | None = None,
        options: Mapping[str, str] | None = None,
    ) -> None:
        default_metrics = (
            self.default_metrics_for(invocation_type)
            if invocation_type is not None
            else self.default_metrics()
        )
        self._metrics = tuple(metrics or default_metrics)
        self._invocation_type = invocation_type
        if options:
            normalized: dict[str, Mapping[str, str]] = {}
            for key, value in options.items():
                if isinstance(value, Mapping):
                    normalized[key] = dict(value)
                else:
                    normalized[key] = {"value": str(value)}
            self._options: Mapping[str, Mapping[str, str]] = normalized
        else:
            self._options = {}

    # ---- Metrics ------------------------------------------------------
    def default_metrics(self) -> Sequence[str]:  # pragma: no cover - trivial
        """Return the default metric identifiers produced by this evaluator."""

        return ()

    def default_metrics_for(
        self, invocation_type: str | None
    ) -> Sequence[str]:
        mapping = self.default_metrics_by_type()
        if invocation_type and invocation_type in mapping:
            return mapping[invocation_type]
        if "LLMInvocation" in mapping:
            return mapping["LLMInvocation"]
        return self.default_metrics()

    def default_metrics_by_type(self) -> Mapping[str, Sequence[str]]:
        """Return default metric identifiers grouped by GenAI invocation type."""

        metrics = self.default_metrics()
        if not metrics:
            return {}
        return {"LLMInvocation": tuple(metrics)}

    @property
    def metrics(self) -> Sequence[str]:  # pragma: no cover - trivial
        """Metric identifiers advertised by this evaluator instance."""

        return self._metrics

    @property
    def options(self) -> Mapping[str, Mapping[str, str]]:
        """Metric configuration supplied at construction time."""

        return self._options

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
