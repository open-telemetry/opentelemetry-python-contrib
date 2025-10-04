from __future__ import annotations

import logging
from typing import Iterable, Mapping, Sequence

from opentelemetry.util._importlib_metadata import (
    entry_points,  # pyright: ignore[reportUnknownVariableType]
)

from .emitters.spec import EmitterSpec

_logger = logging.getLogger(__name__)


def load_emitter_specs(
    names: Sequence[str] | None = None,
) -> list[EmitterSpec]:
    """Load emitter specs declared under the ``opentelemetry_util_genai_emitters`` entry point.

    Entry points should return an iterable of :class:`EmitterSpec` instances or dictionaries
    matching the ``EmitterSpec`` constructor signature. When ``names`` is provided, only
    entry points whose name matches (case-insensitive) the selection are loaded.
    """

    selected = {name.lower() for name in names} if names else None
    loaded_specs: list[EmitterSpec] = []
    seen: set[str] = set()
    for ep in entry_points(group="opentelemetry_util_genai_emitters"):
        ep_name = getattr(ep, "name", "")
        seen.add(ep_name.lower())
        if selected and ep_name.lower() not in selected:
            continue
        try:
            provider = ep.load()
        except Exception:  # pragma: no cover - defensive
            _logger.exception("Emitter entry point %s failed to load", ep_name)
            continue
        try:
            loaded_specs.extend(_coerce_to_specs(provider, ep_name))
        except Exception:  # pragma: no cover - defensive
            _logger.exception(
                "Emitter entry point %s returned an unsupported value", ep_name
            )
    if selected:
        missing = selected - seen
        for name in missing:
            _logger.debug("Emitter entry point '%s' was not found", name)
    return loaded_specs


def _coerce_to_specs(provider: object, source: str) -> list[EmitterSpec]:
    if provider is None:
        return []
    if callable(provider):
        return _coerce_to_specs(provider(), source)
    if isinstance(provider, EmitterSpec):
        return [provider]
    if isinstance(provider, Mapping):
        return [_mapping_to_spec(provider, source)]
    if isinstance(provider, Iterable):
        specs: list[EmitterSpec] = []
        for item in provider:
            if isinstance(item, EmitterSpec):
                specs.append(item)
            elif isinstance(item, Mapping):
                specs.append(_mapping_to_spec(item, source))
            else:
                raise TypeError(
                    f"Unsupported emitter spec element {item!r} from {source}"
                )
        return specs
    raise TypeError(
        f"Unsupported emitter spec provider {provider!r} from {source}"
    )


def _mapping_to_spec(data: Mapping[str, object], source: str) -> EmitterSpec:
    if "factory" not in data:
        raise ValueError(f"Emitter spec from {source} must define a factory")
    return EmitterSpec(**data)  # type: ignore[arg-type]


__all__ = ["load_emitter_specs"]
