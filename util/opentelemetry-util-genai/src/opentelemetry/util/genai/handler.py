# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Telemetry handler for GenAI invocations.

This module exposes the `TelemetryHandler` class, which manages the lifecycle of
GenAI (Generative AI) invocations and emits telemetry data (spans and related attributes).
It supports starting, stopping, and failing LLM invocations.

Classes:
    - TelemetryHandler: Manages GenAI invocation lifecycles and emits telemetry.

Functions:
    - get_telemetry_handler: Returns a singleton `TelemetryHandler` instance.

Usage:
    handler = get_telemetry_handler()

    # Create an invocation object with your request data
    # The span and context_token attributes are set by the TelemetryHandler, and
    # managed by the TelemetryHandler during the lifecycle of the span.

    # Use the context manager to manage the lifecycle of an LLM invocation.
    with handler.llm(invocation) as invocation:
        # Populate outputs and any additional attributes
        invocation.output_messages = [...]
        invocation.attributes.update({"more": "attrs"})

    # Or, if you prefer to manage the lifecycle manually
    invocation = LLMInvocation(
        request_model="my-model",
        input_messages=[...],
        provider="my-provider",
        attributes={"custom": "attr"},
    )

    # Start the invocation (opens a span)
    handler.start_llm(invocation)

    # Populate outputs and any additional attributes, then stop (closes the span)
    invocation.output_messages = [...]
    invocation.attributes.update({"more": "attrs"})
    handler.stop_llm(invocation)

    # Or, in case of error
    handler.fail_llm(invocation, Error(type="...", message="..."))
