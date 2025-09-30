from __future__ import annotations

import importlib
import time
from threading import Event, Thread
from typing import List, Optional

from opentelemetry import _events as _otel_events
from opentelemetry.trace import Tracer

from ..config import Settings
from ..types import Error, EvaluationResult, LLMInvocation
from .base import Evaluator
from .evaluation_emitters import (
    CompositeEvaluationEmitter,
    EvaluationEventsEmitter,
    EvaluationMetricsEmitter,
    EvaluationSpansEmitter,
)
from .registry import get_evaluator, register_evaluator

# NOTE: Type checker warns about heterogeneous list (metrics + events + spans) passed
# to CompositeEvaluationEmitter due to generic inference; safe at runtime.


class EvaluationManager:
    """Coordinates evaluator discovery, execution, and telemetry emission.

    Evaluation manager will check evaluators registered in

    New capabilities:
      * Asynchronous sampling pipeline: ``offer(invocation)`` enqueues sampled invocations.
      * Background thread drains evaluator-specific queues every ``settings.evaluation_interval`` seconds.
      * Synchronous ``evaluate_llm`` retained for on-demand (immediate) evaluation (e.g., legacy tests / explicit calls).
    """

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
        self._histogram = histogram
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
        self._instances: dict[str, Evaluator] = {}
        self._stop = Event()
        self._thread: Thread | None = None
        if settings.evaluation_enabled:
            # Prime instances for configured evaluators
            for name in settings.evaluation_evaluators:
                self._get_instance(name)
            self._thread = Thread(
                target=self._loop, name="genai-eval-worker", daemon=True
            )
            self._thread.start()

    # ---------------- Internal utilities ----------------
    def _loop(self):  # pragma: no cover - timing driven
        interval = max(0.5, float(self._settings.evaluation_interval or 5.0))
        while not self._stop.is_set():
            try:
                self.process_once()
            except Exception:
                pass
            self._stop.wait(interval)

    def shutdown(self):  # pragma: no cover - optional
        self._stop.set()
        if self._thread and self._thread.is_alive():
            try:
                self._thread.join(timeout=1.5)
            except Exception:
                pass

    def _get_instance(self, name: str) -> Evaluator | None:
        key = name.lower()
        inst = self._instances.get(key)
        if inst is not None:
            return inst
        # try dynamic (deepeval) first for this name
        if key == "deepeval":
            try:
                ext_mod = importlib.import_module(
                    "opentelemetry.util.genai.evals.deepeval"
                )
                if hasattr(ext_mod, "DeepEvalEvaluator"):
                    register_evaluator(
                        "deepeval",
                        lambda: ext_mod.DeepEvalEvaluator(
                            self._event_logger, self._tracer
                        ),
                    )
            except Exception:
                pass
        try:
            factory_inst = get_evaluator(name)
        except Exception:
            # attempt builtin lazy import
            try:
                import importlib as _imp
                import sys

                mod_name = "opentelemetry.util.genai.evaluators.builtins"
                if mod_name in sys.modules:
                    _imp.reload(sys.modules[mod_name])
                else:
                    _imp.import_module(mod_name)
                factory_inst = get_evaluator(name)
            except Exception:
                return None
        self._instances[key] = factory_inst
        return factory_inst

    def _emit(
        self, results: list[EvaluationResult], invocation: LLMInvocation
    ):
        if not results:
            return
        self._emitter.emit(results, invocation)

    # ---------------- Public async API ----------------
    def offer(
        self, invocation: LLMInvocation, evaluators: list[str] | None = None
    ) -> dict[str, bool]:
        """Attempt to enqueue invocation for each evaluator; returns sampling map.

        Does not perform evaluation; background worker processes queues.
        """
        sampling: dict[str, bool] = {}
        if not self._settings.evaluation_enabled:
            return sampling
        names = (
            evaluators
            if evaluators is not None
            else self._settings.evaluation_evaluators
        )
        if not names:
            return sampling
        for name in names:
            inst = self._get_instance(name)
            if inst is None:
                sampling[name] = False
                continue
            try:
                sampled = inst.evaluate(
                    invocation,
                    max_per_minute=self._settings.evaluation_max_per_minute,
                )
                sampling[name] = sampled
            except Exception:
                sampling[name] = False
        return sampling

    def process_once(self):
        """Drain queues for each evaluator and emit results (background)."""
        if not self._settings.evaluation_enabled:
            return
        for name, inst in list(self._instances.items()):
            try:
                batch = inst._drain_queue()  # type: ignore[attr-defined]
            except Exception:
                batch = []
            for inv in batch:
                try:
                    out = inst.evaluate_invocation(inv)
                    if isinstance(out, list):
                        results = [
                            r for r in out if isinstance(r, EvaluationResult)
                        ]
                    else:
                        results = (
                            [out] if isinstance(out, EvaluationResult) else []
                        )
                except Exception as exc:
                    results = [
                        EvaluationResult(
                            metric_name=name,
                            error=Error(message=str(exc), type=type(exc)),
                        )
                    ]
                self._emit(results, inv)

    # ---------------- Synchronous (legacy / on-demand) ----------------
    def evaluate(
        self, invocation: LLMInvocation, evaluators: Optional[List[str]] = None
    ) -> List[EvaluationResult]:
        """Immediate evaluation (legacy path). Returns list of EvaluationResult.

        This is separate from asynchronous sampling. It does *not* affect evaluator queues.
        """
        if not self._settings.evaluation_enabled:
            return []
        names = (
            evaluators
            if evaluators is not None
            else self._settings.evaluation_evaluators
        )
        if not names:
            return []
        if invocation.end_time is None:
            invocation.end_time = time.time()
        results: List[EvaluationResult] = []
        for name in names:
            inst = self._get_instance(name)
            if inst is None:
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
                out = inst.evaluate_invocation(invocation)
                if isinstance(out, list):
                    for r in out:
                        if isinstance(r, EvaluationResult):
                            results.append(r)
                elif isinstance(out, EvaluationResult):
                    results.append(out)
                else:
                    results.append(
                        EvaluationResult(
                            metric_name=name,
                            error=Error(
                                message="Evaluator returned unsupported type",
                                type=TypeError,
                            ),
                        )
                    )
            except Exception as exc:
                results.append(
                    EvaluationResult(
                        metric_name=name,
                        error=Error(message=str(exc), type=type(exc)),
                    )
                )
        # Emit telemetry for this synchronous batch
        if results:
            self._emit(results, invocation)
        return results

    # Backwards compatibility alias
    evaluate_llm = evaluate


__all__ = ["EvaluationManager"]
