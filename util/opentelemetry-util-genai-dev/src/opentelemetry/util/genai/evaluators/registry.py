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

import inspect
import logging
from typing import Callable, Dict, Sequence

from opentelemetry.util.genai.evaluators.base import Evaluator
from opentelemetry.util._importlib_metadata import (
    entry_points,
)

_LOGGER = logging.getLogger(__name__)
_ENTRY_POINT_GROUP = "opentelemetry_util_genai_evaluators"

EvaluatorFactory = Callable[[Sequence[str] | None], Evaluator]

_EVALUATORS: Dict[str, EvaluatorFactory] = {}
_ENTRY_POINTS_LOADED = False


def _call_with_optional_metrics(
    target: Callable[..., Evaluator], metrics: Sequence[str] | None
) -> Evaluator:
    """Call a factory/constructor handling optional ``metrics`` gracefully."""

    try:
        sig = inspect.signature(target)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        sig = None
    if sig is not None:
        params = list(sig.parameters.values())
        accepts_kwargs = any(
            p.kind is inspect.Parameter.VAR_KEYWORD for p in params
        )
        accepts_varargs = any(
            p.kind is inspect.Parameter.VAR_POSITIONAL for p in params
        )
        has_metrics_kw = any(
            p.name == "metrics"
            and p.kind
            in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
            for p in params
        )
        if metrics is None and not accepts_kwargs and not accepts_varargs:
            # No metrics requested and callable doesn't need it
            return target()
        if has_metrics_kw or accepts_kwargs:
            return target(metrics=metrics)
        if accepts_varargs:
            return target(metrics)
        if metrics is None:
            return target()
        # Callable doesn't appear to accept metrics explicitly; fall back
        try:
            return target(metrics)
        except TypeError:  # pragma: no cover - defensive
            return target()
    # Unable to introspect signature; best-effort invocation
    try:
        return target(metrics=metrics)
    except TypeError:
        try:
            return target(metrics)
        except TypeError:
            return target()


def register_evaluator(
    name: str, factory: Callable[..., Evaluator]
) -> None:
    """Register a manual evaluator factory (case-insensitive name)."""

    key = name.lower()

    def _wrapped(metrics: Sequence[str] | None = None) -> Evaluator:
        return _call_with_optional_metrics(factory, metrics)

    _EVALUATORS[key] = _wrapped


def _load_entry_points() -> None:
    global _ENTRY_POINTS_LOADED
    if _ENTRY_POINTS_LOADED:
        return
    try:
        eps = entry_points(group=_ENTRY_POINT_GROUP)
    except Exception as exc:  # pragma: no cover - defensive
        _LOGGER.debug("Failed to load evaluator entry points: %s", exc)
        _ENTRY_POINTS_LOADED = True
        return
    for ep in eps:  # type: ignore[assignment]
        name = ep.name
        try:
            target = ep.load()
        except Exception as exc:  # pragma: no cover - import issues
            _LOGGER.warning(
                "Failed to load evaluator entry point '%s': %s", name, exc
            )
            continue
        if not callable(target):
            _LOGGER.warning(
                "Evaluator entry point '%s' is not callable; ignoring", name
            )
            continue

        def _factory(
            metrics: Sequence[str] | None = None,
            _target: Callable[..., Evaluator] = target,
        ) -> Evaluator:
            return _call_with_optional_metrics(_target, metrics)

        # Manual registrations take precedence; avoid overriding explicitly set ones
        key = name.lower()
        if key not in _EVALUATORS:
            _EVALUATORS[key] = _factory
    _ENTRY_POINTS_LOADED = True


def get_evaluator(
    name: str, metrics: Sequence[str] | None = None
) -> Evaluator:
    _load_entry_points()
    key = name.lower()
    factory = _EVALUATORS.get(key)
    if factory is None:
        raise ValueError(f"Unknown evaluator: {name}")
    return factory(metrics)


def list_evaluators() -> list[str]:
    _load_entry_points()
    return sorted(_EVALUATORS.keys())


def clear_registry() -> None:  # pragma: no cover - test helper
    """Internal helper for tests to reset registry state."""

    _EVALUATORS.clear()
    global _ENTRY_POINTS_LOADED
    _ENTRY_POINTS_LOADED = False


__all__ = [
    "register_evaluator",
    "get_evaluator",
    "list_evaluators",
    "clear_registry",
]
