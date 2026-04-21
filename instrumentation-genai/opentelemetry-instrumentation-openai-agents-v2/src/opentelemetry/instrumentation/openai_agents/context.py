"""Telemetry Context Manager for OpenAI Realtime Sessions

Manages OpenTelemetry span lifecycle and context propagation for realtime
sessions. Provides anchor-span bookkeeping so that response and tool-call
spans are correctly parented under the session span.
"""

from __future__ import annotations

import contextlib
import logging
from contextvars import Token

from opentelemetry.context import Context, attach, detach, get_current
from opentelemetry.trace import Span, set_span_in_context

logger = logging.getLogger(__name__)

_UNSET_SESSION = "unset_session"


class TelemetryContext:
    def __init__(self, root_span: Span | None = None) -> None:
        self._session_id: str = _UNSET_SESSION
        self.root_span: Span | None = root_span
        self._anchors: dict[str, tuple[Span, Token[Context] | None]] = {}

    @property
    def session_id(self) -> str:
        return self._session_id

    @session_id.setter
    def session_id(self, value: str) -> None:
        self._session_id = value

    def get_span_context(
        self, key: str | None = None, context: Context | None = None
    ) -> Context:
        """Return a ``Context`` scoped to the given anchor span, root span, or current context."""
        if key and key in self._anchors:
            span, _ = self._anchors[key]
            return set_span_in_context(span, context=context)
        if self.root_span:
            return set_span_in_context(self.root_span)
        return get_current()

    def start_anchor_span(
        self, key: str, span: Span, context: Context | None = None
    ) -> Span:
        new_context = set_span_in_context(span, context=context)
        token: Token[Context] | None = None
        if context is None:
            token = attach(new_context)
        else:
            with contextlib.suppress(Exception):
                attach(new_context)
        self._anchors[key] = (span, token)
        return span

    def get_anchor_span(
        self, key: str, attach_to_current_context: bool = True
    ) -> Span | None:
        anchor = self._anchors.get(key)
        if anchor:
            span, _ = anchor
            if attach_to_current_context:
                with contextlib.suppress(Exception):
                    attach(set_span_in_context(span))
            return span
        return None

    def end_anchor_span(self, key: str | None) -> None:
        if not key:
            return
        anchor = self._anchors.pop(key, None)
        if anchor:
            span, token = anchor
            if token is not None:
                try:
                    detach(token)
                except Exception:
                    logger.debug("Unable to detach span for %s", key)
            try:
                if span.is_recording():
                    span.end()
            except Exception:
                logger.debug("Unable to end span for %s", key)

    def cleanup(self) -> None:
        for key in list(self._anchors.keys()):
            anchor = self._anchors.pop(key, None)
            if anchor:
                span, token = anchor
                if token is not None:
                    with contextlib.suppress(Exception):
                        detach(token)
                try:
                    if span.is_recording():
                        span.end()
                except Exception:
                    logger.debug(
                        "Failed to close anchor span during cleanup: %s", key
                    )
        if self.root_span and self.root_span.is_recording():
            try:
                self.root_span.end()
            except Exception:
                logger.debug("Failed to close root span during cleanup")
            self.root_span = None
