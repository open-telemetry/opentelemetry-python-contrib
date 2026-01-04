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

"""Callback handler for LangChain instrumentation."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Type, Union
from uuid import UUID

from langchain_core.callbacks import (  # type: ignore[import-untyped]
    AsyncCallbackManager,
    BaseCallbackHandler,
    CallbackManager,
)
from langchain_core.messages import (  # type: ignore[import-untyped]
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    HumanMessageChunk,
    SystemMessage,
    SystemMessageChunk,
    ToolMessage,
    ToolMessageChunk,
)
from langchain_core.outputs import (  # type: ignore[import-untyped]
    ChatGeneration,
    ChatGenerationChunk,
    Generation,
    GenerationChunk,
    LLMResult,
)
from opentelemetry import context as context_api
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
from opentelemetry.metrics import Histogram
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv.attributes import error_attributes as ErrorAttributes
from opentelemetry.trace import SpanKind, Tracer, set_span_in_context
from opentelemetry.trace.span import Span
from opentelemetry.trace.status import Status, StatusCode

from opentelemetry.instrumentation.langchain.config import Config
from opentelemetry.instrumentation.langchain.event_emitter import emit_event
from opentelemetry.instrumentation.langchain.event_models import (
    ChoiceEvent,
    MessageEvent,
    ToolCall,
)
from opentelemetry.instrumentation.langchain.semconv import (
    GenAISpanKindValues,
    LLMRequestTypeValues,
    SpanAttributes,
)
from opentelemetry.instrumentation.langchain.span_utils import (
    SpanHolder,
    _set_span_attribute,
    extract_model_name_from_response_metadata,
    set_chat_request,
    set_chat_response,
    set_chat_response_usage,
    set_llm_request,
    set_request_params,
)
from opentelemetry.instrumentation.langchain.utils import (
    CallbackFilteredJSONEncoder,
    dont_throw,
    should_emit_events,
    should_send_prompts,
)
from opentelemetry.instrumentation.langchain.vendor_detection import (
    detect_vendor_from_class,
)

# Key for suppressing language model instrumentation
SUPPRESS_LANGUAGE_MODEL_INSTRUMENTATION_KEY = "suppress_language_model_instrumentation"


def _extract_class_name_from_serialized(
    serialized: Optional[Dict[str, Any]]
) -> str:
    """Extract class name from serialized model information.

    Args:
        serialized: Serialized model information from LangChain callback.

    Returns:
        Class name string, or empty string if not found.
    """
    class_id = (serialized or {}).get("id", [])
    if isinstance(class_id, list) and len(class_id) > 0:
        return class_id[-1]
    elif class_id:
        return str(class_id)
    return ""


def _sanitize_metadata_value(value: Any) -> Any:
    """Convert metadata values to OpenTelemetry-compatible types."""
    if value is None:
        return None
    if isinstance(value, (bool, str, bytes, int, float)):
        return value
    if isinstance(value, (list, tuple)):
        return [str(_sanitize_metadata_value(v)) for v in value]
    return str(value)


def valid_role(role: str) -> bool:
    """Check if a role is valid."""
    return role in ["user", "assistant", "system", "tool"]


def get_message_role(message: Type[BaseMessage]) -> str:  # type: ignore[type-arg]
    """Get the role string from a message type."""
    if isinstance(message, (SystemMessage, SystemMessageChunk)):
        return "system"
    elif isinstance(message, (HumanMessage, HumanMessageChunk)):
        return "user"
    elif isinstance(message, (AIMessage, AIMessageChunk)):
        return "assistant"
    elif isinstance(message, (ToolMessage, ToolMessageChunk)):
        return "tool"
    return "unknown"


def _extract_tool_call_data(
    tool_calls: Optional[List[Dict[str, Any]]],
) -> Optional[List[ToolCall]]:
    """Extract tool call data from LangChain tool calls."""
    if tool_calls is None:
        return None

    response = []
    for tool_call in tool_calls:
        tool_call_function: Dict[str, Any] = {"function_name": tool_call.get("name", "")}

        if tool_call.get("arguments"):
            tool_call_function["arguments"] = tool_call["arguments"]
        elif tool_call.get("args"):
            tool_call_function["arguments"] = tool_call["args"]

        response.append(
            ToolCall(
                id=tool_call.get("id", ""),
                function=tool_call_function,  # type: ignore[typeddict-item]
                type="function",
            )
        )
    return response


class OpenTelemetryLangChainCallbackHandler(BaseCallbackHandler):  # type: ignore[misc]
    """OpenTelemetry callback handler for LangChain.

    This callback handler creates OpenTelemetry spans for LangChain operations
    including chains, LLMs, tools, and agents.
    """

    def __init__(
        self,
        tracer: Tracer,
        duration_histogram: Optional[Histogram] = None,
        token_histogram: Optional[Histogram] = None,
    ) -> None:
        """Initialize the callback handler.

        Args:
            tracer: OpenTelemetry tracer for span creation.
            duration_histogram: Optional histogram for operation duration.
            token_histogram: Optional histogram for token usage.
        """
        super().__init__()  # type: ignore[no-untyped-call]
        self.tracer = tracer
        self.duration_histogram = duration_histogram
        self.token_histogram = token_histogram
        self.spans: Dict[UUID, SpanHolder] = {}
        self.run_inline = True
        self._callback_manager: Optional[
            Union[CallbackManager, AsyncCallbackManager]
        ] = None

    @staticmethod
    def _get_name_from_callback(
        serialized: Dict[str, Any],
        _tags: Optional[List[str]] = None,
        _metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        """Get the name to be used for the span."""
        if (
            serialized
            and "kwargs" in serialized
            and serialized["kwargs"].get("name")
        ):
            return serialized["kwargs"]["name"]
        if kwargs.get("name"):
            return kwargs["name"]
        if serialized.get("name"):
            return serialized["name"]
        if "id" in serialized:
            return serialized["id"][-1]
        return "unknown"

    def _get_span(self, run_id: UUID) -> Span:
        """Get span for a run ID."""
        return self.spans[run_id].span

    def _end_span(self, span: Span, run_id: UUID) -> None:
        """End a span and clean up."""
        for child_id in self.spans[run_id].children:
            if child_id in self.spans:
                child_span = self.spans[child_id].span
                if child_span.end_time is None:
                    child_span.end()
        span.end()
        token = self.spans[run_id].token
        if token:
            self._safe_detach_context(token)
        del self.spans[run_id]

    def _safe_attach_context(self, span: Span) -> Any:
        """Safely attach span to context."""
        try:
            return context_api.attach(set_span_in_context(span))
        except Exception:
            return None

    def _safe_detach_context(self, token: Any) -> None:
        """Safely detach context token."""
        if not token:
            return
        try:
            from opentelemetry.context import _RUNTIME_CONTEXT

            _RUNTIME_CONTEXT.detach(token)
        except Exception:
            pass

    def _create_span(
        self,
        run_id: UUID,
        parent_run_id: Optional[UUID],
        span_name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        workflow_name: str = "",
        entity_name: str = "",
        entity_path: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Span:
        """Create a new span."""
        if metadata is not None:
            current_association_properties = (
                context_api.get_value("association_properties") or {}
            )
            sanitized_metadata = {
                k: _sanitize_metadata_value(v)
                for k, v in metadata.items()
                if v is not None
            }
            try:
                context_api.attach(
                    context_api.set_value(
                        "association_properties",
                        {**current_association_properties, **sanitized_metadata},
                    )
                )
            except Exception:
                pass

        if parent_run_id is not None and parent_run_id in self.spans:
            span = self.tracer.start_span(
                span_name,
                context=set_span_in_context(self.spans[parent_run_id].span),
                kind=kind,
            )
        else:
            span = self.tracer.start_span(span_name, kind=kind)

        token = self._safe_attach_context(span)

        _set_span_attribute(
            span, SpanAttributes.LANGCHAIN_WORKFLOW_NAME, workflow_name
        )
        _set_span_attribute(span, SpanAttributes.LANGCHAIN_ENTITY_PATH, entity_path)

        if metadata is not None:
            for key, value in sanitized_metadata.items():
                _set_span_attribute(
                    span,
                    f"{Config.metadata_key_prefix}.{key}",
                    value,
                )

        self.spans[run_id] = SpanHolder(
            span=span,
            token=token,
            context=set_span_in_context(span),
            children=[],
            workflow_name=workflow_name,
            entity_name=entity_name,
            entity_path=entity_path,
        )

        if parent_run_id is not None and parent_run_id in self.spans:
            self.spans[parent_run_id].children.append(run_id)

        return span

    def _create_task_span(
        self,
        run_id: UUID,
        parent_run_id: Optional[UUID],
        name: str,
        kind: GenAISpanKindValues,
        workflow_name: str,
        entity_name: str = "",
        entity_path: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Span:
        """Create a task span."""
        span_name = f"{name}.{kind.value}"
        span = self._create_span(
            run_id,
            parent_run_id,
            span_name,
            workflow_name=workflow_name,
            entity_name=entity_name,
            entity_path=entity_path,
            metadata=metadata,
        )

        _set_span_attribute(span, GenAIAttributes.GEN_AI_OPERATION_NAME, kind.value)
        _set_span_attribute(span, SpanAttributes.LANGCHAIN_ENTITY_NAME, entity_name)

        return span

    def _create_llm_span(
        self,
        run_id: UUID,
        parent_run_id: Optional[UUID],
        name: str,
        request_type: LLMRequestTypeValues,
        metadata: Optional[Dict[str, Any]] = None,
        serialized: Optional[Dict[str, Any]] = None,
    ) -> Span:
        """Create an LLM span."""
        workflow_name = self.get_workflow_name(parent_run_id)
        entity_path = self.get_entity_path(parent_run_id)

        span = self._create_span(
            run_id,
            parent_run_id,
            f"{name}.{request_type.value}",
            kind=SpanKind.CLIENT,
            workflow_name=workflow_name,
            entity_path=entity_path,
            metadata=metadata,
        )

        vendor = detect_vendor_from_class(
            _extract_class_name_from_serialized(serialized)
        )

        _set_span_attribute(span, GenAIAttributes.GEN_AI_SYSTEM, vendor)
        _set_span_attribute(
            span, GenAIAttributes.GEN_AI_OPERATION_NAME, request_type.value
        )

        try:
            token = context_api.attach(
                context_api.set_value(
                    SUPPRESS_LANGUAGE_MODEL_INSTRUMENTATION_KEY, True
                )
            )
        except Exception:
            token = None

        self.spans[run_id] = SpanHolder(
            span=span,
            token=token,
            context=set_span_in_context(span),
            children=[],
            workflow_name=workflow_name,
            entity_name="",
            entity_path=entity_path,
        )

        return span

    @dont_throw
    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Run when chain starts running."""
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return

        name = self._get_name_from_callback(serialized, **kwargs)
        kind = (
            GenAISpanKindValues.WORKFLOW
            if parent_run_id is None or parent_run_id not in self.spans
            else GenAISpanKindValues.TASK
        )

        if kind == GenAISpanKindValues.WORKFLOW:
            workflow_name = name
            entity_path = ""
        else:
            workflow_name = self.get_workflow_name(parent_run_id)
            entity_path = self.get_entity_path(parent_run_id)

        span = self._create_task_span(
            run_id,
            parent_run_id,
            name,
            kind,
            workflow_name,
            name,
            entity_path,
            metadata,
        )

        if not should_emit_events() and should_send_prompts():
            span.set_attribute(
                "gen_ai.langchain.entity.input",
                json.dumps(
                    {
                        "inputs": inputs,
                        "tags": tags,
                        "metadata": metadata,
                        "kwargs": kwargs,
                    },
                    cls=CallbackFilteredJSONEncoder,
                ),
            )

    @dont_throw
    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Run when chain ends running."""
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return

        if run_id not in self.spans:
            return

        span_holder = self.spans[run_id]
        span = span_holder.span

        if not should_emit_events() and should_send_prompts():
            span.set_attribute(
                "gen_ai.langchain.entity.output",
                json.dumps(
                    {"outputs": outputs, "kwargs": kwargs},
                    cls=CallbackFilteredJSONEncoder,
                ),
            )

        self._end_span(span, run_id)

        if parent_run_id is None:
            try:
                context_api.attach(
                    context_api.set_value(
                        SUPPRESS_LANGUAGE_MODEL_INSTRUMENTATION_KEY, False
                    )
                )
            except Exception:
                pass

    @dont_throw
    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[BaseMessage]],  # type: ignore[type-arg]
        *,
        run_id: UUID,
        tags: Optional[List[str]] = None,
        parent_run_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        """Run when Chat Model starts running."""
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return

        name = self._get_name_from_callback(serialized, kwargs=kwargs)
        span = self._create_llm_span(
            run_id,
            parent_run_id,
            name,
            LLMRequestTypeValues.CHAT,
            metadata=metadata,
            serialized=serialized,
        )

        set_request_params(span, kwargs, self.spans[run_id])

        if should_emit_events():
            self._emit_chat_input_events(messages)
        else:
            set_chat_request(span, serialized, messages, kwargs, self.spans[run_id])

    @dont_throw
    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: UUID,
        tags: Optional[List[str]] = None,
        parent_run_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        """Run when LLM starts running."""
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return

        name = self._get_name_from_callback(serialized, kwargs=kwargs)
        span = self._create_llm_span(
            run_id,
            parent_run_id,
            name,
            LLMRequestTypeValues.COMPLETION,
            serialized=serialized,
        )

        set_request_params(span, kwargs, self.spans[run_id])

        if should_emit_events():
            for prompt in prompts:
                emit_event(MessageEvent(content=prompt, role="user"))
        else:
            set_llm_request(span, serialized, prompts, kwargs, self.spans[run_id])

    @dont_throw
    def on_llm_end(
        self,
        response: LLMResult,  # type: ignore[type-arg]
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Run when LLM ends."""
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return

        if run_id not in self.spans:
            return

        span = self._get_span(run_id)
        span_holder = self.spans[run_id]

        model_name: Optional[str] = None
        if response.llm_output is not None:
            model_name = response.llm_output.get(
                "model_name"
            ) or response.llm_output.get("model_id")
            if model_name is not None:
                _set_span_attribute(
                    span,
                    GenAIAttributes.GEN_AI_RESPONSE_MODEL,
                    model_name or "unknown",
                )
                if span_holder.request_model is None:
                    _set_span_attribute(
                        span, GenAIAttributes.GEN_AI_REQUEST_MODEL, model_name
                    )

            response_id = response.llm_output.get("id")
            if response_id is not None and response_id != "":
                _set_span_attribute(
                    span, GenAIAttributes.GEN_AI_RESPONSE_ID, response_id
                )

        if model_name is None:
            model_name = extract_model_name_from_response_metadata(response)

        # Handle token usage from llm_output
        token_usage = (response.llm_output or {}).get("token_usage") or (
            response.llm_output or {}
        ).get("usage")

        if token_usage is not None:
            prompt_tokens = (
                token_usage.get("prompt_tokens")
                or token_usage.get("input_token_count")
                or token_usage.get("input_tokens")
            )
            completion_tokens = (
                token_usage.get("completion_tokens")
                or token_usage.get("generated_token_count")
                or token_usage.get("output_tokens")
            )
            total_tokens = token_usage.get("total_tokens") or (
                (prompt_tokens or 0) + (completion_tokens or 0)
            )

            _set_span_attribute(
                span, GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS, prompt_tokens
            )
            _set_span_attribute(
                span, GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS, completion_tokens
            )
            _set_span_attribute(
                span, SpanAttributes.LLM_USAGE_TOTAL_TOKENS, total_tokens
            )

            # Record token metrics
            if self.token_histogram is not None:
                vendor = span.attributes.get(
                    GenAIAttributes.GEN_AI_SYSTEM, "langchain"
                )
                if prompt_tokens and prompt_tokens > 0:
                    self.token_histogram.record(
                        prompt_tokens,
                        attributes={
                            GenAIAttributes.GEN_AI_SYSTEM: vendor,
                            GenAIAttributes.GEN_AI_TOKEN_TYPE: "input",
                            GenAIAttributes.GEN_AI_RESPONSE_MODEL: model_name
                            or "unknown",
                        },
                    )
                if completion_tokens and completion_tokens > 0:
                    self.token_histogram.record(
                        completion_tokens,
                        attributes={
                            GenAIAttributes.GEN_AI_SYSTEM: vendor,
                            GenAIAttributes.GEN_AI_TOKEN_TYPE: "output",
                            GenAIAttributes.GEN_AI_RESPONSE_MODEL: model_name
                            or "unknown",
                        },
                    )

        # Also extract from message usage_metadata
        set_chat_response_usage(
            span,
            response,
            self.token_histogram,
            token_usage is None,
            model_name or "unknown",
        )

        if should_emit_events():
            self._emit_llm_end_events(response)
            set_chat_response(span, response)
        else:
            set_chat_response(span, response)

        # Record duration
        if self.duration_histogram is not None:
            duration = time.time() - span_holder.start_time
            vendor = span.attributes.get(GenAIAttributes.GEN_AI_SYSTEM, "langchain")
            self.duration_histogram.record(
                duration,
                attributes={
                    GenAIAttributes.GEN_AI_SYSTEM: vendor,
                    GenAIAttributes.GEN_AI_RESPONSE_MODEL: model_name or "unknown",
                },
            )

        self._end_span(span, run_id)

    @dont_throw
    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        inputs: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Run when tool starts running."""
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return

        name = self._get_name_from_callback(serialized, kwargs=kwargs)
        workflow_name = self.get_workflow_name(parent_run_id)
        entity_path = self.get_entity_path(parent_run_id)

        span = self._create_task_span(
            run_id,
            parent_run_id,
            name,
            GenAISpanKindValues.TOOL,
            workflow_name,
            name,
            entity_path,
        )

        if not should_emit_events() and should_send_prompts():
            span.set_attribute(
                "gen_ai.langchain.entity.input",
                json.dumps(
                    {
                        "input_str": input_str,
                        "tags": tags,
                        "metadata": metadata,
                        "inputs": inputs,
                        "kwargs": kwargs,
                    },
                    cls=CallbackFilteredJSONEncoder,
                ),
            )

    @dont_throw
    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Run when tool ends running."""
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return

        if run_id not in self.spans:
            return

        span = self._get_span(run_id)
        if not should_emit_events() and should_send_prompts():
            span.set_attribute(
                "gen_ai.langchain.entity.output",
                json.dumps(
                    {"output": output, "kwargs": kwargs},
                    cls=CallbackFilteredJSONEncoder,
                ),
            )
        self._end_span(span, run_id)

    def get_parent_span(
        self, parent_run_id: Optional[UUID] = None
    ) -> Optional[SpanHolder]:
        """Get parent span holder."""
        if parent_run_id is None:
            return None
        return self.spans.get(parent_run_id)

    def get_workflow_name(self, parent_run_id: Optional[UUID]) -> str:
        """Get workflow name from parent."""
        parent_span = self.get_parent_span(parent_run_id)
        if parent_span is None:
            return ""
        return parent_span.workflow_name

    def get_entity_path(self, parent_run_id: Optional[UUID]) -> str:
        """Get entity path from parent."""
        parent_span = self.get_parent_span(parent_run_id)
        if parent_span is None:
            return ""
        elif (
            parent_span.entity_path == ""
            and parent_span.entity_name == parent_span.workflow_name
        ):
            return ""
        elif parent_span.entity_path == "":
            return parent_span.entity_name
        return f"{parent_span.entity_path}.{parent_span.entity_name}"

    def _handle_error(
        self,
        error: BaseException,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Common error handling logic."""
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return

        if run_id not in self.spans:
            return

        span = self._get_span(run_id)
        span.set_status(Status(StatusCode.ERROR), str(error))
        span.record_exception(error)
        self._end_span(span, run_id)

    @dont_throw
    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Run when LLM errors."""
        self._handle_error(error, run_id, parent_run_id, **kwargs)

    @dont_throw
    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Run when chain errors."""
        self._handle_error(error, run_id, parent_run_id, **kwargs)

    @dont_throw
    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Run when tool errors."""
        if run_id in self.spans:
            span = self._get_span(run_id)
            span.set_attribute(ErrorAttributes.ERROR_TYPE, type(error).__name__)
        self._handle_error(error, run_id, parent_run_id, **kwargs)

    @dont_throw
    def on_agent_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Run when agent errors."""
        self._handle_error(error, run_id, parent_run_id, **kwargs)

    @dont_throw
    def on_retriever_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Run when retriever errors."""
        self._handle_error(error, run_id, parent_run_id, **kwargs)

    def _emit_chat_input_events(
        self, messages: List[List[BaseMessage]]  # type: ignore[type-arg]
    ) -> None:
        """Emit input events for chat messages."""
        for message_list in messages:
            for message in message_list:
                tool_calls = None
                if hasattr(message, "tool_calls") and message.tool_calls:
                    tool_calls = _extract_tool_call_data(message.tool_calls)
                emit_event(
                    MessageEvent(
                        content=message.content,
                        role=get_message_role(message),
                        tool_calls=tool_calls,
                    )
                )

    def _emit_llm_end_events(self, response: LLMResult) -> None:  # type: ignore[type-arg]
        """Emit end events for LLM response."""
        for generation_list in response.generations:
            for i, generation in enumerate(generation_list):
                self._emit_generation_choice_event(index=i, generation=generation)

    def _emit_generation_choice_event(
        self,
        index: int,
        generation: Union[
            ChatGeneration, ChatGenerationChunk, Generation, GenerationChunk
        ],
    ) -> None:
        """Emit a choice event for a generation."""
        if isinstance(generation, (ChatGeneration, ChatGenerationChunk)):
            # Get finish reason
            finish_reason = "unknown"
            if hasattr(generation, "generation_info") and generation.generation_info:
                finish_reason = generation.generation_info.get(
                    "finish_reason", "unknown"
                )

            # Get tool calls
            tool_calls = None
            if (
                hasattr(generation.message, "tool_calls")
                and generation.message.tool_calls
            ):
                tool_calls = _extract_tool_call_data(generation.message.tool_calls)
            elif (
                hasattr(generation.message, "additional_kwargs")
                and generation.message.additional_kwargs.get("function_call")
            ):
                tool_calls = _extract_tool_call_data(
                    [generation.message.additional_kwargs.get("function_call")]
                )

            # Emit the event
            content = (
                generation.text
                if hasattr(generation, "text") and generation.text
                else generation.message.content
            )
            emit_event(
                ChoiceEvent(
                    index=index,
                    message={"content": content, "role": "assistant"},
                    finish_reason=finish_reason,
                    tool_calls=tool_calls,
                )
            )
        elif isinstance(generation, (Generation, GenerationChunk)):
            finish_reason = "unknown"
            if hasattr(generation, "generation_info") and generation.generation_info:
                finish_reason = generation.generation_info.get(
                    "finish_reason", "unknown"
                )

            emit_event(
                ChoiceEvent(
                    index=index,
                    message={"content": generation.text, "role": "assistant"},
                    finish_reason=finish_reason,
                )
            )
