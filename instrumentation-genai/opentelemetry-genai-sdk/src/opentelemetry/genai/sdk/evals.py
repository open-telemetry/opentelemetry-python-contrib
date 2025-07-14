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