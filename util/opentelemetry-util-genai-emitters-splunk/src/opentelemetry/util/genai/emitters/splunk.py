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
    cast,
)

from opentelemetry.sdk._logs._internal import LogRecord as SDKLogRecord

# NOTE: We intentionally rely on the core ("original") evaluation metrics emitter
# for recording canonical evaluation metrics. The Splunk emitters now focus solely
# on providing a custom aggregated event schema for evaluation results and do NOT
# emit their own metrics to avoid duplication or confusion.
from opentelemetry.util.genai.emitters.spec import EmitterSpec
from opentelemetry.util.genai.emitters.utils import (
    _agent_to_log_record,
    _llm_invocation_to_log_record,
)
from opentelemetry.util.genai.interfaces import EmitterMeta
from opentelemetry.util.genai.types import (
    AgentInvocation,
    EvaluationResult,
    LLMInvocation,
)

_LOGGER = logging.getLogger(__name__)

_EVENT_NAME_EVALUATIONS = "gen_ai.splunk.evaluations"
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


# _sanitize_metric_suffix retained historically; removed after metrics pruning.


class SplunkConversationEventsEmitter(EmitterMeta):
    """Emit semantic-convention conversation / invocation events for LLM & Agent.

    Backward compatibility with the older custom 'gen_ai.splunk.conversation' event
    has been intentionally removed in this development branch.
    """

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
        if self._event_logger is None:
            return
        # Emit semantic convention-aligned events for LLM & Agent invocations.
        if isinstance(obj, LLMInvocation):
            try:
                rec = _llm_invocation_to_log_record(obj, self._capture_content)
                if rec:
                    self._event_logger.emit(rec)
            except Exception:  # pragma: no cover - defensive
                pass
        elif isinstance(obj, AgentInvocation):
            try:
                rec = _agent_to_log_record(obj, self._capture_content)
                if rec:
                    self._event_logger.emit(rec)
            except Exception:  # pragma: no cover - defensive
                pass

    def on_error(self, error: Any, obj: Any) -> None:
        return None

    def on_evaluation_results(
        self, results: Any, obj: Any | None = None
    ) -> None:
        return None


class SplunkEvaluationResultsEmitter(EmitterMeta):
    """Aggregate evaluation results for Splunk ingestion (events only).

    Metrics emission has been removed; canonical evaluation metrics are handled
    by the core evaluation metrics emitter. This class now buffers evaluation
    results per invocation and emits a single aggregated event at invocation end.
    """

    role = "evaluation_results"
    name = "splunk_evaluation_results"

    def __init__(
        self,
        event_logger: Any,
        capture_content: bool = False,
        *_deprecated_args: Any,  # backward compatibility (accept ignored meter)
        **_deprecated_kwargs: Any,
    ) -> None:
        self._event_logger = event_logger
        self._capture_content = capture_content
        self._pending: Dict[
            int, List[Tuple[EvaluationResult, Optional[float], Optional[str]]]
        ] = {}
        # Track invocations whose lifecycle end has already fired so that
        # late-arriving evaluation results (e.g., async evaluators completing
        # after model response) still get emitted immediately.
        self._ended: set[int] = set()

    def handles(self, obj: Any) -> bool:
        return isinstance(obj, LLMInvocation)

    # Explicit no-op implementations to satisfy emitter protocol expectations
    def on_start(self, obj: Any) -> None:  # pragma: no cover - no-op
        return None

    def on_error(
        self, error: Any, obj: Any
    ) -> None:  # pragma: no cover - delegate to end emission for safety
        if isinstance(obj, LLMInvocation):
            self._emit_aggregated_event(obj)
            self._ended.add(id(obj))

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
            # We retain normalization purely for event enrichment; no metrics recorded.
            normalized, range_label = self._compute_normalized_score(result)
            buffer.append((result, normalized, range_label))
        # If the invocation already ended, flush immediately so results are not stranded.
        if key in self._ended:
            self._emit_aggregated_event(invocation)

    def on_end(self, obj: Any) -> None:
        if isinstance(obj, LLMInvocation):
            self._emit_aggregated_event(obj)

    # on_error handled above

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
        resp_id = getattr(invocation, "response_id", None)
        if isinstance(resp_id, str) and resp_id:
            span_attrs.setdefault("gen_ai.response.id", resp_id)

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
        if isinstance(resp_id, str) and resp_id:
            attributes["gen_ai.response.id"] = resp_id

        record = SDKLogRecord(
            body=body,
            attributes=attributes,
            event_name=_EVENT_NAME_EVALUATIONS,
        )
        try:
            self._event_logger.emit(record)
        except Exception:  # pragma: no cover - defensive
            pass

    # _record_metric removed (metrics no longer emitted)

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
        # start/end are floats here; retain defensive shape check
        if end <= start:
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
    def _conversation_factory(ctx: Any) -> SplunkConversationEventsEmitter:
        capture_mode = getattr(ctx, "capture_event_content", False)
        return SplunkConversationEventsEmitter(
            event_logger=getattr(ctx, "event_logger", None),
            capture_content=cast(bool, capture_mode),
        )

    def _evaluation_factory(ctx: Any) -> SplunkEvaluationResultsEmitter:
        capture_mode = getattr(ctx, "capture_event_content", False)
        return SplunkEvaluationResultsEmitter(
            event_logger=getattr(ctx, "event_logger", None),
            capture_content=cast(bool, capture_mode),
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
        data: Dict[str, Any]
        try:
            data = asdict(msg)  # type: ignore[assignment]
        except TypeError:
            if isinstance(msg, dict):
                data = cast(Dict[str, Any], dict(msg))  # type: ignore[arg-type]
            else:
                data = {"value": str(msg)}
        if not capture_content:
            parts = data.get("parts", [])
            for part in parts:
                if isinstance(part, dict) and "content" in part:
                    part["content"] = ""
        result.append(data)
    return result


def _coerce_iterable(values: Any) -> List[Any]:
    if isinstance(values, list):
        return cast(List[Any], values)
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
