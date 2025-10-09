import json
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
from opentelemetry.instrumentation.langchain.utils import (
    CallbackFilteredJSONEncoder,
    dont_throw,
    should_emit_events,
    should_send_prompts,
)
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
from opentelemetry.metrics import Histogram
from .semconv_ai import SUPPRESS_LANGUAGE_MODEL_INSTRUMENTATION_KEY
from opentelemetry.trace import Tracer

from opentelemetry.util.genai.handler import (
    get_telemetry_handler as _get_util_handler,
)

# util-genai deps
from opentelemetry.util.genai.types import (
    AgentInvocation as UtilAgent,
    Error as UtilError,
    GenAI,
    InputMessage as UtilInputMessage,
    LLMInvocation as UtilLLMInvocation,
    OutputMessage as UtilOutputMessage,
    Task as UtilTask,
    Text as UtilText,
    Workflow as UtilWorkflow,
)
from threading import Lock
from .utils import get_property_value


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
        self,
        tracer: Tracer,
        duration_histogram: Histogram,
        token_histogram: Histogram,
        *,
        telemetry_handler: Optional[Any] = None,
        telemetry_handler_kwargs: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__()
        self.tracer = tracer
        self.duration_histogram = duration_histogram
        self.token_histogram = token_histogram
        self.run_inline = True
        self._callback_manager: CallbackManager | AsyncCallbackManager = None
        handler_kwargs = telemetry_handler_kwargs or {}
        if telemetry_handler is not None:
            handler = telemetry_handler
        else:
            handler = _get_util_handler(**handler_kwargs)
            desired_tracer_provider = handler_kwargs.get("tracer_provider")
            desired_meter_provider = handler_kwargs.get("meter_provider")
            handler_tracer_provider = getattr(handler, "_tracer_provider_ref", None)
            handler_meter_provider = getattr(handler, "_meter_provider", None)
            if (
                desired_tracer_provider is not None
                and handler_tracer_provider is not desired_tracer_provider
            ) or (
                desired_meter_provider is not None
                and handler_meter_provider is not desired_meter_provider
            ):
                setattr(_get_util_handler, "_default_handler", None)
                handler = _get_util_handler(**handler_kwargs)
        self._telemetry_handler = handler
        self._entities: dict[UUID, GenAI] = {}
        self._llms: dict[UUID, UtilLLMInvocation] = {}
        self._lock = Lock()
        self._payload_truncation_bytes = 8 * 1024
        # Implicit parent entity stack (workflow/agent) for contexts where
        # LangGraph or manual calls do not emit chain callbacks providing parent_run_id.
        self._context_stack_key = "genai_active_entity_stack"

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

    def _register_entity(self, entity: GenAI) -> None:
        with self._lock:
            self._entities[entity.run_id] = entity
            if isinstance(entity, UtilLLMInvocation):
                self._llms[entity.run_id] = entity

    def _unregister_entity(self, run_id: UUID) -> Optional[GenAI]:
        with self._lock:
            entity = self._entities.pop(run_id, None)
            if isinstance(entity, UtilLLMInvocation):
                self._llms.pop(run_id, None)
            return entity

    def _get_entity(self, run_id: Optional[UUID]) -> Optional[GenAI]:
        if run_id is None:
            return None
        return self._entities.get(run_id)

    def _find_ancestor(
        self, run_id: Optional[UUID], target_type: Type[GenAI]
    ) -> Optional[GenAI]:
        current = self._get_entity(run_id)
        while current is not None:
            if isinstance(current, target_type):
                return current
            current = self._get_entity(current.parent_run_id)
        return None

    def _find_agent(self, run_id: Optional[UUID]) -> Optional[UtilAgent]:
        ancestor = self._find_ancestor(run_id, UtilAgent)
        return ancestor if isinstance(ancestor, UtilAgent) else None

    def _maybe_truncate(self, text: str) -> tuple[str, Optional[int]]:
        encoded = text.encode("utf-8")
        length = len(encoded)
        if length <= self._payload_truncation_bytes:
            return text, None
        return f"<truncated:{length} bytes>", length

    def _record_payload_length(
        self, entity: GenAI, field_name: str, original_length: Optional[int]
    ) -> None:
        if original_length is None:
            return
        lengths = entity.attributes.setdefault("orig_length", {})
        if isinstance(lengths, dict):
            lengths[field_name] = original_length
        else:  # pragma: no cover - defensive
            entity.attributes["orig_length"] = {field_name: original_length}

    def _store_serialized_payload(
        self, entity: GenAI, field_name: str, payload: Any
    ) -> None:
        serialized = self._serialize_payload(payload)
        if serialized is None:
            return
        truncated, original_length = self._maybe_truncate(serialized)
        setattr(entity, field_name, truncated)
        self._record_payload_length(entity, field_name, original_length)

    def _capture_prompt_data(
        self, entity: GenAI, key: str, payload: Any
    ) -> None:
        serialized = self._serialize_payload(payload)
        if serialized is None:
            return
        truncated, original_length = self._maybe_truncate(serialized)
        capture = entity.attributes.setdefault("prompt_capture", {})
        if isinstance(capture, dict):
            capture[key] = truncated
        else:  # pragma: no cover - defensive
            entity.attributes["prompt_capture"] = {key: truncated}
        self._record_payload_length(entity, f"prompt_capture.{key}", original_length)

    def _collect_attributes(
        self,
        *sources: Optional[dict[str, Any]],
        tags: Optional[list[str]] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        attributes: dict[str, Any] = {}
        legacy: dict[str, Any] = {}
        for source in sources:
            if not source:
                continue
            for key, value in list(source.items()):
                sanitized = _sanitize_metadata_value(value)
                if sanitized is None:
                    continue
                if key.startswith("ls_"):
                    legacy[key] = sanitized
                    source.pop(key, None)
                else:
                    attributes[key] = sanitized
        if tags:
            attributes["tags"] = [str(tag) for tag in tags]
        if extra:
            attributes.update(extra)
        if legacy:
            attributes["langchain_legacy"] = legacy
        return attributes

    def _coerce_optional_str(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        try:
            return str(value)
        except Exception:  # pragma: no cover - defensive
            return None

    def _start_entity(self, entity: GenAI) -> None:
        try:
            if isinstance(entity, UtilWorkflow):
                self._telemetry_handler.start_workflow(entity)
            elif isinstance(entity, UtilAgent):
                self._telemetry_handler.start_agent(entity)
            elif isinstance(entity, UtilTask):
                self._telemetry_handler.start_task(entity)
            elif isinstance(entity, UtilLLMInvocation):
                self._telemetry_handler.start_llm(entity)
            else:
                self._telemetry_handler.start(entity)
            if isinstance(entity, (UtilWorkflow, UtilAgent)):
                stack = context_api.get_value(self._context_stack_key) or []
                try:
                    new_stack = list(stack) + [entity.run_id]
                except Exception:  # pragma: no cover - defensive
                    new_stack = [entity.run_id]
                entity.context_token = context_api.attach(
                    context_api.set_value(self._context_stack_key, new_stack)
                )
        except Exception:  # pragma: no cover - defensive
            return
        self._register_entity(entity)

    def _stop_entity(self, entity: GenAI) -> None:
        try:
            if isinstance(entity, UtilWorkflow):
                self._telemetry_handler.stop_workflow(entity)
            elif isinstance(entity, UtilAgent):
                self._telemetry_handler.stop_agent(entity)
            elif isinstance(entity, UtilTask):
                self._telemetry_handler.stop_task(entity)
            elif isinstance(entity, UtilLLMInvocation):
                self._telemetry_handler.stop_llm(entity)
                try:  # pragma: no cover - defensive
                    self._telemetry_handler.evaluate_llm(entity)
                except Exception:
                    pass
            else:
                self._telemetry_handler.finish(entity)
        except Exception:  # pragma: no cover - defensive
            pass
        finally:
            if isinstance(entity, (UtilWorkflow, UtilAgent)):
                try:
                    stack = context_api.get_value(self._context_stack_key) or []
                    if stack and stack[-1] == entity.run_id:
                        new_stack = list(stack[:-1])
                        if entity.context_token is not None:
                            context_api.detach(entity.context_token)
                        context_api.attach(
                            context_api.set_value(self._context_stack_key, new_stack)
                        )
                    elif entity.context_token is not None:  # pragma: no cover
                        context_api.detach(entity.context_token)
                except Exception:  # pragma: no cover - defensive
                    pass
            self._unregister_entity(entity.run_id)

    def _fail_entity(self, entity: GenAI, error: BaseException) -> None:
        util_error = UtilError(message=str(error), type=type(error))
        entity.attributes.setdefault("error_type", type(error).__name__)
        if isinstance(entity, UtilAgent):
            entity.output_result = str(error)
        elif isinstance(entity, UtilTask):
            entity.output_data = str(error)
        elif isinstance(entity, UtilWorkflow):
            entity.final_output = str(error)
        elif isinstance(entity, UtilLLMInvocation):
            entity.output_messages = []
        try:
            if isinstance(entity, UtilWorkflow):
                self._telemetry_handler.fail_workflow(entity, util_error)
            elif isinstance(entity, UtilAgent):
                self._telemetry_handler.fail_agent(entity, util_error)
            elif isinstance(entity, UtilTask):
                self._telemetry_handler.fail_task(entity, util_error)
            elif isinstance(entity, UtilLLMInvocation):
                self._telemetry_handler.fail_llm(entity, util_error)
        except Exception:  # pragma: no cover - defensive
            pass
        finally:
            self._unregister_entity(entity.run_id)

    def _resolve_parent(self, explicit_parent_run_id: Optional[UUID]) -> Optional[GenAI]:
        """Resolve parent entity using explicit id or implicit context stack fallback."""
        if explicit_parent_run_id is not None:
            ent = self._get_entity(explicit_parent_run_id)
            if ent is not None:
                return ent
        try:
            stack = context_api.get_value(self._context_stack_key) or []
            if stack:
                return self._get_entity(stack[-1])
        except Exception:  # pragma: no cover - defensive
            return None
        return None

    def _sanitize_metadata_dict(
        self, metadata: Optional[dict[str, Any]]
    ) -> dict[str, Any]:
        if not metadata:
            return {}
        return {
            key: _sanitize_metadata_value(value)
            for key, value in metadata.items()
            if value is not None
        }

    def _normalize_agent_tools(
        self, metadata: Optional[dict[str, Any]]
    ) -> list[str]:
        if not metadata:
            return []
        raw_tools = metadata.get("ls_tools") or metadata.get("tools")
        tools: list[str] = []
        if isinstance(raw_tools, (list, tuple)):
            for item in raw_tools:
                if isinstance(item, str):
                    tools.append(item)
                elif isinstance(item, dict):
                    name = item.get("name") or item.get("tool") or item.get("id")
                    if name is not None:
                        tools.append(str(name))
                    else:
                        try:
                            tools.append(
                                json.dumps(item, cls=CallbackFilteredJSONEncoder)
                            )
                        except Exception:  # pragma: no cover - defensive
                            tools.append(str(item))
                else:
                    tools.append(str(item))
        elif isinstance(raw_tools, str):
            tools.append(raw_tools)
        return tools

    def _serialize_payload(self, payload: Any) -> Optional[str]:
        if payload is None:
            return None
        if isinstance(payload, (list, tuple, dict)) and not payload:
            return None
        try:
            return json.dumps(payload, cls=CallbackFilteredJSONEncoder)
        except Exception:  # pragma: no cover - defensive
            try:
                return str(payload)
            except Exception:  # pragma: no cover - defensive
                return None

    def _is_agent_run(
        self,
        serialized: Optional[dict[str, Any]],
        metadata: Optional[dict[str, Any]],
        tags: Optional[list[str]],
    ) -> bool:
        if metadata:
            for key in (
                "ls_span_kind",
                "ls_run_kind",
                "ls_entity_kind",
                "run_type",
                "ls_type",
            ):
                value = metadata.get(key)
                if isinstance(value, str) and "agent" in value.lower():
                    return True
            for key in ("ls_is_agent", "is_agent"):
                value = metadata.get(key)
                if isinstance(value, bool) and value:
                    return True
                if isinstance(value, str) and value.lower() in ("true", "1", "agent"):
                    return True
        if tags:
            for tag in tags:
                try:
                    tag_text = str(tag).lower()
                except Exception:  # pragma: no cover - defensive
                    continue
                if "agent" in tag_text:
                    return True
        serialized = serialized or {}
        name = serialized.get("name")
        if isinstance(name, str) and "agent" in name.lower():
            return True
        identifier = serialized.get("id")
        if isinstance(identifier, list):
            identifier_text = " ".join(str(part) for part in identifier).lower()
            if "agent" in identifier_text:
                return True
        elif isinstance(identifier, str) and "agent" in identifier.lower():
            return True
        return False

    def _build_agent_invocation(
        self,
        name: str,
        run_id: UUID,
        parent_run_id: Optional[UUID],
        inputs: dict[str, Any],
        metadata_attrs: dict[str, Any],
        tags: Optional[list[str]],
        extra_attrs: Optional[dict[str, Any]] = None,
    ) -> UtilAgent:
        extras: dict[str, Any] = extra_attrs.copy() if extra_attrs else {}

        raw_operation = None
        for key in ("ls_operation", "operation"):
            if key in metadata_attrs:
                raw_operation = metadata_attrs.pop(key)
                break
        op_text = str(raw_operation).lower() if isinstance(raw_operation, str) else ""
        if "create" in op_text:
            operation = "create_agent"
        else:
            operation = "invoke_agent"

        agent_type = None
        for key in ("ls_agent_type", "agent_type"):
            if key in metadata_attrs:
                agent_type = metadata_attrs.pop(key)
                break
        if agent_type is not None and not isinstance(agent_type, str):
            agent_type = str(agent_type)

        description = None
        for key in ("ls_description", "description"):
            if key in metadata_attrs:
                description = metadata_attrs.pop(key)
                break
        if description is not None and not isinstance(description, str):
            description = str(description)

        model = None
        for key in ("ls_model_name", "model_name"):
            if key in metadata_attrs:
                model = metadata_attrs.pop(key)
                break
        if model is not None and not isinstance(model, str):
            model = str(model)

        system_instructions = None
        for key in ("ls_system_prompt", "system_prompt", "system_instruction"):
            if key in metadata_attrs:
                system_instructions = metadata_attrs.pop(key)
                break
        if system_instructions is not None and not isinstance(system_instructions, str):
            system_instructions = str(system_instructions)

        framework = "langchain"
        for key in ("ls_framework", "framework"):
            if key in metadata_attrs:
                framework = metadata_attrs.pop(key) or framework
                break
        if not isinstance(framework, str):
            framework = str(framework)

        tools = self._normalize_agent_tools(metadata_attrs)
        # remove tool metadata entries now that we've normalized them
        metadata_attrs.pop("ls_tools", None)
        metadata_attrs.pop("tools", None)
        attributes = self._collect_attributes(
            metadata_attrs,
            tags=tags,
            extra=extras,
        )

        agent = UtilAgent(
            name=name,
            operation=operation,
            agent_type=agent_type,
            description=description,
            framework=framework,
            model=model,
            tools=tools,
            system_instructions=system_instructions,
            attributes=attributes,
            run_id=run_id,
            parent_run_id=parent_run_id,
        )
        self._store_serialized_payload(agent, "input_context", inputs)
        return agent

    def _build_workflow(
        self,
        *,
        name: str,
        run_id: UUID,
        metadata_attrs: dict[str, Any],
        extra_attrs: dict[str, Any],
    ) -> UtilWorkflow:
        workflow_type = metadata_attrs.pop("ls_workflow_type", None)
        if workflow_type is None:
            workflow_type = metadata_attrs.pop("workflow_type", None)
        description = metadata_attrs.pop("ls_description", None)
        if description is None:
            description = metadata_attrs.pop("description", None)
        framework = metadata_attrs.pop("ls_framework", None)
        if framework is None:
            framework = metadata_attrs.pop("framework", "langchain")

        attributes = self._collect_attributes(
            metadata_attrs,
            extra=extra_attrs,
        )

        workflow = UtilWorkflow(
            name=name or "workflow",
            workflow_type=self._coerce_optional_str(workflow_type),
            description=self._coerce_optional_str(description),
            framework=self._coerce_optional_str(framework) or "langchain",
            attributes=attributes,
            run_id=run_id,
        )
        return workflow

    def _build_task(
        self,
        *,
        name: str,
        run_id: UUID,
        parent: Optional[GenAI],
        parent_run_id: Optional[UUID],
        metadata_attrs: dict[str, Any],
        extra_attrs: dict[str, Any],
        tags: Optional[list[str]],
        task_type: str,
        inputs: dict[str, Any],
    ) -> UtilTask:
        objective = metadata_attrs.pop("ls_objective", None)
        if objective is None:
            objective = metadata_attrs.pop("objective", None)
        description = metadata_attrs.pop("ls_description", None)
        if description is None:
            description = metadata_attrs.pop("description", None)
        assigned_agent = metadata_attrs.pop("assigned_agent", None)
        source: Optional[str] = None
        if isinstance(parent, UtilAgent):
            source = "agent"
        elif isinstance(parent, UtilWorkflow):
            source = "workflow"

        attributes = self._collect_attributes(
            metadata_attrs,
            tags=tags,
            extra=extra_attrs,
        )

        task = UtilTask(
            name=name or "task",
            objective=self._coerce_optional_str(objective),
            task_type=task_type,
            source=source,
            assigned_agent=self._coerce_optional_str(assigned_agent),
            description=self._coerce_optional_str(description),
            attributes=attributes,
            run_id=run_id,
            parent_run_id=parent.run_id if parent is not None else parent_run_id,
        )
        self._store_serialized_payload(task, "input_data", inputs)
        return task

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

        name = self._get_name_from_callback(serialized, **kwargs)
        is_agent_run = self._is_agent_run(serialized, metadata, tags)
        parent_entity = self._get_entity(parent_run_id)
        metadata_attrs = self._sanitize_metadata_dict(metadata)
        extra_attrs: dict[str, Any] = {
            "callback.name": name,
            "callback.id": serialized.get("id"),
        }

        if is_agent_run:
            agent = self._build_agent_invocation(
                name=name,
                run_id=run_id,
                parent_run_id=parent_run_id,
                inputs=inputs,
                metadata_attrs=metadata_attrs,
                tags=tags,
                extra_attrs=extra_attrs,
            )
            self._start_entity(agent)
            return

        if parent_entity is None:
            workflow = self._build_workflow(
                name=name,
                run_id=run_id,
                metadata_attrs=metadata_attrs,
                extra_attrs=extra_attrs,
            )
            workflow.parent_run_id = parent_run_id
            self._store_serialized_payload(workflow, "initial_input", inputs)
            self._start_entity(workflow)
            return

        task = self._build_task(
            name=name,
            run_id=run_id,
            parent=parent_entity,
            parent_run_id=parent_run_id,
            metadata_attrs=metadata_attrs,
            extra_attrs=extra_attrs,
            tags=tags,
            task_type="chain",
            inputs=inputs,
        )
        self._start_entity(task)

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

        entity = self._get_entity(run_id)
        if entity is None:
            return

        if not should_emit_events() and should_send_prompts():
            self._capture_prompt_data(entity, "outputs", {"outputs": outputs, "kwargs": kwargs})

        if isinstance(entity, UtilAgent):
            self._store_serialized_payload(entity, "output_result", outputs)
        elif isinstance(entity, UtilWorkflow):
            self._store_serialized_payload(entity, "final_output", outputs)
        elif isinstance(entity, UtilTask):
            self._store_serialized_payload(entity, "output_data", outputs)

        self._stop_entity(entity)

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
        metadata_attrs = self._sanitize_metadata_dict(metadata)
        invocation_attrs = self._sanitize_metadata_dict(invocation_params)
        ls_metadata: dict[str, Any] = {}
        raw_model_from_metadata = None
        for key in ("ls_model_name", "model_name"):
            if key in metadata_attrs:
                raw_model_from_metadata = metadata_attrs.pop(key)
                if key == "ls_model_name":
                    ls_metadata[key] = raw_model_from_metadata
                break

        raw_request_model = (
            invocation_params.get("model_name")
            or raw_model_from_metadata
            or serialized.get("name")
            or "unknown-model"
        )
        request_model = str(raw_request_model)
        invocation_attrs.pop("model_name", None)
        invocation_attrs.pop("model", None)

        provider_name = None
        for key in ("ls_provider", "provider"):
            if key in metadata_attrs:
                value = metadata_attrs.pop(key)
                if key == "ls_provider":
                    ls_metadata[key] = value
                provider_name = str(value)
                break
        if provider_name is None and "provider" in invocation_attrs:
            provider_name = str(invocation_attrs.pop("provider"))

        extras: dict[str, Any] = {}
        callback_name = self._get_name_from_callback(serialized, kwargs=kwargs)
        if callback_name:
            extras["callback.name"] = callback_name
        serialized_id = serialized.get("id")
        if serialized_id is not None:
            extras["callback.id"] = _sanitize_metadata_value(serialized_id)
        extras.setdefault("span.kind", "llm")

        def _record_ls_attribute(key: str, value: Any) -> None:
            if value is None:
                return
            ls_metadata[key] = value

        def _pop_float(source: dict[str, Any], *keys: str) -> Optional[float]:
            for key in keys:
                if key in source:
                    raw = source.pop(key)
                    try:
                        return float(raw)
                    except (TypeError, ValueError):
                        return None
            return None

        def _pop_int(source: dict[str, Any], *keys: str) -> Optional[int]:
            for key in keys:
                if key in source:
                    raw = source.pop(key)
                    try:
                        return int(raw)
                    except (TypeError, ValueError):
                        try:
                            return int(float(raw))
                        except (TypeError, ValueError):
                            return None
            return None

        def _pop_stop_sequences(source: dict[str, Any], *keys: str) -> list[str]:
            for key in keys:
                if key in source:
                    raw = source.pop(key)
                    if raw is None:
                        return []
                    if isinstance(raw, (list, tuple, set)):
                        return [str(item) for item in raw if item is not None]
                    return [str(raw)]
            return []

        request_temperature = _pop_float(invocation_attrs, "temperature")
        if request_temperature is None:
            temp_from_metadata = _pop_float(metadata_attrs, "ls_temperature")
            if temp_from_metadata is not None:
                _record_ls_attribute("ls_temperature", temp_from_metadata)
                request_temperature = temp_from_metadata
        request_top_p = _pop_float(invocation_attrs, "top_p")
        request_top_k = _pop_int(invocation_attrs, "top_k")
        request_frequency_penalty = _pop_float(
            invocation_attrs, "frequency_penalty"
        )
        request_presence_penalty = _pop_float(
            invocation_attrs, "presence_penalty"
        )
        request_seed = _pop_int(invocation_attrs, "seed")

        request_max_tokens = _pop_int(
            invocation_attrs, "max_tokens", "max_new_tokens"
        )
        if request_max_tokens is None:
            max_tokens_from_metadata = _pop_int(metadata_attrs, "ls_max_tokens")
            if max_tokens_from_metadata is not None:
                _record_ls_attribute("ls_max_tokens", max_tokens_from_metadata)
                request_max_tokens = max_tokens_from_metadata

        request_stop_sequences = _pop_stop_sequences(invocation_attrs, "stop")
        if not request_stop_sequences:
            request_stop_sequences = _pop_stop_sequences(
                invocation_attrs, "stop_sequences"
            )
        ls_stop_sequences = _pop_stop_sequences(metadata_attrs, "ls_stop")
        if ls_stop_sequences:
            _record_ls_attribute("ls_stop", ls_stop_sequences)
            if not request_stop_sequences:
                request_stop_sequences = ls_stop_sequences

        request_choice_count = _pop_int(
            invocation_attrs,
            "n",
            "choice_count",
            "num_generations",
            "num_return_sequences",
        )

        request_service_tier = metadata_attrs.pop("ls_service_tier", None)
        _record_ls_attribute("ls_service_tier", request_service_tier)
        if request_service_tier is None:
            request_service_tier = invocation_attrs.pop("service_tier", None)

        for key in list(metadata_attrs.keys()):
            if key.startswith("ls_"):
                _record_ls_attribute(key, metadata_attrs.pop(key))
        for key in list(invocation_attrs.keys()):
            if key.startswith("ls_"):
                _record_ls_attribute(key, invocation_attrs.pop(key))

        duplicate_param_keys = (
            "temperature",
            "top_p",
            "top_k",
            "frequency_penalty",
            "presence_penalty",
            "seed",
            "max_tokens",
            "max_new_tokens",
            "stop",
            "stop_sequences",
            "n",
            "choice_count",
            "num_generations",
            "num_return_sequences",
        )
        for key in duplicate_param_keys:
            metadata_attrs.pop(key, None)
            invocation_attrs.pop(key, None)

        if tags:
            extras["tags"] = [str(tag) for tag in tags]

        attributes = self._collect_attributes(
            metadata_attrs,
            invocation_attrs,
            extra=extras,
            tags=None,
        )

        if ls_metadata:
            legacy = attributes.setdefault("langchain_legacy", {})
            if isinstance(legacy, dict):
                for key, value in ls_metadata.items():
                    sanitized = _sanitize_metadata_value(value)
                    if sanitized is not None:
                        legacy[key] = sanitized
            else:  # pragma: no cover - defensive
                attributes["langchain_legacy"] = {
                    key: _sanitize_metadata_value(value)
                    for key, value in ls_metadata.items()
                    if _sanitize_metadata_value(value) is not None
                }

        def _store_request_attribute(key: str, value: Any) -> None:
            if value is None:
                return
            attributes[key] = value

        _store_request_attribute("request_temperature", request_temperature)
        _store_request_attribute("request_top_p", request_top_p)
        _store_request_attribute("request_top_k", request_top_k)
        _store_request_attribute(
            "request_frequency_penalty", request_frequency_penalty
        )
        _store_request_attribute(
            "request_presence_penalty", request_presence_penalty
        )
        _store_request_attribute("request_seed", request_seed)
        _store_request_attribute("request_max_tokens", request_max_tokens)
        _store_request_attribute("request_choice_count", request_choice_count)
        if request_stop_sequences:
            attributes["request_stop_sequences"] = request_stop_sequences
        _store_request_attribute("request_service_tier", request_service_tier)

        request_functions = self._extract_request_functions(invocation_params)
        input_messages = self._build_input_messages(messages)
        llm_kwargs: dict[str, Any] = {
            "request_model": request_model,
            "provider": provider_name,
            "framework": "langchain",
            "input_messages": input_messages,
            "request_functions": request_functions,
            "attributes": attributes,
        }
        if request_temperature is not None:
            llm_kwargs["request_temperature"] = request_temperature
        if request_top_p is not None:
            llm_kwargs["request_top_p"] = request_top_p
        if request_top_k is not None:
            llm_kwargs["request_top_k"] = request_top_k
        if request_frequency_penalty is not None:
            llm_kwargs["request_frequency_penalty"] = request_frequency_penalty
        if request_presence_penalty is not None:
            llm_kwargs["request_presence_penalty"] = request_presence_penalty
        if request_seed is not None:
            llm_kwargs["request_seed"] = request_seed
        if request_max_tokens is not None:
            llm_kwargs["request_max_tokens"] = request_max_tokens
        if request_choice_count is not None:
            llm_kwargs["request_choice_count"] = request_choice_count
        if request_stop_sequences:
            llm_kwargs["request_stop_sequences"] = request_stop_sequences
        if request_service_tier is not None:
            llm_kwargs["request_service_tier"] = request_service_tier

        inv = UtilLLMInvocation(**llm_kwargs)
        inv.run_id = run_id
        if parent_run_id is not None:
            inv.parent_run_id = parent_run_id
        else:
            implicit_parent = self._resolve_parent(parent_run_id)
            if implicit_parent is not None:
                inv.parent_run_id = implicit_parent.run_id

        parent_agent = self._find_agent(parent_run_id)
        if parent_agent is not None:
            inv.agent_name = parent_agent.name
            inv.agent_id = str(parent_agent.run_id)

        if should_emit_events():
            self._emit_chat_input_events(messages)
        elif should_send_prompts():
            self._capture_prompt_data(inv, "inputs", {"messages": messages})

        self._start_entity(inv)

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
        message_batches: list[list[BaseMessage]] = []
        for prompt in prompts:
            message_batches.append([HumanMessage(content=prompt)])

        self.on_chat_model_start(
            serialized=serialized,
            messages=message_batches,
            run_id=run_id,
            tags=tags,
            parent_run_id=parent_run_id,
            metadata=metadata,
            **kwargs,
        )

        invocation = self._llms.get(run_id)
        if invocation is not None:
            invocation.operation = "generate_text"

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
        invocation = self._llms.get(run_id)
        if invocation is None:
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
            invocation.output_messages = [
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
        invocation.response_model_name = response_model
        invocation.response_id = response_id
        if usage:
            invocation.input_tokens = usage.get("prompt_tokens")
            invocation.output_tokens = usage.get("completion_tokens")

        if should_emit_events():
            self._emit_llm_end_events(response)
        elif should_send_prompts():
            self._capture_prompt_data(
                invocation,
                "outputs",
                {
                    "generations": generations,
                    "llm_output": llm_output,
                    "kwargs": kwargs,
                },
            )

        self._stop_entity(invocation)

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
        parent_entity = self._get_entity(parent_run_id)
        metadata_attrs = self._sanitize_metadata_dict(metadata)
        extra_attrs: dict[str, Any] = {
            "callback.name": name,
            "callback.id": serialized.get("id"),
        }

        task_inputs = inputs if inputs is not None else {"input_str": input_str}
        task = self._build_task(
            name=name,
            run_id=run_id,
            parent=parent_entity,
            parent_run_id=parent_run_id,
            metadata_attrs=metadata_attrs,
            extra_attrs=extra_attrs,
            tags=tags,
            task_type="tool_use",
            inputs=task_inputs,
        )

        if not should_emit_events() and should_send_prompts():
            self._capture_prompt_data(
                task,
                "inputs",
                {
                    "input_str": input_str,
                    "inputs": inputs,
                    "metadata": metadata,
                    "kwargs": kwargs,
                },
            )

        self._start_entity(task)

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

        entity = self._get_entity(run_id)
        if not isinstance(entity, UtilTask):
            return

        if not should_emit_events() and should_send_prompts():
            self._capture_prompt_data(
                entity,
                "outputs",
                {"output": output, "kwargs": kwargs},
            )

        self._store_serialized_payload(entity, "output_data", output)
        self._stop_entity(entity)

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
        entity = self._get_entity(run_id)
        if entity is None:
            return

        entity.attributes.setdefault("error_message", str(error))
        if not should_emit_events() and should_send_prompts():
            self._capture_prompt_data(
                entity,
                "error",
                {
                    "error": str(error),
                    "kwargs": kwargs,
                },
            )

        self._fail_entity(entity, error)

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
