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

"""Message, tool, and document serialization with content-redaction support.

Converts LangChain message objects into the compact JSON format expected by
OpenTelemetry GenAI semantic convention span attributes
(``gen_ai.input_messages``, ``gen_ai.output_messages``,
``gen_ai.system_instructions``, ``gen_ai.tool_definitions``, etc.).

Redaction behaviour
-------------------
When *record_content* is ``False``:

* Text content → ``"[redacted]"``
* Tool call arguments → ``"[redacted]"``
* Tool call results → ``"[redacted]"``
* Document page content → omitted (only metadata is kept)
* System instruction content → ``"[redacted]"``
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, cast

from opentelemetry.util.genai.utils import gen_ai_json_dumps

logger = logging.getLogger(__name__)

_REDACTED = "[redacted]"


def _as_dict(value: Any) -> Optional[Dict[str, Any]]:
    if isinstance(value, dict):
        return cast(Dict[str, Any], value)
    return None


def _as_sequence(value: Any) -> Optional[Sequence[Any]]:
    if isinstance(value, (list, tuple)):
        return cast(Sequence[Any], value)
    return None


# ---------------------------------------------------------------------------
# Role mapping
# ---------------------------------------------------------------------------

# LangChain message type → OpenTelemetry GenAI role
_ROLE_MAP: Dict[str, str] = {
    "human": "user",
    "HumanMessage": "user",
    "ai": "assistant",
    "AIMessage": "assistant",
    "AIMessageChunk": "assistant",
    "system": "system",
    "SystemMessage": "system",
    "tool": "tool",
    "ToolMessage": "tool",
    "function": "tool",
    "FunctionMessage": "tool",
    "chat": "user",
    "ChatMessage": "user",
}


def message_role(message: Any) -> str:
    """Map a LangChain message to its GenAI role.

    Handles ``BaseMessage`` subclasses (via ``.type``), plain dicts
    (via ``"role"`` or ``"type"`` keys), and falls back to ``"user"``.
    """
    # BaseMessage subclass
    msg_type = getattr(message, "type", None)
    if isinstance(msg_type, str):
        mapped = _ROLE_MAP.get(msg_type)
        if mapped is not None:
            return mapped

    # Dict-like message
    message_dict = _as_dict(message)
    if message_dict is not None:
        for key in ("role", "type"):
            value = message_dict.get(key)
            if isinstance(value, str):
                mapped = _ROLE_MAP.get(value)
                if mapped is not None:
                    return mapped
                # If the value itself is already a canonical role, accept it
                if value in ("user", "assistant", "system", "tool"):
                    return value

    # Class-name fallback
    cls_name = type(message).__name__
    mapped = _ROLE_MAP.get(cls_name)
    if mapped is not None:
        return mapped

    return "user"


# ---------------------------------------------------------------------------
# Content extraction
# ---------------------------------------------------------------------------


def message_content(message: Any) -> Optional[str]:
    """Extract text content from a LangChain message.

    Returns ``None`` when no text content is available.  Multi-part content
    lists are concatenated with newlines.
    """
    raw: Any = getattr(message, "content", None)
    message_dict = _as_dict(message)
    if raw is None and message_dict is not None:
        raw = message_dict.get("content")

    if raw is None:
        return None

    if isinstance(raw, str):
        return raw if raw else None

    # Multi-part content (list of strings / dicts with "text" key)
    raw_parts = _as_sequence(raw)
    if raw_parts is not None:
        parts: list[str] = []
        for item in raw_parts:
            if isinstance(item, str):
                parts.append(item)
            else:
                item_dict = _as_dict(item)
                if item_dict is None:
                    continue
                text_value = item_dict.get("text")
                if isinstance(text_value, str) and text_value:
                    parts.append(text_value)
        return "\n".join(parts) if parts else None

    return str(raw) if raw else None


# ---------------------------------------------------------------------------
# Tool-call extraction
# ---------------------------------------------------------------------------


def extract_tool_calls(message: Any) -> List[Dict[str, Any]]:
    """Extract tool calls from an ``AIMessage`` or dict.

    Returns a (possibly empty) list of dicts, each with keys
    ``"id"``, ``"name"``, and ``"arguments"``.
    """
    tool_calls: Any = getattr(message, "tool_calls", None)
    message_dict = _as_dict(message)
    if tool_calls is None and message_dict is not None:
        tool_calls = message_dict.get("tool_calls")

    tool_call_items = _as_sequence(tool_calls)
    if not tool_call_items:
        return []

    result: List[Dict[str, Any]] = []
    for tc in tool_call_items:
        entry: Dict[str, Any] = {}

        tc_dict = _as_dict(tc)
        if tc_dict is not None:
            entry["id"] = tc_dict.get("id") or ""
            entry["name"] = tc_dict.get("name") or ""
            entry["arguments"] = tc_dict.get("args") or tc_dict.get(
                "arguments"
            )
        else:
            entry["id"] = getattr(tc, "id", "") or ""
            entry["name"] = getattr(tc, "name", "") or ""
            entry["arguments"] = getattr(tc, "args", None) or getattr(
                tc, "arguments", None
            )

        result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _format_tool_call_part(
    tc: Dict[str, Any], record_content: bool
) -> Dict[str, Any]:
    """Build a serialised tool-call part dict."""
    part: Dict[str, Any] = {"type": "tool_call"}
    if tc.get("id"):
        part["id"] = tc["id"]
    if tc.get("name"):
        part["name"] = tc["name"]

    args = tc.get("arguments")
    if record_content:
        if args is not None:
            part["arguments"] = args
    else:
        part["arguments"] = _REDACTED

    return part


def _format_tool_response_part(
    message: Any, record_content: bool
) -> Dict[str, Any]:
    """Build a serialised tool-call-response part dict."""
    part: Dict[str, Any] = {"type": "tool_call_response"}

    tool_call_id = getattr(message, "tool_call_id", None)
    message_dict = _as_dict(message)
    if tool_call_id is None and message_dict is not None:
        tool_call_id = message_dict.get("tool_call_id")
    if tool_call_id:
        part["id"] = tool_call_id

    if record_content:
        content = message_content(message)
        if content is not None:
            part["result"] = content
    else:
        part["result"] = _REDACTED

    return part


def _format_text_parts(
    message: Any, record_content: bool
) -> List[Dict[str, Any]]:
    """Build text-content part dicts for a message."""
    content = message_content(message)
    if content is None:
        return []

    return [
        {
            "type": "text",
            "content": content if record_content else _REDACTED,
        }
    ]


def _format_single_message(
    message: Any, record_content: bool
) -> Dict[str, Any]:
    """Serialise one LangChain message into the GenAI convention dict."""
    role = message_role(message)
    parts: List[Dict[str, Any]] = []

    if role == "assistant":
        # Tool calls first, then text
        for tc in extract_tool_calls(message):
            parts.append(_format_tool_call_part(tc, record_content))
        parts.extend(_format_text_parts(message, record_content))

    elif role == "tool":
        parts.append(_format_tool_response_part(message, record_content))

    else:
        # user, system, or any other role
        parts.extend(_format_text_parts(message, record_content))

    result: Dict[str, Any] = {"role": role}
    if parts:
        result["parts"] = parts
    return result


def _flatten_messages(raw_messages: Any) -> List[Any]:
    """Accept messages in multiple shapes and return a flat list.

    LangChain callbacks may pass ``list[list[BaseMessage]]`` (grouped by
    prompt) or a simple ``list[BaseMessage]``.
    """
    if not raw_messages:
        return []

    raw_sequence = _as_sequence(raw_messages)
    if raw_sequence is None:
        return [raw_messages]

    # Check for nested lists (list[list[BaseMessage]])
    flat: list[Any] = []
    for item in raw_sequence:
        nested_items = _as_sequence(item)
        if nested_items is not None:
            flat.extend(nested_items)
        else:
            flat.append(item)
    return flat


# ---------------------------------------------------------------------------
# Public API – prepare_messages
# ---------------------------------------------------------------------------


def prepare_messages(
    raw_messages: Any,
    *,
    record_content: bool,
    include_roles: Optional[Set[str]] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Serialise LangChain messages to JSON strings for span attributes.

    Returns ``(formatted_json, system_instructions_json)``:

    * *formatted_json* – JSON array of non-system messages, suitable for
      ``gen_ai.input_messages`` / ``gen_ai.output_messages``.
    * *system_instructions_json* – JSON array of system-message *parts*
      only, suitable for ``gen_ai.system_instructions``.

    Either value may be ``None`` when no messages of that kind exist.

    Parameters
    ----------
    raw_messages:
        Messages as received from LangChain callbacks.  May be a flat list or
        a nested ``list[list[BaseMessage]]``.
    record_content:
        When ``False``, text payloads and tool arguments/results are replaced
        with ``"[redacted]"``.
    include_roles:
        Optional filter.  When provided, only messages whose mapped role is in
        the set are included.
    """
    messages = _flatten_messages(raw_messages)
    if not messages:
        return None, None

    formatted: List[Dict[str, Any]] = []
    system_parts: List[Dict[str, Any]] = []

    for msg in messages:
        role = message_role(msg)

        if include_roles is not None and role not in include_roles:
            continue

        if role == "system":
            # System messages contribute to system_instructions only
            content = message_content(msg)
            if content is not None:
                system_parts.append(
                    {
                        "type": "text",
                        "content": content if record_content else _REDACTED,
                    }
                )
            continue

        formatted.append(_format_single_message(msg, record_content))

    formatted_json = gen_ai_json_dumps(formatted) if formatted else None
    system_json = gen_ai_json_dumps(system_parts) if system_parts else None

    return formatted_json, system_json


