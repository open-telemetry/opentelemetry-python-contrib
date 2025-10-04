from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from ..interfaces import EmitterProtocol


@dataclass(frozen=True)
class EmitterFactoryContext:
    """Context provided to emitter factories when instantiating specs."""

    tracer: Any
    meter: Any
    event_logger: Any
    content_logger: Any
    evaluation_histogram: Any
    capture_span_content: bool
    capture_event_content: bool
    extras: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmitterSpec:
    """Declarative description of an emitter to be created for a category."""

    name: str
    category: str
    factory: Callable[[EmitterFactoryContext], EmitterProtocol]
    mode: str = "append"
    after: Sequence[str] = field(default_factory=tuple)
    before: Sequence[str] = field(default_factory=tuple)
    invocation_types: Sequence[str] | None = None


@dataclass(frozen=True)
class CategoryOverride:
    """Represents an environment-driven override for a category chain."""

    mode: str
    emitter_names: Sequence[str]


__all__ = [
    "EmitterFactoryContext",
    "EmitterSpec",
    "CategoryOverride",
]
