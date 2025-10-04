from __future__ import annotations

from typing import Any, Optional

from opentelemetry._logs import Logger, get_logger

from ..interfaces import EmitterMeta
from ..types import (
    AgentInvocation,
    EmbeddingInvocation,
    Error,
    LLMInvocation,
    Task,
    Workflow,
)
from .utils import (
    _agent_to_log_record,
    _embedding_to_log_record,
    _llm_invocation_to_log_record,
    _task_to_log_record,
    _workflow_to_log_record,
)


class ContentEventsEmitter(EmitterMeta):
    """Emits input/output content as events (log records) instead of span attributes.

    Supported: LLMInvocation only.

    Exclusions:
      * EmbeddingInvocation – embeddings are vector lookups; content events intentionally omitted to reduce noise & cost.
      * ToolCall – tool calls typically reference external functions/APIs; their arguments are already span attributes and
        are not duplicated as content events (future structured tool audit events may be added separately).

    This explicit exclusion avoids surprising cardinality growth and keeps event volume proportional to user/chat messages.
    """

    role = "content_event"
    name = "semconv_content_events"

    def __init__(
        self, logger: Optional[Logger] = None, capture_content: bool = False
    ):
        self._logger: Logger = logger or get_logger(__name__)
        self._capture_content = capture_content

    def on_start(self, obj: Any) -> None:
        # LLM events are emitted in finish() when we have both input and output
        return None

    def on_end(self, obj: Any) -> None:
        if not self._capture_content:
            return

        # if isinstance(obj, Workflow):
        #     self._emit_workflow_event(obj)
        #     return
        # if isinstance(obj, Agent):
        #     self._emit_agent_event(obj)
        #     return
        # if isinstance(obj, Task):
        #     self._emit_task_event(obj)
        #     return
        # if isinstance(obj, EmbeddingInvocation):
        #     self._emit_embedding_event(obj)
        #     return

        if isinstance(obj, LLMInvocation):
            # Emit a single event for the entire LLM invocation
            try:
                record = _llm_invocation_to_log_record(
                    obj,
                    self._capture_content,
                )
                if record and self._logger:
                    self._logger.emit(record)
            except Exception as e:
                import logging

                logging.getLogger(__name__).warning(
                    f"Failed to emit LLM invocation event: {e}", exc_info=True
                )

    def on_error(self, error: Error, obj: Any) -> None:
        return None

    def handles(self, obj: Any) -> bool:
        return isinstance(
            obj, (LLMInvocation, Workflow, AgentInvocation, Task)
        )

    # Helper methods for new agentic types
    def _emit_workflow_event(self, workflow: Workflow) -> None:
        """Emit an event for a workflow."""
        try:
            record = _workflow_to_log_record(workflow, self._capture_content)
            if record and self._logger:
                self._logger.emit(record)
        except Exception:
            pass

    def _emit_agent_event(self, agent: AgentInvocation) -> None:
        """Emit an event for an agent operation."""
        try:
            record = _agent_to_log_record(agent, self._capture_content)
            if record and self._logger:
                self._logger.emit(record)
        except Exception:
            pass

    def _emit_task_event(self, task: Task) -> None:
        """Emit an event for a task."""
        try:
            record = _task_to_log_record(task, self._capture_content)
            if record and self._logger:
                self._logger.emit(record)
        except Exception:
            pass

    def _emit_embedding_event(self, embedding: EmbeddingInvocation) -> None:
        """Emit an event for an embedding operation."""
        try:
            record = _embedding_to_log_record(embedding, self._capture_content)
            if record and self._logger:
                self._logger.emit(record)
        except Exception:
            pass
