# pyright: reportMissingImports=false

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

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field, is_dataclass
from importlib import import_module
from types import SimpleNamespace
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    List,
    Optional,
    Protocol,
    Sequence,
    Union,
    cast,
)
from urllib.parse import urlparse
from uuid import UUID

from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.trace import (
    Span,
    SpanKind,
    Status,
    StatusCode,
    Tracer,
    get_current_span,
    set_span_in_context,
)

LOGGER = logging.getLogger(__name__)


class _BaseCallbackHandlerProtocol(Protocol):
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

    inheritable_handlers: Sequence[Any]

    def add_handler(self, handler: Any, inherit: bool = False) -> None: ...


class _BaseCallbackHandlerStub:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        return

    inheritable_handlers: Sequence[Any] = ()

    def add_handler(self, handler: Any, inherit: bool = False) -> None:
        raise RuntimeError(
            "LangChain is required for the LangChain instrumentation."
        )


if TYPE_CHECKING:
    BaseCallbackHandler = _BaseCallbackHandlerProtocol
else:
    try:
        from langchain_core.callbacks import (
            BaseCallbackHandler,  # type: ignore[import]
        )
    except ImportError:  # pragma: no cover - optional dependency
        BaseCallbackHandler = _BaseCallbackHandlerStub


try:  # pragma: no cover - optional dependency
    from langchain_core.agents import AgentAction, AgentFinish
except ImportError:  # pragma: no cover - optional dependency

    class AgentAction:  # type: ignore[too-few-public-methods]
        tool: Any = None
        tool_input: Any = None
        log: Any = None

    class AgentFinish:  # type: ignore[too-few-public-methods]
        return_values: Any = None


try:  # pragma: no cover - optional dependency
    from langchain_core.documents import Document
except ImportError:  # pragma: no cover - optional dependency

    @dataclass
    class Document:  # type: ignore[too-few-public-methods]
        page_content: str = ""
        metadata: Dict[str, Any] = field(default_factory=dict)


try:  # pragma: no cover - optional dependency
    from langchain_core.messages import (
        AIMessage,
        BaseMessage,
        HumanMessage,
        ToolMessage,
    )
except ImportError:  # pragma: no cover - optional dependency

    class BaseMessage:  # type: ignore[too-few-public-methods]
        type: str = "message"
        content: Any = None

    class HumanMessage(BaseMessage):  # type: ignore[too-few-public-methods]
        type = "human"

    class AIMessage(BaseMessage):  # type: ignore[too-few-public-methods]
        type = "ai"
        tool_calls: Optional[List[dict[str, Any]]] = None

    class ToolMessage(BaseMessage):  # type: ignore[too-few-public-methods]
        type = "tool"
        tool_call_id: Optional[str] = None


try:  # pragma: no cover - optional dependency
    from langchain_core.outputs import ChatGeneration, LLMResult
except ImportError:  # pragma: no cover - optional dependency

    @dataclass
    class ChatGeneration:  # type: ignore[too-few-public-methods]
        message: Any = None
        generation_info: Optional[Dict[str, Any]] = None

    @dataclass
    class LLMResult:  # type: ignore[too-few-public-methods]
        generations: Sequence[Sequence[ChatGeneration]] = ()
        llm_output: Optional[Dict[str, Any]] = None


try:
    _gen_ai_attributes = import_module(
        "opentelemetry.semconv._incubating.attributes.gen_ai_attributes"
    )
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    _gen_ai_attributes = SimpleNamespace()

try:
    _openai_attributes = import_module(
        "opentelemetry.semconv._incubating.attributes.openai_attributes"
    )
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    _openai_attributes = SimpleNamespace()

GenAI = cast(Any, _gen_ai_attributes)
OpenAI = cast(Any, _openai_attributes)


def _enum_member_value(enum_name: str, member_name: str, default: str) -> str:
    """Return the value for a GenAI enum member, falling back to the provided default."""
    enum_cls = getattr(GenAI, enum_name, None)
    member = (
        getattr(enum_cls, member_name, None) if enum_cls is not None else None
    )
    value = getattr(member, "value", None)
    if isinstance(value, str):
        return value
    if isinstance(member, str):
        return member
    return default


def _gen_ai_attr(name: str, default: str) -> str:
    """Fetch a GenAI semantic attribute constant, defaulting to the provided string."""
    value = getattr(GenAI, name, None)
    if isinstance(value, str):
        return value
    return default


