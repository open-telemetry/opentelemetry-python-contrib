# Phase 1 refactor: introduce lightweight protocol-style interfaces so future
# composite generator + plugin system can rely on a stable narrow contract.
from __future__ import annotations

from typing import Any, Protocol, Sequence, runtime_checkable

from .types import Error, EvaluationResult, LLMInvocation


@runtime_checkable
class EmitterProtocol(Protocol):
    """Protocol implemented by all telemetry emitters.

    Accepts any GenAI domain object (LLMInvocation, EmbeddingInvocation, etc.).
    Implementations MAY ignore objects of unsupported types.
    """

    def on_start(self, obj: Any) -> None:  # pragma: no cover - structural
        ...

    def on_end(self, obj: Any) -> None:  # pragma: no cover - structural
        ...

    def on_error(
        self, error: Error, obj: Any
    ) -> None:  # pragma: no cover - structural
        ...

    def on_evaluation_results(
        self, results: Sequence[EvaluationResult], obj: Any | None = None
    ) -> None:  # pragma: no cover - structural
        ...


@runtime_checkable
class EvaluatorProtocol(Protocol):
    """Protocol for evaluator objects (future phases may broaden)."""

    def evaluate(
        self, invocation: LLMInvocation
    ) -> Any:  # pragma: no cover - structural
        ...


class EmitterMeta:
    """Simple metadata mixin for emitters (role/name used by future plugin system)."""

    role: str = "span"  # default / legacy generators are span focused
    name: str = "legacy"
    override: bool = False

    def handles(self, obj: Any) -> bool:  # pragma: no cover (trivial)
        return True

    def on_evaluation_results(
        self, results: Sequence[EvaluationResult], obj: Any | None = None
    ) -> None:  # pragma: no cover - default no-op
        return None
