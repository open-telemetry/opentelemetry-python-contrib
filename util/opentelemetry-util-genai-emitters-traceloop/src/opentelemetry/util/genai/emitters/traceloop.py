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
    build_completion_enumeration,
    build_prompt_enumeration,
)
from opentelemetry.util.genai.interfaces import EmitterMeta
from opentelemetry.util.genai.types import (
    ContentCapturingMode,
    Error,
    LLMInvocation,
)

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
_TRACELOOP_ASSOCIATION_PREFIX = "traceloop.association.properties."
_TRACELOOP_PASSTHROUGH = (
    "callback.name",
    "callback.id",
    "entity.name",
    "entity.path",
    "workflow.name",
)


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
        self._content_mode = ContentCapturingMode.NO_CONTENT

    def set_capture_content(
        self, value: bool
    ) -> None:  # pragma: no cover - trivial
        self._capture_content = value

    def set_content_mode(
        self, mode: ContentCapturingMode
    ) -> None:  # pragma: no cover - trivial
        self._content_mode = mode

    def handles(self, obj: object) -> bool:
        return isinstance(obj, LLMInvocation)

    def _set_attr(
        self,
        span,
        extras: dict[str, object],
        key: str,
        value: object,
        *,
        write_to_span: bool = True,
    ) -> None:
        extras[key] = value
        if not write_to_span:
            return
        try:
            span.set_attribute(key, value)
        except Exception:  # pragma: no cover - defensive
            pass

    def _should_emit_span_content(self) -> bool:
        if not self._capture_content:
            return False
        return self._content_mode in (
            ContentCapturingMode.SPAN_ONLY,
            ContentCapturingMode.SPAN_AND_EVENT,
        )

    def on_start(self, invocation: LLMInvocation) -> None:
        if not isinstance(invocation, LLMInvocation):
            return
        extras = invocation.attributes
        cb_name = extras.get("traceloop.callback_name") or extras.get(
            "callback.name"
        )
        operation = invocation.operation
        span_name = (
            f"{cb_name}.{operation}"
            if cb_name
            else f"{operation} {invocation.request_model}"
        )
        cm = self._tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT, end_on_exit=False
        )
        span = cm.__enter__()
        invocation.__dict__["traceloop_span"] = span
        invocation.__dict__["traceloop_cm"] = cm

        if "span.kind" not in extras:
            extras["span.kind"] = "llm"
        span_kind = extras.get("span.kind", "llm")
        legacy_kind = extras.get("traceloop.span.kind", span_kind)
        self._set_attr(span, extras, "span.kind", span_kind)
        self._set_attr(span, extras, "traceloop.span.kind", legacy_kind)

        for key in _TRACELOOP_PASSTHROUGH:
            if key in extras:
                self._set_attr(
                    span, extras, _to_traceloop_key(key), extras[key]
                )
        if cb_name:
            self._set_attr(span, extras, "traceloop.callback.name", cb_name)

        ls_metadata = extras.get("_ls_metadata")
        if isinstance(ls_metadata, dict):
            for ls_key, ls_value in ls_metadata.items():
                self._set_attr(
                    span,
                    extras,
                    f"{_TRACELOOP_ASSOCIATION_PREFIX}{ls_key}",
                    ls_value,
                )

        for key, value in list(extras.items()):
            if not isinstance(key, str):
                continue
            if key == "_ls_metadata":
                continue
            if key.startswith("ls_"):
                self._set_attr(
                    span,
                    extras,
                    f"{_TRACELOOP_ASSOCIATION_PREFIX}{key}",
                    value,
                )
            elif key.startswith(_TRACELOOP_PREFIX):
                self._set_attr(span, extras, key, value)

        self._set_attr(span, extras, "llm.request.type", operation)
        self._apply_semconv_start(invocation, span)

        should_write_content = self._should_emit_span_content()
        if self._capture_content and invocation.input_messages:
            prompt_attrs = build_prompt_enumeration(invocation.input_messages)
            for key, value in prompt_attrs.items():
                self._set_attr(
                    span,
                    extras,
                    key,
                    value,
                    write_to_span=should_write_content,
                )
            serialized = _serialize_messages(invocation.input_messages)
            if serialized is not None:
                entity_key = _TRACELOOP_SPECIAL_KEYS["entity.input"]
                self._set_attr(
                    span,
                    extras,
                    entity_key,
                    serialized,
                    write_to_span=should_write_content,
                )
                extras.setdefault("entity.input", serialized)

    def on_end(self, invocation: LLMInvocation) -> None:
        span = getattr(invocation, "traceloop_span", None)
        cm = getattr(invocation, "traceloop_cm", None)
        if span is None:
            return
        should_write_content = self._should_emit_span_content()
        self._apply_finish_attributes(
            span, invocation, write_content=should_write_content
        )
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
        should_write_content = self._should_emit_span_content()
        self._apply_finish_attributes(
            span, invocation, write_content=should_write_content
        )
        _apply_llm_finish_semconv(span, invocation)
        if cm and hasattr(cm, "__exit__"):
            try:
                cm.__exit__(None, None, None)
            except Exception:  # pragma: no cover
                pass
        span.end()

    def _apply_finish_attributes(
        self,
        span,
        invocation: LLMInvocation,
        *,
        write_content: bool,
    ) -> None:
        extras = invocation.attributes
        if self._capture_content and invocation.output_messages:
            completion_attrs = build_completion_enumeration(
                invocation.output_messages
            )
            for key, value in completion_attrs.items():
                self._set_attr(
                    span,
                    extras,
                    key,
                    value,
                    write_to_span=write_content,
                )
            serialized = _serialize_messages(invocation.output_messages)
            if serialized is not None:
                entity_key = _TRACELOOP_SPECIAL_KEYS["entity.output"]
                self._set_attr(
                    span,
                    extras,
                    entity_key,
                    serialized,
                    write_to_span=write_content,
                )
                extras.setdefault("entity.output", serialized)

        prompt_tokens = getattr(invocation, "input_tokens", None)
        completion_tokens = getattr(invocation, "output_tokens", None)
        if prompt_tokens is not None:
            self._set_attr(
                span,
                extras,
                "gen_ai.usage.prompt_tokens",
                prompt_tokens,
            )
        if completion_tokens is not None:
            self._set_attr(
                span,
                extras,
                "gen_ai.usage.completion_tokens",
                completion_tokens,
            )
        if isinstance(prompt_tokens, (int, float)) and isinstance(
            completion_tokens, (int, float)
        ):
            total = prompt_tokens + completion_tokens
            self._set_attr(span, extras, "llm.usage.total_tokens", total)

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