# ---------------------------------------------------------------------------
# Document formatting (for retrievers)
# ---------------------------------------------------------------------------


def format_documents(
    documents: Optional[Sequence[Any]], *, record_content: bool
) -> Optional[str]:
    """Format retrieved documents as a JSON string for span attributes.

    Each document is serialised as a dict with optional ``page_content``
    (when *record_content* is ``True``) and ``metadata`` fields.

    Returns ``None`` when *documents* is empty or ``None``.
    """
    if not documents:
        return None

    result: List[Dict[str, Any]] = []
    for doc in documents:
        entry: Dict[str, Any] = {}
        doc_dict = _as_dict(doc)

        # page_content
        page_content = getattr(doc, "page_content", None)
        if page_content is None and doc_dict is not None:
            page_content = doc_dict.get("page_content")

        if record_content and page_content is not None:
            entry["page_content"] = str(page_content)

        # metadata
        metadata = getattr(doc, "metadata", None)
        if metadata is None and doc_dict is not None:
            metadata = doc_dict.get("metadata")
        if metadata:
            entry["metadata"] = metadata

        if entry:
            result.append(entry)

    return gen_ai_json_dumps(result) if result else None


# ---------------------------------------------------------------------------
# Tool result serialization
# ---------------------------------------------------------------------------


