"""Event emission helpers for GenAI instrumentation.

Provides thin wrappers around the OpenTelemetry event logger for
spec-defined GenAI events:

- gen_ai.client.inference.operation.details
- gen_ai.evaluation.result (helper only; actual evaluation may happen
  externally – e.g. offline evaluator script)

All GenAI events are emitted by default.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from opentelemetry._events import Event

OP_DETAILS_EVENT = "gen_ai.client.inference.operation.details"
EVAL_RESULT_EVENT = "gen_ai.evaluation.result"

# Attribute allowlist subset to avoid dumping huge blobs blindly.
# (Large content already controlled by capture-content env var.)
_OPERATION_DETAILS_CORE_KEYS = {
    "gen_ai.provider.name",
    "gen_ai.operation.name",
    "gen_ai.request.model",
    "gen_ai.response.id",
    "gen_ai.response.model",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "gen_ai.usage.total_tokens",
    "gen_ai.output.type",
    "gen_ai.system_instructions",
    "gen_ai.input.messages",
    "gen_ai.output.messages",
}

_MAX_VALUE_LEN = 4000  # defensive truncation


def emit_operation_details_event(
    event_logger,
    span_attributes: Dict[str, Any],
    otel_span: Optional[Any] = None,
) -> None:
    """Emit operation details event with span attributes.

    Args:
        event_logger: The event logger instance
        span_attributes: Dictionary of span attributes to include
        otel_span: Optional OpenTelemetry span for context
    """
    if not event_logger:
        return
    # Always enabled

    attrs: Dict[str, Any] = {}
    for k in _OPERATION_DETAILS_CORE_KEYS:
        if k in span_attributes:
            v = span_attributes[k]
            if isinstance(v, str) and len(v) > _MAX_VALUE_LEN:
                v = v[: _MAX_VALUE_LEN - 3] + "..."
            attrs[k] = v

    if not attrs:
        return

    try:
        event_logger.emit(
            Event(
                name=OP_DETAILS_EVENT,
                attributes=attrs,
            )
        )
    except Exception:  # pragma: no cover - defensive
        pass


def emit_evaluation_result_event(
    event_logger,
    *,
    name: str,
    score_value: Optional[float] = None,
    score_label: Optional[str] = None,
    explanation: Optional[str] = None,
    response_id: Optional[str] = None,
    error_type: Optional[str] = None,
) -> None:
    """Emit evaluation result event.

    Args:
        event_logger: The event logger instance
        name: Name of the evaluation metric
        score_value: Numeric score value
        score_label: Label for the score (e.g., "good", "bad")
        explanation: Explanation of the evaluation
        response_id: ID of the response being evaluated
        error_type: Type of error if evaluation failed
    """
    if not event_logger:
        return
    # Always enabled

    attrs: Dict[str, Any] = {"gen_ai.evaluation.name": name}
    if score_value is not None:
        attrs["gen_ai.evaluation.score.value"] = float(score_value)
    if score_label is not None:
        attrs["gen_ai.evaluation.score.label"] = score_label
    if explanation:
        attrs["gen_ai.evaluation.explanation"] = (
            explanation[:4000] if len(explanation) > 4000 else explanation
        )
    if response_id:
        attrs["gen_ai.response.id"] = response_id
    if error_type:
        attrs["error.type"] = error_type

    try:
        event_logger.emit(
            Event(
                name=EVAL_RESULT_EVENT,
                attributes=attrs,
            )
        )
    except Exception:  # pragma: no cover - defensive
        pass