class Attrs:
    PROVIDER_NAME = _gen_ai_attr(
        "GEN_AI_PROVIDER_NAME", "gen_ai.provider.name"
    )
    OPERATION_NAME = _gen_ai_attr(
        "GEN_AI_OPERATION_NAME", "gen_ai.operation.name"
    )
    REQUEST_MODEL = _gen_ai_attr(
        "GEN_AI_REQUEST_MODEL", "gen_ai.request.model"
    )
    REQUEST_MAX_TOKENS = _gen_ai_attr(
        "GEN_AI_REQUEST_MAX_TOKENS", "gen_ai.request.max_tokens"
    )
    REQUEST_MAX_INPUT_TOKENS = _gen_ai_attr(
        "GEN_AI_REQUEST_MAX_INPUT_TOKENS", "gen_ai.request.max_input_tokens"
    )
    REQUEST_MAX_OUTPUT_TOKENS = _gen_ai_attr(
        "GEN_AI_REQUEST_MAX_OUTPUT_TOKENS", "gen_ai.request.max_output_tokens"
    )
    REQUEST_TEMPERATURE = _gen_ai_attr(
        "GEN_AI_REQUEST_TEMPERATURE", "gen_ai.request.temperature"
    )
    REQUEST_TOP_P = _gen_ai_attr(
        "GEN_AI_REQUEST_TOP_P", "gen_ai.request.top_p"
    )
    REQUEST_TOP_K = _gen_ai_attr(
        "GEN_AI_REQUEST_TOP_K", "gen_ai.request.top_k"
    )
    REQUEST_STOP = _gen_ai_attr(
        "GEN_AI_REQUEST_STOP_SEQUENCES", "gen_ai.request.stop_sequences"
    )
    REQUEST_FREQ_PENALTY = _gen_ai_attr(
        "GEN_AI_REQUEST_FREQUENCY_PENALTY",
        "gen_ai.request.frequency_penalty",
    )
    REQUEST_PRES_PENALTY = _gen_ai_attr(
        "GEN_AI_REQUEST_PRESENCE_PENALTY",
        "gen_ai.request.presence_penalty",
    )
    REQUEST_CHOICE_COUNT = _gen_ai_attr(
        "GEN_AI_REQUEST_CHOICE_COUNT", "gen_ai.request.choice.count"
    )
    REQUEST_SEED = _gen_ai_attr("GEN_AI_REQUEST_SEED", "gen_ai.request.seed")
    REQUEST_ENCODING_FORMATS = _gen_ai_attr(
        "GEN_AI_REQUEST_ENCODING_FORMATS",
        "gen_ai.request.encoding_formats",
    )
    RESPONSE_ID = _gen_ai_attr("GEN_AI_RESPONSE_ID", "gen_ai.response.id")
    RESPONSE_MODEL = _gen_ai_attr(
        "GEN_AI_RESPONSE_MODEL", "gen_ai.response.model"
    )
    RESPONSE_FINISH_REASONS = _gen_ai_attr(
        "GEN_AI_RESPONSE_FINISH_REASONS",
        "gen_ai.response.finish_reasons",
    )
    USAGE_INPUT_TOKENS = _gen_ai_attr(
        "GEN_AI_USAGE_INPUT_TOKENS", "gen_ai.usage.input_tokens"
    )
    USAGE_OUTPUT_TOKENS = _gen_ai_attr(
        "GEN_AI_USAGE_OUTPUT_TOKENS", "gen_ai.usage.output_tokens"
    )
    INPUT_MESSAGES = _gen_ai_attr(
        "GEN_AI_INPUT_MESSAGES", "gen_ai.input.messages"
    )
    OUTPUT_MESSAGES = _gen_ai_attr(
        "GEN_AI_OUTPUT_MESSAGES", "gen_ai.output.messages"
    )
    SYSTEM_INSTRUCTIONS = _gen_ai_attr(
        "GEN_AI_SYSTEM_INSTRUCTIONS", "gen_ai.system_instructions"
    )
    OUTPUT_TYPE = _gen_ai_attr("GEN_AI_OUTPUT_TYPE", "gen_ai.output.type")
    TOOL_NAME = _gen_ai_attr("GEN_AI_TOOL_NAME", "gen_ai.tool.name")
    TOOL_TYPE = _gen_ai_attr("GEN_AI_TOOL_TYPE", "gen_ai.tool.type")
    TOOL_DESCRIPTION = _gen_ai_attr(
        "GEN_AI_TOOL_DESCRIPTION", "gen_ai.tool.description"
    )
    TOOL_DEFINITIONS = _gen_ai_attr(
        "GEN_AI_TOOL_DEFINITIONS", "gen_ai.tool.definitions"
    )
    TOOL_CALL_ID = _gen_ai_attr("GEN_AI_TOOL_CALL_ID", "gen_ai.tool.call.id")
    TOOL_CALL_ARGUMENTS = _gen_ai_attr(
        "GEN_AI_TOOL_CALL_ARGUMENTS", "gen_ai.tool.call.arguments"
    )
    TOOL_CALL_RESULT = _gen_ai_attr(
        "GEN_AI_TOOL_CALL_RESULT", "gen_ai.tool.call.result"
    )
    DATA_SOURCE_ID = _gen_ai_attr(
        "GEN_AI_DATA_SOURCE_ID", "gen_ai.data_source.id"
    )
    AGENT_ID = _gen_ai_attr("GEN_AI_AGENT_ID", "gen_ai.agent.id")
    AGENT_NAME = _gen_ai_attr("GEN_AI_AGENT_NAME", "gen_ai.agent.name")
    AGENT_DESCRIPTION = _gen_ai_attr(
        "GEN_AI_AGENT_DESCRIPTION", "gen_ai.agent.description"
    )
    CONVERSATION_ID = _gen_ai_attr(
        "GEN_AI_CONVERSATION_ID", "gen_ai.conversation.id"
    )
    RETRIEVER_RESULTS = _gen_ai_attr(
        "GEN_AI_RETRIEVER_RESULTS", "gen_ai.retriever.results"
    )
    RETRIEVER_QUERY = _gen_ai_attr(
        "GEN_AI_RETRIEVER_QUERY", "gen_ai.retriever.query"
    )
    SERVER_ADDRESS = "server.address"
    SERVER_PORT = "server.port"
    ERROR_TYPE = getattr(ErrorAttributes, "ERROR_TYPE", "error.type")
    OPENAI_REQUEST_SERVICE_TIER = cast(
        str,
        getattr(
            OpenAI,
            "OPENAI_REQUEST_SERVICE_TIER",
            "gen_ai.openai.request.service_tier",
        ),
    )
    OPENAI_RESPONSE_SERVICE_TIER = cast(
        str,
        getattr(
            OpenAI,
            "OPENAI_RESPONSE_SERVICE_TIER",
            "gen_ai.openai.response.service_tier",
        ),
    )
    OPENAI_RESPONSE_SYSTEM_FINGERPRINT = cast(
        str,
        getattr(
            OpenAI,
            "OPENAI_RESPONSE_SYSTEM_FINGERPRINT",
            "gen_ai.openai.response.system_fingerprint",
        ),
    )


