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

"""OpenTelemetry span handler for LlamaIndex dispatcher integration."""

from __future__ import annotations

import inspect
import json
import logging
import re
from dataclasses import dataclass, field
from functools import singledispatchmethod
from typing import Any, AsyncGenerator, Dict, Generator, List, Optional

from opentelemetry import context as context_api
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.trace import Span, Tracer, set_span_in_context

from opentelemetry.instrumentation.llamaindex.utils import (
    LlamaIndexJSONEncoder,
    should_capture_content,
)

logger = logging.getLogger(__name__)

# Custom semantic attributes for LlamaIndex (following gen_ai.* namespace)
GENAI_OPERATION_NAME = "gen_ai.operation.name"
LLAMAINDEX_ENTITY_NAME = "gen_ai.llamaindex.entity.name"
LLAMAINDEX_ENTITY_INPUT = "gen_ai.llamaindex.entity.input"
LLAMAINDEX_ENTITY_OUTPUT = "gen_ai.llamaindex.entity.output"

# LLM-specific attributes
LLAMAINDEX_LLM_MODEL = "gen_ai.llamaindex.llm.model"
LLAMAINDEX_LLM_TEMPERATURE = "gen_ai.llamaindex.llm.temperature"

# Embedding attributes
LLAMAINDEX_EMBEDDING_MODEL = "gen_ai.llamaindex.embedding.model"
LLAMAINDEX_EMBEDDING_TEXT_COUNT = "gen_ai.llamaindex.embedding.text_count"

# Retriever attributes
LLAMAINDEX_RETRIEVER_TOP_K = "gen_ai.llamaindex.retriever.top_k"

# Agent attributes
LLAMAINDEX_AGENT_TOOL_NAME = "gen_ai.llamaindex.agent.tool.name"
LLAMAINDEX_AGENT_TOOL_DESCRIPTION = "gen_ai.llamaindex.agent.tool.description"

# Key for suppressing nested instrumentation
SUPPRESS_LANGUAGE_MODEL_INSTRUMENTATION_KEY = "suppress_language_model_instrumentation"

# Regex to extract class and method names from LlamaIndex span IDs
CLASS_AND_METHOD_NAME_FROM_ID_REGEX = re.compile(r"([a-zA-Z]+)\.([a-zA-Z_]+)-")

# Classes that have their own OpenTelemetry instrumentation
AVAILABLE_OPENTELEMETRY_INSTRUMENTATIONS = ["OpenAI", "Anthropic"]


