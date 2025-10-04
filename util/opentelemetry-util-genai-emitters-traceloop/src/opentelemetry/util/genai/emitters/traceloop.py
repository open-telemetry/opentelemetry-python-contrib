from __future__ import annotations

from typing import Optional

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util.genai.attributes import (
    GEN_AI_FRAMEWORK,
    GEN_AI_PROVIDER_NAME,
)
from opentelemetry.util.genai.emitters.spec import (
    EmitterFactoryContext,
    EmitterSpec,
)
from opentelemetry.util.genai.emitters.utils import (
    _apply_function_definitions,
    _apply_llm_finish_semconv,
    _serialize_messages,
)
from opentelemetry.util.genai.interfaces import EmitterMeta
from opentelemetry.util.genai.types import Error, LLMInvocation

_TRACELOOP_PREFIX = "traceloop."
_TRACELOOP_SPECIAL_KEYS: dict[str, str] = {
    "span.kind": "traceloop.span.kind",
    "entity.input": "traceloop.entity.input",
    "entity.output": "traceloop.entity.output",
    "workflow.name": "traceloop.workflow.name",
    "entity.name": "traceloop.entity.name",
    "entity.path": "traceloop.entity.path",
    "callback.name": "traceloop.callback.name",
    "callback.id": "traceloop.callback.id",
}


def _to_traceloop_key(key: str) -> str:
    if key.startswith(_TRACELOOP_PREFIX):
        return key
    return _TRACELOOP_SPECIAL_KEYS.get(key, f"{_TRACELOOP_PREFIX}{key}")


class TraceloopCompatEmitter(EmitterMeta):
    """Emitter that recreates the legacy Traceloop span format for LLM calls."""

    role = "traceloop_compat"
    name = "traceloop_compat_span"

    def __init__(
        self, tracer: Optional[Tracer] = None, capture_content: bool = False
    ) -> None:
        self._tracer: Tracer = tracer or trace.get_tracer(__name__)
        self._capture_content = capture_content

    def set_capture_content(
        self, value: bool
    ) -> None:  # pragma: no cover - trivial
        self._capture_content = value

    def handles(self, obj: object) -> bool:
        return isinstance(obj, LLMInvocation)

    def on_start(self, invocation: LLMInvocation) -> None:
        if not isinstance(invocation, LLMInvocation):
            return
        operation = invocation.operation
        cb_name = invocation.attributes.get("traceloop.callback_name")
        span_name = (
            f"{cb_name}.{operation}"
            if cb_name
            else f"{operation} {invocation.request_model}"
        )
        cm = self._tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT, end_on_exit=False
        )
        span = cm.__enter__()
        invocation.attributes.setdefault("traceloop.span.kind", "llm")
        invocation.__dict__["traceloop_span"] = span
        invocation.__dict__["traceloop_cm"] = cm

        extras = invocation.attributes
        if "span.kind" not in extras:
            extras["span.kind"] = "llm"
        # Maintain legacy prefixed entry for downstream compatibility
        extras.setdefault("traceloop.span.kind", extras.get("span.kind"))

        for key, value in list(extras.items()):
            if key.startswith("gen_ai."):
                continue
            traceloop_key = _to_traceloop_key(key)
            try:
                span.set_attribute(traceloop_key, value)
            except Exception:  # pragma: no cover
                pass
            extras.setdefault(traceloop_key, value)
        self._apply_semconv_start(invocation, span)
        if self._capture_content and invocation.input_messages:
            serialized = _serialize_messages(invocation.input_messages)
            if serialized is not None:
                traceloop_key = _TRACELOOP_SPECIAL_KEYS["entity.input"]
                try:
                    span.set_attribute(traceloop_key, serialized)
                    extras[traceloop_key] = serialized
                    extras.setdefault("entity.input", serialized)
                except Exception:  # pragma: no cover
                    pass

    def on_end(self, invocation: LLMInvocation) -> None:
        span = getattr(invocation, "traceloop_span", None)
        cm = getattr(invocation, "traceloop_cm", None)
        if span is None:
            return
        if self._capture_content and invocation.output_messages:
            serialized = _serialize_messages(invocation.output_messages)
            if serialized is not None:
                try:
                    traceloop_key = _TRACELOOP_SPECIAL_KEYS["entity.output"]
                    span.set_attribute(traceloop_key, serialized)
                    invocation.attributes[traceloop_key] = serialized
                    invocation.attributes.setdefault(
                        "entity.output", serialized
                    )
                except Exception:  # pragma: no cover
                    pass
        _apply_llm_finish_semconv(span, invocation)
        if cm and hasattr(cm, "__exit__"):
            try:
                cm.__exit__(None, None, None)
            except Exception:  # pragma: no cover
                pass
        span.end()

    def on_error(self, error: Error, invocation: LLMInvocation) -> None:
        span = getattr(invocation, "traceloop_span", None)
        cm = getattr(invocation, "traceloop_cm", None)
        if span is None:
            return
        try:
            span.set_status(Status(StatusCode.ERROR, error.message))
        except Exception:  # pragma: no cover
            pass
        _apply_llm_finish_semconv(span, invocation)
        if cm and hasattr(cm, "__exit__"):
            try:
                cm.__exit__(None, None, None)
            except Exception:  # pragma: no cover
                pass
        span.end()

    # ------------------------------------------------------------------
    @staticmethod
    def _apply_semconv_start(invocation: LLMInvocation, span):
        try:  # pragma: no cover - defensive
            span.set_attribute("gen_ai.operation.name", invocation.operation)
            span.set_attribute(
                "gen_ai.request.model", invocation.request_model
            )
            if invocation.provider:
                span.set_attribute(GEN_AI_PROVIDER_NAME, invocation.provider)
            if invocation.framework:
                span.set_attribute(GEN_AI_FRAMEWORK, invocation.framework)
            _apply_function_definitions(span, invocation.request_functions)
        except Exception:
            pass


def traceloop_emitters() -> list[EmitterSpec]:
    def _factory(ctx: EmitterFactoryContext) -> TraceloopCompatEmitter:
        capture = ctx.capture_span_content or ctx.capture_event_content
        return TraceloopCompatEmitter(
            tracer=ctx.tracer, capture_content=capture
        )

    return [
        EmitterSpec(
            name="TraceloopCompatSpan",
            category="span",
            factory=_factory,
        )
    ]


__all__ = ["TraceloopCompatEmitter", "traceloop_emitters"]