_OPERATION_INVOKE_AGENT = _enum_member_value(
    "GenAiOperationNameValues", "INVOKE_AGENT", "invoke_agent"
)
_OPERATION_CHAT = _enum_member_value(
    "GenAiOperationNameValues", "CHAT", "chat"
)
_OPERATION_TEXT_COMPLETION = _enum_member_value(
    "GenAiOperationNameValues", "TEXT_COMPLETION", "text_completion"
)
_OPERATION_EXECUTE_TOOL = _enum_member_value(
    "GenAiOperationNameValues", "EXECUTE_TOOL", "execute_tool"
)

_OUTPUT_TYPE_JSON = _enum_member_value("GenAiOutputTypeValues", "JSON", "json")
_OUTPUT_TYPE_TEXT = _enum_member_value("GenAiOutputTypeValues", "TEXT", "text")


def _as_json_attribute(value: Any) -> str:
    """Return a JSON string suitable for OpenTelemetry string attributes."""
    try:
        return json.dumps(value, default=str, ensure_ascii=False)
    except Exception:  # pragma: no cover - defensive
        return json.dumps(str(value), ensure_ascii=False)


def _redact_text_content() -> dict[str, str]:
    return {"type": "text", "content": "[redacted]"}


def _message_role(message: Union[BaseMessage, dict[str, Any]]) -> str:
    if isinstance(message, BaseMessage):
        if isinstance(message, HumanMessage):
            return "user"
        if isinstance(message, ToolMessage):
            return "tool"
        if isinstance(message, AIMessage):
            return "assistant"
        # Fallback to message.type for other subclasses
        type_value = getattr(message, "type", None)
        if isinstance(type_value, str):
            return type_value
        return "user"
    role = message.get("role") or message.get("type")
    if role in {"human", "user"}:
        return "user"
    if role in {"ai", "assistant"}:
        return "assistant"
    if role == "tool":
        return "tool"
    if role == "system":
        return "system"
    return str(role or "user")


def _message_content(message: Union[BaseMessage, dict[str, Any]]) -> Any:
    if isinstance(message, BaseMessage):
        return message.content
    return message.get("content")


def _coerce_content_to_text(content: Any) -> Optional[str]:
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, (list, tuple)):
        return " ".join(str(part) for part in content if part is not None)
    return str(content)


def _extract_tool_calls(
    message: Union[BaseMessage, dict[str, Any]],
) -> List[dict[str, Any]]:
    if isinstance(message, BaseMessage) and getattr(
        message, "tool_calls", None
    ):
        tool_calls = getattr(message, "tool_calls") or []
        if isinstance(tool_calls, list):
            return [tc for tc in tool_calls if isinstance(tc, dict)]
    if isinstance(message, dict):
        tool_calls = message.get("tool_calls") or []
        if isinstance(tool_calls, list):
            return [tc for tc in tool_calls if isinstance(tc, dict)]
    return []


def _tool_call_id_from_message(
    message: Union[BaseMessage, dict[str, Any]],
) -> Optional[str]:
    if isinstance(message, ToolMessage):
        if getattr(message, "tool_call_id", None):
            return str(message.tool_call_id)
    if isinstance(message, dict):
        if message.get("tool_call_id"):
            return str(message["tool_call_id"])
    return None


