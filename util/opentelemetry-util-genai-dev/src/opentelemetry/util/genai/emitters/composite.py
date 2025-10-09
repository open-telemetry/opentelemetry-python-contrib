from __future__ import annotations

import logging
from typing import Any, Iterable, Iterator, Mapping, Sequence

from ..interfaces import EmitterMeta, EmitterProtocol
from ..types import Error, EvaluationResult

_LOGGER = logging.getLogger(__name__)

_CATEGORY_START_ORDER: Sequence[str] = ("span", "metrics", "content_events")
_CATEGORY_END_ORDER: Sequence[str] = (
    "evaluation",
    "metrics",
    "content_events",
    "span",
)
_EVALUATION_CATEGORY = "evaluation"


class CompositeEmitter(EmitterMeta):
    """Category-aware orchestrator for GenAI emitters.

    Emitters are grouped by category to allow targeted replacement/augmentation while
    preserving ordering guarantees:

    * ``span`` emitters run first on ``on_start`` and last on ``on_end``/``on_error``
    * ``metrics`` emitters run before content emitters at the end of an invocation
    * ``content_events`` emitters observe invocations after metrics but before the
      final span closure
    * ``evaluation`` emitters observe ``on_evaluation_results`` and receive ``on_end``/``on_error`` for flush-style behaviour
    """

    role = "composite"
    name = "composite"

    def __init__(
        self,
        *,
        span_emitters: Iterable[EmitterProtocol] | None = None,
        metrics_emitters: Iterable[EmitterProtocol] | None = None,
        content_event_emitters: Iterable[EmitterProtocol] | None = None,
        evaluation_emitters: Iterable[EmitterProtocol] | None = None,
    ) -> None:
        self._categories: dict[str, list[EmitterProtocol]] = {
            "span": list(span_emitters or []),
            "metrics": list(metrics_emitters or []),
            "content_events": list(content_event_emitters or []),
            _EVALUATION_CATEGORY: list(evaluation_emitters or []),
        }

    # ------------------------------------------------------------------
    # Public API used by the handler lifecycle

    def on_start(self, obj: Any) -> None:  # type: ignore[override]
        self._dispatch(_CATEGORY_START_ORDER, "on_start", obj=obj)

    def on_end(self, obj: Any) -> None:  # type: ignore[override]
        self._dispatch(_CATEGORY_END_ORDER, "on_end", obj=obj)

    def on_error(self, error: Error, obj: Any) -> None:  # type: ignore[override]
        self._dispatch(_CATEGORY_END_ORDER, "on_error", obj=obj, error=error)

    def on_evaluation_results(
        self,
        results: Sequence[EvaluationResult],
        obj: Any | None = None,
    ) -> None:  # type: ignore[override]
        if not results:
            return
        self._dispatch(
            (_EVALUATION_CATEGORY,),
            "on_evaluation_results",
            obj=obj,
            results=results,
        )

    # ------------------------------------------------------------------
    # Introspection helpers used during configuration refresh

    def iter_emitters(
        self, categories: Sequence[str] | None = None
    ) -> Iterator[EmitterProtocol]:
        names = categories or (
            "span",
            "metrics",
            "content_events",
            _EVALUATION_CATEGORY,
        )
        for name in names:
            for emitter in self._categories.get(name, []):
                yield emitter

    def emitters_for(self, category: str) -> Sequence[EmitterProtocol]:
        return self._categories.get(category, [])

    def categories(self) -> Mapping[str, Sequence[EmitterProtocol]]:
        return self._categories

    def add_emitter(self, category: str, emitter: EmitterProtocol) -> None:
        self._categories.setdefault(category, []).append(emitter)

    # ------------------------------------------------------------------
    # Internal helpers

    def _dispatch(
        self,
        categories: Sequence[str],
        method_name: str,
        *,
        obj: Any | None = None,
        error: Error | None = None,
        results: Sequence[EvaluationResult] | None = None,
    ) -> None:
        for category in categories:
            emitters = self._categories.get(category)
            if not emitters:
                continue
            for emitter in list(emitters):
                handler = getattr(emitter, method_name, None)
                if handler is None:
                    continue
                if method_name == "on_evaluation_results":
                    args = (results or (), obj)
                    target = obj
                elif method_name == "on_error":
                    args = (error, obj)
                    target = obj
                else:
                    args = (obj,)
                    target = obj
                try:
                    handles = getattr(emitter, "handles", None)
                    if handles is not None and target is not None:
                        if not handles(target):
                            continue
                    handler(*args)
                except Exception:  # pragma: no cover - defensive
                    _LOGGER.debug(
                        "Emitter %s failed during %s for category %s",
                        getattr(emitter, "name", repr(emitter)),
                        method_name,
                        category,
                        exc_info=True,
                    )
