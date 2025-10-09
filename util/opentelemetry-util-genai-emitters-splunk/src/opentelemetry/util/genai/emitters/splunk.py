from __future__ import annotations

import logging
import re
from dataclasses import asdict
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from opentelemetry.sdk._logs._internal import LogRecord as SDKLogRecord
from opentelemetry.util.genai.attributes import (
    GEN_AI_EVALUATION_NAME,
    GEN_AI_EVALUATION_SCORE_LABEL,
)
from opentelemetry.util.genai.emitters.spec import EmitterSpec
from opentelemetry.util.genai.interfaces import EmitterMeta
from opentelemetry.util.genai.types import EvaluationResult, LLMInvocation

_LOGGER = logging.getLogger(__name__)

_EVENT_NAME_CONVERSATION = "gen_ai.splunk.conversation"
_EVENT_NAME_EVALUATIONS = "gen_ai.splunk.evaluations"
_METRIC_PREFIX = "gen_ai.evaluation.result."
_RANGE_ATTRIBUTE_KEYS = (
    "score_range",
    "range",
    "score-range",
    "scoreRange",
    "range_values",
)
_MIN_ATTRIBUTE_KEYS = (
    "range_min",
    "score_min",
    "min",
    "lower_bound",
    "lower",
)
_MAX_ATTRIBUTE_KEYS = (
    "range_max",
    "score_max",
    "max",
    "upper_bound",
    "upper",
)


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _parse_range_spec(value: Any) -> Optional[Tuple[float, float]]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        start = _to_float(value[0])
        end = _to_float(value[1])
        if start is not None and end is not None:
            return start, end
    if isinstance(value, Mapping):
        start = None
        end = None
        for key in ("min", "lower", "start", "from", "low"):
            if key in value:
                start = _to_float(value[key])
                break
        for key in ("max", "upper", "end", "to", "high"):
            if key in value:
                end = _to_float(value[key])
                break
        if start is not None and end is not None:
            return start, end
    if isinstance(value, str):
        matches = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", value)
        if len(matches) >= 2:
            start = _to_float(matches[0])
            end = _to_float(matches[1])
            if start is not None and end is not None:
                return start, end
    return None


def _extract_range(
    attributes: Mapping[str, Any],
) -> Optional[Tuple[float, float]]:
    for key in _RANGE_ATTRIBUTE_KEYS:
        if key in attributes:
            bounds = _parse_range_spec(attributes[key])
            if bounds is not None:
                return bounds
    start = None
    end = None
    for key in _MIN_ATTRIBUTE_KEYS:
        if key in attributes:
            start = _to_float(attributes[key])
            if start is not None:
                break
    for key in _MAX_ATTRIBUTE_KEYS:
        if key in attributes:
            end = _to_float(attributes[key])
            if end is not None:
                break
    if start is not None and end is not None:
        return start, end
    return None


def _sanitize_metric_suffix(name: str) -> str:
    sanitized = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()
    return sanitized or "unknown"


class SplunkConversationEventsEmitter(EmitterMeta):
    """Emit Splunk-friendly conversation events from GenAI invocations."""

    role = "content_event"
    name = "splunk_conversation_event"

    def __init__(
        self, event_logger: Any, capture_content: bool = False
    ) -> None:
        self._event_logger = event_logger
        self._capture_content = capture_content

    def handles(self, obj: Any) -> bool:
        return isinstance(obj, LLMInvocation)

    def on_start(self, obj: Any) -> None:
        return None

    def on_end(self, obj: Any) -> None:
        if not isinstance(obj, LLMInvocation):
            return
        if not self._capture_content or self._event_logger is None:
            return

        conversation = {
            "inputs": _coerce_messages(
                obj.input_messages, self._capture_content
            ),
            "outputs": _coerce_messages(
                obj.output_messages, self._capture_content
            ),
        }
        system_instruction = obj.attributes.get("system_instruction")
        if system_instruction:
            conversation["system_instruction"] = _coerce_iterable(
                system_instruction
            )

        span_context = obj.span.get_span_context() if obj.span else None
        span_attrs: Dict[str, Any] = {}
        if obj.span and hasattr(obj.span, "attributes"):
            try:
                span_attrs = dict(obj.span.attributes)  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - defensive
                span_attrs = {}

        if span_context and span_context.is_valid:
            span_attrs.setdefault("trace_id", f"{span_context.trace_id:032x}")
            span_attrs.setdefault("span_id", f"{span_context.span_id:016x}")

        body: Dict[str, Any] = {
            "conversation": conversation,
            "span": span_attrs,
        }
        attributes = {
            "event.name": _EVENT_NAME_CONVERSATION,
            "gen_ai.request.model": obj.request_model,
        }
        if obj.provider:
            attributes["gen_ai.provider.name"] = obj.provider

        record = SDKLogRecord(
            body=body,
            attributes=attributes,
            event_name=_EVENT_NAME_CONVERSATION,
        )
        try:
            self._event_logger.emit(record)
        except Exception:  # pragma: no cover - defensive
            pass

    def on_error(self, error: Any, obj: Any) -> None:
        return None

    def on_evaluation_results(
        self, results: Any, obj: Any | None = None
    ) -> None:
        return None


