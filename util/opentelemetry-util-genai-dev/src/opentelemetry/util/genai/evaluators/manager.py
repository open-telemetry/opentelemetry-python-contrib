from __future__ import annotations

import logging
import time
from typing import Dict, Iterable, Sequence

from opentelemetry import _events as _otel_events
from opentelemetry.trace import Tracer

from ..config import Settings
from ..types import Error, EvaluationResult, GenAI, LLMInvocation
from .base import Evaluator
from .evaluation_emitters import (
    CompositeEvaluationEmitter,
    EvaluationEventsEmitter,
    EvaluationMetricsEmitter,
    EvaluationSpansEmitter,
)
from .registry import get_evaluator

_logger = logging.getLogger(__name__)


class EvaluationManager:
    """Coordinates evaluator discovery, execution, and telemetry emission."""

    def __init__(
        self,
        settings: Settings,
        tracer: Tracer,
        event_logger: _otel_events.EventLogger,  # type: ignore[attr-defined]
        histogram,  # opentelemetry.metrics.Histogram
    ) -> None:
        self._settings = settings
        self._tracer = tracer
        self._event_logger = event_logger
        emitters = [
            EvaluationMetricsEmitter(histogram),
            EvaluationEventsEmitter(event_logger),
        ]
        if settings.evaluation_span_mode in ("aggregated", "per_metric"):
            emitters.append(
                EvaluationSpansEmitter(
                    tracer=tracer, span_mode=settings.evaluation_span_mode
                )
            )
        self._emitter = CompositeEvaluationEmitter(emitters)  # type: ignore[arg-type]
        (
            self._configured_names,
            self._configured_metrics,
        ) = self._normalise_configuration(settings.evaluation_evaluators)
        self._instances: Dict[str, Evaluator] = {}

    # ------------------------------------------------------------------
    @staticmethod
    def _normalise_configuration(
        raw: Iterable[str],
    ) -> tuple[list[str], dict[str, Sequence[str]]]:
        names: list[str] = []
        metrics: dict[str, Sequence[str]] = {}
        seen: set[str] = set()
        for token in raw:
            candidate = token.strip()
            if not candidate:
                continue
            metrics_part: Sequence[str] = ()
            name = candidate
            if candidate.endswith(")") and "(" in candidate:
                prefix, _, suffix = candidate.partition("(")
                name = prefix.strip()
                metrics_part = [
                    item.strip()
                    for item in suffix[:-1].split(",")
                    if item.strip()
                ]
            elif ":" in candidate:
                prefix, _, suffix = candidate.partition(":")
                name = prefix.strip()
                metrics_part = [
                    item.strip()
                    for item in suffix.split(",")
                    if item.strip()
                ]
            if not name:
                continue
            key = name.lower()
            if metrics_part:
                metrics[key] = tuple(metrics_part)
            if key in seen:
                continue
            seen.add(key)
            names.append(name)
        return names, metrics

    def _get_instance(self, name: str) -> Evaluator | None:
        key = name.lower()
        inst = self._instances.get(key)
        if inst is not None:
            return inst
        metrics = self._configured_metrics.get(key)
        try:
            inst = get_evaluator(name, metrics)
        except ValueError:
            _logger.debug("Evaluator '%s' is not registered", name)
            return None
        except Exception as exc:  # pragma: no cover - defensive
            _logger.warning(
                "Evaluator '%s' failed to initialize: %s", name, exc
            )
            return None
        self._instances[key] = inst
        return inst

    def should_evaluate(
        self, invocation: GenAI, evaluators: Sequence[str] | None = None
    ) -> bool:
        if not self._settings.evaluation_enabled:
            return False
        if not isinstance(invocation, LLMInvocation):
            return False
        names = (
            list(evaluators)
            if evaluators is not None
            else self._configured_names
        )
        return bool(names)

    def offer(
        self, invocation: GenAI, evaluators: Sequence[str] | None = None
    ) -> bool:
        if not self.should_evaluate(invocation, evaluators):
            return False
        results = self.evaluate(invocation, evaluators)
        return bool(results)

    def evaluate(
        self, invocation: GenAI, evaluators: Sequence[str] | None = None
    ) -> list[EvaluationResult]:
        if not isinstance(invocation, LLMInvocation):
            return []
        if not self._settings.evaluation_enabled:
            return []
        names = (
            list(evaluators)
            if evaluators is not None
            else self._configured_names
        )
        if not names:
            return []
        if invocation.end_time is None:
            invocation.end_time = time.time()
        results: list[EvaluationResult] = []
        for name in names:
            if not name:
                continue
            evaluator = self._get_instance(name)
            if evaluator is None:
                results.append(
                    EvaluationResult(
                        metric_name=name,
                        error=Error(
                            message=f"Unknown evaluator: {name}",
                            type=LookupError,
                        ),
                    )
                )
                continue
            try:
                raw_results = evaluator.evaluate(invocation)
            except Exception as exc:  # pragma: no cover - defensive
                results.append(
                    EvaluationResult(
                        metric_name=name,
                        error=Error(message=str(exc), type=type(exc)),
                    )
                )
                continue
            results.extend(self._normalise_results(name, raw_results))
        if results:
            self._emitter.emit(results, invocation)
        return results

    @staticmethod
    def _normalise_results(
        evaluator_name: str, raw_results
    ) -> list[EvaluationResult]:
        if raw_results is None:
            return []
        if isinstance(raw_results, EvaluationResult):
            raw_results = [raw_results]
        normalised: list[EvaluationResult] = []
        for res in raw_results:
            if not isinstance(res, EvaluationResult):
                continue
            if not res.metric_name:
                res.metric_name = evaluator_name
            normalised.append(res)
        return normalised

    # Compatibility shim for legacy tests expecting background worker cleanup.
    def shutdown(self) -> None:  # pragma: no cover - legacy no-op
        """Retained for backward compatibility; no background worker to stop."""
        return None

    # Backwards compatibility alias
    evaluate_llm = evaluate


__all__ = ["EvaluationManager"]