@dataclass
class SpanHolder:
    """Holds span state during LlamaIndex instrumentation."""

    span_id: str
    parent: Optional["SpanHolder"] = None
    otel_span: Optional[Span] = None
    token: Optional[Any] = None
    context: Optional[context_api.context.Context] = None
    waiting_for_streaming: bool = field(init=False, default=False)
    _active: bool = field(init=False, default=True)

    def process_event(self, event: Any) -> List["SpanHolder"]:
        """Process an event and update the span."""
        self._update_span_for_event(event)

        # Check if this is a streaming end event
        if self.waiting_for_streaming and self._is_streaming_end_event(event):
            self.end()
            return [self] + self._notify_parent()

        return []

    def _is_streaming_end_event(self, event: Any) -> bool:
        """Check if event signals end of streaming."""
        event_type = type(event).__name__
        return event_type in (
            "LLMChatEndEvent",
            "LLMCompletionEndEvent",
            "StreamChatEndEvent",
        )

    def _notify_parent(self) -> List["SpanHolder"]:
        """Notify parent spans to end."""
        if self.parent:
            self.parent.end()
            return [self.parent] + self.parent._notify_parent()
        return []

    def end(self, should_detach_context: bool = True) -> None:
        """End the span."""
        if not self._active:
            return

        self._active = False
        if self.otel_span:
            self.otel_span.end()
        if self.token and should_detach_context:
            context_api.detach(self.token)

    @singledispatchmethod
    def _update_span_for_event(self, event: Any) -> None:
        """Update span with event data. Dispatched by event type."""
        pass

    def _set_llm_attributes(self, event: Any) -> None:
        """Set LLM-related attributes from event."""
        if not self.otel_span:
            return

        # Extract model info from event
        if hasattr(event, "model"):
            self.otel_span.set_attribute(
                GenAIAttributes.GEN_AI_REQUEST_MODEL, str(event.model)
            )
        if hasattr(event, "model_name"):
            self.otel_span.set_attribute(
                GenAIAttributes.GEN_AI_REQUEST_MODEL, str(event.model_name)
            )
        if hasattr(event, "temperature"):
            self.otel_span.set_attribute(
                GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE, event.temperature
            )

        # Handle messages if content capture is enabled
        if should_capture_content() and hasattr(event, "messages"):
            try:
                messages_str = json.dumps(
                    [
                        {"role": getattr(m, "role", "user"), "content": str(m.content)}
                        for m in event.messages
                        if hasattr(m, "content")
                    ]
                )
                self.otel_span.set_attribute(LLAMAINDEX_ENTITY_INPUT, messages_str)
            except Exception:
                pass

    def _set_embedding_attributes(self, event: Any) -> None:
        """Set embedding-related attributes from event."""
        if not self.otel_span:
            return

        if hasattr(event, "model_name"):
            self.otel_span.set_attribute(
                LLAMAINDEX_EMBEDDING_MODEL, str(event.model_name)
            )

    def _set_tool_attributes(self, event: Any) -> None:
        """Set tool-related attributes from event."""
        if not self.otel_span:
            return

        if hasattr(event, "tool_name"):
            self.otel_span.set_attribute(LLAMAINDEX_AGENT_TOOL_NAME, event.tool_name)
        if hasattr(event, "tool_description"):
            self.otel_span.set_attribute(
                LLAMAINDEX_AGENT_TOOL_DESCRIPTION, event.tool_description
            )