def serialize_tool_result(output: Any, record_content: bool) -> str:
    """Serialise a tool result for span attributes.

    When *record_content* is ``False`` the literal ``"[redacted]"`` is
    returned.
    """
    if not record_content:
        return _REDACTED

    if isinstance(output, str):
        return output

    # Try common attribute shapes produced by LangChain tools
    content = getattr(output, "content", None)
    if content is not None:
        return str(content)

    output_dict = _as_dict(output)
    if output_dict is not None:
        content = output_dict.get("content") or output_dict.get("output")
        if content is not None:
            return str(content)

    # Fallback: JSON-encode arbitrary values
    try:
        return gen_ai_json_dumps(output)
    except (TypeError, ValueError):
        return str(output)


# ---------------------------------------------------------------------------
# Tool definitions formatting
# ---------------------------------------------------------------------------


def format_tool_definitions(definitions: Optional[Any]) -> Optional[str]:
    """Format tool definitions for ``gen_ai.tool_definitions`` span attribute.

    Accepts a list of LangChain tool objects, dicts, or any mix thereof and
    returns a compact JSON string.  Returns ``None`` when *definitions* is
    empty or ``None``.
    """
    if not definitions:
        return None

    definition_items = _as_sequence(definitions)
    if definition_items is None:
        definition_items = [definitions]

    result: List[Dict[str, Any]] = []
    for defn in definition_items:
        entry: Dict[str, Any] = {}
        defn_dict = _as_dict(defn)

        if defn_dict is not None:
            # Already a dict – keep recognised keys
            if "name" in defn_dict:
                entry["name"] = defn_dict["name"]
            if "description" in defn_dict:
                entry["description"] = defn_dict["description"]
            if "parameters" in defn_dict:
                entry["parameters"] = defn_dict["parameters"]

            func_dict = _as_dict(defn_dict.get("function"))
            if func_dict is not None:
                func_name = func_dict.get("name")
                if "name" not in entry and func_name is not None:
                    entry["name"] = func_name
                func_description = func_dict.get("description")
                if "description" not in entry and func_description is not None:
                    entry["description"] = func_description
                func_parameters = func_dict.get("parameters")
                if "parameters" not in entry and func_parameters is not None:
                    entry["parameters"] = func_parameters

            entry.setdefault("type", defn_dict.get("type", "function"))
        else:
            # Object with attributes (e.g. a LangChain BaseTool)
            name = getattr(defn, "name", None)
            if name is not None:
                entry["name"] = str(name)

            description = getattr(defn, "description", None)
            if description is not None:
                entry["description"] = str(description)

            args_schema = getattr(defn, "args_schema", None)
            if args_schema is not None:
                schema_method = getattr(args_schema, "schema", None)
                if callable(schema_method):
                    try:
                        entry["parameters"] = schema_method()
                    except Exception:  # noqa: BLE001
                        pass

            entry.setdefault("type", "function")

        if entry:
            result.append(entry)

    return gen_ai_json_dumps(result) if result else None


# ---------------------------------------------------------------------------
# JSON helper
# ---------------------------------------------------------------------------


def as_json_attribute(value: Any) -> str:
    """Return a JSON string suitable for OpenTelemetry string attributes.

    Uses the same compact encoder (no whitespace, base64 for bytes) as
    the rest of the GenAI instrumentation.
    """
    return gen_ai_json_dumps(value)
