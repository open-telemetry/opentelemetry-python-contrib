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

from abc import ABC, abstractmethod

from .types import LLMInvocation


class EvaluationResult:
    """
    Standardized result for any GenAI evaluation.
    """

    def __init__(self, score: float, details: dict = None):
        self.score = score
        self.details = details or {}


class Evaluator(ABC):
    """
    Abstract base: any evaluation backend must implement.
    """

    @abstractmethod
    def evaluate(self, invocation: LLMInvocation) -> EvaluationResult:
        """
        Evaluate a completed LLMInvocation and return a result.
        """
        pass


class DeepEvalsEvaluator(Evaluator):
    """
    Uses DeepEvals library for LLM-as-judge evaluations.
    """

    def __init__(self, config: dict = None):
        # e.g. load models, setup API keys
        self.config = config or {}

    def evaluate(self, invocation: LLMInvocation) -> EvaluationResult:
        # stub: integrate with deepevals SDK
        # result = deepevals.judge(invocation.prompt, invocation.response, **self.config)
        score = 0.0  # placeholder
        details = {"method": "deepevals"}
        return EvaluationResult(score=score, details=details)


class OpenLitEvaluator(Evaluator):
    """
    Uses OpenLit or similar OSS evaluation library.
    """

    def __init__(self, config: dict = None):
        self.config = config or {}

    def evaluate(self, invocation: LLMInvocation) -> EvaluationResult:
        # stub: integrate with openlit SDK
        score = 0.0  # placeholder
        details = {"method": "openlit"}
        return EvaluationResult(score=score, details=details)


# Registry for easy lookup
EVALUATORS = {
    "deepevals": DeepEvalsEvaluator,
    "openlit": OpenLitEvaluator,
}


def get_evaluator(name: str, config: dict = None) -> Evaluator:
    """
    Factory: return an evaluator by name.
    """
    cls = EVALUATORS.get(name.lower())
    if not cls:
        raise ValueError(f"Unknown evaluator: {name}")
    return cls(config)
