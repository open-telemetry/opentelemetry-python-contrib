"""Emitters responsible for emitting telemetry derived from evaluation results."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Protocol

from opentelemetry import _events as _otel_events
from opentelemetry.trace import Link, Tracer

from ..attributes import (
    GEN_AI_EVALUATION_NAME,
    GEN_AI_EVALUATION_SCORE_LABEL,
    GEN_AI_EVALUATION_SCORE_VALUE,
    GEN_AI_OPERATION_NAME,
    GEN_AI_PROVIDER_NAME,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_RESPONSE_ID,
)
from ..types import EvaluationResult, LLMInvocation


class EvaluationEmitter(Protocol):  # pragma: no cover - structural protocol
    def emit(
        self, results: List[EvaluationResult], invocation: LLMInvocation
    ) -> None: ...


class EvaluationMetricsEmitter:
    """Records evaluation scores to a unified histogram."""

    role = "evaluation_metrics"

    def __init__(
        self, histogram
    ):  # histogram: opentelemetry.metrics.Histogram
        self._hist = histogram

    def emit(
        self, results: List[EvaluationResult], invocation: LLMInvocation
    ) -> None:  # type: ignore[override]
        for res in results:
            if isinstance(res.score, (int, float)):
                attrs: Dict[str, Any] = {
                    GEN_AI_OPERATION_NAME: "evaluation",
                    GEN_AI_EVALUATION_NAME: res.metric_name,
                    GEN_AI_REQUEST_MODEL: invocation.request_model,
                }
                if invocation.provider:
                    attrs[GEN_AI_PROVIDER_NAME] = invocation.provider
                if res.label is not None:
                    attrs[GEN_AI_EVALUATION_SCORE_LABEL] = res.label
                if res.error is not None:
                    attrs["error.type"] = res.error.type.__qualname__
                # record numeric score
                try:
                    self._hist.record(res.score, attributes=attrs)  # type: ignore[attr-defined]
                except Exception:  # pragma: no cover - defensive
                    pass


class EvaluationEventsEmitter:
    """Emits a single gen_ai.evaluations event containing all results."""

    role = "evaluation_events"

    def __init__(self, event_logger):
        self._event_logger = event_logger

    def emit(
        self, results: List[EvaluationResult], invocation: LLMInvocation
    ) -> None:  # type: ignore[override]
        if not results:
            return
        evaluation_items: List[Dict[str, Any]] = []
        for res in results:
            item: Dict[str, Any] = {"gen_ai.evaluation.name": res.metric_name}
            if isinstance(res.score, (int, float)):
                item[GEN_AI_EVALUATION_SCORE_VALUE] = res.score
            if res.label is not None:
                item[GEN_AI_EVALUATION_SCORE_LABEL] = res.label
            if res.explanation:
                item["gen_ai.evaluation.explanation"] = res.explanation
            if res.error is not None:
                item["error.type"] = res.error.type.__qualname__
                item["error.message"] = res.error.message
            for k, v in res.attributes.items():
                item[k] = v
            evaluation_items.append(item)
        if not evaluation_items:
            return
        event_attrs: Dict[str, Any] = {
            GEN_AI_OPERATION_NAME: "evaluation",
            GEN_AI_REQUEST_MODEL: invocation.request_model,
        }
        if invocation.provider:
            event_attrs[GEN_AI_PROVIDER_NAME] = invocation.provider
        if invocation.response_id:
            event_attrs[GEN_AI_RESPONSE_ID] = invocation.response_id
        body = {"evaluations": evaluation_items}
        try:
            self._event_logger.emit(
                _otel_events.Event(
                    name="gen_ai.evaluations",
                    attributes=event_attrs,
                    body=body,
                    span_id=invocation.span.get_span_context().span_id
                    if invocation.span
                    else None,
                    trace_id=invocation.span.get_span_context().trace_id
                    if invocation.span
                    else None,
                )
            )
        except Exception:  # pragma: no cover
            pass


class EvaluationSpansEmitter:
    """Creates spans representing evaluation outcomes.

    span_mode: off | aggregated | per_metric
    """

    role = "evaluation_spans"

    def __init__(self, tracer: Tracer, span_mode: str):
        self._tracer = tracer
        self._mode = span_mode

    def emit(
        self, results: List[EvaluationResult], invocation: LLMInvocation
    ) -> None:  # type: ignore[override]
        if not results or self._mode == "off":
            return
        # Build items like event emitter does (without re-duplicating code). Minimal reconstruction.
        evaluation_items: List[Dict[str, Any]] = []
        for res in results:
            item: Dict[str, Any] = {"gen_ai.evaluation.name": res.metric_name}
            if isinstance(res.score, (int, float)):
                item[GEN_AI_EVALUATION_SCORE_VALUE] = res.score
            if res.label is not None:
                item[GEN_AI_EVALUATION_SCORE_LABEL] = res.label
            if res.error is not None:
                item["error.type"] = res.error.type.__qualname__
            evaluation_items.append(item)
        parent_link = None
        if invocation.span:
            try:
                parent_link = Link(
                    invocation.span.get_span_context(),
                    attributes={GEN_AI_OPERATION_NAME: "chat"},
                )
            except Exception:  # pragma: no cover
                parent_link = None
        if self._mode == "aggregated":
            from statistics import mean

            numeric_scores = [
                it.get(GEN_AI_EVALUATION_SCORE_VALUE)
                for it in evaluation_items
                if isinstance(
                    it.get(GEN_AI_EVALUATION_SCORE_VALUE), (int, float)
                )
            ]
            with self._tracer.start_as_current_span(
                "evaluation", links=[parent_link] if parent_link else None
            ) as span:
                span.set_attribute(GEN_AI_OPERATION_NAME, "evaluation")
                span.set_attribute(
                    GEN_AI_REQUEST_MODEL, invocation.request_model
                )
                if invocation.provider:
                    span.set_attribute(
                        GEN_AI_PROVIDER_NAME, invocation.provider
                    )
                span.set_attribute(
                    "gen_ai.evaluation.count", len(evaluation_items)
                )
                if numeric_scores:
                    span.set_attribute(
                        "gen_ai.evaluation.score.min", min(numeric_scores)
                    )
                    span.set_attribute(
                        "gen_ai.evaluation.score.max", max(numeric_scores)
                    )
                    span.set_attribute(
                        "gen_ai.evaluation.score.avg", mean(numeric_scores)
                    )
                span.set_attribute(
                    "gen_ai.evaluation.names",
                    [it["gen_ai.evaluation.name"] for it in evaluation_items],
                )
        elif self._mode == "per_metric":
            for item in evaluation_items:
                name = item.get("gen_ai.evaluation.name", "unknown")
                span_name = f"evaluation.{name}"
                with self._tracer.start_as_current_span(
                    span_name, links=[parent_link] if parent_link else None
                ) as span:
                    span.set_attribute(GEN_AI_OPERATION_NAME, "evaluation")
                    span.set_attribute(GEN_AI_EVALUATION_NAME, name)
                    span.set_attribute(
                        GEN_AI_REQUEST_MODEL, invocation.request_model
                    )
                    if invocation.provider:
                        span.set_attribute(
                            GEN_AI_PROVIDER_NAME, invocation.provider
                        )
                    if GEN_AI_EVALUATION_SCORE_VALUE in item:
                        span.set_attribute(
                            GEN_AI_EVALUATION_SCORE_VALUE,
                            item[GEN_AI_EVALUATION_SCORE_VALUE],
                        )
                    if GEN_AI_EVALUATION_SCORE_LABEL in item:
                        span.set_attribute(
                            GEN_AI_EVALUATION_SCORE_LABEL,
                            item[GEN_AI_EVALUATION_SCORE_LABEL],
                        )
                    if "error.type" in item:
                        span.set_attribute("error.type", item["error.type"])


class CompositeEvaluationEmitter:
    """Fan-out evaluation results to an ordered list of evaluation emitters."""

    def __init__(self, emitters: Iterable[EvaluationEmitter]):
        self._emitters: List[EvaluationEmitter] = list(emitters)

    def emit(
        self, results: List[EvaluationResult], invocation: LLMInvocation
    ) -> None:
        for em in self._emitters:
            try:
                em.emit(results, invocation)
            except Exception:  # pragma: no cover
                pass


__all__ = [
    "EvaluationEmitter",
    "EvaluationMetricsEmitter",
    "EvaluationEventsEmitter",
    "EvaluationSpansEmitter",
    "CompositeEvaluationEmitter",
]
