from __future__ import annotations

import logging
from dataclasses import dataclass
from types import MethodType
from typing import Any, Dict, Iterable, List, Sequence

from ..config import Settings
from ..interfaces import EmitterProtocol
from ..plugins import load_emitter_specs
from ..types import ContentCapturingMode
from .composite import CompositeEmitter
from .content_events import ContentEventsEmitter
from .evaluation import EvaluationEventsEmitter, EvaluationMetricsEmitter
from .metrics import MetricsEmitter
from .span import SpanEmitter
from .spec import CategoryOverride, EmitterFactoryContext, EmitterSpec

_logger = logging.getLogger(__name__)

_CATEGORY_SPAN = "span"
_CATEGORY_METRICS = "metrics"
_CATEGORY_CONTENT = "content_events"
_CATEGORY_EVALUATION = "evaluation"


@dataclass(frozen=True)
class CaptureControl:
    span_allowed: bool
    span_initial: bool
    events_initial: bool
    mode: ContentCapturingMode


def build_emitter_pipeline(
    *,
    tracer: Any,
    meter: Any,
    event_logger: Any,
    content_logger: Any,
    evaluation_histogram: Any,
    settings: Settings,
) -> tuple[CompositeEmitter, CaptureControl]:
    """Construct the CompositeEmitter and capture control metadata."""

    span_allowed = (
        settings.capture_messages_override
        or settings.legacy_capture_request
        or not settings.enable_content_events
    )
    span_initial = span_allowed and settings.capture_messages_mode in (
        ContentCapturingMode.SPAN_ONLY,
        ContentCapturingMode.SPAN_AND_EVENT,
    )
    events_initial = settings.enable_content_events and (
        settings.capture_messages_mode
        in (
            ContentCapturingMode.EVENT_ONLY,
            ContentCapturingMode.SPAN_AND_EVENT,
        )
    )

    context = EmitterFactoryContext(
        tracer=tracer,
        meter=meter,
        event_logger=event_logger,
        content_logger=content_logger,
        evaluation_histogram=evaluation_histogram,
        capture_span_content=span_initial,
        capture_event_content=events_initial,
    )

    category_specs: Dict[str, List[EmitterSpec]] = {
        _CATEGORY_SPAN: [],
        _CATEGORY_METRICS: [],
        _CATEGORY_CONTENT: [],
        _CATEGORY_EVALUATION: [],
    }
    spec_registry: Dict[str, EmitterSpec] = {}

    def _register(spec: EmitterSpec) -> None:
        target = category_specs.setdefault(spec.category, [])
        mode = getattr(spec, "mode", "append")
        if mode == "replace-category":
            target.clear()
            target.append(spec)
        elif mode == "prepend":
            target.insert(0, spec)
        elif mode == "replace-same-name":
            replaced = False
            for idx, existing in enumerate(target):
                if existing.name == spec.name:
                    target[idx] = spec
                    replaced = True
                    break
            if not replaced:
                target.append(spec)
        else:
            target.append(spec)
        spec_registry[spec.name] = spec

    if settings.enable_span and not settings.only_traceloop_compat:
        _register(
            EmitterSpec(
                name="SemanticConvSpan",
                category=_CATEGORY_SPAN,
                factory=lambda ctx: SpanEmitter(
                    tracer=ctx.tracer,
                    capture_content=ctx.capture_span_content,
                ),
            )
        )
    if settings.enable_metrics:
        _register(
            EmitterSpec(
                name="SemanticConvMetrics",
                category=_CATEGORY_METRICS,
                factory=lambda ctx: MetricsEmitter(meter=ctx.meter),
            )
        )
    if settings.enable_content_events:
        _register(
            EmitterSpec(
                name="ContentEvents",
                category=_CATEGORY_CONTENT,
                factory=lambda ctx: ContentEventsEmitter(
                    logger=ctx.content_logger,
                    capture_content=ctx.capture_event_content,
                ),
            )
        )

    # Evaluation emitters are always present
    _register(
        EmitterSpec(
            name="EvaluationMetrics",
            category=_CATEGORY_EVALUATION,
            factory=lambda ctx: EvaluationMetricsEmitter(
                ctx.evaluation_histogram
            ),
        )
    )
    _register(
        EmitterSpec(
            name="EvaluationEvents",
            category=_CATEGORY_EVALUATION,
            factory=lambda ctx: EvaluationEventsEmitter(
                ctx.event_logger,
                emit_legacy_event=settings.emit_legacy_evaluation_event,
            ),
        )
    )

    for spec in load_emitter_specs(settings.extra_emitters):
        if spec.category not in {
            _CATEGORY_SPAN,
            _CATEGORY_METRICS,
            _CATEGORY_CONTENT,
            _CATEGORY_EVALUATION,
        }:
            _logger.warning(
                "Emitter spec %s targets unknown category '%s'",
                spec.name,
                spec.category,
            )
            continue
        _register(spec)

    _apply_category_overrides(
        category_specs, spec_registry, settings.category_overrides
    )

    span_emitters = _instantiate_category(
        category_specs.get(_CATEGORY_SPAN, ()), context
    )
    metrics_emitters = _instantiate_category(
        category_specs.get(_CATEGORY_METRICS, ()), context
    )
    content_emitters = _instantiate_category(
        category_specs.get(_CATEGORY_CONTENT, ()), context
    )
    evaluation_emitters = _instantiate_category(
        category_specs.get(_CATEGORY_EVALUATION, ()), context
    )

    composite = CompositeEmitter(
        span_emitters=span_emitters,
        metrics_emitters=metrics_emitters,
        content_event_emitters=content_emitters,
        evaluation_emitters=evaluation_emitters,
    )
    control = CaptureControl(
        span_allowed=span_allowed,
        span_initial=span_initial,
        events_initial=events_initial,
        mode=settings.capture_messages_mode,
    )
    return composite, control


