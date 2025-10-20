# pylint: skip-file

from __future__ import annotations

from typing import Collection


class BaseInstrumentor:
    def __init__(self) -> None:
        pass

    def instrument(self, **kwargs) -> None:
        self._instrument(**kwargs)

    def uninstrument(self, **kwargs) -> None:
        self._uninstrument(**kwargs)

    # Subclasses override
    def _instrument(self, **kwargs) -> None:  # pragma: no cover - stub
        raise NotImplementedError

    def _uninstrument(self, **kwargs) -> None:  # pragma: no cover - stub
        raise NotImplementedError

    def instrumentation_dependencies(
        self,
    ) -> Collection[str]:  # pragma: no cover
        return []
