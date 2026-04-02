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

"""Span lifecycle manager for the LangChain instrumentor.

Manages creation, parent-context resolution, ignored-run walk-through,
per-thread agent stacks, and clean teardown for all GenAI operation types.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from opentelemetry.instrumentation.langchain.semconv_attributes import (
    OP_CHAT,
    OP_INVOKE_AGENT,
    OP_TEXT_COMPLETION,
    get_operation_span_kind,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import error_attributes
from opentelemetry.trace import Span, SpanKind, Tracer, set_span_in_context
from opentelemetry.trace.status import Status, StatusCode

__all__ = ["_SpanManager"]

# Operations that produce model-level duration metrics.
_MODEL_OPERATIONS: frozenset[str] = frozenset({OP_CHAT, OP_TEXT_COMPLETION})


@dataclass
class SpanRecord:
    """Rich record stored for every active span."""

    run_id: str
    span: Span
    operation: str
    parent_run_id: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    # Mutable scratch space for streaming timing, thread keys, etc.
    stash: Dict[str, Any] = field(default_factory=dict)


class _SpanManager:
    """Thread-safe span lifecycle manager for every GenAI operation type."""

    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer
        self._lock = threading.Lock()

        # run_id (str) → SpanRecord
        self._spans: Dict[str, SpanRecord] = {}

        # Runs we decided to skip (e.g. internal LangChain plumbing) but
        # whose children should still be linked to the correct parent.
        self._ignored_runs: set[str] = set()
        # Maps an ignored run_id to the parent_run_id it was called with,
        # so children can walk through to the real ancestor.
        self._run_parent_override: Dict[str, Optional[str]] = {}

        # Per-thread stacks of invoke_agent run_ids for hierarchy tracking
        # in concurrent execution.  key = thread_key (str).
        self._agent_stack_by_thread: Dict[str, List[str]] = {}

        # Per-thread stacks for LangGraph Command(goto=...) transitions.
        # key = thread_key (str), value = stack of parent_run_ids.
        self._goto_parent_stack: Dict[str, List[str]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_span(
        self,
        run_id: str | object,
        name: str,
        operation: str,
        kind: Optional[SpanKind] = None,
        parent_run_id: Optional[str | object] = None,
        attributes: Optional[Dict[str, Any]] = None,
        thread_key: Optional[str] = None,
    ) -> SpanRecord:
        """Create and register a new span.

        Parameters
        ----------
        run_id:
            Unique identifier for this run (UUID or str).
        name:
            Human-readable span name (e.g. ``"chat gpt-4o"``).
        operation:
            One of the ``OP_*`` constants from ``semconv_attributes``.
        kind:
            Override the SpanKind.  When *None* the kind is derived from
            *operation* via ``get_operation_span_kind``.
        parent_run_id:
            The run_id of the logical parent (may be an ignored run).
        attributes:
            Initial span attributes to set immediately.
        thread_key:
            Identifies the execution thread; used for agent stack tracking.
        """
        rid = str(run_id)
        prid = str(parent_run_id) if parent_run_id is not None else None

        if kind is None:
            kind = get_operation_span_kind(operation)

        # Walk through ignored runs so children attach to the correct
        # visible ancestor.
        resolved_prid = self._resolve_parent_id(prid)

        # Build parent context.
        ctx = None
        with self._lock:
            if resolved_prid is not None:
                parent_record = self._spans.get(resolved_prid)
                if parent_record is not None:
                    ctx = set_span_in_context(parent_record.span)

        span = self._tracer.start_span(name=name, kind=kind, context=ctx)

        attrs = attributes or {}
        for attr_key, attr_val in attrs.items():
            span.set_attribute(attr_key, attr_val)

        stash: Dict[str, Any] = {}
        if operation in _MODEL_OPERATIONS:
            stash["started_at"] = time.perf_counter()
        if thread_key is not None:
            stash["thread_key"] = thread_key

        record = SpanRecord(
            run_id=rid,
            span=span,
            operation=operation,
            parent_run_id=prid,
            attributes=attrs,
            stash=stash,
        )

        with self._lock:
            self._spans[rid] = record

            # Maintain per-thread agent stack.
            if operation == OP_INVOKE_AGENT and thread_key is not None:
                self._agent_stack_by_thread.setdefault(thread_key, []).append(
                    rid
                )

        return record

    def end_span(
        self,
        run_id: str | object,
        status: Optional[StatusCode] = None,
        error: Optional[BaseException] = None,
    ) -> None:
        """Finalise and end the span identified by *run_id*.

        Parameters
        ----------
        run_id:
            The run whose span should be ended.
        status:
            Explicit status code.  When *error* is provided this defaults to
            ``StatusCode.ERROR``.
        error:
            If supplied the span is marked as failed with ``error.type``
            recorded as an attribute.
        """
        rid = str(run_id)

        with self._lock:
            record = self._spans.pop(rid, None)
        if record is None:
            return

        span = record.span

        if error is not None:
            span.set_attribute(
                error_attributes.ERROR_TYPE, type(error).__qualname__
            )
            span.set_status(Status(StatusCode.ERROR, str(error)))
        elif status is not None:
            span.set_status(Status(status))

        # Pop from agent stack if applicable.
        thread_key = record.stash.get("thread_key")
        if record.operation == OP_INVOKE_AGENT and thread_key is not None:
            with self._lock:
                stack = self._agent_stack_by_thread.get(thread_key)
                if stack:
                    try:
                        stack.remove(rid)
                    except ValueError:
                        pass
                    if not stack:
                        del self._agent_stack_by_thread[thread_key]

        span.end()

    def get_record(self, run_id: str | object) -> Optional[SpanRecord]:
        """Return the ``SpanRecord`` for *run_id*, or ``None``."""
        rid = str(run_id)
        with self._lock:
            return self._spans.get(rid)

    # ------------------------------------------------------------------
    # Ignored-run management
    # ------------------------------------------------------------------

    def ignore_run(
        self,
        run_id: str | object,
        parent_run_id: Optional[str | object] = None,
    ) -> None:
        """Mark *run_id* as ignored.

        Any future child whose ``parent_run_id`` points at an ignored run
        will be re-parented to the ignored run's own parent via
        ``resolve_parent_id``.
        """
        rid = str(run_id)
        prid = str(parent_run_id) if parent_run_id is not None else None
        with self._lock:
            self._ignored_runs.add(rid)
            self._run_parent_override[rid] = prid

    def is_ignored(self, run_id: str | object) -> bool:
        rid = str(run_id)
        with self._lock:
            return rid in self._ignored_runs

    def resolve_parent_id(
        self, parent_run_id: Optional[str | object]
    ) -> Optional[str]:
        """Public wrapper around the internal resolver."""
        prid = str(parent_run_id) if parent_run_id is not None else None
        return self._resolve_parent_id(prid)

    # ------------------------------------------------------------------
    # Token usage accumulation
    # ------------------------------------------------------------------

    def _accumulate_on_record(
        self,
        record: SpanRecord,
        input_tokens: Optional[int],
        output_tokens: Optional[int],
    ) -> None:
        """Add token counts to *record*.  Caller **must** hold ``self._lock``."""
        if input_tokens is not None:
            existing = record.attributes.get(
                GenAI.GEN_AI_USAGE_INPUT_TOKENS, 0
            )
            new_val = (existing or 0) + input_tokens
            record.span.set_attribute(GenAI.GEN_AI_USAGE_INPUT_TOKENS, new_val)
            record.attributes[GenAI.GEN_AI_USAGE_INPUT_TOKENS] = new_val
        if output_tokens is not None:
            existing = record.attributes.get(
                GenAI.GEN_AI_USAGE_OUTPUT_TOKENS, 0
            )
            new_val = (existing or 0) + output_tokens
            record.span.set_attribute(
                GenAI.GEN_AI_USAGE_OUTPUT_TOKENS, new_val
            )
            record.attributes[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] = new_val

    def accumulate_usage_to_parent(
        self,
        record: SpanRecord,
        input_tokens: Optional[int],
        output_tokens: Optional[int],
    ) -> None:
        """Propagate token usage from a model span to its parent agent span."""
        if input_tokens is None and output_tokens is None:
            return

        parent_key = record.parent_run_id
        visited: set[str] = set()
        with self._lock:
            while parent_key:
                if parent_key in visited:
                    break
                visited.add(parent_key)
                parent_record = self._spans.get(parent_key)
                if not parent_record:
                    break
                if parent_record.operation == OP_INVOKE_AGENT:
                    self._accumulate_on_record(
                        parent_record, input_tokens, output_tokens
                    )
                    break
                parent_key = parent_record.parent_run_id

    def accumulate_llm_usage_to_agent(
        self,
        parent_run_id: Optional[str | object],
        input_tokens: Optional[int],
        output_tokens: Optional[int],
    ) -> None:
        """Propagate LLM token usage up to the nearest agent span.

        Unlike ``accumulate_usage_to_parent`` (which starts from a
        ``SpanRecord``'s parent), this resolves through ignored runs first
        and then walks up to find the nearest ``invoke_agent`` ancestor.
        Designed to be called from ``on_llm_end`` where the LLM span is
        managed by :class:`TelemetryHandler`, not :class:`_SpanManager`.
        """
        if input_tokens is None and output_tokens is None:
            return

        prid = str(parent_run_id) if parent_run_id is not None else None
        resolved = self._resolve_parent_id(prid)
        if resolved is None:
            return

        visited: set[str] = set()
        current = resolved
        with self._lock:
            while current:
                if current in visited:
                    break
                visited.add(current)
                record = self._spans.get(current)
                if not record:
                    break
                if record.operation == OP_INVOKE_AGENT:
                    self._accumulate_on_record(
                        record, input_tokens, output_tokens
                    )
                    return
                current = record.parent_run_id

    def nearest_agent_parent(self, record: SpanRecord) -> Optional[str]:
        """Walk up the parent chain to find the nearest invoke_agent ancestor.

        Returns the run_id of the nearest agent span, or *None*.
        """
        parent_key = record.parent_run_id
        visited: set[str] = set()
        with self._lock:
            while parent_key:
                if parent_key in visited:
                    break
                visited.add(parent_key)
                parent_record = self._spans.get(parent_key)
                if not parent_record:
                    break
                if parent_record.operation == OP_INVOKE_AGENT:
                    return parent_key
                parent_key = parent_record.parent_run_id
        return None

    # ------------------------------------------------------------------
    # LangGraph goto support
    # ------------------------------------------------------------------

    def push_goto_parent(self, thread_key: str, parent_run_id: str) -> None:
        """Push a goto parent onto the per-thread stack."""
        with self._lock:
            self._goto_parent_stack.setdefault(thread_key, []).append(
                parent_run_id
            )

    def pop_goto_parent(self, thread_key: str) -> Optional[str]:
        """Pop and return the most recent goto parent, or *None*."""
        with self._lock:
            stack = self._goto_parent_stack.get(thread_key)
            if stack:
                val = stack.pop()
                if not stack:
                    del self._goto_parent_stack[thread_key]
                return val
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_parent_id(
        self, parent_run_id: Optional[str]
    ) -> Optional[str]:
        """Walk through ignored runs to find the nearest visible ancestor."""
        if parent_run_id is None:
            return None

        visited: set[str] = set()
        current = parent_run_id
        with self._lock:
            while current in self._ignored_runs:
                if current in visited:
                    # Cycle guard.
                    return None
                visited.add(current)
                current = self._run_parent_override.get(current)
                if current is None:
                    return None
        return current
