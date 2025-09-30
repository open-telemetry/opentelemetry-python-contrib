from __future__ import annotations

from typing import Any, Optional

from opentelemetry._logs import Logger, get_logger

from ..types import Error, LLMInvocation
from .utils import _chat_generation_to_log_record, _message_to_log_record


class ContentEventsEmitter:
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

    def start(self, obj: Any) -> None:
        if not isinstance(obj, LLMInvocation) or not self._capture_content:
            return
        invocation = obj
        if not invocation.input_messages:
            return
        for msg in invocation.input_messages:
            try:
                record = _message_to_log_record(
                    msg,
                    provider_name=invocation.provider,
                    framework=invocation.attributes.get("framework"),
                    capture_content=self._capture_content,
                )
                if record and self._logger:
                    self._logger.emit(record)
            except Exception:
                pass

    def finish(self, obj: Any) -> None:
        if not isinstance(obj, LLMInvocation) or not self._capture_content:
            return
        invocation = obj
        if invocation.span is None or not invocation.output_messages:
            return
        for index, msg in enumerate(invocation.output_messages):
            try:
                record = _chat_generation_to_log_record(
                    msg,
                    index,
                    invocation.provider,
                    invocation.attributes.get("framework"),
                    self._capture_content,
                )
                if record:
                    try:
                        self._logger.emit(record)
                    except Exception:
                        pass
            except Exception:
                pass

    def error(self, error: Error, obj: Any) -> None:
        return None

    def handles(self, obj: Any) -> bool:
        return isinstance(obj, LLMInvocation)
