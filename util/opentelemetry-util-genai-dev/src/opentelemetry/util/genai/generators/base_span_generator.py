# Shared base span generator to reduce duplication among span-based generators.
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Optional

from opentelemetry import trace
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.trace import SpanKind, Tracer, use_span
from opentelemetry.trace.status import Status, StatusCode

from ..types import Error, LLMInvocation
from .base_generator import BaseTelemetryGenerator


class BaseSpanGenerator(BaseTelemetryGenerator):
    """Template base class handling common span lifecycle for LLM invocations.
    Subclasses can override hooks to add metrics/events without duplicating
    core span creation, attribute population, and content capture.
    """

    def __init__(
        self, tracer: Optional[Tracer] = None, capture_content: bool = False
    ):
        self._tracer: Tracer = tracer or trace.get_tracer(__name__)
        self._capture_content = capture_content

    # ---- Hook methods (no-op by default) ---------------------------------
    def _on_after_start(self, invocation: LLMInvocation):
        """Hook after span start & initial attrs/content applied."""

    def _on_before_end(
        self, invocation: LLMInvocation, error: Optional[Error]
    ):
        """Hook before span is ended (span still active)."""

    # ---- Internal helpers ------------------------------------------------
    def _serialize_messages(self, messages):
        try:
            return json.dumps([asdict(m) for m in messages])
        except Exception:  # pragma: no cover
            return None

    def _apply_start_attrs(self, invocation: LLMInvocation):
        span = invocation.span
        if span is None:
            return
        span.set_attribute(
            GenAI.GEN_AI_OPERATION_NAME,
            GenAI.GenAiOperationNameValues.CHAT.value,
        )
        span.set_attribute(
            GenAI.GEN_AI_REQUEST_MODEL, invocation.request_model
        )
        if invocation.provider:
            span.set_attribute("gen_ai.provider.name", invocation.provider)
        # Custom attributes present at start
        for k, v in invocation.attributes.items():
            span.set_attribute(k, v)
        if self._capture_content and invocation.input_messages:
            serialized = self._serialize_messages(invocation.input_messages)
            if serialized is not None:
                span.set_attribute("gen_ai.input.messages", serialized)

    def _apply_finish_attrs(self, invocation: LLMInvocation):
        span = invocation.span
        if span is None:
            return
        for k, v in invocation.attributes.items():
            span.set_attribute(k, v)
        if self._capture_content and invocation.output_messages:
            serialized = self._serialize_messages(invocation.output_messages)
            if serialized is not None:
                span.set_attribute("gen_ai.output.messages", serialized)

    # ---- Public API ------------------------------------------------------
    def start(self, invocation: LLMInvocation) -> None:  # type: ignore[override]
        span_name = f"chat {invocation.request_model}"
        span = self._tracer.start_span(name=span_name, kind=SpanKind.CLIENT)
        invocation.span = span
        cm = use_span(span, end_on_exit=False)
        cm.__enter__()
        # store context manager (not just token) for later controlled exit
        invocation.context_token = cm  # type: ignore[assignment]
        self._apply_start_attrs(invocation)
        self._on_after_start(invocation)

    def finish(self, invocation: LLMInvocation) -> None:  # type: ignore[override]
        span = invocation.span
        if span is None:
            return
        self._on_before_end(invocation, error=None)
        self._apply_finish_attrs(invocation)
        token = invocation.context_token
        if token is not None and hasattr(token, "__exit__"):
            try:  # pragma: no cover
                token.__exit__(None, None, None)  # type: ignore[misc]
            except Exception:  # pragma: no cover
                pass
        span.end()

    def error(self, error: Error, invocation: LLMInvocation) -> None:  # type: ignore[override]
        span = invocation.span
        if span is None:
            return
        span.set_status(Status(StatusCode.ERROR, error.message))
        if span.is_recording():
            span.set_attribute(
                ErrorAttributes.ERROR_TYPE, error.type.__qualname__
            )
        self._on_before_end(invocation, error=error)
        self._apply_finish_attrs(invocation)
        token = invocation.context_token
        if token is not None and hasattr(token, "__exit__"):
            try:  # pragma: no cover
                token.__exit__(None, None, None)  # type: ignore[misc]
            except Exception:  # pragma: no cover
                pass
        span.end()
