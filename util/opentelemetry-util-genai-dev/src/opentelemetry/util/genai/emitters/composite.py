# CompositeGenerator relocated from emission_composite.py
from __future__ import annotations

from typing import Any, Iterable, List

from ..interfaces import GeneratorProtocol
from ..types import Error


class CompositeGenerator(GeneratorProtocol):
    """Delegates lifecycle calls to an ordered list of emitter instances.

    Ordering semantics:
      * start: span emitters first (so span context is available), then others
      * finish/error: non-span emitters first, span emitters last (so metrics/events
        observe active span, and span closes last)
    """

    def __init__(self, generators: Iterable[GeneratorProtocol]):
        self._generators: List[GeneratorProtocol] = list(generators)
        self._primary = self._generators[0] if self._generators else None

    def add(self, generator: GeneratorProtocol):  # pragma: no cover
        self._generators.append(generator)
        if not self._primary:
            self._primary = generator

    def set_capture_content(self, value: bool):  # pragma: no cover
        for g in self._generators:
            if hasattr(g, "_capture_content"):
                try:
                    setattr(g, "_capture_content", value)
                except Exception:
                    pass

    def __getattr__(self, item):  # pragma: no cover
        primary = getattr(self, "_primary", None)
        if primary is not None:
            try:
                return getattr(primary, item)
            except AttributeError:
                pass
        raise AttributeError(item)

    def _partition(self):
        span_emitters = []
        other_emitters = []
        for g in self._generators:
            role = getattr(g, "role", None)
            if role == "span":
                span_emitters.append(g)
            else:
                other_emitters.append(g)
        return span_emitters, other_emitters

    def start(self, obj: Any) -> None:  # type: ignore[override]
        span_emitters, other_emitters = self._partition()
        for g in span_emitters:
            if getattr(g, "handles", lambda o: True)(obj):
                g.start(obj)
        for g in other_emitters:
            if getattr(g, "handles", lambda o: True)(obj):
                g.start(obj)

    def finish(self, obj: Any) -> None:  # type: ignore[override]
        span_emitters, other_emitters = self._partition()
        for g in other_emitters:
            if getattr(g, "handles", lambda o: True)(obj):
                g.finish(obj)
        for g in span_emitters:
            if getattr(g, "handles", lambda o: True)(obj):
                g.finish(obj)

    def error(self, error: Error, obj: Any) -> None:  # type: ignore[override]
        span_emitters, other_emitters = self._partition()
        for g in other_emitters:
            if getattr(g, "handles", lambda o: True)(obj):
                try:
                    g.error(error, obj)
                except Exception:  # pragma: no cover
                    pass
        for g in span_emitters:
            if getattr(g, "handles", lambda o: True)(obj):
                g.error(error, obj)
