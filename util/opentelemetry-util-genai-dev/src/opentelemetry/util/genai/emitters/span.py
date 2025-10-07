# Span emitter (moved from generators/span_emitter.py)
from __future__ import annotations

import json  # noqa: F401 (kept for backward compatibility if external code relies on this module re-exporting json)
from dataclasses import asdict  # noqa: F401
from typing import Any, Optional

from opentelemetry import trace
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.trace import Span, SpanKind, Tracer
from opentelemetry.trace.status import Status, StatusCode

from ..attributes import (
    GEN_AI_AGENT_ID,
    GEN_AI_AGENT_NAME,
    GEN_AI_AGENT_TOOLS,
    GEN_AI_AGENT_TYPE,
    GEN_AI_EMBEDDINGS_DIMENSION_COUNT,
    GEN_AI_EMBEDDINGS_INPUT_TEXTS,
    GEN_AI_INPUT_MESSAGES,
    GEN_AI_OUTPUT_MESSAGES,
    GEN_AI_PROVIDER_NAME,
    GEN_AI_REQUEST_ENCODING_FORMATS,
    GEN_AI_TASK_ASSIGNED_AGENT,
    GEN_AI_TASK_NAME,
    GEN_AI_TASK_OBJECTIVE,
    GEN_AI_TASK_SOURCE,
    GEN_AI_TASK_STATUS,
    GEN_AI_TASK_TYPE,
    GEN_AI_WORKFLOW_DESCRIPTION,
    GEN_AI_WORKFLOW_NAME,
    GEN_AI_WORKFLOW_TYPE,
    SERVER_ADDRESS,
    SERVER_PORT,
)
from ..interfaces import EmitterMeta
from ..types import (
    AgentInvocation,
    ContentCapturingMode,
    EmbeddingInvocation,
    Error,
    LLMInvocation,
    Task,
    ToolCall,
    Workflow,
)
from ..types import (
    GenAI as GenAIType,
)
from .utils import (
    _apply_function_definitions,
    _apply_llm_finish_semconv,
    _extract_system_instructions,
    _serialize_messages,
    filter_semconv_gen_ai_attributes,
)

_SPAN_ALLOWED_SUPPLEMENTAL_KEYS: tuple[str, ...] = ("gen_ai.framework",)


def _sanitize_span_attribute_value(value: Any) -> Optional[Any]:
    """Cast arbitrary invocation attribute values to OTEL-compatible types."""

    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (str, int, float)):
        return value
    if isinstance(value, (list, tuple)):
        sanitized_items: list[Any] = []
        for item in value:
            sanitized = _sanitize_span_attribute_value(item)
            if sanitized is None:
                continue
            if isinstance(sanitized, list):
                sanitized_items.append(str(sanitized))
            else:
                sanitized_items.append(sanitized)
        return sanitized_items
    if isinstance(value, dict):
        try:
            return json.dumps(value, default=str)
        except Exception:  # pragma: no cover - defensive
            return str(value)
    return str(value)


def _apply_gen_ai_semconv_attributes(
    span: Span,
    attributes: Optional[dict[str, Any]],
) -> None:
    if not attributes:
        return
    for key, value in attributes.items():
        sanitized = _sanitize_span_attribute_value(value)
        if sanitized is None:
            continue
        try:
            span.set_attribute(key, sanitized)
        except Exception:  # pragma: no cover - defensive
            pass


