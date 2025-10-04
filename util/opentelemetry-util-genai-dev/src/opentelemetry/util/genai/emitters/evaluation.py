"""Emitters responsible for emitting telemetry derived from evaluation results."""

from __future__ import annotations

from typing import Any, Dict, Sequence

from opentelemetry import _events as _otel_events

from ..attributes import (
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

    def __init__(self, event_logger) -> None:
        self._event_logger = event_logger

    def on_evaluation_results(  # type: ignore[override]
        self,
        results: Sequence[EvaluationResult],
        obj: Any | None = None,
    ) -> None:
        invocation = obj if isinstance(obj, GenAI) else None
        if invocation is None or not results:
            return
        req_model = _get_request_model(invocation)
        provider = getattr(invocation, "provider", None)
        response_id = _get_response_id(invocation)

        for res in results:
            attrs: Dict[str, Any] = {
                GEN_AI_OPERATION_NAME: "evaluation",
                GEN_AI_EVALUATION_NAME: res.metric_name,
            }
            if req_model:
                attrs[GEN_AI_REQUEST_MODEL] = req_model
            if provider:
                attrs[GEN_AI_PROVIDER_NAME] = provider
            if response_id:
                attrs[GEN_AI_RESPONSE_ID] = response_id
            if isinstance(res.score, (int, float)):
                attrs[GEN_AI_EVALUATION_SCORE_VALUE] = res.score
            if res.label is not None:
                attrs[GEN_AI_EVALUATION_SCORE_LABEL] = res.label
            if res.error is not None:
                attrs["error.type"] = res.error.type.__qualname__
                attrs["error.message"] = res.error.message

            body: Dict[str, Any] = {}
            if res.explanation:
                body["gen_ai.evaluation.explanation"] = res.explanation
            if res.attributes:
                body["gen_ai.evaluation.attributes"] = dict(res.attributes)

            try:
                self._event_logger.emit(
                    _otel_events.Event(
                        name="gen_ai.evaluation",
                        attributes=attrs,
                        body=body or None,
                        span_id=(
                            getattr(
                                invocation.span.get_span_context(),
                                "span_id",
                                None,
                            )
                            if invocation.span
                            else None
                        ),
                        trace_id=(
                            getattr(
                                invocation.span.get_span_context(),
                                "trace_id",
                                None,
                            )
                            if invocation.span
                            else None
                        ),
                    )
                )
            except Exception:  # pragma: no cover
                pass


__all__ = [
    "EvaluationMetricsEmitter",
    "EvaluationEventsEmitter",
]