class OpenTelemetrySpanHandler:
    """Span handler for LlamaIndex dispatcher integration.

    This handler integrates with LlamaIndex's instrumentation dispatcher
    to create OpenTelemetry spans for various LlamaIndex operations.
    """

    def __init__(self, tracer: Tracer) -> None:
        """Initialize the span handler.

        Args:
            tracer: The OpenTelemetry tracer to use.
        """
        self._tracer = tracer
        self.open_spans: Dict[str, SpanHolder] = {}
        self.waiting_for_streaming_spans: Dict[str, SpanHolder] = {}

    def new_span(
        self,
        id_: str,
        bound_args: inspect.BoundArguments,
        instance: Optional[Any] = None,
        parent_span_id: Optional[str] = None,
        tags: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Optional[SpanHolder]:
        """Create a new span for a LlamaIndex operation.

        Args:
            id_: Unique identifier for the span.
            bound_args: Bound arguments from the method call.
            instance: The instance the method was called on.
            parent_span_id: ID of the parent span, if any.
            tags: Optional tags for the span.
            **kwargs: Additional keyword arguments.

        Returns:
            SpanHolder containing the span, or None if creation failed.
        """
        # Extract class and method name from ID
        matches = CLASS_AND_METHOD_NAME_FROM_ID_REGEX.match(id_)
        if not matches:
            return None

        class_name = matches.groups()[0]
        method_name = matches.groups()[1]

        parent = self.open_spans.get(parent_span_id) if parent_span_id else None

        # If the class has its own OTel instrumentation, don't create a span
        if class_name in AVAILABLE_OPENTELEMETRY_INSTRUMENTATIONS:
            token = context_api.attach(
                context_api.set_value(SUPPRESS_LANGUAGE_MODEL_INSTRUMENTATION_KEY, False)
            )
            holder = SpanHolder(id_, parent, token=token)
            self.open_spans[id_] = holder
            return holder

        # Determine operation name based on context
        if parent:
            operation_name = "task"
        else:
            operation_name = "workflow"

        # Create span name
        span_name = f"{class_name}.{operation_name}"

        # Start the span
        span = self._tracer.start_span(
            span_name,
            context=parent.context if parent else None,
        )

        # Set up context
        current_context = set_span_in_context(
            span, context=parent.context if parent else None
        )
        current_context = context_api.set_value(
            SUPPRESS_LANGUAGE_MODEL_INSTRUMENTATION_KEY,
            True,
            current_context,
        )
        token = context_api.attach(current_context)

        # Set standard attributes
        span.set_attribute(GenAIAttributes.GEN_AI_SYSTEM, "llamaindex")
        span.set_attribute(GENAI_OPERATION_NAME, operation_name)
        span.set_attribute(LLAMAINDEX_ENTITY_NAME, span_name)

        # Set input attributes if content capture is enabled
        if should_capture_content():
            try:
                span.set_attribute(
                    LLAMAINDEX_ENTITY_INPUT,
                    json.dumps(bound_args.arguments, cls=LlamaIndexJSONEncoder),
                )
            except Exception:
                pass

        holder = SpanHolder(id_, parent, span, token, current_context)
        self.open_spans[id_] = holder
        return holder

    def prepare_to_exit_span(
        self,
        id_: str,
        instance: Optional[Any] = None,
        result: Optional[Any] = None,
        **kwargs: Any,
    ) -> Optional[SpanHolder]:
        """Prepare to exit a span, capturing result data.

        Args:
            id_: The span ID.
            instance: The instance the method was called on.
            result: The result of the method call.
            **kwargs: Additional keyword arguments.

        Returns:
            The SpanHolder, or None if not found.
        """
        span_holder = self.open_spans.get(id_)
        if not span_holder:
            return None

        # Set output attributes if content capture is enabled
        if should_capture_content() and span_holder.otel_span:
            try:
                serialized_output = json.dumps(result, cls=LlamaIndexJSONEncoder)
                output = json.loads(serialized_output)
                # Remove large fields
                if isinstance(output, dict) and "source_nodes" in output:
                    del output["source_nodes"]
                span_holder.otel_span.set_attribute(
                    LLAMAINDEX_ENTITY_OUTPUT,
                    json.dumps(output, cls=LlamaIndexJSONEncoder),
                )
            except Exception:
                pass

        # Check if this is a streaming response
        if self._is_streaming_result(result):
            span_holder.waiting_for_streaming = True
            self.waiting_for_streaming_spans[id_] = span_holder
            return span_holder

        # End the span normally
        span_holder.end()
        return span_holder

    def _is_streaming_result(self, result: Any) -> bool:
        """Check if the result is a streaming response."""
        if isinstance(result, (Generator, AsyncGenerator)):
            return True
        # Check for LlamaIndex StreamingResponse
        result_type = type(result).__name__
        return result_type in ("StreamingResponse", "StreamingAgentChatResponse")

    def prepare_to_drop_span(
        self, id_: str, err: Optional[Exception] = None, **kwargs: Any
    ) -> Optional[SpanHolder]:
        """Prepare to drop a span (on error).

        Args:
            id_: The span ID.
            err: The exception that caused the span to be dropped.
            **kwargs: Additional keyword arguments.

        Returns:
            The SpanHolder, or None if not found.
        """
        return self.open_spans.get(id_)


class OpenTelemetryEventHandler:
    """Event handler for LlamaIndex dispatcher integration.

    This handler processes events from LlamaIndex and updates
    the corresponding spans.
    """

    def __init__(self, span_handler: OpenTelemetrySpanHandler) -> None:
        """Initialize the event handler.

        Args:
            span_handler: The span handler to use.
        """
        self._span_handler = span_handler

    def handle(self, event: Any, **kwargs: Any) -> None:
        """Handle an event from LlamaIndex.

        Args:
            event: The event to handle.
            **kwargs: Additional keyword arguments.
        """
        span_id = getattr(event, "span_id", None)
        if not span_id:
            return

        span = self._span_handler.open_spans.get(span_id)
        if not span:
            span = self._span_handler.waiting_for_streaming_spans.get(span_id)
        if not span:
            return

        finished_spans = span.process_event(event)

        for finished_span in finished_spans:
            self._span_handler.waiting_for_streaming_spans.pop(
                finished_span.span_id, None
            )
