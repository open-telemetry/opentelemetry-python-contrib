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
Span generation utilities for GenAI telemetry.

This module maps GenAI (Generative AI) invocations to OpenTelemetry spans and
applies GenAI semantic convention attributes.

Classes:
    - BaseTelemetryGenerator: Abstract base for GenAI telemetry emitters.
    - SpanGenerator: Concrete implementation that creates and finalizes spans
      for LLM operations (e.g., chat) and records input/output messages when
      experimental mode and content capture settings allow.

Usage:
    See `opentelemetry/util/genai/handler.py` for `TelemetryHandler`, which
    constructs `LLMInvocation` objects and delegates to `SpanGenerator.start`,
    `SpanGenerator.finish`, and `SpanGenerator.error` to produce spans that
    follow the GenAI semantic conventions.
"""

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from uuid import UUID

from opentelemetry import trace
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.trace import (
    Span,
    SpanKind,
    Tracer,
    set_span_in_context,
    use_span,
)

from .span_utils import (
    _apply_error_attributes,
    _apply_finish_attributes,
)
from .types import Error, LLMInvocation


@dataclass
class _SpanState:
    span: Span
    children: List[UUID] = field(default_factory=list)


class BaseTelemetryGenerator:
    """
    Abstract base for emitters mapping GenAI types -> OpenTelemetry.
    """

    def start(self, invocation: LLMInvocation) -> None:
        raise NotImplementedError

    def finish(self, invocation: LLMInvocation) -> None:
        raise NotImplementedError

    def error(self, error: Error, invocation: LLMInvocation) -> None:
        raise NotImplementedError


class SpanGenerator(BaseTelemetryGenerator):
    """
    Generates only spans.
    """

    def __init__(
        self,
        tracer: Optional[Tracer] = None,
    ):
        self._tracer: Tracer = tracer or trace.get_tracer(__name__)

        # TODO: Map from run_id -> _SpanState, to keep track of spans and parent/child relationships
        self.spans: Dict[UUID, _SpanState] = {}

    def _start_span(
        self,
        name: str,
        kind: SpanKind,
        parent_run_id: Optional[UUID] = None,
    ) -> Span:
        parent_span = (
            self.spans.get(parent_run_id)
            if parent_run_id is not None
            else None
        )
        if parent_span is not None:
            ctx = set_span_in_context(parent_span.span)
            span = self._tracer.start_span(name=name, kind=kind, context=ctx)
        else:
            # top-level or missing parent
            span = self._tracer.start_span(name=name, kind=kind)
            set_span_in_context(span)

        return span

    def _end_span(self, run_id: UUID):
        state = self.spans[run_id]
        for child_id in state.children:
            child_state = self.spans.get(child_id)
            if child_state:
                child_state.span.end()
        state.span.end()
        del self.spans[run_id]

    def start(self, invocation: LLMInvocation):
        # Create/register the span; keep it active but do not end it here.
        with self._start_span_for_invocation(invocation):
            pass

    @contextmanager
    def _start_span_for_invocation(self, invocation: LLMInvocation):
        """Create/register a span for the invocation and yield it.

        The span is not ended automatically on exiting the context; callers
        must finalize via _finalize_invocation.
        """
        # Establish parent/child relationship if a parent span exists.
        parent_state = (
            self.spans.get(invocation.parent_run_id)
            if invocation.parent_run_id is not None
            else None
        )
        if parent_state is not None:
            parent_state.children.append(invocation.run_id)
        span = self._start_span(
            name=f"{GenAI.GenAiOperationNameValues.CHAT.value} {invocation.request_model}",
            kind=SpanKind.CLIENT,
            parent_run_id=invocation.parent_run_id,
        )
        with use_span(span, end_on_exit=False) as span:
            span_state = _SpanState(
                span=span,
            )
            self.spans[invocation.run_id] = span_state
            yield span

    def finish(self, invocation: LLMInvocation):
        state = self.spans.get(invocation.run_id)
        if state is None:
            with self._start_span_for_invocation(invocation) as span:
                _apply_finish_attributes(span, invocation)
            self._end_span(invocation.run_id)
            return

        span = state.span
        _apply_finish_attributes(span, invocation)
        self._end_span(invocation.run_id)

    def error(self, error: Error, invocation: LLMInvocation):
        state = self.spans.get(invocation.run_id)
        if state is None:
            with self._start_span_for_invocation(invocation) as span:
                _apply_error_attributes(span, error)
            self._end_span(invocation.run_id)
            return

        span = state.span
        _apply_error_attributes(span, error)
        self._end_span(invocation.run_id)
