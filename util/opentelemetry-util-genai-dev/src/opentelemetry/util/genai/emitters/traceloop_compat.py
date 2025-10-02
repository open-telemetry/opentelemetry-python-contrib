# Traceloop compatibility emitter
from __future__ import annotations

import json  # noqa: F401 (backward compatibility re-export)
from dataclasses import asdict  # noqa: F401 (backward compatibility re-export)
from typing import Optional

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.trace.status import Status, StatusCode

from ..attributes import GEN_AI_FRAMEWORK, GEN_AI_PROVIDER_NAME
from ..types import Error, LLMInvocation
from .utils import (
    _apply_function_definitions,
    _apply_llm_finish_semconv,
    _serialize_messages,
)


class TraceloopCompatEmitter:
    """Emitter that recreates (a subset of) the original Traceloop LangChain span format.

    Phase 1 scope:
      * One span per LLMInvocation (no workflow/task/tool hierarchy yet)
      * Span name: ``<callback_name>.chat`` (fallback to ``chat <model>``)
      * Attributes prefixed with ``traceloop.`` copied from invocation.attributes
      * Emits semantic convention attributes from named fields and request_functions
      * Optional content capture (inputs/outputs) if enabled via util-genai content mode
    """

    role = "traceloop_compat"
    name = "traceloop_compat_span"

    def __init__(
        self, tracer: Optional[Tracer] = None, capture_content: bool = False
    ):
        self._tracer: Tracer = tracer or trace.get_tracer(__name__)
        self._capture_content = capture_content

    def set_capture_content(
        self, value: bool
    ):  # pragma: no cover - trivial mutator
        self._capture_content = value

    # Lifecycle -----------------------------------------------------------
    def handles(self, obj: object) -> bool:
        return isinstance(obj, LLMInvocation)

    def _apply_semconv_start(self, invocation: LLMInvocation, span):
        """Apply semantic convention attributes at start."""
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
        except Exception:  # pragma: no cover
            pass

    def start(self, invocation: LLMInvocation) -> None:  # noqa: D401
        if not isinstance(invocation, LLMInvocation):  # defensive
            return
        cb_name = invocation.attributes.get("traceloop.callback_name")
        if cb_name:
            span_name = f"{cb_name}.chat"
        else:
            # Fallback similar but distinct from semconv span naming to avoid collision
            span_name = f"chat {invocation.request_model}"
        cm = self._tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT, end_on_exit=False
        )
        span = cm.__enter__()
        # Persist references for finish/error
        invocation.attributes.setdefault("traceloop.span.kind", "llm")
        invocation.__dict__["traceloop_span"] = span
        invocation.__dict__["traceloop_cm"] = cm
        # Copy traceloop.* and any custom non-semconv attributes present at start
        for k, v in invocation.attributes.items():
            if not k.startswith("gen_ai."):
                try:
                    span.set_attribute(k, v)
                except Exception:  # pragma: no cover
                    pass
        # Apply semantic convention attrs
        self._apply_semconv_start(invocation, span)
        # Input capture
        if self._capture_content and invocation.input_messages:
            serialized = _serialize_messages(invocation.input_messages)
            if serialized is not None:
                try:  # pragma: no cover
                    span.set_attribute("traceloop.entity.input", serialized)
                except Exception:  # pragma: no cover
                    pass

    def finish(self, invocation: LLMInvocation) -> None:  # noqa: D401
        span = getattr(invocation, "traceloop_span", None)
        cm = getattr(invocation, "traceloop_cm", None)
        if span is None:
            return
        # Output capture
        if self._capture_content and invocation.output_messages:
            serialized = _serialize_messages(invocation.output_messages)
            if serialized is not None:
                try:  # pragma: no cover
                    span.set_attribute("traceloop.entity.output", serialized)
                except Exception:  # pragma: no cover
                    pass
        # Apply finish-time semconv attributes (response model/id, usage tokens, function defs)
        _apply_llm_finish_semconv(span, invocation)
        if cm and hasattr(cm, "__exit__"):
            try:  # pragma: no cover
                cm.__exit__(None, None, None)
            except Exception:  # pragma: no cover
                pass
        span.end()

    def error(self, error: Error, invocation: LLMInvocation) -> None:  # noqa: D401
        span = getattr(invocation, "traceloop_span", None)
        cm = getattr(invocation, "traceloop_cm", None)
        if span is None:
            return
        try:  # pragma: no cover
            span.set_status(Status(StatusCode.ERROR, error.message))
        except Exception:  # pragma: no cover
            pass
        # On error still apply finishing semconv attributes if any set
        _apply_llm_finish_semconv(span, invocation)
        if cm and hasattr(cm, "__exit__"):
            try:  # pragma: no cover
                cm.__exit__(None, None, None)
            except Exception:  # pragma: no cover
                pass
        span.end()
