from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Iterable, List

from opentelemetry.sdk._logs._internal import LogRecord as SDKLogRecord
from opentelemetry.util.genai.emitters.metrics import MetricsEmitter
from opentelemetry.util.genai.emitters.span import SpanEmitter
from opentelemetry.util.genai.plugins import PluginEmitterBundle
from opentelemetry.util.genai.types import LLMInvocation


class SplunkConversationEventsEmitter:
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

    def start(self, obj: Any) -> None:
        return None

    def finish(self, obj: Any) -> None:
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
        event_name = "gen_ai.splunk.conversation"
        attributes = {
            "event.name": event_name,
            "gen_ai.request.model": obj.request_model,
        }
        if obj.provider:
            attributes["gen_ai.provider.name"] = obj.provider

        record = SDKLogRecord(
            body=body,
            attributes=attributes,
            event_name=event_name,
        )
        try:
            self._event_logger.emit(record)
        except Exception:  # pragma: no cover - defensive
            pass

    def error(self, error: Any, obj: Any) -> None:
        return None


def splunk_emitters(
    *,
    tracer: Any,
    meter: Any,
    event_logger: Any,
    settings: Any,
) -> PluginEmitterBundle:
    capture_span = getattr(settings, "capture_content_span", False)
    capture_events = getattr(settings, "capture_content_events", False)
    span_emitter = SpanEmitter(tracer=tracer, capture_content=capture_span)
    metrics_emitter = MetricsEmitter(meter=meter)
    events_emitter = SplunkConversationEventsEmitter(
        event_logger=event_logger, capture_content=capture_events
    )
    return PluginEmitterBundle(
        emitters=[span_emitter, metrics_emitter, events_emitter],
        replace_default_emitters=True,
    )


def _coerce_messages(
    messages: Iterable[Any], capture_content: bool
) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for msg in messages or []:
        try:
            data = asdict(msg)
        except TypeError:
            # Fallback if already dict-like
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
    return [values]


__all__ = [
    "SplunkConversationEventsEmitter",
    "splunk_emitters",
]