class SplunkEvaluationResultsEmitter(EmitterMeta):
    """Aggregate evaluation results for Splunk ingestion."""

    role = "evaluation_results"
    name = "splunk_evaluation_results"

    def __init__(
        self,
        event_logger: Any,
        meter: Any,
        capture_content: bool = False,
    ) -> None:
        self._event_logger = event_logger
        self._meter = meter
        self._capture_content = capture_content
        self._pending: Dict[
            int, List[Tuple[EvaluationResult, Optional[float], Optional[str]]]
        ] = {}
        self._histograms: Dict[str, Any] = {}

    def handles(self, obj: Any) -> bool:
        return isinstance(obj, LLMInvocation)

    def on_evaluation_results(
        self,
        results: Sequence[EvaluationResult],
        obj: Any | None = None,
    ) -> None:
        invocation = obj if isinstance(obj, LLMInvocation) else None
        if invocation is None or not results:
            return
        key = id(invocation)
        buffer = self._pending.setdefault(key, [])
        for result in results:
            normalized, range_label = self._compute_normalized_score(result)
            if normalized is not None:
                self._record_metric(result, normalized)
            buffer.append((result, normalized, range_label))

    def on_end(self, obj: Any) -> None:
        if isinstance(obj, LLMInvocation):
            self._emit_aggregated_event(obj)

    def on_error(self, error: Any, obj: Any) -> None:
        if isinstance(obj, LLMInvocation):
            self._emit_aggregated_event(obj)

    def _emit_aggregated_event(self, invocation: LLMInvocation) -> None:
        key = id(invocation)
        records = self._pending.pop(key, None)
        if not records or self._event_logger is None:
            return

        conversation: Dict[str, Any] = {
            "inputs": _coerce_messages(
                invocation.input_messages, self._capture_content
            ),
            "outputs": _coerce_messages(
                invocation.output_messages, self._capture_content
            ),
        }
        system_instruction = invocation.attributes.get(
            "system_instruction"
        ) or invocation.attributes.get("system_instructions")
        if not system_instruction and getattr(invocation, "system", None):
            system_instruction = invocation.system
        if system_instruction:
            conversation["system_instructions"] = _coerce_iterable(
                system_instruction
            )

        span_attrs: Dict[str, Any] = {}
        if invocation.span and hasattr(invocation.span, "attributes"):
            try:
                span_attrs = dict(invocation.span.attributes)  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - defensive
                span_attrs = {}
        span_context = (
            invocation.span.get_span_context() if invocation.span else None
        )
        if span_context and getattr(span_context, "is_valid", False):
            span_attrs.setdefault("trace_id", f"{span_context.trace_id:032x}")
            span_attrs.setdefault("span_id", f"{span_context.span_id:016x}")
        if invocation.request_model:
            span_attrs.setdefault(
                "gen_ai.request.model", invocation.request_model
            )
        if invocation.provider:
            span_attrs.setdefault("gen_ai.provider.name", invocation.provider)
        if getattr(invocation, "response_id", None):
            span_attrs.setdefault("gen_ai.response.id", invocation.response_id)

        body: Dict[str, Any] = {
            "conversation": conversation,
            "span": span_attrs,
            "evaluations": [
                self._serialize_result(result, normalized, range_label)
                for result, normalized, range_label in records
            ],
        }

        attributes = {"event.name": _EVENT_NAME_EVALUATIONS}
        if invocation.request_model:
            attributes["gen_ai.request.model"] = invocation.request_model
        if invocation.provider:
            attributes["gen_ai.provider.name"] = invocation.provider
        if getattr(invocation, "response_id", None):
            attributes["gen_ai.response.id"] = invocation.response_id

        record = SDKLogRecord(
            body=body,
            attributes=attributes,
            event_name=_EVENT_NAME_EVALUATIONS,
        )
        try:
            self._event_logger.emit(record)
        except Exception:  # pragma: no cover - defensive
            pass

    def _record_metric(self, result: EvaluationResult, value: float) -> None:
        if self._meter is None:
            return
        metric_name = (
            f"{_METRIC_PREFIX}{_sanitize_metric_suffix(result.metric_name)}"
        )
        histogram = self._histograms.get(metric_name)
        if histogram is None:
            description = f"Normalized evaluation score for metric '{result.metric_name}'"
            try:
                histogram = self._meter.create_histogram(
                    name=metric_name,
                    unit="1",
                    description=description,
                )
            except Exception as exc:  # pragma: no cover - defensive
                _LOGGER.debug(
                    "Failed to create histogram '%s': %s", metric_name, exc
                )
                return
            self._histograms[metric_name] = histogram
        attributes = {GEN_AI_EVALUATION_NAME: result.metric_name}
        if result.label is not None:
            attributes[GEN_AI_EVALUATION_SCORE_LABEL] = result.label
        try:
            histogram.record(value, attributes=attributes)
        except Exception as exc:  # pragma: no cover - defensive
            _LOGGER.debug(
                "Failed to record histogram '%s': %s", metric_name, exc
            )

    def _compute_normalized_score(
        self, result: EvaluationResult
    ) -> Tuple[Optional[float], Optional[str]]:
        score = result.score
        if not isinstance(score, (int, float)):
            return None, None
        score_f = float(score)
        if 0.0 <= score_f <= 1.0:
            return score_f, "[0,1]"
        attributes = result.attributes or {}
        bounds = _extract_range(attributes)
        if bounds is None:
            _LOGGER.debug(
                "Skipping metric for '%s': score %.3f outside [0,1] with no range",
                result.metric_name,
                score_f,
            )
            return None, None
        start, end = bounds
        if start is None or end is None or end <= start:
            _LOGGER.debug(
                "Invalid range %s for metric '%s'", bounds, result.metric_name
            )
            return None, None
        if start != 0:
            _LOGGER.debug(
                "Range for metric '%s' starts at %s (expected 0)",
                result.metric_name,
                start,
            )
        normalized = (score_f - start) / (end - start)
        if normalized < 0 or normalized > 1:
            _LOGGER.debug(
                "Score %.3f for metric '%s' outside range %s; clamping",
                score_f,
                result.metric_name,
                bounds,
            )
        normalized = max(0.0, min(1.0, normalized))
        return normalized, f"[{start},{end}]"

    def _serialize_result(
        self,
        result: EvaluationResult,
        normalized: Optional[float],
        range_label: Optional[str],
    ) -> Dict[str, Any]:
        entry: Dict[str, Any] = {"name": result.metric_name}
        if result.score is not None:
            entry["score"] = result.score
        if normalized is not None:
            entry["normalized_score"] = normalized
        if range_label:
            entry["range"] = range_label
        if result.label is not None:
            entry["label"] = result.label
        if result.explanation:
            entry["explanation"] = result.explanation
        if result.attributes:
            entry["attributes"] = dict(result.attributes)
        if result.error is not None:
            entry["error"] = {
                "type": result.error.type.__qualname__,
                "message": result.error.message,
            }
        return entry


