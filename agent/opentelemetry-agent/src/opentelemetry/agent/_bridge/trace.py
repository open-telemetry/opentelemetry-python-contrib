# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""The application's tracer provider, creating spans with the vendored one.

The application's ``get_tracer_provider()`` loads `BridgeTracerProvider` (``OTEL_PYTHON_TRACER_PROVIDER``)
unless the application set its own provider first.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING

from opentelemetry import context as app_context
from opentelemetry import trace as app_trace
from opentelemetry.agent._bridge import release_environment_variable
from opentelemetry.agent._bridge.context import BridgeRuntimeContext, to_agent_context
from opentelemetry.agent._bridge.span import BridgeSpan, to_agent_span_context
from opentelemetry.agent._vendor.opentelemetry import trace as agent_trace
from opentelemetry.agent._vendor.opentelemetry.context.context import Context as AgentContext
from opentelemetry.agent._vendor.opentelemetry.environment_variables import OTEL_PYTHON_TRACER_PROVIDER
from opentelemetry.context import Context
from opentelemetry.util import types as app_types

if TYPE_CHECKING:
    from opentelemetry.util._decorator import _agnosticcontextmanager
else:
    try:
        from opentelemetry.util._decorator import _agnosticcontextmanager
    except ImportError:  # opentelemetry-api < 1.24: start_as_current_span isn't usable as a decorator.
        from contextlib import contextmanager as _agnosticcontextmanager


class BridgeTracerProvider(app_trace.TracerProvider):
    """Gets tracers from the vendored global tracer provider (set when the agent configures the SDK)."""

    def __init__(self) -> None:
        release_environment_variable(OTEL_PYTHON_TRACER_PROVIDER)

    def get_tracer(
        self,
        instrumenting_module_name: str,
        instrumenting_library_version: str | None = None,
        schema_url: str | None = None,
        attributes: app_types.Attributes = None,
    ) -> app_trace.Tracer:
        return BridgeTracer(
            agent_trace.get_tracer_provider().get_tracer(
                instrumenting_module_name, instrumenting_library_version, schema_url, attributes
            )
        )

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Flush the vendored SDK's span processors, like the SDK's ``TracerProvider.force_flush()``."""
        force_flush = getattr(agent_trace.get_tracer_provider(), "force_flush", None)
        return force_flush(timeout_millis) if force_flush is not None else True


def _agent_parent_context(context: Context | None) -> AgentContext | None:
    if context is not None:
        return to_agent_context(context)
    if isinstance(app_context._RUNTIME_CONTEXT, BridgeRuntimeContext):
        # The vendored SDK reads the same current context.
        return None
    # The application selected another runtime context: its current span isn't the vendored one.
    return to_agent_context(app_context.get_current())


def _to_agent_links(links: Sequence[app_trace.Link] | None) -> list[agent_trace.Link] | None:
    if links is None:
        return None
    return [agent_trace.Link(to_agent_span_context(link.context), link.attributes) for link in links]


class BridgeTracer(app_trace.Tracer):
    def __init__(self, tracer: agent_trace.Tracer) -> None:
        self._tracer = tracer

    def start_span(
        self,
        name: str,
        context: Context | None = None,
        kind: app_trace.SpanKind = app_trace.SpanKind.INTERNAL,
        attributes: app_types.Attributes = None,
        links: Sequence[app_trace.Link] | None = None,
        start_time: int | None = None,
        record_exception: bool = True,
        set_status_on_exception: bool = True,
    ) -> app_trace.Span:
        span = self._tracer.start_span(
            name,
            context=_agent_parent_context(context),
            kind=agent_trace.SpanKind[kind.name],
            attributes=attributes,
            links=_to_agent_links(links),
            start_time=start_time,
            record_exception=record_exception,
            set_status_on_exception=set_status_on_exception,
        )
        return BridgeSpan(span)

    @_agnosticcontextmanager
    def start_as_current_span(
        self,
        name: str,
        context: Context | None = None,
        kind: app_trace.SpanKind = app_trace.SpanKind.INTERNAL,
        attributes: app_types.Attributes = None,
        links: Sequence[app_trace.Link] | None = None,
        start_time: int | None = None,
        record_exception: bool = True,
        set_status_on_exception: bool = True,
        end_on_exit: bool = True,
    ) -> Iterator[app_trace.Span]:
        # Same as the SDK's Tracer.start_as_current_span; use_span sets the span in the application's context.
        span = self.start_span(
            name, context, kind, attributes, links, start_time, record_exception, set_status_on_exception
        )
        with app_trace.use_span(
            span,
            end_on_exit=end_on_exit,
            record_exception=record_exception,
            set_status_on_exception=set_status_on_exception,
        ) as current_span:
            yield current_span
