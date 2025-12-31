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

"""Span utilities for LangChain instrumentation."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.messages import BaseMessage  # type: ignore[import-untyped]
from langchain_core.outputs import LLMResult  # type: ignore[import-untyped]
from opentelemetry.context import Context
from opentelemetry.metrics import Histogram
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.trace import Span, SpanKind, Tracer, set_span_in_context
from opentelemetry.trace.status import Status, StatusCode

from opentelemetry.instrumentation.langchain.semconv import (
    GenAISpanKindValues,
    LLMRequestTypeValues,
    SpanAttributes,
)
from opentelemetry.instrumentation.langchain.utils import (
    CallbackFilteredJSONEncoder,
    should_send_prompts,
)

__all__ = ["SpanHolder", "SpanManager"]


@dataclass
class SpanHolder:
    """Holds span state and metadata for a LangChain execution.

    Attributes:
        span: The OpenTelemetry span.
        token: Context token for span attachment.
        context: The context containing this span.
        children: List of child run IDs.
        workflow_name: Name of the workflow.
        entity_name: Name of the entity (chain, tool, etc.).
        entity_path: Full path of the entity in the workflow.
        start_time: Start time of the span.
        request_model: The model name used for the request.
    """

    span: Span
    token: Any
    context: Context
    children: List[UUID] = field(default_factory=list)
    workflow_name: str = ""
    entity_name: str = ""
    entity_path: str = ""
    start_time: float = field(default_factory=time.time)
    request_model: Optional[str] = None


@dataclass
class _SpanState:
    """Legacy span state for backward compatibility."""

    span: Span
    children: List[UUID] = field(default_factory=list)


class SpanManager:
    """Manages OpenTelemetry spans for LangChain operations.

    This class handles span creation, parent-child relationships,
    and span lifecycle for LangChain instrumentation.
    """

    def __init__(self, tracer: Tracer) -> None:
        """Initialize the span manager.

        Args:
            tracer: The OpenTelemetry tracer to use for span creation.
        """
        self._tracer = tracer
        # Map from run_id -> SpanHolder
        self.spans: Dict[UUID, SpanHolder] = {}

    def create_span(
        self,
        run_id: UUID,
        parent_run_id: Optional[UUID],
        span_name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        span_kind_value: GenAISpanKindValues = GenAISpanKindValues.TASK,
        entity_name: str = "",
        workflow_name: str = "",
    ) -> SpanHolder:
        """Create a new span for a LangChain operation.

        Args:
            run_id: Unique identifier for this run.
            parent_run_id: Parent run ID, if any.
            span_name: Name for the span.
            kind: OpenTelemetry span kind.
            span_kind_value: GenAI operation name value.
            entity_name: Name of the entity.
            workflow_name: Name of the workflow.

        Returns:
            SpanHolder containing the created span and metadata.
        """
        parent_context = None
        entity_path = entity_name

        if parent_run_id is not None and parent_run_id in self.spans:
            parent_holder = self.spans[parent_run_id]
            parent_context = set_span_in_context(parent_holder.span)
            parent_holder.children.append(run_id)
            # Build entity path
            if parent_holder.entity_path:
                entity_path = f"{parent_holder.entity_path}.{entity_name}"
            # Inherit workflow name
            if not workflow_name and parent_holder.workflow_name:
                workflow_name = parent_holder.workflow_name

        span = self._tracer.start_span(
            name=span_name, kind=kind, context=parent_context
        )

        # Set common attributes
        if span.is_recording():
            span.set_attribute(
                GenAIAttributes.GEN_AI_OPERATION_NAME, span_kind_value.value
            )
            if entity_name:
                span.set_attribute(
                    SpanAttributes.LANGCHAIN_ENTITY_NAME, entity_name
                )
            if entity_path:
                span.set_attribute(
                    SpanAttributes.LANGCHAIN_ENTITY_PATH, entity_path
                )
            if workflow_name:
                span.set_attribute(
                    SpanAttributes.LANGCHAIN_WORKFLOW_NAME, workflow_name
                )

        context = set_span_in_context(span)
        token = None  # Context attachment handled separately

        holder = SpanHolder(
            span=span,
            token=token,
            context=context,
            workflow_name=workflow_name,
            entity_name=entity_name,
            entity_path=entity_path,
        )
        self.spans[run_id] = holder
        return holder

    def create_chat_span(
        self,
        run_id: UUID,
        parent_run_id: Optional[UUID],
        request_model: str,
        vendor: str = "langchain",
    ) -> SpanHolder:
        """Create a span for a chat model invocation.

        Args:
            run_id: Unique identifier for this run.
            parent_run_id: Parent run ID, if any.
            request_model: The model name being used.
            vendor: The LLM vendor name.

        Returns:
            SpanHolder containing the created span.
        """
        holder = self.create_span(
            run_id=run_id,
            parent_run_id=parent_run_id,
            span_name=f"chat {request_model}",
            kind=SpanKind.CLIENT,
            span_kind_value=GenAISpanKindValues.CHAT,
            entity_name=request_model,
        )

        span = holder.span
        if span.is_recording():
            span.set_attribute(
                GenAIAttributes.GEN_AI_OPERATION_NAME,
                GenAIAttributes.GenAiOperationNameValues.CHAT.value,
            )
            span.set_attribute(GenAIAttributes.GEN_AI_REQUEST_MODEL, request_model)
            span.set_attribute(GenAIAttributes.GEN_AI_SYSTEM, vendor)

        holder.request_model = request_model
        return holder

    def create_chain_span(
        self,
        run_id: UUID,
        parent_run_id: Optional[UUID],
        chain_name: str,
        span_kind_value: GenAISpanKindValues = GenAISpanKindValues.TASK,
    ) -> SpanHolder:
        """Create a span for a chain execution.

        Args:
            run_id: Unique identifier for this run.
            parent_run_id: Parent run ID, if any.
            chain_name: Name of the chain.
            span_kind_value: The operation name value (workflow or task).

        Returns:
            SpanHolder containing the created span.
        """
        span_name = f"{chain_name}.{span_kind_value.value}"
        workflow_name = chain_name if span_kind_value == GenAISpanKindValues.WORKFLOW else ""

        return self.create_span(
            run_id=run_id,
            parent_run_id=parent_run_id,
            span_name=span_name,
            kind=SpanKind.INTERNAL,
            span_kind_value=span_kind_value,
            entity_name=chain_name,
            workflow_name=workflow_name,
        )

    def create_tool_span(
        self,
        run_id: UUID,
        parent_run_id: Optional[UUID],
        tool_name: str,
    ) -> SpanHolder:
        """Create a span for a tool execution.

        Args:
            run_id: Unique identifier for this run.
            parent_run_id: Parent run ID, if any.
            tool_name: Name of the tool.

        Returns:
            SpanHolder containing the created span.
        """
        return self.create_span(
            run_id=run_id,
            parent_run_id=parent_run_id,
            span_name=f"{tool_name}.tool",
            kind=SpanKind.INTERNAL,
            span_kind_value=GenAISpanKindValues.TOOL,
            entity_name=tool_name,
        )

    def get_span_holder(self, run_id: UUID) -> Optional[SpanHolder]:
        """Get the SpanHolder for a run ID.

        Args:
            run_id: The run ID to look up.

        Returns:
            The SpanHolder if found, None otherwise.
        """
        return self.spans.get(run_id)

    def get_span(self, run_id: UUID) -> Optional[Span]:
        """Get the span for a run ID.

        Args:
            run_id: The run ID to look up.

        Returns:
            The Span if found, None otherwise.
        """
        holder = self.spans.get(run_id)
        return holder.span if holder else None

    def end_span(self, run_id: UUID) -> None:
        """End a span and clean up.

        Args:
            run_id: The run ID of the span to end.
        """
        holder = self.spans.get(run_id)
        if holder is None:
            return

        # End children first
        for child_id in holder.children:
            child_holder = self.spans.get(child_id)
            if child_holder:
                child_holder.span.end()
                del self.spans[child_id]

        holder.span.end()
        del self.spans[run_id]

    def handle_error(self, error: BaseException, run_id: UUID) -> None:
        """Handle an error by setting span status and ending.

        Args:
            error: The exception that occurred.
            run_id: The run ID of the span.
        """
        holder = self.spans.get(run_id)
        if holder is None:
            return

        holder.span.set_status(Status(StatusCode.ERROR, str(error)))
        holder.span.set_attribute(
            ErrorAttributes.ERROR_TYPE, type(error).__qualname__
        )
        self.end_span(run_id)


# Utility functions for setting span attributes


def _message_type_to_role(message_type: str) -> str:
    """Convert LangChain message type to role.

    Args:
        message_type: The LangChain message type.

    Returns:
        The corresponding role string.
    """
    mapping = {
        "human": "user",
        "system": "system",
        "ai": "assistant",
        "tool": "tool",
    }
    return mapping.get(message_type, "unknown")


def _set_span_attribute(span: Span, key: str, value: Any) -> None:
    """Set a span attribute if the value is not None.

    Args:
        span: The span to set the attribute on.
        key: The attribute key.
        value: The attribute value.
    """
    if value is not None and span.is_recording():
        span.set_attribute(key, value if value != "" else "")


def set_request_params(
    span: Span, kwargs: Dict[str, Any], span_holder: SpanHolder
) -> None:
    """Set request parameters on a span.

    Args:
        span: The span to set attributes on.
        kwargs: The keyword arguments containing request parameters.
        span_holder: The span holder to update with model name.
    """
    if not span.is_recording():
        return

    # Extract model name
    model = None
    for model_tag in ("model", "model_id", "model_name"):
        if (m := kwargs.get(model_tag)) is not None:
            model = m
            break
        if (m := (kwargs.get("invocation_params") or {}).get(model_tag)) is not None:
            model = m
            break

    if model:
        span_holder.request_model = model
        _set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_MODEL, model)
        _set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, model)

    # Get params from invocation_params or kwargs
    if "invocation_params" in kwargs:
        params = kwargs["invocation_params"].get("params") or kwargs["invocation_params"]
    else:
        params = kwargs

    _set_span_attribute(
        span,
        GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS,
        params.get("max_tokens") or params.get("max_new_tokens"),
    )
    _set_span_attribute(
        span, GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE, params.get("temperature")
    )
    _set_span_attribute(
        span, GenAIAttributes.GEN_AI_REQUEST_TOP_P, params.get("top_p")
    )

    # Set tool/function definitions
    tools = kwargs.get("invocation_params", {}).get("tools", [])
    for i, tool in enumerate(tools):
        tool_function = tool.get("function", tool)
        _set_span_attribute(
            span,
            f"{SpanAttributes.LLM_REQUEST_FUNCTIONS}.{i}.name",
            tool_function.get("name"),
        )
        _set_span_attribute(
            span,
            f"{SpanAttributes.LLM_REQUEST_FUNCTIONS}.{i}.description",
            tool_function.get("description"),
        )
        _set_span_attribute(
            span,
            f"{SpanAttributes.LLM_REQUEST_FUNCTIONS}.{i}.parameters",
            json.dumps(tool_function.get("parameters", tool.get("input_schema"))),
        )


def set_llm_request(
    span: Span,
    serialized: Dict[str, Any],
    prompts: List[str],
    kwargs: Any,
    span_holder: SpanHolder,
) -> None:
    """Set LLM request attributes on a span.

    Args:
        span: The span to set attributes on.
        serialized: Serialized model information.
        prompts: List of prompts.
        kwargs: Additional keyword arguments.
        span_holder: The span holder.
    """
    set_request_params(span, kwargs, span_holder)

    if should_send_prompts():
        for i, msg in enumerate(prompts):
            _set_span_attribute(
                span,
                f"{GenAIAttributes.GEN_AI_PROMPT}.{i}.role",
                "user",
            )
            _set_span_attribute(
                span,
                f"{GenAIAttributes.GEN_AI_PROMPT}.{i}.content",
                msg,
            )


def set_chat_request(
    span: Span,
    serialized: Dict[str, Any],
    messages: List[List[BaseMessage]],
    kwargs: Any,
    span_holder: SpanHolder,
) -> None:
    """Set chat request attributes on a span.

    Args:
        span: The span to set attributes on.
        serialized: Serialized model information.
        messages: List of message lists.
        kwargs: Additional keyword arguments.
        span_holder: The span holder.
    """
    set_request_params(span, serialized.get("kwargs", {}), span_holder)

    if not should_send_prompts():
        return

    # Set function definitions
    for i, function in enumerate(
        kwargs.get("invocation_params", {}).get("functions", [])
    ):
        prefix = f"{SpanAttributes.LLM_REQUEST_FUNCTIONS}.{i}"
        _set_span_attribute(span, f"{prefix}.name", function.get("name"))
        _set_span_attribute(span, f"{prefix}.description", function.get("description"))
        _set_span_attribute(
            span, f"{prefix}.parameters", json.dumps(function.get("parameters"))
        )

    # Set messages
    i = 0
    for message_list in messages:
        for msg in message_list:
            _set_span_attribute(
                span,
                f"{GenAIAttributes.GEN_AI_PROMPT}.{i}.role",
                _message_type_to_role(msg.type),
            )

            # Handle tool calls
            tool_calls = (
                msg.tool_calls
                if hasattr(msg, "tool_calls")
                else msg.additional_kwargs.get("tool_calls")
            )
            if tool_calls:
                _set_chat_tool_calls(
                    span, f"{GenAIAttributes.GEN_AI_PROMPT}.{i}", tool_calls
                )

            # Set content
            content = (
                msg.content
                if isinstance(msg.content, str)
                else json.dumps(msg.content, cls=CallbackFilteredJSONEncoder)
            )
            _set_span_attribute(
                span,
                f"{GenAIAttributes.GEN_AI_PROMPT}.{i}.content",
                content,
            )

            # Set tool call ID for tool messages
            if msg.type == "tool" and hasattr(msg, "tool_call_id"):
                _set_span_attribute(
                    span,
                    f"{GenAIAttributes.GEN_AI_PROMPT}.{i}.tool_call_id",
                    msg.tool_call_id,
                )

            i += 1


def set_chat_response(span: Span, response: LLMResult) -> None:
    """Set chat response attributes on a span.

    Args:
        span: The span to set attributes on.
        response: The LLM result.
    """
    if not should_send_prompts():
        return

    i = 0
    for generations in response.generations:
        for generation in generations:
            prefix = f"{GenAIAttributes.GEN_AI_COMPLETION}.{i}"
            _set_span_attribute(
                span,
                f"{prefix}.role",
                _message_type_to_role(generation.type),
            )

            # Get content from various sources
            content = None
            if hasattr(generation, "text") and generation.text:
                content = generation.text
            elif (
                hasattr(generation, "message")
                and generation.message
                and generation.message.content
            ):
                if isinstance(generation.message.content, str):
                    content = generation.message.content
                else:
                    content = json.dumps(
                        generation.message.content, cls=CallbackFilteredJSONEncoder
                    )

            if content:
                _set_span_attribute(span, f"{prefix}.content", content)

            # Set finish reason
            if generation.generation_info and generation.generation_info.get(
                "finish_reason"
            ):
                _set_span_attribute(
                    span,
                    f"{prefix}.finish_reason",
                    generation.generation_info.get("finish_reason"),
                )

            # Handle tool calls
            if hasattr(generation, "message") and generation.message:
                # Legacy function_call format
                if generation.message.additional_kwargs.get("function_call"):
                    func_call = generation.message.additional_kwargs["function_call"]
                    _set_span_attribute(
                        span, f"{prefix}.tool_calls.0.name", func_call.get("name")
                    )
                    _set_span_attribute(
                        span,
                        f"{prefix}.tool_calls.0.arguments",
                        func_call.get("arguments"),
                    )

                # New tool_calls format
                tool_calls = (
                    generation.message.tool_calls
                    if hasattr(generation.message, "tool_calls")
                    else generation.message.additional_kwargs.get("tool_calls")
                )
                if tool_calls and isinstance(tool_calls, list):
                    _set_span_attribute(span, f"{prefix}.role", "assistant")
                    _set_chat_tool_calls(span, prefix, tool_calls)

            i += 1


def set_chat_response_usage(
    span: Span,
    response: LLMResult,
    token_histogram: Optional[Histogram],
    record_token_usage: bool,
    model_name: str,
) -> None:
    """Set token usage attributes on a span.

    Args:
        span: The span to set attributes on.
        response: The LLM result.
        token_histogram: Optional histogram for token metrics.
        record_token_usage: Whether to record token metrics.
        model_name: The model name for metrics labels.
    """
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    cache_read_tokens = 0

    if not response.generations:
        return

    try:
        for generations in response.generations:
            for generation in generations:
                if (
                    hasattr(generation, "message")
                    and hasattr(generation.message, "usage_metadata")
                    and generation.message.usage_metadata is not None
                ):
                    usage = generation.message.usage_metadata
                    input_tokens += usage.get("input_tokens") or usage.get(
                        "prompt_tokens", 0
                    )
                    output_tokens += usage.get("output_tokens") or usage.get(
                        "completion_tokens", 0
                    )
                    total_tokens = input_tokens + output_tokens

                    if usage.get("input_token_details"):
                        cache_read_tokens += usage.get("input_token_details", {}).get(
                            "cache_read", 0
                        )
    except Exception:
        pass

    if input_tokens > 0 or output_tokens > 0 or total_tokens > 0:
        _set_span_attribute(
            span, GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS, input_tokens
        )
        _set_span_attribute(
            span, GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS, output_tokens
        )
        _set_span_attribute(span, SpanAttributes.LLM_USAGE_TOTAL_TOKENS, total_tokens)

        if cache_read_tokens > 0:
            _set_span_attribute(
                span,
                SpanAttributes.LLM_USAGE_CACHE_READ_INPUT_TOKENS,
                cache_read_tokens,
            )

        if record_token_usage and token_histogram is not None:
            vendor = span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM, "langchain")

            if input_tokens > 0:
                token_histogram.record(
                    input_tokens,
                    attributes={
                        GenAIAttributes.GEN_AI_SYSTEM: vendor,
                        GenAIAttributes.GEN_AI_TOKEN_TYPE: "input",
                        GenAIAttributes.GEN_AI_RESPONSE_MODEL: model_name,
                    },
                )

            if output_tokens > 0:
                token_histogram.record(
                    output_tokens,
                    attributes={
                        GenAIAttributes.GEN_AI_SYSTEM: vendor,
                        GenAIAttributes.GEN_AI_TOKEN_TYPE: "output",
                        GenAIAttributes.GEN_AI_RESPONSE_MODEL: model_name,
                    },
                )


def extract_model_name_from_response_metadata(response: LLMResult) -> Optional[str]:
    """Extract model name from response metadata.

    Args:
        response: The LLM result.

    Returns:
        The model name if found, None otherwise.
    """
    for generations in response.generations:
        for generation in generations:
            if (
                getattr(generation, "message", None)
                and getattr(generation.message, "response_metadata", None)
                and (
                    model_name := generation.message.response_metadata.get("model_name")
                )
            ):
                return model_name
    return None


def _set_chat_tool_calls(
    span: Span, prefix: str, tool_calls: List[Dict[str, Any]]
) -> None:
    """Set tool call attributes on a span.

    Args:
        span: The span to set attributes on.
        prefix: The attribute prefix.
        tool_calls: List of tool call dictionaries.
    """
    for idx, tool_call in enumerate(tool_calls):
        tool_call_prefix = f"{prefix}.tool_calls.{idx}"
        tool_call_dict = dict(tool_call)
        tool_id = tool_call_dict.get("id")
        tool_name = tool_call_dict.get("name") or tool_call_dict.get(
            "function", {}
        ).get("name")
        tool_args = tool_call_dict.get("args") or tool_call_dict.get(
            "function", {}
        ).get("arguments")

        _set_span_attribute(span, f"{tool_call_prefix}.id", tool_id)
        _set_span_attribute(span, f"{tool_call_prefix}.name", tool_name)
        _set_span_attribute(
            span,
            f"{tool_call_prefix}.arguments",
            json.dumps(tool_args, cls=CallbackFilteredJSONEncoder),
        )


# Legacy alias for backward compatibility
_SpanManager = SpanManager
