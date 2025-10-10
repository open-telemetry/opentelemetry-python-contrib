from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping, Protocol, Sequence

from ..callbacks import CompletionCallback
from ..environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS,
    OTEL_INSTRUMENTATION_GENAI_EVALS_INTERVAL,
    OTEL_INSTRUMENTATION_GENAI_EVALS_RESULTS_AGGREGATION,
    OTEL_INSTRUMENTATION_GENAI_EVALUATION_SAMPLE_RATE,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..handler import TelemetryHandler
from opentelemetry.sdk.trace.sampling import Decision, TraceIdRatioBased

from ..types import (
    AgentInvocation,
    EmbeddingInvocation,
    EvaluationResult,
    GenAI,
    LLMInvocation,
    Task,
    ToolCall,
    Workflow,
)
from .base import Evaluator
from .registry import get_default_metrics, get_evaluator, list_evaluators

_LOGGER = logging.getLogger(__name__)


class Sampler(Protocol):
    def should_sample(self, invocation: GenAI) -> bool: ...


class _AllSampler:
    def should_sample(
        self, invocation: GenAI
    ) -> bool:  # pragma: no cover - trivial
        return True


@dataclass(frozen=True)
class MetricConfig:
    name: str
    options: Mapping[str, str]


@dataclass(frozen=True)
class EvaluatorPlan:
    name: str
    per_type: Mapping[str, Sequence[MetricConfig]]


_GENAI_TYPE_LOOKUP: Mapping[str, type[GenAI]] = {
    "LLMInvocation": LLMInvocation,
    "AgentInvocation": AgentInvocation,
    "EmbeddingInvocation": EmbeddingInvocation,
    "ToolCall": ToolCall,
    "Workflow": Workflow,
    "Task": Task,
}


