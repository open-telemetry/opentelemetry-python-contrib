"""Emitters responsible for emitting telemetry derived from evaluation results."""

from __future__ import annotations

from typing import Any, Dict, Sequence

from opentelemetry import _events as _otel_events

from ..attributes import (
    GEN_AI_EVALUATION_ATTRIBUTES_PREFIX,
    GEN_AI_EVALUATION_EXPLANATION,
    GEN_AI_EVALUATION_NAME,
    GEN_AI_EVALUATION_SCORE_LABEL,
    GEN_AI_EVALUATION_SCORE_VALUE,
    GEN_AI_OPERATION_NAME,
    GEN_AI_PROVIDER_NAME,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_RESPONSE_ID,
)
from ..interfaces import EmitterMeta
from ..types import EvaluationResult, GenAI


def _get_request_model(invocation: GenAI) -> str | None:
    return getattr(invocation, "request_model", None) or getattr(
        invocation, "model", None
    )


def _get_response_id(invocation: GenAI) -> str | None:  # best-effort
    return getattr(invocation, "response_id", None)


class _EvaluationEmitterBase(EmitterMeta):
    role = "evaluation"

    def on_start(self, obj: Any) -> None:  # pragma: no cover - default no-op
        return None

    def on_end(self, obj: Any) -> None:  # pragma: no cover - default no-op
        return None

    def on_error(
        self, error, obj: Any
    ) -> None:  # pragma: no cover - default no-op
        return None


class EvaluationMetricsEmitter(_EvaluationEmitterBase):
    """Records evaluation scores to a unified histogram."""

    role = "evaluation_metrics"

    def __init__(
        self, histogram
    ) -> None:  # histogram: opentelemetry.metrics.Histogram
        self._hist = histogram

    def on_evaluation_results(  # type: ignore[override]
        self,
        results: Sequence[EvaluationResult],
        obj: Any | None = None,
    ) -> None:
        invocation = obj if isinstance(obj, GenAI) else None
        if invocation is None:
            return
        for res in results:
            if isinstance(res.score, (int, float)):
                attrs: Dict[str, Any] = {
                    GEN_AI_OPERATION_NAME: "evaluation",
                    GEN_AI_EVALUATION_NAME: res.metric_name,
                }
                req_model = _get_request_model(invocation)
                if req_model:
                    attrs[GEN_AI_REQUEST_MODEL] = req_model
                provider = getattr(invocation, "provider", None)
                if provider:
                    attrs[GEN_AI_PROVIDER_NAME] = provider
                if res.label is not None:
                    attrs[GEN_AI_EVALUATION_SCORE_LABEL] = res.label
                if res.error is not None:
                    attrs["error.type"] = res.error.type.__qualname__
                try:
                    self._hist.record(res.score, attributes=attrs)  # type: ignore[attr-defined]
                except Exception:  # pragma: no cover - defensive
                    pass


class EvaluationEventsEmitter(_EvaluationEmitterBase):
    """Emits one event per evaluation result."""

    role = "evaluation_events"

    def __init__(
        self, event_logger, *, emit_legacy_event: bool = False
    ) -> None:
        self._event_logger = event_logger
        self._emit_legacy_event = emit_legacy_event
        self._primary_event_name = "gen_ai.evaluation.result"
        self._legacy_event_name = "gen_ai.evaluation"

    def on_evaluation_results(  # type: ignore[override]
        self,
        results: Sequence[EvaluationResult],
        obj: Any | None = None,
    ) -> None:
        if self._event_logger is None:
            return
        invocation = obj if isinstance(obj, GenAI) else None
        if invocation is None or not results:
            return

        req_model = _get_request_model(invocation)
        provider = getattr(invocation, "provider", None)
        response_id = _get_response_id(invocation)

        span_context = None
        if getattr(invocation, "span", None) is not None:
            try:
                span_context = invocation.span.get_span_context()
            except Exception:  # pragma: no cover - defensive
                span_context = None
        span_id = (
            getattr(span_context, "span_id", None)
            if span_context is not None
            else None
        )
        trace_id = (
            getattr(span_context, "trace_id", None)
            if span_context is not None
            else None
        )

        for res in results:
            base_attrs: Dict[str, Any] = {
                GEN_AI_OPERATION_NAME: "evaluation",
                GEN_AI_EVALUATION_NAME: res.metric_name,
            }
            if req_model:
                base_attrs[GEN_AI_REQUEST_MODEL] = req_model
            if provider:
                base_attrs[GEN_AI_PROVIDER_NAME] = provider
            if response_id:
                base_attrs[GEN_AI_RESPONSE_ID] = response_id
            if isinstance(res.score, (int, float)):
                base_attrs[GEN_AI_EVALUATION_SCORE_VALUE] = res.score
            if res.label is not None:
                base_attrs[GEN_AI_EVALUATION_SCORE_LABEL] = res.label
            if res.error is not None:
                base_attrs["error.type"] = res.error.type.__qualname__

            spec_attrs = dict(base_attrs)
            if res.explanation:
                spec_attrs[GEN_AI_EVALUATION_EXPLANATION] = res.explanation
            if res.attributes:
                for key, value in dict(res.attributes).items():
                    key_str = str(key)
                    spec_attrs[
                        f"{GEN_AI_EVALUATION_ATTRIBUTES_PREFIX}{key_str}"
                    ] = value
            if res.error is not None and getattr(res.error, "message", None):
                spec_attrs[
                    f"{GEN_AI_EVALUATION_ATTRIBUTES_PREFIX}error.message"
                ] = res.error.message

            try:
                self._event_logger.emit(
                    _otel_events.Event(
                        name=self._primary_event_name,
                        attributes=spec_attrs,
                        span_id=span_id,
                        trace_id=trace_id,
                    )
                )
            except Exception:  # pragma: no cover - defensive
                pass

            if not self._emit_legacy_event:
                continue

            legacy_attrs = dict(base_attrs)
            legacy_body: Dict[str, Any] = {}
            if res.explanation:
                legacy_body["gen_ai.evaluation.explanation"] = res.explanation
            if res.attributes:
                legacy_body["gen_ai.evaluation.attributes"] = dict(
                    res.attributes
                )
            if res.error is not None and getattr(res.error, "message", None):
                legacy_attrs["error.message"] = res.error.message

            try:
                self._event_logger.emit(
                    _otel_events.Event(
                        name=self._legacy_event_name,
                        attributes=legacy_attrs,
                        body=legacy_body or None,
                        span_id=span_id,
                        trace_id=trace_id,
                    )
                )
            except Exception:  # pragma: no cover - defensive
                pass


__all__ = [
    "EvaluationMetricsEmitter",
    "EvaluationEventsEmitter",
]
