# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Conversions between the application's and the vendored spans, span contexts and statuses.

Only the application's ``opentelemetry.trace.span`` and ``opentelemetry.trace.status`` are imported:
the context bridge imports this module as soon as the application's ``opentelemetry.trace.propagation``
defines its span key, before its ``opentelemetry.trace`` has finished importing.
"""

from __future__ import annotations

import types
import weakref
from collections.abc import Mapping

from opentelemetry.agent._vendor.opentelemetry.trace import span as agent_span
from opentelemetry.agent._vendor.opentelemetry.trace import status as agent_status
from opentelemetry.trace.span import INVALID_SPAN, Span, SpanContext, TraceFlags, TraceState
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util import types as app_types

# The application's spans that aren't bridge spans (e.g. extracted by its propagators) are stored as vendored
# non-recording spans: map those back to the original span.
_APP_SPANS: weakref.WeakKeyDictionary[agent_span.Span, Span] = weakref.WeakKeyDictionary()


def to_agent_span_context(span_context: SpanContext) -> agent_span.SpanContext:
    return agent_span.SpanContext(
        trace_id=span_context.trace_id,
        span_id=span_context.span_id,
        is_remote=span_context.is_remote,
        trace_flags=agent_span.TraceFlags(span_context.trace_flags),
        trace_state=agent_span.TraceState(list(span_context.trace_state.items())),
    )


def to_app_span_context(span_context: agent_span.SpanContext) -> SpanContext:
    return SpanContext(
        trace_id=span_context.trace_id,
        span_id=span_context.span_id,
        is_remote=span_context.is_remote,
        trace_flags=TraceFlags(span_context.trace_flags),
        trace_state=TraceState(list(span_context.trace_state.items())),
    )


def to_agent_status_code(status_code: StatusCode) -> agent_status.StatusCode:
    return agent_status.StatusCode[status_code.name]


def to_agent_status(status: Status) -> agent_status.Status:
    return agent_status.Status(to_agent_status_code(status.status_code), status.description)


class BridgeSpan(Span):
    """The application's span type, wrapping a vendored span.

    Bridge spans are created for each lookup of the current span; they're equal when they wrap the same span.
    """

    def __init__(self, span: agent_span.Span) -> None:
        self._span = span

    def end(self, end_time: int | None = None) -> None:
        self._span.end(end_time)

    def get_span_context(self) -> SpanContext:
        return to_app_span_context(self._span.get_span_context())

    def set_attributes(self, attributes: Mapping[str, app_types.AttributeValue]) -> None:
        self._span.set_attributes(attributes)

    def set_attribute(self, key: str, value: app_types.AttributeValue) -> None:
        self._span.set_attribute(key, value)

    def add_event(self, name: str, attributes: app_types.Attributes = None, timestamp: int | None = None) -> None:
        self._span.add_event(name, attributes, timestamp)

    def add_link(self, context: SpanContext, attributes: app_types.Attributes = None) -> None:
        self._span.add_link(to_agent_span_context(context), attributes)

    def update_name(self, name: str) -> None:
        self._span.update_name(name)

    def is_recording(self) -> bool:
        return self._span.is_recording()

    def set_status(self, status: Status | StatusCode, description: str | None = None) -> None:
        if isinstance(status, Status):
            self._span.set_status(to_agent_status(status), description)
        else:
            self._span.set_status(to_agent_status_code(status), description)

    def record_exception(
        self,
        exception: BaseException,
        attributes: app_types.Attributes = None,
        timestamp: int | None = None,
        escaped: bool = False,
    ) -> None:
        self._span.record_exception(exception, attributes, timestamp, escaped)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        # The SDK's span records the exception and sets the error status (as configured at its start).
        self._span.__exit__(exc_type, exc_val, exc_tb)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, BridgeSpan) and other._span is self._span

    def __hash__(self) -> int:
        return hash(self._span)

    def __repr__(self) -> str:
        return f"BridgeSpan({self._span!r})"


def to_app_span(span: object) -> object:
    """The application's span for a vendored span (in the vendored context)."""
    if span is agent_span.INVALID_SPAN:
        return INVALID_SPAN
    if not isinstance(span, agent_span.Span):
        return span
    app_span = _APP_SPANS.get(span)
    if app_span is not None:
        return app_span
    return BridgeSpan(span)


def to_agent_span(span: object) -> object:
    """The vendored span for an application's span (in the application's context)."""
    if isinstance(span, BridgeSpan):
        return span._span
    if span is INVALID_SPAN:
        return agent_span.INVALID_SPAN
    if not isinstance(span, Span):
        return span
    agent = agent_span.NonRecordingSpan(to_agent_span_context(span.get_span_context()))
    _APP_SPANS[agent] = span
    return agent
