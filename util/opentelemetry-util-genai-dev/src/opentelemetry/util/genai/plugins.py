from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from opentelemetry.util._importlib_metadata import (
    entry_points,  # pyright: ignore[reportUnknownVariableType]
)

_logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PluginEmitterBundle:
    """Container for emitters contributed by external packages.

    ``replace_default_emitters`` allows a plugin to take full ownership of signal
    emission (e.g., provide custom span/metric implementations) while still
    participating in the standard configuration flow.
    """

    emitters: list[Any] = field(default_factory=list)
    replace_default_emitters: bool = False


def load_emitter_plugin(
    name: str,
    *,
    tracer: Any,
    meter: Any,
    event_logger: Any,
    settings: Any,
) -> PluginEmitterBundle | None:
    """Load a third-party emitter bundle by entry point name.

    Entry points must be declared under the ``opentelemetry_genai_emitters`` group
    and return a callable that accepts telemetry primitives and produces a
    :class:`PluginEmitterBundle`.
    """

    for entry_point in entry_points(  # pyright: ignore[reportUnknownVariableType]
        group="opentelemetry_genai_emitters"
    ):
        try:
            if getattr(entry_point, "name", None) != name:  # pyright: ignore[reportUnknownMemberType]
                continue
            factory = entry_point.load()  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
            bundle = factory(
                tracer=tracer,
                meter=meter,
                event_logger=event_logger,
                settings=settings,
            )
            if isinstance(bundle, PluginEmitterBundle):
                _logger.debug("Using emitter plugin %s", name)
                return bundle
            _logger.warning(
                "Emitter plugin %s returned unexpected type %s",
                name,
                type(bundle),
            )
        except Exception:  # pylint: disable=broad-except
            _logger.exception("Emitter plugin %s configuration failed", name)
            return None
    _logger.debug("Emitter plugin %s not found", name)
    return None


__all__ = ["PluginEmitterBundle", "load_emitter_plugin"]
