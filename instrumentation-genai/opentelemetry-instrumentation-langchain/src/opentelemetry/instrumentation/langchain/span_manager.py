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

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from uuid import UUID

from cachetools import TTLCache
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.trace import Span, SpanKind, Tracer, set_span_in_context
from opentelemetry.trace.status import Status, StatusCode

__all__ = ["_SpanManager"]


@dataclass
class _SpanState:
    span: Span
    children: List[UUID] = field(default_factory=lambda: list())


class _SpanManager:
    def __init__(
        self,
        tracer: Tracer,
    ) -> None:
        self._tracer = tracer

        # Map from run_id -> _SpanState, to keep track of spans and parent/child relationships
        # Using a TTL cache to avoid memory leaks in long-running processes where end_span might not be called.
        self.spans: TTLCache[UUID, _SpanState] = TTLCache(maxsize=1024, ttl=3600)

    def _create_span(
        self,
        run_id: UUID,
        parent_run_id: Optional[UUID],
        span_name: str,
        kind: SpanKind = SpanKind.INTERNAL,
    ) -> Span:
        if parent_run_id is not None and parent_run_id in self.spans:
            parent_state = self.spans[parent_run_id]
            parent_span = parent_state.span
            ctx = set_span_in_context(parent_span)
            span = self._tracer.start_span(
                name=span_name, kind=kind, context=ctx
            )
            parent_state.children.append(run_id)
        else:
            # top-level or missing parent
            span = self._tracer.start_span(name=span_name, kind=kind)
            set_span_in_context(span)

        span_state = _SpanState(span=span)
        self.spans[run_id] = span_state

        return span

    def create_chat_span(
        self,
        run_id: UUID,
        parent_run_id: Optional[UUID],
        request_model: str,
    ) -> Span:
        span = self._create_span(
            run_id=run_id,
            parent_run_id=parent_run_id,
            span_name=f"{GenAI.GenAiOperationNameValues.CHAT.value} {request_model}",
            kind=SpanKind.CLIENT,
        )
        span.set_attribute(
            GenAI.GEN_AI_OPERATION_NAME,
            GenAI.GenAiOperationNameValues.CHAT.value,
        )
        if request_model:
            span.set_attribute(GenAI.GEN_AI_REQUEST_MODEL, request_model)

        return span

    def end_span(self, run_id: UUID) -> None:
        state = self.spans.get(run_id)
        if not state:
            return

        for child_id in state.children:
            child_state = self.spans.get(child_id)
            if child_state:
                child_state.span.end()
                del self.spans[child_id]

        state.span.end()
        del self.spans[run_id]

    def get_span(self, run_id: UUID) -> Optional[Span]:
        state = self.spans.get(run_id)
        return state.span if state else None

    def handle_error(self, error: BaseException, run_id: UUID):
        span = self.get_span(run_id)
        if span is None:
            # If the span does not exist, we cannot set the error status
            return
        span.set_status(Status(StatusCode.ERROR, str(error)))
        span.set_attribute(
            ErrorAttributes.ERROR_TYPE, type(error).__qualname__
        )
        self.end_span(run_id)