def _prepare_messages(
    raw_messages: Any,
    *,
    record_content: bool,
    include_roles: Optional[Iterable[str]] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Return (formatted_messages_json, system_instructions_json)."""
    if not raw_messages:
        return None, None

    include_role_set = (
        set(include_roles) if include_roles is not None else None
    )

    if isinstance(raw_messages, dict):
        iterable: Sequence[Any] = raw_messages.get("messages") or []
    elif isinstance(raw_messages, (list, tuple)):
        if raw_messages and isinstance(raw_messages[0], (list, tuple)):
            iterable = [msg for thread in raw_messages for msg in thread]
        else:
            iterable = list(raw_messages)
    else:
        iterable = [raw_messages]

    formatted: List[dict[str, Any]] = []
    system_parts: List[dict[str, str]] = []

    for item in iterable:
        role = _message_role(item)
        content = _coerce_content_to_text(_message_content(item))

        if role == "system":
            if content:
                system_parts.append(
                    {
                        "type": "text",
                        "content": content if record_content else "[redacted]",
                    }
                )
            continue

        if include_role_set is not None and role not in include_role_set:
            continue

        parts: List[dict[str, Any]] = []

        if role in {"user", "assistant"} and content:
            parts.append(
                {
                    "type": "text",
                    "content": content if record_content else "[redacted]",
                }
            )

        if role == "tool":
            tool_result = content if record_content else "[redacted]"
            parts.append(
                {
                    "type": "tool_call_response",
                    "id": _tool_call_id_from_message(item),
                    "result": tool_result,
                }
            )

        tool_calls = _extract_tool_calls(item)
        for tc in tool_calls:
            arguments = tc.get("args") or tc.get("arguments")
            if arguments is None:
                arguments = {}
            tc_entry = {
                "type": "tool_call",
                "id": tc.get("id"),
                "name": tc.get("name"),
                "arguments": arguments if record_content else "[redacted]",
            }
            parts.append(tc_entry)

        if not parts:
            parts.append(_redact_text_content())

        formatted.append({"role": role, "parts": parts})

    formatted_json = _as_json_attribute(formatted) if formatted else None
    system_json = _as_json_attribute(system_parts) if system_parts else None
    return formatted_json, system_json


def _filter_assistant_output(formatted_messages: str) -> Optional[str]:
    try:
        messages = json.loads(formatted_messages)
    except Exception:
        return formatted_messages
    cleaned: List[dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        text_parts = [
            part for part in msg.get("parts", []) if part.get("type") == "text"
        ]
        if not text_parts:
            continue
        cleaned.append({"role": "assistant", "parts": text_parts})
    if not cleaned:
        return None
    return _as_json_attribute(cleaned)


def _scrub_value(value: Any, record_content: bool) -> Any:
    if value is None:
        return None
    if isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if not record_content:
            return "[redacted]"
        stripped = value.strip()
        if stripped and stripped[0] in "{[":
            try:
                return json.loads(stripped)
            except Exception:
                pass
        return value
    if not record_content:
        return "[redacted]"
    if isinstance(value, BaseMessage):
        return {
            "type": getattr(value, "type", "message"),
            "content": _coerce_content_to_text(
                getattr(value, "content", None)
            ),
        }
    if isinstance(value, dict):
        return {k: _scrub_value(v, record_content) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_scrub_value(v, record_content) for v in value]
    if is_dataclass(value) and not isinstance(value, type):
        try:
            return asdict(value)
        except Exception:  # pragma: no cover
            return str(value)
    return str(value)


def _serialise_tool_result(output: Any, record_content: bool) -> str:
    if isinstance(output, ToolMessage):
        data = {
            "name": getattr(output, "name", None),
            "tool_call_id": _tool_call_id_from_message(output),
            "content": _scrub_value(output.content, record_content),
        }
        return _as_json_attribute(data)
    if isinstance(output, BaseMessage):
        data = {
            "type": getattr(output, "type", "message"),
            "content": _scrub_value(output.content, record_content),
        }
        return _as_json_attribute(data)
    scrubbed = _scrub_value(output, record_content)
    return _as_json_attribute(scrubbed)


def _format_tool_definitions(
    definitions: Optional[Iterable[Any]],
) -> Optional[str]:
    if not definitions:
        return None
    return _as_json_attribute(list(definitions))


def _format_documents(
    documents: Optional[Sequence[Document]],
    *,
    record_content: bool,
) -> Optional[str]:
    if not documents:
        return None
    serialised: List[Dict[str, Any]] = []
    for doc in documents:
        metadata = getattr(doc, "metadata", {}) or {}
        entry: Dict[str, Any] = {"metadata": dict(metadata)}
        if record_content:
            entry["content"] = getattr(doc, "page_content", None)
        serialised.append(entry)
    return _as_json_attribute(serialised)


def _first_non_empty(*values: Any) -> Optional[Any]:
    for value in values:
        if value:
            return value
    return None


def _infer_provider_name(
    serialized: Optional[dict[str, Any]],
    metadata: Optional[dict[str, Any]],
    invocation_params: Optional[dict[str, Any]],
) -> Optional[str]:
    provider = (metadata or {}).get("ls_provider")
    if provider:
        provider = provider.lower()
        if provider in {"azure", "azure_openai", "azure-openai"}:
            return "azure.ai.openai"
        if provider in {"azure_ai_inference", "azure-ai-inference"}:
            return "azure.ai.inference"
        if provider in {"openai"}:
            return "openai"
        if provider in {"github"}:
            return "azure.ai.openai"
        if provider in {"bedrock", "aws", "amazon"}:
            return "aws.bedrock"
    if invocation_params:
        base_url = invocation_params.get("base_url")
        if isinstance(base_url, str):
            lowered = base_url.lower()
            if "azure" in lowered:
                return "azure.ai.openai"
            if "openai" in lowered:
                return "openai"
            if "ollama" in lowered:
                return "ollama"
    if serialized:
        kwargs = serialized.get("kwargs", {})
        if isinstance(kwargs, dict):
            if kwargs.get("azure_endpoint") or str(
                kwargs.get("openai_api_base", "")
            ).endswith(".azure.com"):
                return "azure.ai.openai"
    return None


def _infer_server_address(
    serialized: Optional[dict[str, Any]],
    invocation_params: Optional[dict[str, Any]],
) -> Optional[str]:
    base_url = None
    if invocation_params:
        base_url = _first_non_empty(
            invocation_params.get("base_url"),
            invocation_params.get("openai_api_base"),
        )
    if not base_url and serialized:
        kwargs = serialized.get("kwargs", {})
        if isinstance(kwargs, dict):
            base_url = _first_non_empty(
                kwargs.get("openai_api_base"),
                kwargs.get("azure_endpoint"),
            )
    if not base_url:
        return None
    try:
        parsed = urlparse(base_url)
        return parsed.hostname or None
    except Exception:  # pragma: no cover
        return None


def _infer_server_port(
    serialized: Optional[dict[str, Any]],
    invocation_params: Optional[dict[str, Any]],
) -> Optional[int]:
    base_url = None
    if invocation_params:
        base_url = _first_non_empty(
            invocation_params.get("base_url"),
            invocation_params.get("openai_api_base"),
        )
    if not base_url and serialized:
        kwargs = serialized.get("kwargs", {})
        if isinstance(kwargs, dict):
            base_url = _first_non_empty(
                kwargs.get("openai_api_base"),
                kwargs.get("azure_endpoint"),
            )
    if not base_url:
        return None
    try:
        parsed = urlparse(base_url)
        if parsed.port:
            return parsed.port
    except Exception:  # pragma: no cover
        return None
    return None


def _tool_type_from_definition(defn: dict[str, Any]) -> Optional[str]:
    if not defn:
        return None
    if defn.get("type"):
        return str(defn["type"]).lower()
    function = defn.get("function")
    if isinstance(function, dict):
        return str(function.get("type") or "function")
    return None


@dataclass
class _SpanRecord:
    span: Span
    operation: str
    parent_run_id: Optional[str]
    attributes: Dict[str, Any] = field(default_factory=dict)
    stash: Dict[str, Any] = field(default_factory=dict)


class OpenTelemetryLangChainCallbackHandler(BaseCallbackHandler):
    """LangChain callback handler that emits OpenTelemetry GenAI spans."""

    def __init__(
        self,
        *,
        tracer: Tracer,
        capture_messages: bool,
        agent_id: Optional[str] = None,
        provider_name: Optional[str] = None,
        name: str = "OpenTelemetryLangChainTracer",
    ) -> None:
        super().__init__()
        self._name = name
        self._default_agent_id = agent_id
        self._default_provider_name = provider_name
        self._content_recording = capture_messages
        self._tracer = tracer
        self._spans: Dict[str, _SpanRecord] = {}
        self._ignored_runs: set[str] = set()
        self._run_parent_override: Dict[str, Optional[str]] = {}

    def _should_ignore_agent_span(
        self,
        agent_name: Optional[str],
        parent_run_id: Optional[UUID],
        metadata: Optional[dict[str, Any]],
    ) -> bool:
        if metadata and metadata.get("otel_agent_span"):
            node_name = metadata.get("langgraph_node")
            meta_agent_name = metadata.get("agent_name") or metadata.get(
                "agent_type"
            )
            if (
                node_name
                and meta_agent_name
                and str(node_name) != str(meta_agent_name)
            ):
                return True
            return False
        if agent_name == "LangGraph":
            return False
        if parent_run_id is None:
            return False
        if agent_name and "Middleware." in agent_name:
            return True
        return True

    def _resolve_parent_id(
        self, parent_run_id: Optional[UUID]
    ) -> Optional[str]:
        if parent_run_id is None:
            return None
        candidate: Optional[str] = str(parent_run_id)
        visited: set[str] = set()
        while candidate is not None:
            if candidate in visited:
                return None
            visited.add(candidate)
            if candidate in self._ignored_runs:
                candidate = self._run_parent_override.get(candidate)
                continue
            override = self._run_parent_override.get(candidate)
            if override:
                candidate = override
                continue
            return candidate
        return None

    def _update_parent_attribute(
        self,
        parent_key: Optional[str],
        attr: str,
        value: Any,
    ) -> None:
        if not parent_key or value is None:
            return
        parent_record = self._spans.get(parent_key)
        if not parent_record:
            return
        parent_record.span.set_attribute(attr, value)
        parent_record.attributes[attr] = value

    # ------------------------------------------------------------------
    # LangChain callback overrides
    # ------------------------------------------------------------------
    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        metadata = metadata or {}
        agent_name = _first_non_empty(
            metadata.get("agent_name"),
            metadata.get("agent_type"),
            metadata.get("langgraph_node"),
            kwargs.get("name"),
        )
        run_key = str(run_id)
        parent_key = str(parent_run_id) if parent_run_id else None
        if self._should_ignore_agent_span(agent_name, parent_run_id, metadata):
            self._ignored_runs.add(run_key)
            self._run_parent_override[run_key] = parent_key
            return
        attributes: Dict[str, Any] = {
            Attrs.OPERATION_NAME: _OPERATION_INVOKE_AGENT,
        }
        if agent_name:
            attributes[Attrs.AGENT_NAME] = str(agent_name)
        else:
            attributes[Attrs.AGENT_NAME] = self._name
        node_label = metadata.get("langgraph_node")
        if node_label:
            attributes["metadata.langgraph_node"] = str(node_label)
        agent_id = metadata.get("agent_id")
        if agent_id is not None:
            attributes[Attrs.AGENT_ID] = str(agent_id)
        elif self._default_agent_id:
            attributes[Attrs.AGENT_ID] = self._default_agent_id
        agent_description = metadata.get("agent_description")
        if agent_description:
            attributes[Attrs.AGENT_DESCRIPTION] = str(agent_description)
        conversation_id = _first_non_empty(
            metadata.get("thread_id"),
            metadata.get("session_id"),
            metadata.get("conversation_id"),
        )
        if conversation_id:
            attributes[Attrs.CONVERSATION_ID] = str(conversation_id)
        path = metadata.get("langgraph_path")
        if path:
            attributes["metadata.langgraph_path"] = json.dumps(
                path, default=str
            )
        for key in (
            Attrs.PROVIDER_NAME,
            Attrs.SERVER_ADDRESS,
            Attrs.SERVER_PORT,
            "service.name",
        ):
            value = metadata.get(key)
            if value is not None:
                attributes[key] = value
        for meta_key, meta_value in metadata.items():
            if meta_key.startswith("gen_ai."):
                attributes[meta_key] = meta_value
        if (
            Attrs.PROVIDER_NAME not in attributes
            and self._default_provider_name
        ):
            attributes[Attrs.PROVIDER_NAME] = self._default_provider_name

        formatted_messages, system_instr = _prepare_messages(
            inputs.get("messages"),
            record_content=self._content_recording,
            include_roles={"user", "assistant", "tool"},
        )
        if formatted_messages:
            attributes[Attrs.INPUT_MESSAGES] = formatted_messages
        if system_instr:
            attributes[Attrs.SYSTEM_INSTRUCTIONS] = system_instr

        is_agent_span = bool(metadata.get("otel_agent_span"))
        effective_parent_run_id = parent_run_id
        resolved_parent = self._resolve_parent_id(parent_run_id)
        parent_record = (
            self._spans.get(resolved_parent) if resolved_parent else None
        )
        if (
            is_agent_span
            and parent_record
            and parent_record.operation == _OPERATION_INVOKE_AGENT
        ):
            parent_agent_name = parent_record.attributes.get(Attrs.AGENT_NAME)
            if parent_agent_name != attributes.get(Attrs.AGENT_NAME):
                parent_override_key = parent_record.parent_run_id
                if parent_override_key:
                    try:
                        effective_parent_run_id = UUID(parent_override_key)
                    except (ValueError, TypeError, AttributeError):
                        effective_parent_run_id = None
                else:
                    effective_parent_run_id = None
                resolved_parent = self._resolve_parent_id(
                    effective_parent_run_id
                )
                parent_record = (
                    self._spans.get(resolved_parent)
                    if resolved_parent
                    else None
                )

        span_name = f"{_OPERATION_INVOKE_AGENT} {attributes[Attrs.AGENT_NAME]}"
        self._start_span(
            run_id,
            span_name,
            operation=_OPERATION_INVOKE_AGENT,
            kind=SpanKind.CLIENT,
            parent_run_id=effective_parent_run_id,
            attributes=attributes,
        )
        new_record = self._spans.get(run_key)
        allowed_sources = metadata.get("otel_agent_span_allowed")
        if new_record and allowed_sources:
            try:
                new_record.stash["allowed_agent_sources"] = set(
                    allowed_sources
                )
            except TypeError:
                pass
        if formatted_messages:
            self._update_parent_attribute(
                resolved_parent, Attrs.INPUT_MESSAGES, formatted_messages
            )
        if system_instr:
            self._update_parent_attribute(
                resolved_parent, Attrs.SYSTEM_INSTRUCTIONS, system_instr
            )
        if conversation_id:
            self._update_parent_attribute(
                resolved_parent, Attrs.CONVERSATION_ID, str(conversation_id)
            )

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        run_key = str(run_id)
        if run_key in self._ignored_runs:
            self._ignored_runs.remove(run_key)
            self._run_parent_override.pop(run_key, None)
            return
        record = self._spans.get(run_key)
        if not record:
            return
        try:
            messages_payload: Any
            if isinstance(outputs, dict):
                messages_payload = outputs.get("messages")
            elif hasattr(outputs, "get"):
                try:
                    messages_payload = outputs.get(  # type: ignore[attr-defined]
                        "messages"
                    )
                except Exception:
                    messages_payload = outputs
            else:
                messages_payload = outputs
            formatted_messages, _ = _prepare_messages(
                messages_payload,
                record_content=self._content_recording,
                include_roles={"assistant"},
            )
            if formatted_messages:
                if record.operation == _OPERATION_INVOKE_AGENT:
                    cleaned = _filter_assistant_output(formatted_messages)
                    if cleaned:
                        record.span.set_attribute(
                            Attrs.OUTPUT_MESSAGES, cleaned
                        )
                else:
                    record.span.set_attribute(
                        Attrs.OUTPUT_MESSAGES, formatted_messages
                    )
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.debug(
                "Failed to serialise chain outputs: %s", exc, exc_info=True
            )
        record.span.set_status(Status(status_code=StatusCode.OK))
        self._end_span(run_id)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        run_key = str(run_id)
        if run_key in self._ignored_runs:
            self._ignored_runs.remove(run_key)
            self._run_parent_override.pop(run_key, None)
            return
        self._end_span(
            run_id,
            status=Status(StatusCode.ERROR, str(error)),
            error=error,
        )

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        self._handle_model_start(
            serialized=serialized,
            inputs=messages,
            run_id=run_id,
            parent_run_id=parent_run_id,
            metadata=metadata,
            invocation_kwargs=kwargs,
            is_chat_model=True,
        )

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: List[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        self._handle_model_start(
            serialized=serialized,
            inputs=prompts,
            run_id=run_id,
            parent_run_id=parent_run_id,
            metadata=metadata,
            invocation_kwargs=kwargs,
            is_chat_model=False,
        )

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        record = self._spans.get(str(run_id))
        if not record:
            return

        generations = cast(
            Sequence[Sequence[ChatGeneration]], response.generations or []
        )
        chat_generations: List[ChatGeneration] = []
        if generations:
            chat_generations = [
                gen for thread in generations for gen in thread
            ]

        if chat_generations:
            messages = [gen.message for gen in chat_generations if gen.message]
            formatted, _ = _prepare_messages(
                messages,
                record_content=self._content_recording,
                include_roles={"assistant"},
            )
            if formatted:
                record.span.set_attribute(Attrs.OUTPUT_MESSAGES, formatted)
                output_type = _OUTPUT_TYPE_TEXT
                try:
                    parsed = json.loads(formatted)
                    if any(
                        part.get("type") == "tool_call"
                        for msg in parsed
                        for part in msg.get("parts", [])
                    ):
                        output_type = _OUTPUT_TYPE_JSON
                except Exception:  # pragma: no cover
                    LOGGER.debug(
                        "Failed to inspect output message for tool calls",
                        exc_info=True,
                    )
                record.span.set_attribute(Attrs.OUTPUT_TYPE, output_type)

        finish_reasons: List[str] = []
        for gen in chat_generations:
            info = getattr(gen, "generation_info", {}) or {}
            if info.get("finish_reason"):
                finish_reasons.append(str(info["finish_reason"]))
        if finish_reasons:
            record.span.set_attribute(
                Attrs.RESPONSE_FINISH_REASONS,
                _as_json_attribute(finish_reasons),
            )

        llm_output = getattr(response, "llm_output", {}) or {}
        token_usage = llm_output.get("token_usage") or {}
        if "prompt_tokens" in token_usage:
            record.span.set_attribute(
                Attrs.USAGE_INPUT_TOKENS, int(token_usage["prompt_tokens"])
            )
        if "completion_tokens" in token_usage:
            record.span.set_attribute(
                Attrs.USAGE_OUTPUT_TOKENS,
                int(token_usage["completion_tokens"]),
            )
        if "id" in llm_output:
            record.span.set_attribute(Attrs.RESPONSE_ID, str(llm_output["id"]))
        if "model_name" in llm_output:
            record.span.set_attribute(
                Attrs.RESPONSE_MODEL, llm_output["model_name"]
            )
        if llm_output.get("system_fingerprint"):
            record.span.set_attribute(
                Attrs.OPENAI_RESPONSE_SYSTEM_FINGERPRINT,
                llm_output["system_fingerprint"],
            )
        if llm_output.get("service_tier"):
            record.span.set_attribute(
                Attrs.OPENAI_RESPONSE_SERVICE_TIER, llm_output["service_tier"]
            )

        model_name = llm_output.get("model_name") or record.attributes.get(
            Attrs.REQUEST_MODEL
        )
        if model_name:
            record.span.update_name(f"{record.operation} {model_name}")

        record.span.set_status(Status(StatusCode.OK))
        self._end_span(run_id)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        self._end_span(
            run_id,
            status=Status(StatusCode.ERROR, str(error)),
            error=error,
        )

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        metadata: Optional[dict[str, Any]] = None,
        inputs: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        resolved_parent = self._resolve_parent_id(parent_run_id)
        tool_name = _first_non_empty(
            serialized.get("name"),
            (metadata or {}).get("tool_name"),
            kwargs.get("name"),
        )
        attributes = {
            Attrs.OPERATION_NAME: _OPERATION_EXECUTE_TOOL,
            Attrs.TOOL_NAME: tool_name or "tool",
        }
        if serialized.get("description"):
            attributes[Attrs.TOOL_DESCRIPTION] = serialized["description"]
        tool_type = _tool_type_from_definition(serialized)
        if tool_type:
            attributes[Attrs.TOOL_TYPE] = tool_type
        tool_id = (inputs or {}).get("tool_call_id") or (
            (metadata or {}).get("tool_call_id")
        )
        if tool_id:
            attributes[Attrs.TOOL_CALL_ID] = str(tool_id)
        if inputs:
            attributes[Attrs.TOOL_CALL_ARGUMENTS] = _as_json_attribute(inputs)
        elif input_str:
            attributes[Attrs.TOOL_CALL_ARGUMENTS] = input_str
        parent_provider = None
        if resolved_parent and resolved_parent in self._spans:
            parent_provider = self._spans[resolved_parent].attributes.get(
                Attrs.PROVIDER_NAME
            )
        if parent_provider:
            attributes[Attrs.PROVIDER_NAME] = parent_provider
        elif self._default_provider_name:
            attributes[Attrs.PROVIDER_NAME] = self._default_provider_name

        self._start_span(
            run_id,
            name=f"{_OPERATION_EXECUTE_TOOL} {tool_name}"
            if tool_name
            else _OPERATION_EXECUTE_TOOL,
            operation=_OPERATION_EXECUTE_TOOL,
            kind=SpanKind.INTERNAL,
            parent_run_id=parent_run_id,
            attributes=attributes,
        )

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        record = self._spans.get(str(run_id))
        if not record:
            return
        if output is not None:
            record.span.set_attribute(
                Attrs.TOOL_CALL_RESULT,
                _serialise_tool_result(output, self._content_recording),
            )
        record.span.set_status(Status(StatusCode.OK))
        self._end_span(run_id)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        self._end_span(
            run_id,
            status=Status(StatusCode.ERROR, str(error)),
            error=error,
        )

    def on_agent_action(
        self,
        action: AgentAction,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        resolved_parent = self._resolve_parent_id(parent_run_id)
        record = self._spans.get(resolved_parent) if resolved_parent else None
        if record is not None:
            record.stash.setdefault("pending_actions", {})[str(run_id)] = {
                "tool": getattr(action, "tool", None),
                "tool_input": getattr(action, "tool_input", None),
                "log": getattr(action, "log", None),
            }
            last_chat = record.stash.get("last_chat_run")
            if last_chat:
                self._run_parent_override[str(run_id)] = last_chat

    def on_agent_finish(
        self,
        finish: AgentFinish,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        record = self._spans.get(str(run_id))
        if not record:
            return
        if getattr(finish, "return_values", None):
            record.span.set_attribute(
                Attrs.OUTPUT_MESSAGES, _as_json_attribute(finish.return_values)
            )
        record.span.set_status(Status(StatusCode.OK))
        self._end_span(run_id)

    def on_retriever_start(
        self,
        serialized: dict[str, Any],
        query: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        resolved_parent = self._resolve_parent_id(parent_run_id)
        attributes = {
            Attrs.OPERATION_NAME: _OPERATION_EXECUTE_TOOL,
            Attrs.TOOL_NAME: serialized.get("name", "retriever"),
            Attrs.TOOL_DESCRIPTION: serialized.get("description", "retriever"),
            Attrs.TOOL_TYPE: "retriever",
            Attrs.RETRIEVER_QUERY: query,
        }
        parent_provider = None
        if resolved_parent and resolved_parent in self._spans:
            parent_provider = self._spans[resolved_parent].attributes.get(
                Attrs.PROVIDER_NAME
            )
        if parent_provider:
            attributes[Attrs.PROVIDER_NAME] = parent_provider
        self._start_span(
            run_id,
            name=f"{_OPERATION_EXECUTE_TOOL} {serialized.get('name', 'retriever')}",
            operation=_OPERATION_EXECUTE_TOOL,
            kind=SpanKind.INTERNAL,
            parent_run_id=parent_run_id,
            attributes=attributes,
        )

    def on_retriever_end(
        self,
        documents: Sequence[Document],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        record = self._spans.get(str(run_id))
        if not record:
            return
        formatted = _format_documents(
            documents, record_content=self._content_recording
        )
        if formatted:
            record.span.set_attribute(Attrs.RETRIEVER_RESULTS, formatted)
        record.span.set_status(Status(StatusCode.OK))
        self._end_span(run_id)

    def on_retriever_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        self._end_span(
            run_id,
            status=Status(StatusCode.ERROR, str(error)),
            error=error,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _handle_model_start(
        self,
        *,
        serialized: dict[str, Any],
        inputs: Any,
        run_id: UUID,
        parent_run_id: Optional[UUID],
        metadata: Optional[dict[str, Any]],
        invocation_kwargs: dict[str, Any],
        is_chat_model: bool,
    ) -> None:
        invocation_params = invocation_kwargs.get("invocation_params") or {}
        model_name = _first_non_empty(
            invocation_params.get("model"),
            invocation_params.get("model_name"),
            (serialized.get("kwargs", {}) or {}).get("model"),
            (serialized.get("kwargs", {}) or {}).get("model_name"),
        )
        provider = _infer_provider_name(
            serialized, metadata, invocation_params
        )
        attributes: Dict[str, Any] = {
            Attrs.OPERATION_NAME: _OPERATION_CHAT
            if is_chat_model
            else _OPERATION_TEXT_COMPLETION,
        }
        if provider:
            attributes[Attrs.PROVIDER_NAME] = provider
        elif self._default_provider_name:
            attributes[Attrs.PROVIDER_NAME] = self._default_provider_name
        if model_name:
            attributes[Attrs.REQUEST_MODEL] = model_name

        for attr_name, key in [
            (Attrs.REQUEST_MAX_TOKENS, "max_tokens"),
            (Attrs.REQUEST_MAX_INPUT_TOKENS, "max_input_tokens"),
            (Attrs.REQUEST_MAX_OUTPUT_TOKENS, "max_output_tokens"),
            (Attrs.REQUEST_TEMPERATURE, "temperature"),
            (Attrs.REQUEST_TOP_P, "top_p"),
            (Attrs.REQUEST_TOP_K, "top_k"),
            (Attrs.REQUEST_FREQ_PENALTY, "frequency_penalty"),
            (Attrs.REQUEST_PRES_PENALTY, "presence_penalty"),
            (Attrs.REQUEST_CHOICE_COUNT, "n"),
            (Attrs.REQUEST_SEED, "seed"),
        ]:
            if key in invocation_params and invocation_params[key] is not None:
                attributes[attr_name] = invocation_params[key]

        if invocation_params.get("stop"):
            attributes[Attrs.REQUEST_STOP] = _as_json_attribute(
                invocation_params["stop"]
            )
        if invocation_params.get("response_format"):
            attributes[Attrs.REQUEST_ENCODING_FORMATS] = _as_json_attribute(
                invocation_params["response_format"]
            )

        formatted_input, system_instr = _prepare_messages(
            inputs,
            record_content=self._content_recording,
            include_roles={"user", "assistant", "tool"},
        )
        if formatted_input:
            attributes[Attrs.INPUT_MESSAGES] = formatted_input
        if system_instr:
            attributes[Attrs.SYSTEM_INSTRUCTIONS] = system_instr

        tool_definitions = invocation_params.get("tools")
        tool_definitions_json = None
        if tool_definitions:
            tool_definitions_json = _format_tool_definitions(tool_definitions)
            attributes[Attrs.TOOL_DEFINITIONS] = tool_definitions_json

        server_address = _infer_server_address(serialized, invocation_params)
        if server_address:
            attributes[Attrs.SERVER_ADDRESS] = server_address
        server_port = _infer_server_port(serialized, invocation_params)
        if server_port:
            attributes[Attrs.SERVER_PORT] = server_port

        service_tier = invocation_params.get("service_tier")
        if service_tier:
            attributes[Attrs.OPENAI_REQUEST_SERVICE_TIER] = service_tier

        operation_name = attributes[Attrs.OPERATION_NAME]
        span_name = (
            f"{operation_name} {model_name}" if model_name else operation_name
        )
        resolved_parent = self._resolve_parent_id(parent_run_id)
        self._start_span(
            run_id,
            name=span_name,
            operation=attributes[Attrs.OPERATION_NAME],
            kind=SpanKind.CLIENT,
            parent_run_id=parent_run_id,
            attributes=attributes,
        )
        if provider:
            self._update_parent_attribute(
                resolved_parent, Attrs.PROVIDER_NAME, provider
            )
        if formatted_input:
            self._update_parent_attribute(
                resolved_parent, Attrs.INPUT_MESSAGES, formatted_input
            )
        if system_instr:
            self._update_parent_attribute(
                resolved_parent, Attrs.SYSTEM_INSTRUCTIONS, system_instr
            )
        if tool_definitions_json and resolved_parent:
            self._update_parent_attribute(
                resolved_parent, Attrs.TOOL_DEFINITIONS, tool_definitions_json
            )
        chat_run_key = str(run_id)
        if resolved_parent and resolved_parent in self._spans:
            self._spans[resolved_parent].stash["last_chat_run"] = chat_run_key

    def _start_span(
        self,
        run_id: UUID,
        name: str,
        *,
        operation: str,
        kind: SpanKind,
        parent_run_id: Optional[UUID],
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        run_key = str(run_id)
        resolved_parent_key = self._resolve_parent_id(parent_run_id)
        parent_context = None
        parent_record = None
        if resolved_parent_key and resolved_parent_key in self._spans:
            parent_record = self._spans[resolved_parent_key]
            actual_parent_record = parent_record
            if (
                operation == _OPERATION_EXECUTE_TOOL
                and parent_record.operation == _OPERATION_INVOKE_AGENT
            ):
                last_chat = parent_record.stash.get("last_chat_run")
                if last_chat and last_chat in self._spans:
                    actual_parent_record = self._spans[last_chat]
                    resolved_parent_key = last_chat
            parent_context = set_span_in_context(actual_parent_record.span)
        elif resolved_parent_key is None:
            current_span = get_current_span()
            if current_span and current_span.get_span_context().is_valid:
                parent_context = set_span_in_context(current_span)

        span = self._tracer.start_span(
            name=name,
            context=parent_context,
            kind=kind,
            attributes=attributes or {},
        )
        self._spans[run_key] = _SpanRecord(
            span=span,
            operation=operation,
            parent_run_id=resolved_parent_key,
            attributes=attributes or {},
        )
        self._run_parent_override[run_key] = resolved_parent_key
        if resolved_parent_key and resolved_parent_key in self._spans:
            conv_id = self._spans[resolved_parent_key].attributes.get(
                Attrs.CONVERSATION_ID
            )
            if conv_id and Attrs.CONVERSATION_ID not in (attributes or {}):
                span.set_attribute(Attrs.CONVERSATION_ID, conv_id)
                self._spans[run_key].attributes[Attrs.CONVERSATION_ID] = (
                    conv_id
                )

    def _end_span(
        self,
        run_id: UUID,
        *,
        status: Optional[Status] = None,
        error: Optional[BaseException] = None,
    ) -> None:
        record = self._spans.pop(str(run_id), None)
        if not record:
            return
        if error and status is None:
            status = Status(StatusCode.ERROR, str(error))
            record.span.set_attribute(
                Attrs.ERROR_TYPE, error.__class__.__name__
            )
        if status:
            record.span.set_status(status)
        record.span.end()
        self._run_parent_override.pop(str(run_id), None)