class Manager(CompletionCallback):
    """Asynchronous evaluation manager implementing the completion callback."""

    def __init__(
        self,
        handler: "TelemetryHandler",
        *,
        interval: float | None = None,
        aggregate_results: bool | None = None,
    ) -> None:
        self._handler = handler
        evaluation_sample_rate = _read_evaluation_sample_rate()
        self._sampler = TraceIdRatioBased(evaluation_sample_rate)
        self._interval = interval if interval is not None else _read_interval()
        self._aggregate_results = (
            aggregate_results
            if aggregate_results is not None
            else _read_aggregation_flag()
        )
        self._plans = self._load_plans()
        self._evaluators = self._instantiate_evaluators(self._plans)
        self._queue: queue.Queue[GenAI] = queue.Queue()
        self._shutdown = threading.Event()
        self._worker: threading.Thread | None = None
        if self.has_evaluators:
            self._worker = threading.Thread(
                target=self._worker_loop,
                name="opentelemetry-genai-evaluator",
                daemon=True,
            )
            self._worker.start()

    # CompletionCallback -------------------------------------------------
    def on_completion(self, invocation: GenAI) -> None:
        if not self.has_evaluators:
            return
        if invocation.span.get_span_context().trace_id:
            try:
                sampling_result = self._sampler.should_sample(
                    trace_id=invocation.span.get_span_context().trace_id,
                    parent_context=None,
                    name="",
                )
                if (
                    sampling_result
                    and sampling_result.decision is Decision.RECORD_AND_SAMPLE
                ):
                    self.offer(invocation)
            except Exception:  # pragma: no cover - defensive
                _LOGGER.debug("Sampler raised an exception", exc_info=True)
        else:  # TODO remove else branch when trace_id is set on all invocations
            _LOGGER.debug(
                "Trace based sampling not applied as trace id is not set.",
                exc_info=True,
            )
            self.offer(invocation)

    # Public API ---------------------------------------------------------
    def offer(self, invocation: GenAI) -> None:
        """Enqueue an invocation for asynchronous evaluation."""

        if not self.has_evaluators:
            return
        try:
            self._queue.put_nowait(invocation)
        except Exception:  # pragma: no cover - defensive
            _LOGGER.debug(
                "Failed to enqueue invocation for evaluation", exc_info=True
            )

    def wait_for_all(self, timeout: float | None = None) -> None:
        if not self.has_evaluators:
            return
        if timeout is None:
            self._queue.join()
            return
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._queue.unfinished_tasks == 0:
                return
            time.sleep(0.05)

    def shutdown(self) -> None:
        if self._worker is None:
            return
        self._shutdown.set()
        self._worker.join(timeout=1.0)
        self._worker = None

    def evaluate_now(self, invocation: GenAI) -> list[EvaluationResult]:
        """Synchronously evaluate an invocation."""

        buckets = self._collect_results(invocation)
        flattened = self._emit_results(invocation, buckets)
        self._flag_invocation(invocation)
        return flattened

    @property
    def has_evaluators(self) -> bool:
        return any(self._evaluators.values())

    # Internal helpers ---------------------------------------------------
    def _worker_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                invocation = self._queue.get(timeout=self._interval)
            except queue.Empty:
                continue
            try:
                self._process_invocation(invocation)
            except Exception:  # pragma: no cover - defensive
                _LOGGER.exception("Evaluator processing failed")
            finally:
                self._queue.task_done()

    def _process_invocation(self, invocation: GenAI) -> None:
        if not self.has_evaluators:
            return
        buckets = self._collect_results(invocation)
        self._emit_results(invocation, buckets)
        self._flag_invocation(invocation)

    def _collect_results(
        self, invocation: GenAI
    ) -> Sequence[Sequence[EvaluationResult]]:
        if not self.has_evaluators:
            return ()
        type_name = type(invocation).__name__
        evaluators = self._evaluators.get(type_name, ())
        if not evaluators:
            return ()
        buckets: list[Sequence[EvaluationResult]] = []
        for descriptor in evaluators:
            try:
                results = descriptor.evaluate(invocation)
            except Exception as exc:  # pragma: no cover - defensive
                _LOGGER.debug("Evaluator %s failed: %s", descriptor, exc)
                continue
            if results:
                buckets.append(list(results))
        return buckets

    def _emit_results(
        self,
        invocation: GenAI,
        buckets: Sequence[Sequence[EvaluationResult]],
    ) -> list[EvaluationResult]:
        if not buckets:
            return []
        # Dynamic aggregation: allow enabling aggregation via env var after manager initialization.
        aggregate = self._aggregate_results or _read_aggregation_flag()
        if aggregate:
            aggregated: list[EvaluationResult] = []
            for bucket in buckets:
                aggregated.extend(bucket)
            if aggregated:
                self._handler.evaluation_results(invocation, aggregated)
            return aggregated
        for bucket in buckets:
            if bucket:
                self._handler.evaluation_results(invocation, list(bucket))
        flattened: list[EvaluationResult] = []
        for bucket in buckets:
            flattened.extend(bucket)
        return flattened

    def _flag_invocation(self, invocation: GenAI) -> None:
        if not self.has_evaluators:
            return
        attributes = getattr(invocation, "attributes", None)
        if isinstance(attributes, dict):
            attributes.setdefault("gen_ai.evaluation.executed", True)

    # Configuration ------------------------------------------------------
    def _load_plans(self) -> Sequence[EvaluatorPlan]:
        raw_value = _read_raw_evaluator_config()
        raw = (raw_value or "").strip()
        normalized = raw.lower()
        if normalized in {"none", "off", "false"}:
            _LOGGER.info(
                "GenAI evaluations disabled via %s",
                OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS,
            )
            return []
        if not raw:
            # Auto-discover defaults when no explicit config provided.
            plans = self._generate_default_plans()
            if not plans:
                _LOGGER.info(
                    "GenAI evaluations disabled (no defaults registered); set %s to enable specific evaluators",
                    OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS,
                )
            else:
                _LOGGER.debug(
                    "Auto-discovered evaluator default metrics: %s",
                    [p.name for p in plans],
                )
            return plans
        try:
            requested = _parse_evaluator_config(raw)
        except ValueError as exc:
            _LOGGER.warning(
                "Failed to parse evaluator configuration '%s': %s", raw, exc
            )
            return []
        available = {name.lower() for name in list_evaluators()}
        plans: list[EvaluatorPlan] = []
        for spec in requested:
            if spec.name.lower() not in available:
                _LOGGER.warning("Evaluator '%s' is not registered", spec.name)
                continue
            try:
                defaults = get_default_metrics(spec.name)
            except ValueError:
                defaults = {}
            per_type: dict[str, Sequence[MetricConfig]] = {}
            if spec.per_type:
                for type_name, metrics in spec.per_type.items():
                    per_type[type_name] = metrics
            else:
                per_type = {
                    key: [MetricConfig(name=m, options={}) for m in value]
                    for key, value in defaults.items()
                }
            if not per_type:
                _LOGGER.debug(
                    "Evaluator '%s' does not declare any metrics", spec.name
                )
                continue
            plans.append(
                EvaluatorPlan(
                    name=spec.name,
                    per_type=per_type,
                )
            )
        return plans

    def _instantiate_evaluators(
        self, plans: Sequence[EvaluatorPlan]
    ) -> Mapping[str, Sequence[Evaluator]]:
        evaluators_by_type: dict[str, list[Evaluator]] = {}
        for plan in plans:
            for type_name, metrics in plan.per_type.items():
                if type_name not in _GENAI_TYPE_LOOKUP:
                    _LOGGER.warning(
                        "Unsupported GenAI invocation type '%s' for evaluator '%s'",
                        type_name,
                        plan.name,
                    )
                    continue
                metric_names = [metric.name for metric in metrics]
                options: Mapping[str, Mapping[str, str]] = {
                    metric.name: metric.options
                    for metric in metrics
                    if metric.options
                }
                try:
                    evaluator = get_evaluator(
                        plan.name,
                        metric_names,
                        invocation_type=type_name,
                        options=options,
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    _LOGGER.warning(
                        "Evaluator '%s' failed to initialise for type '%s': %s",
                        plan.name,
                        type_name,
                        exc,
                    )
                    continue
                evaluators_by_type.setdefault(type_name, []).append(evaluator)
        return evaluators_by_type

    def _generate_default_plans(self) -> Sequence[EvaluatorPlan]:
        plans: list[EvaluatorPlan] = []
        available = list_evaluators()
        if not available:
            _LOGGER.info(
                "No evaluator entry points registered; skipping evaluations"
            )
            return plans
        for name in available:
            try:
                defaults = get_default_metrics(name)
            except ValueError:
                continue
            if not defaults:
                continue
            per_type: dict[str, Sequence[MetricConfig]] = {}
            for type_name, metrics in defaults.items():
                entries = [
                    MetricConfig(name=metric, options={}) for metric in metrics
                ]
                if entries:
                    per_type[type_name] = entries
            if not per_type:
                continue
            plans.append(EvaluatorPlan(name=name, per_type=per_type))
        if not plans:
            _LOGGER.warning(
                "No evaluators declared default metrics; set %s to an explicit list to enable evaluations",
                OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS,
            )
        return plans


# ---------------------------------------------------------------------------
# Environment parsing helpers


def _read_raw_evaluator_config() -> str | None:
    return _get_env(OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS)


def _read_interval() -> float:
    raw = _get_env(OTEL_INSTRUMENTATION_GENAI_EVALS_INTERVAL)
    if not raw:
        return 5.0
    try:
        return float(raw)
    except ValueError:  # pragma: no cover - defensive
        _LOGGER.warning(
            "Invalid value for %s: %s",
            OTEL_INSTRUMENTATION_GENAI_EVALS_INTERVAL,
            raw,
        )
        return 5.0


def _read_aggregation_flag() -> bool:
    raw = _get_env(OTEL_INSTRUMENTATION_GENAI_EVALS_RESULTS_AGGREGATION)
    if not raw:
        return False
    return raw.strip().lower() in {"1", "true", "yes"}


def _read_evaluation_sample_rate() -> float:
    raw = _get_env(OTEL_INSTRUMENTATION_GENAI_EVALUATION_SAMPLE_RATE)
    if raw is None or raw == "":
        return 1.0
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 1.0
    if value < 0.0 or value > 1.0:
        return 1.0
    return value


def _get_env(name: str) -> str | None:
    import os

    return os.environ.get(name)


# ---------------------------------------------------------------------------
# Evaluator configuration parser


@dataclass
class _EvaluatorSpec:
    name: str
    per_type: Mapping[str, Sequence[MetricConfig]]


class _ConfigParser:
    def __init__(self, text: str) -> None:
        self._text = text
        self._length = len(text)
        self._pos = 0

    def parse(self) -> Sequence[_EvaluatorSpec]:
        specs: list[_EvaluatorSpec] = []
        while True:
            self._skip_ws()
            if self._pos >= self._length:
                break
            specs.append(self._parse_evaluator())
            self._skip_ws()
            if self._pos >= self._length:
                break
            self._expect(",")
        return specs

    def _parse_evaluator(self) -> _EvaluatorSpec:
        name = self._parse_identifier()
        per_type: dict[str, Sequence[MetricConfig]] = {}
        self._skip_ws()
        if self._peek() == "(":
            self._advance()
            while True:
                self._skip_ws()
                type_name = self._parse_identifier()
                metrics: list[MetricConfig] = []
                self._skip_ws()
                if self._peek() == "(":
                    self._advance()
                    while True:
                        self._skip_ws()
                        metrics.append(self._parse_metric())
                        self._skip_ws()
                        char = self._peek()
                        if char == ",":
                            self._advance()
                            continue
                        if char == ")":
                            self._advance()
                            break
                        raise ValueError(
                            f"Unexpected character '{char}' while parsing metrics"
                        )
                per_type[type_name] = metrics
                self._skip_ws()
                char = self._peek()
                if char == ",":
                    self._advance()
                    continue
                if char == ")":
                    self._advance()
                    break
                raise ValueError(
                    f"Unexpected character '{char}' while parsing type configuration"
                )
        return _EvaluatorSpec(name=name, per_type=per_type)

    def _parse_metric(self) -> MetricConfig:
        name = self._parse_identifier()
        options: dict[str, str] = {}
        self._skip_ws()
        if self._peek() == "(":
            self._advance()
            while True:
                self._skip_ws()
                key = self._parse_identifier()
                self._skip_ws()
                self._expect("=")
                self._skip_ws()
                value = self._parse_value()
                options[key] = value
                self._skip_ws()
                char = self._peek()
                if char == ",":
                    self._advance()
                    continue
                if char == ")":
                    self._advance()
                    break
                raise ValueError(
                    f"Unexpected character '{char}' while parsing metric options"
                )
        return MetricConfig(name=name, options=options)

    def _parse_value(self) -> str:
        start = self._pos
        while self._pos < self._length and self._text[self._pos] not in {
            ",",
            ")",
        }:
            self._pos += 1
        value = self._text[start : self._pos].strip()
        if not value:
            raise ValueError("Metric option value cannot be empty")
        return value

    def _parse_identifier(self) -> str:
        self._skip_ws()
        start = self._pos
        while self._pos < self._length and (
            self._text[self._pos].isalnum() or self._text[self._pos] in {"_"}
        ):
            self._pos += 1
        if start == self._pos:
            raise ValueError("Expected identifier")
        return self._text[start : self._pos]

    def _skip_ws(self) -> None:
        while self._pos < self._length and self._text[self._pos].isspace():
            self._pos += 1

    def _expect(self, char: str) -> None:
        self._skip_ws()
        if self._peek() != char:
            raise ValueError(f"Expected '{char}'")
        self._advance()

    def _peek(self) -> str:
        if self._pos >= self._length:
            return ""
        return self._text[self._pos]

    def _advance(self) -> None:
        self._pos += 1


def _parse_evaluator_config(text: str) -> Sequence[EvaluatorPlan]:
    parser = _ConfigParser(text)
    specs = parser.parse()
    plans: list[EvaluatorPlan] = []
    for spec in specs:
        plans.append(
            EvaluatorPlan(
                name=spec.name,
                per_type=spec.per_type,
            )
        )
    return plans


__all__ = [
    "Manager",
    "Sampler",
    "MetricConfig",
]