def splunk_emitters() -> list[EmitterSpec]:
    def _conversation_factory(ctx):
        capture_mode = getattr(ctx, "capture_event_content", False)
        return SplunkConversationEventsEmitter(
            event_logger=ctx.event_logger, capture_content=capture_mode
        )

    def _evaluation_factory(ctx):
        capture_mode = getattr(ctx, "capture_event_content", False)
        return SplunkEvaluationResultsEmitter(
            event_logger=ctx.event_logger,
            meter=ctx.meter,
            capture_content=capture_mode,
        )

    return [
        EmitterSpec(
            name="SplunkConversationEvents",
            category="content_events",
            mode="replace-category",
            factory=_conversation_factory,
        ),
        EmitterSpec(
            name="SplunkEvaluationResults",
            category="evaluation",
            factory=_evaluation_factory,
        ),
    ]


def _coerce_messages(
    messages: Iterable[Any], capture_content: bool
) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for msg in messages or []:
        try:
            data = asdict(msg)
        except TypeError:
            data = dict(msg) if isinstance(msg, dict) else {"value": str(msg)}
        if not capture_content:
            for part in data.get("parts", []):
                if isinstance(part, dict) and "content" in part:
                    part["content"] = ""
        result.append(data)
    return result


def _coerce_iterable(values: Any) -> List[Any]:
    if isinstance(values, list):
        return values
    if isinstance(values, tuple):
        return list(values)
    if values is None:
        return []
    return [values]


__all__ = [
    "SplunkConversationEventsEmitter",
    "SplunkEvaluationResultsEmitter",
    "splunk_emitters",
]
