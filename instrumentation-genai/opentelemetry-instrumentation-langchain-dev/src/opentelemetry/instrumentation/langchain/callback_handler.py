import json
import os
from typing import Any, Dict, List, Optional, Type, Union
from uuid import UUID

from langchain_core.callbacks import (
    BaseCallbackHandler,
    CallbackManager,
    AsyncCallbackManager,
)
from langchain_core.messages import (
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
from langchain_core.outputs import (
    ChatGeneration,
    ChatGenerationChunk,
    Generation,
    GenerationChunk,
    LLMResult,
)
from opentelemetry import context as context_api
from opentelemetry.instrumentation.langchain.event_emitter import emit_event
from opentelemetry.instrumentation.langchain.event_models import (
    ChoiceEvent,
    MessageEvent,
    ToolCall,
)
from opentelemetry.instrumentation.langchain.span_utils import (
    SpanHolder,
    _set_span_attribute,
    set_llm_request,
    set_request_params,
)
from opentelemetry.instrumentation.langchain.vendor_detection import (
    detect_vendor_from_class,
)
from opentelemetry.instrumentation.langchain.utils import (
    CallbackFilteredJSONEncoder,
    dont_throw,
    should_emit_events,
    should_send_prompts,
)
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
from opentelemetry.metrics import Histogram
from .semconv_ai import (
    SUPPRESS_LANGUAGE_MODEL_INSTRUMENTATION_KEY,
    LLMRequestTypeValues,
    SpanAttributes,
    TraceloopSpanKindValues,
)
from opentelemetry.trace import SpanKind, Tracer, set_span_in_context
from opentelemetry.trace.span import Span
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE

from opentelemetry.util.genai.handler import (
    get_telemetry_handler as _get_util_handler,
)

# util-genai deps
from opentelemetry.util.genai.types import (
    InputMessage as UtilInputMessage,
    LLMInvocation as UtilLLMInvocation,
    OutputMessage as UtilOutputMessage,
    Text as UtilText,
)
from threading import Lock
from .utils import get_property_value


_TRACELOOP_COMPAT_ENABLED = "traceloop_compat" in (
    os.getenv("OTEL_INSTRUMENTATION_GENAI_EMITTERS", "").lower()
)


def _extract_class_name_from_serialized(serialized: Optional[dict[str, Any]]) -> str:
    """
    Extract class name from serialized model information.

    Args:
        serialized: Serialized model information from LangChain callback

    Returns:
        Class name string, or empty string if not found
    """
    class_id = (serialized or {}).get("id", [])
    if isinstance(class_id, list) and len(class_id) > 0:
        return class_id[-1]
    elif class_id:
        return str(class_id)
    else:
        return ""


def _sanitize_metadata_value(value: Any) -> Any:
    """Convert metadata values to OpenTelemetry-compatible types."""
    if value is None:
        return None
    if isinstance(value, (bool, str, bytes, int, float)):
        return value
    if isinstance(value, (list, tuple)):
        return [str(_sanitize_metadata_value(v)) for v in value]
    # Convert other types to strings
    return str(value)


def valid_role(role: str) -> bool:
    return role in ["user", "assistant", "system", "tool"]


def get_message_role(message: Type[BaseMessage]) -> str:
    if isinstance(message, (SystemMessage, SystemMessageChunk)):
        return "system"
    elif isinstance(message, (HumanMessage, HumanMessageChunk)):
        return "user"
    elif isinstance(message, (AIMessage, AIMessageChunk)):
        return "assistant"
    elif isinstance(message, (ToolMessage, ToolMessageChunk)):
        return "tool"
    else:
        return "unknown"


def _extract_tool_call_data(
    tool_calls: Optional[List[dict[str, Any]]],
) -> Union[List[ToolCall], None]:
    if tool_calls is None:
        return tool_calls

    response = []

    for tool_call in tool_calls:
        tool_call_function = {"name": tool_call.get("name", "")}

        if tool_call.get("arguments"):
            tool_call_function["arguments"] = tool_call["arguments"]
        elif tool_call.get("args"):
            tool_call_function["arguments"] = tool_call["args"]
        response.append(
            ToolCall(
                id=tool_call.get("id", ""),
                function=tool_call_function,
                type="function",
            )
        )

    return response


class TraceloopCallbackHandler(BaseCallbackHandler):
    def __init__(
        self, tracer: Tracer, duration_histogram: Histogram, token_histogram: Histogram
    ) -> None:
        super().__init__()
        self.tracer = tracer
        self.duration_histogram = duration_histogram
        self.token_histogram = token_histogram
        self.spans: dict[UUID, SpanHolder] = {}
        self.run_inline = True
        self._callback_manager: CallbackManager | AsyncCallbackManager = None
        self._telemetry_handler = _get_util_handler()
        self._invocations: dict[UUID, UtilLLMInvocation] = {}
        self._lock = Lock()

    @staticmethod
    def _get_name_from_callback(
        serialized: dict[str, Any],
        _tags: Optional[list[str]] = None,
        _metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        """Get the name to be used for the span. Based on heuristic. Can be extended."""
        if serialized and "kwargs" in serialized and serialized["kwargs"].get("name"):
            return serialized["kwargs"]["name"]
        if kwargs.get("name"):
            return kwargs["name"]
        if serialized.get("name"):
            return serialized["name"]
        if "id" in serialized:
            return serialized["id"][-1]

        return "unknown"

    def _get_span(self, run_id: UUID) -> Span:
        return self.spans[run_id].span

    def _end_span(self, span: Span, run_id: UUID) -> None:
        for child_id in self.spans[run_id].children:
            if child_id in self.spans:
                child_span = self.spans[child_id].span
                try:
                    child_span.end()
                except Exception:
                    pass
        span.end()
        token = self.spans[run_id].token
        if token:
            self._safe_detach_context(token)

        del self.spans[run_id]

    def _safe_attach_context(self, span: Span):
        """
        Safely attach span to context, handling potential failures in async scenarios.

        Returns the context token for later detachment, or None if attachment fails.
        """
        try:
            return context_api.attach(set_span_in_context(span))
        except Exception:
            # Context attachment can fail in some edge cases, particularly in
            # complex async scenarios or when context is corrupted.
            # Return None to indicate no token needs to be detached later.
            return None

    def _safe_detach_context(self, token):
        """
        Safely detach context token without causing application crashes.

        This method implements a fail-safe approach to context detachment that handles
        all known edge cases in async/concurrent scenarios where context tokens may
        become invalid or be detached in different execution contexts.

        We use the runtime context directly to avoid logging errors from context_api.detach()
        """
        if not token:
            return

        try:
            # Use the runtime context directly to avoid error logging from context_api.detach()
            from opentelemetry.context import _RUNTIME_CONTEXT

            _RUNTIME_CONTEXT.detach(token)
        except Exception:
            # Context detach can fail in async scenarios when tokens are created in different contexts
            # This includes ValueError, RuntimeError, and other context-related exceptions
            # This is expected behavior and doesn't affect the correct span hierarchy
            #
            # Common scenarios where this happens:
            # 1. Token created in one async task/thread, detached in another
            # 2. Context was already detached by another process
            # 3. Token became invalid due to context switching
            # 4. Race conditions in highly concurrent scenarios
            #
            # This is safe to ignore as the span itself was properly ended
            # and the tracing data is correctly captured.
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
        metadata: Optional[dict[str, Any]] = None,
    ) -> Span:
        if metadata is not None:
            current_association_properties = (
                context_api.get_value("association_properties") or {}
            )
            # Sanitize metadata values to ensure they're compatible with OpenTelemetry
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
                # If setting association properties fails, continue without them
                # This doesn't affect the core span functionality
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

        _set_span_attribute(span, SpanAttributes.TRACELOOP_WORKFLOW_NAME, workflow_name)
        _set_span_attribute(span, SpanAttributes.TRACELOOP_ENTITY_PATH, entity_path)

        # Set metadata as span attributes if available
        if metadata is not None:
            for key, value in sanitized_metadata.items():
                _set_span_attribute(
                    span,
                    f"{SpanAttributes.TRACELOOP_ASSOCIATION_PROPERTIES}.{key}",
                    value,
                )

        self.spans[run_id] = SpanHolder(
            span, token, None, [], workflow_name, entity_name, entity_path
        )

        if parent_run_id is not None and parent_run_id in self.spans:
            self.spans[parent_run_id].children.append(run_id)

        return span

    def _create_task_span(
        self,
        run_id: UUID,
        parent_run_id: Optional[UUID],
        name: str,
        kind: TraceloopSpanKindValues,
        workflow_name: str,
        entity_name: str = "",
        entity_path: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> Span:
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

        _set_span_attribute(span, SpanAttributes.TRACELOOP_SPAN_KIND, kind.value)
        _set_span_attribute(span, SpanAttributes.TRACELOOP_ENTITY_NAME, entity_name)

        return span

    def _create_llm_span(
        self,
        run_id: UUID,
        parent_run_id: Optional[UUID],
        name: str,
        request_type: LLMRequestTypeValues,
        metadata: Optional[dict[str, Any]] = None,
        serialized: Optional[dict[str, Any]] = None,
    ) -> Span:
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

        _set_span_attribute(span, SpanAttributes.LLM_SYSTEM, vendor)
        _set_span_attribute(span, SpanAttributes.LLM_REQUEST_TYPE, request_type.value)

        # we already have an LLM span by this point,
        # so skip any downstream instrumentation from here
        try:
            token = context_api.attach(
                context_api.set_value(SUPPRESS_LANGUAGE_MODEL_INSTRUMENTATION_KEY, True)
            )
        except Exception:
            # If context setting fails, continue without suppression token
            token = None

        self.spans[run_id] = SpanHolder(
            span, token, None, [], workflow_name, None, entity_path
        )

        return span

    @dont_throw
    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Run when chain starts running."""
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return

        workflow_name = ""
        entity_path = ""

        name = self._get_name_from_callback(serialized, **kwargs)
        kind = (
            TraceloopSpanKindValues.WORKFLOW
            if parent_run_id is None or parent_run_id not in self.spans
            else TraceloopSpanKindValues.TASK
        )

        if kind == TraceloopSpanKindValues.WORKFLOW:
            workflow_name = name
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
                SpanAttributes.TRACELOOP_ENTITY_INPUT,
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

        # The start_time is now automatically set when creating the SpanHolder

    @dont_throw
    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Run when chain ends running."""
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return

        span_holder = self.spans[run_id]
        span = span_holder.span
        if not should_emit_events() and should_send_prompts():
            span.set_attribute(
                SpanAttributes.TRACELOOP_ENTITY_OUTPUT,
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
                # If context reset fails, it's not critical for functionality
                pass

    # util-genai dev
    def _extract_request_functions(self, invocation_params: dict) -> list[dict[str, Any]]:
        tools = invocation_params.get("tools") if invocation_params else None
        if not tools:
            return []
        result: list[dict[str, Any]] = []
        for tool in tools:
            fn = tool.get("function") if isinstance(tool, dict) else None
            if not fn:
                continue
            entry = {k: v for k, v in fn.items() if k in ("name", "description", "parameters")}
            if entry:
                result.append(entry)
        return result

    def _build_input_messages(
        self, messages: List[List[BaseMessage]]
    ) -> list[UtilInputMessage]:
        result: list[UtilInputMessage] = []
        for sub in messages:
            for m in sub:
                role = (
                    getattr(m, "type", None)
                    or m.__class__.__name__.replace("Message", "").lower()
                )
                content = get_property_value(m, "content")
                result.append(
                    UtilInputMessage(
                        role=role, parts=[UtilText(content=str(content))]
                    )
                )
        return result

    @dont_throw
    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        tags: Optional[list[str]] = None,
        parent_run_id: Optional[UUID] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        """Run when Chat Model starts running."""
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return

        invocation_params = kwargs.get("invocation_params") or {}
        request_model = (
            invocation_params.get("model_name")
            or serialized.get("name")
            or "unknown-model"
        )
        provider_name = (metadata or {}).get("ls_provider")
        # attributes dict now reserved for non-semconv extensions only
        attrs: dict[str, Any] = {}
        if _TRACELOOP_COMPAT_ENABLED:
            callback_name = self._get_name_from_callback(serialized, kwargs=kwargs)
            attrs["traceloop.callback_name"] = callback_name
            attrs.setdefault("traceloop.span.kind", "llm")
        # copy selected params (non-semconv)
        for key in (
            "top_p",
            "frequency_penalty",
            "presence_penalty",
            "stop",
            "seed",
        ):
            if key in invocation_params and invocation_params[key] is not None:
                attrs[f"request_{key}"] = invocation_params[key]
        if metadata:
            if metadata.get("ls_max_tokens") is not None:
                attrs["request_max_tokens"] = metadata.get("ls_max_tokens")
            if metadata.get("ls_temperature") is not None:
                attrs["request_temperature"] = metadata.get("ls_temperature")
        request_functions = self._extract_request_functions(invocation_params)
        input_messages = self._build_input_messages(messages)
        inv = UtilLLMInvocation(
            request_model=request_model,
            provider=provider_name,
            framework="langchain",
            input_messages=input_messages,
            request_functions=request_functions,
            attributes=attrs,
        )
        # no need for messages/chat_generations fields; generator uses input_messages and output_messages
        self._telemetry_handler.start_llm(inv)
        with self._lock:
            self._invocations[run_id] = inv
        # name = self._get_name_from_callback(serialized, kwargs=kwargs)
        # span = self._create_llm_span(
        #     run_id,
        #     parent_run_id,
        #     name,
        #     LLMRequestTypeValues.CHAT,
        #     metadata=metadata,
        #     serialized=serialized,
        # )
        # set_request_params(span, kwargs, self.spans[run_id])
        # if should_emit_events():
        #     self._emit_chat_input_events(messages)
        # else:
        #     set_chat_request(span, serialized, messages, kwargs, self.spans[run_id])

    @dont_throw
    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: UUID,
        tags: Optional[list[str]] = None,
        parent_run_id: Optional[UUID] = None,
        metadata: Optional[dict[str, Any]] = None,
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
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Union[UUID, None] = None,
        **kwargs: Any,
    ):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return
        with self._lock:
            inv = self._invocations.pop(run_id, None)
        if not inv:
            return
        generations = getattr(response, "generations", [])
        content_text = None
        finish_reason = "stop"
        if generations:
            first_list = generations[0]
            if first_list:
                first = first_list[0]
                content_text = get_property_value(first.message, "content")
                if getattr(first, "generation_info", None):
                    finish_reason = first.generation_info.get(
                        "finish_reason", finish_reason
                    )
        if content_text is not None:
            inv.output_messages = [
                UtilOutputMessage(
                    role="assistant",
                    parts=[UtilText(content=str(content_text))],
                    finish_reason=finish_reason,
                )
            ]
        llm_output = getattr(response, "llm_output", None) or {}
        response_model = llm_output.get("model_name") or llm_output.get(
            "model"
        )
        response_id = llm_output.get("id")
        usage = llm_output.get("usage") or llm_output.get("token_usage") or {}
        inv.response_model_name = response_model
        inv.response_id = response_id
        if usage:
            inv.input_tokens = usage.get("prompt_tokens")
            inv.output_tokens = usage.get("completion_tokens")
        # Stop LLM (emitters finish here, so invocation fields must be set first)
        self._telemetry_handler.stop_llm(inv)
        ### below is just a temporary hack, evaluations should be happening in the util-genai implicitly
        try:
            self._telemetry_handler.evaluate_llm(inv)
        except Exception:  # pragma: no cover
            pass

    @dont_throw
    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        inputs: Optional[dict[str, Any]] = None,
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
            TraceloopSpanKindValues.TOOL,
            workflow_name,
            name,
            entity_path,
        )
        if not should_emit_events() and should_send_prompts():
            span.set_attribute(
                SpanAttributes.TRACELOOP_ENTITY_INPUT,
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

        span = self._get_span(run_id)
        if not should_emit_events() and should_send_prompts():
            span.set_attribute(
                SpanAttributes.TRACELOOP_ENTITY_OUTPUT,
                json.dumps(
                    {"output": output, "kwargs": kwargs},
                    cls=CallbackFilteredJSONEncoder,
                ),
            )
        self._end_span(span, run_id)

    def get_parent_span(self, parent_run_id: Optional[str] = None):
        if parent_run_id is None:
            return None
        return self.spans[parent_run_id]

    def get_workflow_name(self, parent_run_id: str):
        parent_span = self.get_parent_span(parent_run_id)

        if parent_span is None:
            return ""

        return parent_span.workflow_name

    def get_entity_path(self, parent_run_id: str):
        parent_span = self.get_parent_span(parent_run_id)

        if parent_span is None:
            return ""
        elif (
            parent_span.entity_path == ""
            and parent_span.entity_name == parent_span.workflow_name
        ):
            return ""
        elif parent_span.entity_path == "":
            return f"{parent_span.entity_name}"
        else:
            return f"{parent_span.entity_path}.{parent_span.entity_name}"

    def _handle_error(
        self,
        error: BaseException,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Common error handling logic for all components."""
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return

        span = self._get_span(run_id)
        span.set_status(Status(StatusCode.ERROR))
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
        span = self._get_span(run_id)
        span.set_attribute(ERROR_TYPE, type(error).__name__)
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

    def _emit_chat_input_events(self, messages):
        for message_list in messages:
            for message in message_list:
                if hasattr(message, "tool_calls") and message.tool_calls:
                    tool_calls = _extract_tool_call_data(message.tool_calls)
                else:
                    tool_calls = None
                emit_event(
                    MessageEvent(
                        content=message.content,
                        role=get_message_role(message),
                        tool_calls=tool_calls,
                    )
                )

    def _emit_llm_end_events(self, response):
        for generation_list in response.generations:
            for i, generation in enumerate(generation_list):
                self._emit_generation_choice_event(index=i, generation=generation)

    def _emit_generation_choice_event(
        self,
        index: int,
        generation: Union[
            ChatGeneration, ChatGenerationChunk, Generation, GenerationChunk
        ],
    ):
        if isinstance(generation, (ChatGeneration, ChatGenerationChunk)):
            # Get finish reason
            if hasattr(generation, "generation_info") and generation.generation_info:
                finish_reason = generation.generation_info.get(
                    "finish_reason", "unknown"
                )
            else:
                finish_reason = "unknown"

            # Get tool calls
            if (
                hasattr(generation.message, "tool_calls")
                and generation.message.tool_calls
            ):
                tool_calls = _extract_tool_call_data(generation.message.tool_calls)
            elif hasattr(
                generation.message, "additional_kwargs"
            ) and generation.message.additional_kwargs.get("function_call"):
                tool_calls = _extract_tool_call_data(
                    [generation.message.additional_kwargs.get("function_call")]
                )
            else:
                tool_calls = None

            # Emit the event
            if hasattr(generation, "text") and generation.text != "":
                emit_event(
                    ChoiceEvent(
                        index=index,
                        message={"content": generation.text, "role": "assistant"},
                        finish_reason=finish_reason,
                        tool_calls=tool_calls,
                    )
                )
            else:
                emit_event(
                    ChoiceEvent(
                        index=index,
                        message={
                            "content": generation.message.content,
                            "role": "assistant",
                        },
                        finish_reason=finish_reason,
                        tool_calls=tool_calls,
                    )
                )
        elif isinstance(generation, (Generation, GenerationChunk)):
            # Get finish reason
            if hasattr(generation, "generation_info") and generation.generation_info:
                finish_reason = generation.generation_info.get(
                    "finish_reason", "unknown"
                )
            else:
                finish_reason = "unknown"

            # Emit the event
            emit_event(
                ChoiceEvent(
                    index=index,
                    message={"content": generation.text, "role": "assistant"},
                    finish_reason=finish_reason,
                )
            )
