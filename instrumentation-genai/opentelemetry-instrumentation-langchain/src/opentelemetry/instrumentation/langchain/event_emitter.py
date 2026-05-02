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

"""Event emission for non-LLM GenAI operations in LangChain.

Emits semantic-convention-aligned log-record events for tool, agent, and
retriever spans.  LLM event emission is handled by the shared
``TelemetryHandler`` and is **not** duplicated here.

All event emission is gated behind the content policy so that events are
only produced when the user opts in via the
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` /
``OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT`` environment variables.
"""

from __future__ import annotations

from typing import Any, Optional

from opentelemetry._logs import Logger, LoggerProvider, LogRecord, get_logger
from opentelemetry.context import get_current
from opentelemetry.instrumentation.langchain.content_recording import (
    get_content_policy,
)
from opentelemetry.instrumentation.langchain.version import __version__
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import Span
from opentelemetry.trace.propagation import set_span_in_context

_REDACTED = "[redacted]"


class EventEmitter:
    """Emits GenAI semantic convention events for LangChain operations.

    Events are emitted as ``LogRecord`` instances linked to the active span
    context, following the same pattern used by the OpenAI v2 instrumentor
    and the shared ``_maybe_emit_llm_event`` helper in ``span_utils``.
    """

    def __init__(
        self, logger_provider: Optional[LoggerProvider] = None
    ) -> None:
        self._logger: Logger = get_logger(
            __name__,
            __version__,
            logger_provider,
            schema_url=Schemas.V1_37_0.value,
        )

    # ------------------------------------------------------------------
    # Tool events
    # ------------------------------------------------------------------

    def emit_tool_call_event(
        self,
        span: Span,
        tool_name: str,
        arguments: Optional[str] = None,
        tool_call_id: Optional[str] = None,
    ) -> None:
        """Emit a ``gen_ai.tool.call`` event when a tool is invoked."""
        if not self._should_emit():
            return

        policy = get_content_policy()
        body: dict[str, Any] = {"name": tool_name}
        if tool_call_id:
            body["id"] = tool_call_id
        if arguments is not None:
            body["arguments"] = (
                arguments if policy.record_content else _REDACTED
            )

        self._emit(span, "gen_ai.tool.call", body)

    def emit_tool_result_event(
        self,
        span: Span,
        tool_name: str,
        result: Optional[str] = None,
        tool_call_id: Optional[str] = None,
    ) -> None:
        """Emit a ``gen_ai.tool.result`` event when a tool returns."""
        if not self._should_emit():
            return

        policy = get_content_policy()
        body: dict[str, Any] = {"name": tool_name}
        if tool_call_id:
            body["id"] = tool_call_id
        if result is not None:
            body["result"] = result if policy.record_content else _REDACTED

        self._emit(span, "gen_ai.tool.result", body)

    # ------------------------------------------------------------------
    # Agent events
    # ------------------------------------------------------------------

    def emit_agent_start_event(
        self,
        span: Span,
        agent_name: str,
        input_messages: Optional[str] = None,
    ) -> None:
        """Emit a ``gen_ai.agent.start`` event when an agent begins."""
        if not self._should_emit():
            return

        policy = get_content_policy()
        body: dict[str, Any] = {"name": agent_name}
        if input_messages is not None:
            body["input"] = (
                input_messages if policy.record_content else _REDACTED
            )

        self._emit(span, "gen_ai.agent.start", body)

    def emit_agent_end_event(
        self,
        span: Span,
        agent_name: str,
        output_messages: Optional[str] = None,
    ) -> None:
        """Emit a ``gen_ai.agent.end`` event when an agent completes."""
        if not self._should_emit():
            return

        policy = get_content_policy()
        body: dict[str, Any] = {"name": agent_name}
        if output_messages is not None:
            body["output"] = (
                output_messages if policy.record_content else _REDACTED
            )

        self._emit(span, "gen_ai.agent.end", body)

    # ------------------------------------------------------------------
    # Retriever events
    # ------------------------------------------------------------------

    def emit_retriever_query_event(
        self,
        span: Span,
        retriever_name: str,
        query: Optional[str] = None,
    ) -> None:
        """Emit a ``gen_ai.retriever.query`` event for a retriever query."""
        if not self._should_emit():
            return

        policy = get_content_policy()
        body: dict[str, Any] = {"name": retriever_name}
        if query is not None:
            body["query"] = query if policy.record_content else _REDACTED

        self._emit(span, "gen_ai.retriever.query", body)

    def emit_retriever_result_event(
        self,
        span: Span,
        retriever_name: str,
        documents: Optional[str] = None,
    ) -> None:
        """Emit a ``gen_ai.retriever.result`` event with retrieved docs."""
        if not self._should_emit():
            return

        policy = get_content_policy()
        body: dict[str, Any] = {"name": retriever_name}
        if documents is not None:
            body["documents"] = (
                documents if policy.record_content else _REDACTED
            )

        self._emit(span, "gen_ai.retriever.result", body)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _should_emit() -> bool:
        """Check whether event emission is enabled via content policy."""
        return get_content_policy().should_emit_events

    def _emit(self, span: Span, event_name: str, body: dict[str, Any]) -> None:
        """Create a ``LogRecord`` linked to *span* and emit it."""
        context = set_span_in_context(span, get_current())
        self._logger.emit(
            LogRecord(
                event_name=event_name,
                body=body,
                context=context,
            )
        )