"""

from __future__ import annotations

import logging
import timeit
from contextlib import contextmanager
from typing import Callable, Iterator, TypeVar

from opentelemetry import context as otel_context
from opentelemetry._logs import (
    LoggerProvider,
    get_logger,
)
from opentelemetry.metrics import MeterProvider, get_meter
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import (
    Span,
    SpanKind,
    TracerProvider,
    get_tracer,
    set_span_in_context,
)
from opentelemetry.util.genai.metrics import InvocationMetricsRecorder
from opentelemetry.util.genai.span_utils import (
    _apply_agent_finish_attributes,
    _apply_error_attributes,
    _apply_llm_finish_attributes,
    _get_base_agent_span_name,
    _maybe_emit_agent_event,
    _maybe_emit_llm_event,
)
from opentelemetry.util.genai.types import (
    AgentCreation,
    AgentInvocation,
    Error,
    GenAIInvocation,
    LLMInvocation,
    _BaseAgent,
)
from opentelemetry.util.genai.version import __version__

_logger = logging.getLogger(__name__)

_T = TypeVar("_T", bound=GenAIInvocation)


@contextmanager
def _lifecycle_context(
    invocation: _T,
    start: Callable[[_T], _T],
    stop: Callable[[_T], _T],
    fail: Callable[[_T, Error], _T],
    label: str,
) -> Iterator[_T]:
    """Shared lifecycle context manager for GenAI invocations.

    Wraps start/stop/fail calls with error handling so SDK-internal
    errors never propagate to the caller.
    """
    try:
        start(invocation)
    except Exception:
        _logger.warning("Failed to start %s span", label, exc_info=True)
    try:
        yield invocation
    except Exception as exc:
        try:
            fail(invocation, Error(message=str(exc), type=type(exc)))
        except Exception:
            _logger.warning(
                "Failed to record %s failure", label, exc_info=True
            )
        raise
    else:
        try:
            stop(invocation)
        except Exception:
            _logger.warning("Failed to stop %s span", label, exc_info=True)


class TelemetryHandler:
    """
    High-level handler managing GenAI invocation lifecycles and emitting
    them as spans, metrics, and events.
    """

    def __init__(
        self,
        tracer_provider: TracerProvider | None = None,
        meter_provider: MeterProvider | None = None,
        logger_provider: LoggerProvider | None = None,
    ):
        self._tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=Schemas.V1_37_0.value,
        )
        self._metrics_recorder: InvocationMetricsRecorder | None = None
        meter = get_meter(__name__, meter_provider=meter_provider)
        self._metrics_recorder = InvocationMetricsRecorder(meter)
        self._logger = get_logger(
            __name__,
            __version__,
            logger_provider,
            schema_url=Schemas.V1_37_0.value,
        )

    def _record_llm_metrics(
        self,
        invocation: LLMInvocation,
        span: Span | None = None,
        *,
        error_type: str | None = None,
    ) -> None:
        if self._metrics_recorder is None or span is None:
            return
        self._metrics_recorder.record(
            span,
            invocation,
            error_type=error_type,
        )

    def start_llm(
        self,
        invocation: LLMInvocation,
    ) -> LLMInvocation:
        """Start an LLM invocation and create a pending span entry."""
        # Create a span and attach it as current; keep the token to detach later
        span = self._tracer.start_span(
            name=f"{invocation.operation_name} {invocation.request_model}",
            kind=SpanKind.CLIENT,
        )
        # Record a monotonic start timestamp (seconds) for duration
        # calculation using timeit.default_timer.
        invocation.monotonic_start_s = timeit.default_timer()
        invocation.span = span
        invocation.context_token = otel_context.attach(
            set_span_in_context(span)
        )
        return invocation

    def stop_llm(self, invocation: LLMInvocation) -> LLMInvocation:  # pylint: disable=no-self-use
        """Finalize an LLM invocation successfully and end its span."""
        if invocation.context_token is None or invocation.span is None:
            # TODO: Provide feedback that this invocation was not started
            return invocation

        try:
            _apply_llm_finish_attributes(invocation.span, invocation)
            self._record_llm_metrics(invocation, invocation.span)
            _maybe_emit_llm_event(self._logger, invocation.span, invocation)
        finally:
            otel_context.detach(invocation.context_token)
            invocation.span.end()
        return invocation

    def fail_llm(  # pylint: disable=no-self-use
        self, invocation: LLMInvocation, error: Error
    ) -> LLMInvocation:
        """Fail an LLM invocation and end its span with error status."""
        if invocation.context_token is None or invocation.span is None:
            # TODO: Provide feedback that this invocation was not started
            return invocation

        try:
            _apply_llm_finish_attributes(invocation.span, invocation)
            _apply_error_attributes(invocation.span, error)
            error_type = getattr(error.type, "__qualname__", None)
            self._record_llm_metrics(
                invocation, invocation.span, error_type=error_type
            )
            _maybe_emit_llm_event(
                self._logger, invocation.span, invocation, error
            )
        finally:
            otel_context.detach(invocation.context_token)
            invocation.span.end()
        return invocation

    @contextmanager
    def llm(
        self, invocation: LLMInvocation | None = None
    ) -> Iterator[LLMInvocation]:
        """Context manager for LLM invocations.

        Only set data attributes on the invocation object, do not modify the span or context.

        Starts the span on entry. On normal exit, finalizes the invocation and ends the span.
        If an exception occurs inside the context, marks the span as error, ends it, and
        re-raises the original exception.
        """
        if invocation is None:
            invocation = LLMInvocation(
                request_model="",
            )
        with _lifecycle_context(
            invocation, self.start_llm, self.stop_llm, self.fail_llm, "llm"
        ) as inv:
            yield inv

    # ---- Unified agent lifecycle (invoke_agent / create_agent) ----

    def start_agent(
        self,
        agent: _BaseAgent,
    ) -> _BaseAgent:
        """Start an agent operation and create a pending span entry.

        Accepts any _BaseAgent subclass (AgentInvocation, AgentCreation).
        """
        span_name = _get_base_agent_span_name(agent)
        is_remote = getattr(agent, "is_remote", True)
        kind = SpanKind.CLIENT if is_remote else SpanKind.INTERNAL
        span = self._tracer.start_span(
            name=span_name,
            kind=kind,
        )
        agent.monotonic_start_s = timeit.default_timer()
        agent.span = span
        agent.context_token = otel_context.attach(set_span_in_context(span))
        return agent

    def _record_agent_metrics(
        self,
        agent: _BaseAgent,
        span: Span | None = None,
        *,
        error_type: str | None = None,
    ) -> None:
        if self._metrics_recorder is None or span is None:
            return
        self._metrics_recorder.record_agent(
            span,
            agent,
            error_type=error_type,
        )

    def stop_agent(self, agent: _BaseAgent) -> _BaseAgent:
        """Finalize an agent operation successfully and end its span."""
        if agent.context_token is None or agent.span is None:
            return agent

        try:
            _apply_agent_finish_attributes(agent.span, agent)
            self._record_agent_metrics(agent, agent.span)
            _maybe_emit_agent_event(self._logger, agent.span, agent)
        finally:
            otel_context.detach(agent.context_token)
            agent.span.end()
        return agent

    def fail_agent(self, agent: _BaseAgent, error: Error) -> _BaseAgent:
        """Fail an agent operation and end its span with error status."""
        if agent.context_token is None or agent.span is None:
            return agent

        try:
            _apply_agent_finish_attributes(agent.span, agent)
            _apply_error_attributes(agent.span, error)
            error_type = getattr(error.type, "__qualname__", None)
            self._record_agent_metrics(
                agent, agent.span, error_type=error_type
            )
            _maybe_emit_agent_event(self._logger, agent.span, agent, error)
        finally:
            otel_context.detach(agent.context_token)
            agent.span.end()
        return agent

    @contextmanager
    def agent(
        self, invocation: AgentInvocation | None = None
    ) -> Iterator[AgentInvocation]:
        """Context manager for agent invocations.

        Only set data attributes on the invocation object, do not modify the span or context.

        Starts the span on entry. On normal exit, finalizes the invocation and ends the span.
        If an exception occurs inside the context, marks the span as error, ends it, and
        re-raises the original exception.
        """
        if invocation is None:
            invocation = AgentInvocation()
        with _lifecycle_context(
            invocation,
            self.start_agent,
            self.stop_agent,
            self.fail_agent,
            "agent",
        ) as inv:
            yield inv

    @contextmanager
    def create_agent(
        self, creation: AgentCreation | None = None
    ) -> Iterator[AgentCreation]:
        """Context manager for agent creation.

        Only set data attributes on the creation object, do not modify the span or context.

        Starts the span on entry. On normal exit, finalizes the creation and ends the span.
        If an exception occurs inside the context, marks the span as error, ends it, and
        re-raises the original exception.
        """
        if creation is None:
            creation = AgentCreation()
        with _lifecycle_context(
            creation,
            self.start_agent,
            self.stop_agent,
            self.fail_agent,
            "create_agent",
        ) as c:
            yield c


def get_telemetry_handler(
    tracer_provider: TracerProvider | None = None,
    meter_provider: MeterProvider | None = None,
    logger_provider: LoggerProvider | None = None,
) -> TelemetryHandler:
    """
    Returns a singleton TelemetryHandler instance.
    """
    handler: TelemetryHandler | None = getattr(
        get_telemetry_handler, "_default_handler", None
    )
    if handler is None:
        handler = TelemetryHandler(
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
            logger_provider=logger_provider,
        )
        setattr(get_telemetry_handler, "_default_handler", handler)
    return handler
