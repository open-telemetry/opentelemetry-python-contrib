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
from dataclasses import dataclass
from typing import Callable, Dict, Mapping, Sequence

from opentelemetry.util._importlib_metadata import (
    entry_points,
)
from opentelemetry.util.genai.evaluators.base import Evaluator

_LOGGER = logging.getLogger(__name__)
_ENTRY_POINT_GROUP = "opentelemetry_util_genai_evaluators"

EvaluatorFactory = Callable[..., Evaluator]


@dataclass
class EvaluatorRegistration:
    """Registration metadata for an evaluator plugin."""

    factory: EvaluatorFactory
    default_metrics_factory: Callable[[], Mapping[str, Sequence[str]]]


_EVALUATORS: Dict[str, EvaluatorRegistration] = {}
_ENTRY_POINTS_LOADED = False


def _call_with_optional_params(
    target: EvaluatorFactory,
    *,
    metrics: Sequence[str] | None = None,
    invocation_type: str | None = None,
    options: Mapping[str, str] | None = None,
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
        parameter_names = {p.name for p in params}
        call_kwargs: dict[str, object] = {}
        args: list[object] = []
        if metrics is not None:
            if "metrics" in parameter_names:
                call_kwargs["metrics"] = metrics
            elif accepts_varargs:
                args.append(metrics)
        if (
            invocation_type is not None
            and "invocation_type" in parameter_names
        ):
            call_kwargs["invocation_type"] = invocation_type
        if options and "options" in parameter_names:
            call_kwargs["options"] = options
        if accepts_kwargs:
            return target(*args, **call_kwargs)
        try:
            return target(*args, **call_kwargs)
        except TypeError:
            # Retry progressively dropping optional parameters
            if call_kwargs:
                call_kwargs.pop("options", None)
                try:
                    return target(*args, **call_kwargs)
                except TypeError:
                    call_kwargs.pop("invocation_type", None)
                    try:
                        return target(*args, **call_kwargs)
                    except TypeError:
                        call_kwargs.pop("metrics", None)
                        return target(*args, **call_kwargs)
            raise
    # Unable to introspect signature; best-effort invocation cascade
    for attempt in (
        lambda: target(
            metrics=metrics, invocation_type=invocation_type, options=options
        ),
        lambda: target(metrics=metrics, invocation_type=invocation_type),
        lambda: target(metrics=metrics),
        target,
    ):
        try:
            return attempt()  # type: ignore[misc]
        except TypeError:
            continue
    raise TypeError("Unable to invoke evaluator factory")


def register_evaluator(
    name: str,
    factory: EvaluatorFactory,
    *,
    default_metrics: Callable[[], Mapping[str, Sequence[str]]]
    | Mapping[str, Sequence[str]]
    | None = None,
) -> None:
    """Register a manual evaluator factory (case-insensitive name)."""

    key = name.lower()

    def _default_supplier() -> Mapping[str, Sequence[str]]:
        if default_metrics is None:
            try:
                instance = _call_with_optional_params(factory)
            except Exception:  # pragma: no cover - defensive
                return {}
            provider = getattr(instance, "default_metrics_by_type", None)
            if callable(provider):
                try:
                    return provider()
                except Exception:  # pragma: no cover - defensive
                    return {}
            try:
                metrics = instance.default_metrics()
            except Exception:  # pragma: no cover - defensive
                metrics = []
            return {"LLMInvocation": tuple(metrics)}
        if callable(default_metrics):
            return default_metrics()
        return default_metrics

    _EVALUATORS[key] = EvaluatorRegistration(
        factory=factory,
        default_metrics_factory=_default_supplier,
    )


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
        try:
            target = ep.load()
        except Exception as exc:  # pragma: no cover - import issues
            _LOGGER.warning(
                "Failed to load evaluator entry point '%s': %s", ep.name, exc
            )
            continue
        registration: EvaluatorRegistration | None = None
        if isinstance(target, EvaluatorRegistration):
            registration = target
        elif hasattr(target, "factory") and hasattr(target, "default_metrics"):
            try:
                defaults_callable = getattr(target, "default_metrics")
                if callable(defaults_callable):
                    registration = EvaluatorRegistration(
                        factory=getattr(target, "factory"),
                        default_metrics_factory=lambda _f=defaults_callable: _f(),
                    )
            except Exception:  # pragma: no cover - defensive
                registration = None
        elif callable(target):
            # Legacy entry point exposing factory directly
            registration = EvaluatorRegistration(
                factory=target,
                default_metrics_factory=lambda: {},
            )

        if registration is None:
            _LOGGER.warning(
                "Evaluator entry point '%s' did not yield a registration",
                ep.name,
            )
            continue

        key = ep.name.lower()
        if key not in _EVALUATORS:
            _EVALUATORS[key] = registration
    _ENTRY_POINTS_LOADED = True


def get_evaluator(
    name: str,
    metrics: Sequence[str] | None = None,
    *,
    invocation_type: str | None = None,
    options: Mapping[str, str] | None = None,
) -> Evaluator:
    _load_entry_points()
    key = name.lower()
    registration = _EVALUATORS.get(key)
    if registration is None:
        raise ValueError(f"Unknown evaluator: {name}")
    return _call_with_optional_params(
        registration.factory,
        metrics=metrics,
        invocation_type=invocation_type,
        options=options,
    )


def get_default_metrics(name: str) -> Mapping[str, Sequence[str]]:
    _load_entry_points()
    registration = _EVALUATORS.get(name.lower())
    if registration is None:
        raise ValueError(f"Unknown evaluator: {name}")
    try:
        defaults = registration.default_metrics_factory()
    except Exception:  # pragma: no cover - defensive
        return {}
    normalized: dict[str, Sequence[str]] = {}
    for key, value in defaults.items():
        normalized[key] = tuple(value)
    return normalized


def list_evaluators() -> list[str]:
    _load_entry_points()
    return sorted(_EVALUATORS.keys())


def clear_registry() -> None:  # pragma: no cover - test helper
    """Internal helper for tests to reset registry state."""

    _EVALUATORS.clear()
    global _ENTRY_POINTS_LOADED
    _ENTRY_POINTS_LOADED = False


__all__ = [
    "EvaluatorRegistration",
    "register_evaluator",
    "get_evaluator",
    "get_default_metrics",
    "list_evaluators",
    "clear_registry",
]