def _instantiate_category(
    specs: Iterable[EmitterSpec], context: EmitterFactoryContext
) -> List[EmitterProtocol]:
    instances: List[EmitterProtocol] = []
    for spec in specs:
        try:
            emitter = spec.factory(context)
            if spec.invocation_types:
                allowed = {name for name in spec.invocation_types}
                original = getattr(emitter, "handles", None)
                orig_func = getattr(original, "__func__", None)

                def _filtered_handles(
                    self, obj, _allowed=allowed, _orig=orig_func
                ):
                    if obj is None:
                        if _orig is not None:
                            return _orig(self, obj)
                        return True
                    if type(obj).__name__ not in _allowed:
                        return False
                    if _orig is not None:
                        return _orig(self, obj)
                    return True

                setattr(
                    emitter,
                    "handles",
                    MethodType(_filtered_handles, emitter),
                )
            instances.append(emitter)
        except Exception:  # pragma: no cover - defensive
            _logger.exception("Failed to instantiate emitter %s", spec.name)
    return instances


def _apply_category_overrides(
    category_specs: Dict[str, List[EmitterSpec]],
    spec_registry: Dict[str, EmitterSpec],
    overrides: Dict[str, CategoryOverride],
) -> None:
    for category, override in overrides.items():
        current = category_specs.setdefault(category, [])
        if override.mode == "replace-category":
            replacement: List[EmitterSpec] = []
            for name in override.emitter_names:
                spec = spec_registry.get(name)
                if spec is None:
                    _logger.warning(
                        "Emitter '%s' referenced in %s override is not registered",
                        name,
                        category,
                    )
                    continue
                replacement.append(spec)
            category_specs[category] = replacement
            continue
        if override.mode == "prepend":
            additions = _resolve_specs(
                override.emitter_names, spec_registry, category
            )
            category_specs[category] = additions + current
            continue
        if override.mode == "replace-same-name":
            for name in override.emitter_names:
                spec = spec_registry.get(name)
                if spec is None:
                    _logger.warning(
                        "Emitter '%s' referenced in %s override is not registered",
                        name,
                        category,
                    )
                    continue
                replaced = False
                for idx, existing in enumerate(current):
                    if existing.name == name:
                        current[idx] = spec
                        replaced = True
                        break
                if not replaced:
                    current.append(spec)
            continue
        # append (default)
        additions = _resolve_specs(
            override.emitter_names, spec_registry, category
        )
        current.extend(additions)


def _resolve_specs(
    names: Sequence[str],
    spec_registry: Dict[str, EmitterSpec],
    category: str,
) -> List[EmitterSpec]:
    resolved: List[EmitterSpec] = []
    for name in names:
        spec = spec_registry.get(name)
        if spec is None:
            _logger.warning(
                "Emitter '%s' referenced in %s override is not registered",
                name,
                category,
            )
            continue
        resolved.append(spec)
    return resolved


__all__ = ["CaptureControl", "build_emitter_pipeline"]