class SpanEmitter(EmitterMeta):
    """Span-focused emitter supporting optional content capture.

    Original implementation migrated from generators/span_emitter.py. Additional telemetry
    (metrics, content events) are handled by separate emitters composed via CompositeEmitter.
    """

    role = "span"
    name = "semconv_span"

    def __init__(
        self, tracer: Optional[Tracer] = None, capture_content: bool = False
    ):
        self._tracer: Tracer = tracer or trace.get_tracer(__name__)
        self._capture_content = capture_content
        self._content_mode = ContentCapturingMode.NO_CONTENT

    def set_capture_content(
        self, value: bool
    ):  # pragma: no cover - trivial mutator
        self._capture_content = value

    def set_content_mode(
        self, mode: ContentCapturingMode
    ) -> None:  # pragma: no cover - trivial mutator
        self._content_mode = mode

    def handles(self, obj: object) -> bool:
        return True

    # ---- helpers ---------------------------------------------------------
    def _apply_start_attrs(self, invocation: GenAIType):
        span = getattr(invocation, "span", None)
        if span is None:
            return
        semconv_attrs = dict(invocation.semantic_convention_attributes())
        if isinstance(invocation, ToolCall):
            enum_val = getattr(
                GenAI.GenAiOperationNameValues, "EXECUTE_TOOL", None
            )
            semconv_attrs[GenAI.GEN_AI_OPERATION_NAME] = (
                enum_val.value if enum_val else "execute_tool"
            )
            semconv_attrs[GenAI.GEN_AI_REQUEST_MODEL] = invocation.name
        elif isinstance(invocation, EmbeddingInvocation):
            semconv_attrs.setdefault(
                GenAI.GEN_AI_REQUEST_MODEL, invocation.request_model
            )
        elif isinstance(invocation, LLMInvocation):
            semconv_attrs.setdefault(
                GenAI.GEN_AI_REQUEST_MODEL, invocation.request_model
            )
        _apply_gen_ai_semconv_attributes(span, semconv_attrs)
        _apply_gen_ai_semconv_attributes(
            span, getattr(invocation, "attributes", None)
        )
        provider = getattr(invocation, "provider", None)
        if provider:
            span.set_attribute(GEN_AI_PROVIDER_NAME, provider)
        # framework (named field)
        if isinstance(invocation, LLMInvocation) and invocation.framework:
            span.set_attribute("gen_ai.framework", invocation.framework)
        # function definitions (semantic conv derived from structured list)
        if isinstance(invocation, LLMInvocation):
            _apply_function_definitions(span, invocation.request_functions)
        # Agent context (already covered by semconv metadata on base fields)

    def _apply_finish_attrs(
        self, invocation: LLMInvocation | EmbeddingInvocation
    ):
        span = getattr(invocation, "span", None)
        if span is None:
            return

        # Capture input messages and system instructions if enabled
        if (
            self._capture_content
            and isinstance(invocation, LLMInvocation)
            and invocation.input_messages
        ):
            # Extract and set system instructions separately
            system_instructions = _extract_system_instructions(
                invocation.input_messages
            )
            if system_instructions is not None:
                span.set_attribute(
                    "gen_ai.system.instructions", system_instructions
                )

            # Serialize input messages (excluding system messages)
            serialized_in = _serialize_messages(
                invocation.input_messages, exclude_system=True
            )
            if serialized_in is not None:
                span.set_attribute(GEN_AI_INPUT_MESSAGES, serialized_in)

        # Finish-time semconv attributes (response + usage tokens + functions)
        if isinstance(invocation, LLMInvocation):
            _apply_llm_finish_semconv(span, invocation)
        _apply_gen_ai_semconv_attributes(
            span, invocation.semantic_convention_attributes()
        )
        extra_attrs = filter_semconv_gen_ai_attributes(
            getattr(invocation, "attributes", None),
            extras=_SPAN_ALLOWED_SUPPLEMENTAL_KEYS,
        )
        if extra_attrs:
            _apply_gen_ai_semconv_attributes(span, extra_attrs)

        # Capture output messages if enabled
        if (
            self._capture_content
            and isinstance(invocation, LLMInvocation)
            and invocation.output_messages
        ):
            serialized = _serialize_messages(invocation.output_messages)
            if serialized is not None:
                span.set_attribute(GEN_AI_OUTPUT_MESSAGES, serialized)

    # ---- lifecycle -------------------------------------------------------
    def on_start(
        self, invocation: LLMInvocation | EmbeddingInvocation
    ) -> None:  # type: ignore[override]
        # Handle new agentic types
        if isinstance(invocation, Workflow):
            self._start_workflow(invocation)
        elif isinstance(invocation, AgentInvocation):
            self._start_agent(invocation)
        elif isinstance(invocation, Task):
            self._start_task(invocation)
        # Handle existing types
        elif isinstance(invocation, ToolCall):
            span_name = f"tool {invocation.name}"
            cm = self._tracer.start_as_current_span(
                span_name, kind=SpanKind.CLIENT, end_on_exit=False
            )
            span = cm.__enter__()
            invocation.span = span  # type: ignore[assignment]
            invocation.context_token = cm  # type: ignore[assignment]
            self._apply_start_attrs(invocation)
        elif isinstance(invocation, EmbeddingInvocation):
            self._start_embedding(invocation)
        else:
            # Use operation field for span name (defaults to "chat")
            operation = getattr(invocation, "operation", "chat")
            model_name = invocation.request_model
            span_name = f"{operation} {model_name}"
            cm = self._tracer.start_as_current_span(
                span_name, kind=SpanKind.CLIENT, end_on_exit=False
            )
            span = cm.__enter__()
            invocation.span = span  # type: ignore[assignment]
            invocation.context_token = cm  # type: ignore[assignment]
            self._apply_start_attrs(invocation)

    def on_end(self, invocation: LLMInvocation | EmbeddingInvocation) -> None:  # type: ignore[override]
        if isinstance(invocation, Workflow):
            self._finish_workflow(invocation)
        elif isinstance(invocation, AgentInvocation):
            self._finish_agent(invocation)
        elif isinstance(invocation, Task):
            self._finish_task(invocation)
        elif isinstance(invocation, EmbeddingInvocation):
            self._finish_embedding(invocation)
        else:
            span = getattr(invocation, "span", None)
            if span is None:
                return
            self._apply_finish_attrs(invocation)
            token = getattr(invocation, "context_token", None)
            if token is not None and hasattr(token, "__exit__"):
                try:  # pragma: no cover
                    token.__exit__(None, None, None)  # type: ignore[misc]
                except Exception:  # pragma: no cover
                    pass
            span.end()

    def on_error(
        self, error: Error, invocation: LLMInvocation | EmbeddingInvocation
    ) -> None:  # type: ignore[override]
        if isinstance(invocation, Workflow):
            self._error_workflow(error, invocation)
        elif isinstance(invocation, AgentInvocation):
            self._error_agent(error, invocation)
        elif isinstance(invocation, Task):
            self._error_task(error, invocation)
        elif isinstance(invocation, EmbeddingInvocation):
            self._error_embedding(error, invocation)
        else:
            span = getattr(invocation, "span", None)
            if span is None:
                return
            span.set_status(Status(StatusCode.ERROR, error.message))
            if span.is_recording():
                span.set_attribute(
                    ErrorAttributes.ERROR_TYPE, error.type.__qualname__
                )
            self._apply_finish_attrs(invocation)
            token = getattr(invocation, "context_token", None)
            if token is not None and hasattr(token, "__exit__"):
                try:  # pragma: no cover
                    token.__exit__(None, None, None)  # type: ignore[misc]
                except Exception:  # pragma: no cover
                    pass
            span.end()

    # ---- Workflow lifecycle ----------------------------------------------
    def _start_workflow(self, workflow: Workflow) -> None:
        """Start a workflow span."""
        span_name = f"gen_ai.workflow {workflow.name}"
        cm = self._tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT, end_on_exit=False
        )
        span = cm.__enter__()
        workflow.span = span
        workflow.context_token = cm

        # Set workflow attributes
        span.set_attribute(GEN_AI_WORKFLOW_NAME, workflow.name)
        if workflow.workflow_type:
            span.set_attribute(GEN_AI_WORKFLOW_TYPE, workflow.workflow_type)
        if workflow.description:
            span.set_attribute(
                GEN_AI_WORKFLOW_DESCRIPTION, workflow.description
            )
        if workflow.framework:
            span.set_attribute("gen_ai.framework", workflow.framework)
        if workflow.initial_input and self._capture_content:
            # Format as a message with text content
            import json

            input_msg = {
                "role": "user",
                "parts": [{"type": "text", "content": workflow.initial_input}],
            }
            span.set_attribute(
                "gen_ai.input.messages", json.dumps([input_msg])
            )
        _apply_gen_ai_semconv_attributes(
            span, workflow.semantic_convention_attributes()
        )

    def _finish_workflow(self, workflow: Workflow) -> None:
        """Finish a workflow span."""
        span = workflow.span
        if span is None:
            return
        # Set final output if capture_content enabled
        if workflow.final_output and self._capture_content:
            import json

            output_msg = {
                "role": "assistant",
                "parts": [{"type": "text", "content": workflow.final_output}],
                "finish_reason": "stop",
            }
            span.set_attribute(
                "gen_ai.output.messages", json.dumps([output_msg])
            )
        _apply_gen_ai_semconv_attributes(
            span, workflow.semantic_convention_attributes()
        )
        token = workflow.context_token
        if token is not None and hasattr(token, "__exit__"):
            try:
                token.__exit__(None, None, None)  # type: ignore[misc]
            except Exception:
                pass
        span.end()

    def _error_workflow(self, error: Error, workflow: Workflow) -> None:
        """Fail a workflow span with error status."""
        span = workflow.span
        if span is None:
            return
        span.set_status(Status(StatusCode.ERROR, error.message))
        if span.is_recording():
            span.set_attribute(
                ErrorAttributes.ERROR_TYPE, error.type.__qualname__
            )
        _apply_gen_ai_semconv_attributes(
            span, workflow.semantic_convention_attributes()
        )
        token = workflow.context_token
        if token is not None and hasattr(token, "__exit__"):
            try:
                token.__exit__(None, None, None)  # type: ignore[misc]
            except Exception:
                pass
        span.end()

    # ---- Agent lifecycle -------------------------------------------------
    def _start_agent(self, agent: AgentInvocation) -> None:
        """Start an agent span (create or invoke)."""
        # Span name per semantic conventions
        if agent.operation == "create_agent":
            span_name = f"create_agent {agent.name}"
        else:
            span_name = f"invoke_agent {agent.name}"

        cm = self._tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT, end_on_exit=False
        )
        span = cm.__enter__()
        agent.span = span
        agent.context_token = cm

        # Required attributes per semantic conventions
        # Set operation name based on agent operation (create or invoke)
        semconv_attrs = dict(agent.semantic_convention_attributes())
        semconv_attrs.setdefault(GEN_AI_AGENT_NAME, agent.name)
        semconv_attrs.setdefault(GEN_AI_AGENT_ID, str(agent.run_id))
        _apply_gen_ai_semconv_attributes(span, semconv_attrs)

        # Optional attributes
        if agent.agent_type:
            span.set_attribute(GEN_AI_AGENT_TYPE, agent.agent_type)
        if agent.framework:
            span.set_attribute("gen_ai.framework", agent.framework)
        if agent.tools:
            span.set_attribute(GEN_AI_AGENT_TOOLS, agent.tools)
        if agent.system_instructions and self._capture_content:
            import json

            system_parts = [
                {"type": "text", "content": agent.system_instructions}
            ]
            span.set_attribute(
                "gen_ai.system.instructions", json.dumps(system_parts)
            )
        if agent.input_context and self._capture_content:
            import json

            input_msg = {
                "role": "user",
                "parts": [{"type": "text", "content": agent.input_context}],
            }
            span.set_attribute(
                "gen_ai.input.messages", json.dumps([input_msg])
            )
        _apply_gen_ai_semconv_attributes(
            span, agent.semantic_convention_attributes()
        )

    def _finish_agent(self, agent: AgentInvocation) -> None:
        """Finish an agent span."""
        span = agent.span
        if span is None:
            return
        # Set output result if capture_content enabled
        if agent.output_result and self._capture_content:
            import json

            output_msg = {
                "role": "assistant",
                "parts": [{"type": "text", "content": agent.output_result}],
                "finish_reason": "stop",
            }
            span.set_attribute(
                "gen_ai.output.messages", json.dumps([output_msg])
            )
        _apply_gen_ai_semconv_attributes(
            span, agent.semantic_convention_attributes()
        )
        token = agent.context_token
        if token is not None and hasattr(token, "__exit__"):
            try:
                token.__exit__(None, None, None)  # type: ignore[misc]
            except Exception:
                pass
        span.end()

    def _error_agent(self, error: Error, agent: AgentInvocation) -> None:
        """Fail an agent span with error status."""
        span = agent.span
        if span is None:
            return
        span.set_status(Status(StatusCode.ERROR, error.message))
        if span.is_recording():
            span.set_attribute(
                ErrorAttributes.ERROR_TYPE, error.type.__qualname__
            )
        _apply_gen_ai_semconv_attributes(
            span, agent.semantic_convention_attributes()
        )
        token = agent.context_token
        if token is not None and hasattr(token, "__exit__"):
            try:
                token.__exit__(None, None, None)  # type: ignore[misc]
            except Exception:
                pass
        span.end()

    # ---- Task lifecycle --------------------------------------------------
    def _start_task(self, task: Task) -> None:
        """Start a task span."""
        span_name = f"gen_ai.task {task.name}"
        cm = self._tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT, end_on_exit=False
        )
        span = cm.__enter__()
        task.span = span
        task.context_token = cm

        # Set task attributes
        span.set_attribute(GEN_AI_TASK_NAME, task.name)
        if task.task_type:
            span.set_attribute(GEN_AI_TASK_TYPE, task.task_type)
        if task.objective:
            span.set_attribute(GEN_AI_TASK_OBJECTIVE, task.objective)
        if task.source:
            span.set_attribute(GEN_AI_TASK_SOURCE, task.source)
        if task.assigned_agent:
            span.set_attribute(GEN_AI_TASK_ASSIGNED_AGENT, task.assigned_agent)
        if task.status:
            span.set_attribute(GEN_AI_TASK_STATUS, task.status)
        if task.input_data and self._capture_content:
            import json

            input_msg = {
                "role": "user",
                "parts": [{"type": "text", "content": task.input_data}],
            }
            span.set_attribute(
                "gen_ai.input.messages", json.dumps([input_msg])
            )
        _apply_gen_ai_semconv_attributes(
            span, task.semantic_convention_attributes()
        )

    def _finish_task(self, task: Task) -> None:
        """Finish a task span."""
        span = task.span
        if span is None:
            return
        # Set output data if capture_content enabled
        if task.output_data and self._capture_content:
            import json

            output_msg = {
                "role": "assistant",
                "parts": [{"type": "text", "content": task.output_data}],
                "finish_reason": "stop",
            }
            span.set_attribute(
                "gen_ai.output.messages", json.dumps([output_msg])
            )
        # Update status if changed
        if task.status:
            span.set_attribute(GEN_AI_TASK_STATUS, task.status)
        _apply_gen_ai_semconv_attributes(
            span, task.semantic_convention_attributes()
        )
        token = task.context_token
        if token is not None and hasattr(token, "__exit__"):
            try:
                token.__exit__(None, None, None)  # type: ignore[misc]
            except Exception:
                pass
        span.end()

    def _error_task(self, error: Error, task: Task) -> None:
        """Fail a task span with error status."""
        span = task.span
        if span is None:
            return
        span.set_status(Status(StatusCode.ERROR, error.message))
        if span.is_recording():
            span.set_attribute(
                ErrorAttributes.ERROR_TYPE, error.type.__qualname__
            )
        # Update status to failed
        span.set_attribute(GEN_AI_TASK_STATUS, "failed")
        _apply_gen_ai_semconv_attributes(
            span, task.semantic_convention_attributes()
        )
        token = task.context_token
        if token is not None and hasattr(token, "__exit__"):
            try:
                token.__exit__(None, None, None)  # type: ignore[misc]
            except Exception:
                pass
        span.end()

    # ---- Embedding lifecycle ---------------------------------------------
    def _start_embedding(self, embedding: EmbeddingInvocation) -> None:
        """Start an embedding span."""
        span_name = f"{embedding.operation_name} {embedding.request_model}"
        cm = self._tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT, end_on_exit=False
        )
        span = cm.__enter__()
        embedding.span = span  # type: ignore[assignment]
        embedding.context_token = cm  # type: ignore[assignment]
        self._apply_start_attrs(embedding)

        # Set embedding-specific start attributes
        if embedding.server_address:
            span.set_attribute(SERVER_ADDRESS, embedding.server_address)
        if embedding.server_port:
            span.set_attribute(SERVER_PORT, embedding.server_port)
        if embedding.encoding_formats:
            span.set_attribute(
                GEN_AI_REQUEST_ENCODING_FORMATS, embedding.encoding_formats
            )
        if self._capture_content and embedding.input_texts:
            # Capture input texts as array attribute
            span.set_attribute(
                GEN_AI_EMBEDDINGS_INPUT_TEXTS, embedding.input_texts
            )

    def _finish_embedding(self, embedding: EmbeddingInvocation) -> None:
        """Finish an embedding span."""
        span = embedding.span
        if span is None:
            return
        # Apply finish-time semantic conventions
        if embedding.dimension_count:
            span.set_attribute(
                GEN_AI_EMBEDDINGS_DIMENSION_COUNT, embedding.dimension_count
            )
        if embedding.input_tokens is not None:
            span.set_attribute(
                GenAI.GEN_AI_USAGE_INPUT_TOKENS, embedding.input_tokens
            )
        token = embedding.context_token
        if token is not None and hasattr(token, "__exit__"):
            try:
                token.__exit__(None, None, None)  # type: ignore[misc]
            except Exception:
                pass
        span.end()

    def _error_embedding(
        self, error: Error, embedding: EmbeddingInvocation
    ) -> None:
        """Fail an embedding span with error status."""
        span = embedding.span
        if span is None:
            return
        span.set_status(Status(StatusCode.ERROR, error.message))
        if span.is_recording():
            span.set_attribute(
                ErrorAttributes.ERROR_TYPE, error.type.__qualname__
            )
        # Set error type from invocation if available
        if embedding.error_type:
            span.set_attribute(
                ErrorAttributes.ERROR_TYPE, embedding.error_type
            )
        token = embedding.context_token
        if token is not None and hasattr(token, "__exit__"):
            try:
                token.__exit__(None, None, None)  # type: ignore[misc]
            except Exception:
                pass
