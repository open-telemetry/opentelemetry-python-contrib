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
    # The span and span_scope attributes are set by the TelemetryHandler, and
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

from contextlib import contextmanager
from typing import Iterator, Optional

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import (
    SpanKind,
    TracerProvider,
    get_tracer,
    use_span,
)
from opentelemetry.util.genai.span_utils import (
    _apply_error_attributes,
    _apply_finish_attributes,
)
from opentelemetry.util.genai.types import (
    Error,
    LLMInvocation,
)
from opentelemetry.util.genai.version import __version__


class TelemetryHandler:
    """
    High-level handler managing GenAI invocation lifecycles and emitting
    them as spans, metrics, and events.
    """

    def __init__(self, tracer_provider: TracerProvider | None = None):
        self._tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=Schemas.V1_36_0.value,
        )

    def start_llm(
        self,
        invocation: LLMInvocation,
    ) -> LLMInvocation:
        """Start an LLM invocation and create a pending span entry."""
        # Create a span and activate it using the OpenTelemetry helper scope
        span = self._tracer.start_span(
            name=f"{GenAI.GenAiOperationNameValues.CHAT.value} {invocation.request_model}",
            kind=SpanKind.CLIENT,
        )
        invocation.span = span
        scope = use_span(
            span,
            end_on_exit=False,
            record_exception=False,
            set_status_on_exception=False,
        )
        scope.__enter__()
        invocation.span_scope = scope
        return invocation

    def stop_llm(self, invocation: LLMInvocation) -> LLMInvocation:  # pylint: disable=no-self-use
        """Finalize an LLM invocation successfully and end its span."""
        if invocation.span_scope is None or invocation.span is None:
            # TODO: Provide feedback that this invocation was not started
            return invocation

        scope = invocation.span_scope
        span = invocation.span
        try:
            _apply_finish_attributes(span, invocation)
        finally:
            scope.__exit__(None, None, None)
            span.end()
            invocation.span_scope = None
            invocation.span = None
        return invocation

    def fail_llm(  # pylint: disable=no-self-use
        self, invocation: LLMInvocation, error: Error
    ) -> LLMInvocation:
        """Fail an LLM invocation and end its span with error status."""
        if invocation.span_scope is None or invocation.span is None:
            # TODO: Provide feedback that this invocation was not started
            return invocation

        scope = invocation.span_scope
        span = invocation.span
        try:
            _apply_error_attributes(span, error)
        finally:
            scope.__exit__(None, None, None)
            span.end()
            invocation.span_scope = None
            invocation.span = None
        return invocation

    @contextmanager
    def llm(
        self, invocation: Optional[LLMInvocation] = None
    ) -> Iterator[LLMInvocation]:
        """Context manager for LLM invocations.

        Only set data attributes on the invocation object, do not modify the span or
        context. Starts the span on entry. On normal exit, finalizes the invocation and
        ends the span. If an exception occurs inside the context, marks the span as
        error, ends it, and re-raises the original exception.
        """
        if invocation is None:
            invocation = LLMInvocation(request_model="")

        self.start_llm(invocation)
        try:
            yield invocation
        except Exception as exc:
            self.fail_llm(
                invocation,
                Error(message=str(exc), type=type(exc)),
            )
            raise
        self.stop_llm(invocation)


def get_telemetry_handler(
    tracer_provider: TracerProvider | None = None,
) -> TelemetryHandler:
    """
    Returns a singleton TelemetryHandler instance.
    """
    handler: Optional[TelemetryHandler] = getattr(
        get_telemetry_handler, "_default_handler", None
    )
    if handler is None:
        handler = TelemetryHandler(tracer_provider=tracer_provider)
        setattr(get_telemetry_handler, "_default_handler", handler)
    return handler
