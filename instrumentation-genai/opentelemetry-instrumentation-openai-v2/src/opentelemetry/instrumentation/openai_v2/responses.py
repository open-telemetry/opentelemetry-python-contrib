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

"""
OpenAI Responses API -> OpenTelemetry GenAI log events.

We emit structured `LogRecord` bodies that are a **small, stable subset** of the
OpenTelemetry GenAI input/output message schemas:

- Input messages schema: `https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-input-messages.json`
- Output messages schema: `https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-output-messages.json`

Outcome of this module:
- `responses_input_to_event(...)` produces `gen_ai.<role>.input` events.
- `output_to_event(...)` produces `gen_ai.output` events.

We keep bodies intentionally minimal and content-gated (`capture_content`) to
avoid leaking sensitive user data.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from openai.types.responses import ResponseInputItemParam, ResponseOutputItem

from opentelemetry._logs import LogRecord
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)

from .utils import get_property_value

_EVENT_NAME_OUTPUT = "gen_ai.output"
_EVENT_NAME_INPUT_FMT = "gen_ai.{role}.input"
_GEN_AI_SYSTEM_ATTRIBUTES = {
    GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value
}

_TOOL_CALL_OUTPUT_TYPES = frozenset(
    {
        "file_search_call",
        "web_search_call",
        "computer_call",
        "code_interpreter_call",
        "mcp_call",
        "image_generation_call",
    }
)

_OutputBodyBuilder = Callable[[ResponseOutputItem, bool], dict[str, Any]]
_InputBody = dict[str, Any]
_InputHandlerResult = tuple[str, _InputBody]
_InputHandler = Callable[[Any, bool], _InputHandlerResult]


def _select_input_handler(item_type: Any) -> _InputHandler:
    """
    Select an input handler for a Responses input item.

    We avoid enumerating every OpenAI `type` value. Instead we:
    - Handle a few semantically special types explicitly.
    - Route tool requests/results by naming patterns (`*_call`, `*_call_output`, etc.).
    - Fall back to `_handle_generic_input` for unknown/future types.
    """
    handler: _InputHandler = _handle_generic_input
    if not isinstance(item_type, str) or not item_type:
        return handler

    # Explicit "special" types where we want stable, structured bodies.
    if item_type == "message":
        handler = _handle_message_input
    elif item_type == "function_call":
        handler = _handle_function_tool_call
    elif item_type == "mcp_call":
        handler = _handle_mcp_call
    elif item_type == "reasoning":
        handler = _handle_reasoning_item
    elif item_type == "image_generation_call":
        handler = _handle_image_generation_call
    # Tool call results sent back to the model.
    elif (
        item_type.endswith("_call_output")
        or item_type.endswith("_output")
        or item_type.endswith("_response")
    ):
        handler = _handle_tool_call_output_input
    # Tool calls requested by the model.
    elif item_type.endswith("_call") or item_type.startswith("mcp_"):
        handler = _handle_tool_call_input

    return handler


def _create_log_record(
    event_name: str, body: Mapping[str, Any] | None
) -> LogRecord:
    return LogRecord(
        event_name=event_name,
        attributes=_GEN_AI_SYSTEM_ATTRIBUTES,
        body=dict(body) if body else None,
    )


def responses_input_to_event(
    input_value: str | ResponseInputItemParam, capture_content: bool
) -> LogRecord | None:
    """
    Convert a single Responses API input item to an input log event.

    Flow:
    - Determine the item "type"
    - Dispatch to a handler that extracts a minimal body + role
    - Build a `gen_ai.<role>.input` `LogRecord`
    """
    if isinstance(input_value, str):
        body = {"content": input_value} if capture_content else {}
        return _create_log_record(
            _EVENT_NAME_INPUT_FMT.format(role="user"),
            body,
        )

    item_type = get_property_value(input_value, "type")
    handler = _select_input_handler(item_type)
    role, body = handler(input_value, capture_content)
    return _create_log_record(_EVENT_NAME_INPUT_FMT.format(role=role), body)


def _base_output_body(output: ResponseOutputItem) -> dict[str, Any]:
    body: dict[str, Any] = {}

    index = getattr(output, "index", None)
    if index is not None:
        body["index"] = index

    status = getattr(output, "status", None)
    if status:
        body["finish_reason"] = status

    return body


def _output_message_body(
    output: ResponseOutputItem, capture_content: bool
) -> dict[str, Any]:
    role = getattr(output, "role", None) or "assistant"
    content_parts = getattr(output, "content", [])
    message: dict[str, Any] = {"role": role}

    if capture_content and content_parts:
        text_content = _extract_text_from_content_parts(content_parts)
        if text_content:
            message["content"] = text_content

    return {"message": message}


def _output_function_call_body(
    output: ResponseOutputItem, capture_content: bool
) -> dict[str, Any]:
    tool_call: dict[str, Any] = {
        "id": getattr(output, "call_id", None),
        "type": "function",
        "function": {"name": getattr(output, "name", None)},
    }
    if capture_content:
        arguments = getattr(output, "arguments", None)
        if arguments:
            tool_call["function"]["arguments"] = arguments

    return {"message": {"role": "assistant", "tool_calls": [tool_call]}}


def _output_reasoning_body(
    output: ResponseOutputItem, capture_content: bool
) -> dict[str, Any]:
    body: dict[str, Any] = {"type": "reasoning"}

    item_id = getattr(output, "id", None)
    if item_id:
        body["id"] = item_id

    if capture_content:
        summary = getattr(output, "summary", None)
        if summary:
            body["content"] = _extract_text_from_content_parts(summary)

    return body


def _output_tool_call_body(
    output: ResponseOutputItem,
    capture_content: bool,  # noqa: ARG001
) -> dict[str, Any]:
    output_type = getattr(output, "type", None)
    body: dict[str, Any] = {"type": output_type}

    call_id = getattr(output, "call_id", None) or getattr(output, "id", None)
    if call_id:
        body["id"] = call_id

    name = getattr(output, "name", None)
    if name:
        body["name"] = name

    return body


def _output_unknown_body(
    output: ResponseOutputItem,
    capture_content: bool,  # noqa: ARG001
) -> dict[str, Any]:
    return {}


_OUTPUT_TYPE_HANDLERS: dict[Any, _OutputBodyBuilder] = {
    "message": _output_message_body,
    "function_call": _output_function_call_body,
    "reasoning": _output_reasoning_body,
}


def output_to_event(
    output: ResponseOutputItem, capture_content: bool
) -> LogRecord | None:
    """
    Convert a single Responses API output item to an output log event.

    Flow:
    - Extract common output fields (`index`, `finish_reason`)
    - Dispatch by `output.type` to a small body builder
    - Build a `gen_ai.output` `LogRecord`
    """
    body = _base_output_body(output)
    output_type = getattr(output, "type", None)
    if output_type in _TOOL_CALL_OUTPUT_TYPES:
        body.update(_output_tool_call_body(output, capture_content))
    else:
        handler = _OUTPUT_TYPE_HANDLERS.get(output_type, _output_unknown_body)
        body.update(handler(output, capture_content))

    return _create_log_record(_EVENT_NAME_OUTPUT, body)


def _handle_message_input(
    input_value: Any, capture_content: bool
) -> _InputHandlerResult:
    """Message: { content: ContentPart[], role, type: "message" }"""
    role = get_property_value(input_value, "role") or "user"
    body: _InputBody = {}

    if capture_content:
        content_parts = get_property_value(input_value, "content")
        if content_parts:
            text_content = _extract_text_from_content_parts(content_parts)
            if text_content:
                body["content"] = text_content

    return role, body


def _handle_mcp_call(
    input_value: Any, capture_content: bool
) -> _InputHandlerResult:
    """McpCall: { id, name, arguments, output?, type: "mcp_call" }"""
    body: _InputBody = {}

    item_id = get_property_value(input_value, "id")
    if item_id:
        body["id"] = item_id

    name = get_property_value(input_value, "name")
    if name:
        body["name"] = name

    if capture_content:
        arguments = get_property_value(input_value, "arguments")
        if arguments:
            body["arguments"] = arguments

        output = get_property_value(input_value, "output")
        if output and isinstance(output, str):
            body["content"] = output

    return "tool", body


def _handle_function_tool_call(
    input_value: Any, capture_content: bool
) -> _InputHandlerResult:
    """FunctionToolCall: { call_id, name, arguments, type: "function_call" }"""
    body: _InputBody = {}

    call_id = get_property_value(input_value, "call_id")
    name = get_property_value(input_value, "name")

    tool_call = {"type": "function", "function": {}}
    if call_id:
        tool_call["id"] = call_id
    if name:
        tool_call["function"]["name"] = name

    if capture_content:
        arguments = get_property_value(input_value, "arguments")
        if arguments:
            tool_call["function"]["arguments"] = arguments

    body["tool_calls"] = [tool_call]

    return "assistant", body


def _handle_reasoning_item(
    input_value: Any, capture_content: bool
) -> _InputHandlerResult:
    """ReasoningItem: { id, summary: ContentPart[], type: "reasoning" }"""
    body: _InputBody = {}

    item_id = get_property_value(input_value, "id")
    if item_id:
        body["id"] = item_id

    if capture_content:
        summary = get_property_value(input_value, "summary")
        if summary:
            text_content = _extract_text_from_content_parts(summary)
            if text_content:
                body["content"] = text_content

    return "assistant", body


def _handle_tool_call_input(
    input_value: Any, capture_content: bool
) -> _InputHandlerResult:
    """Generic handler for tool call inputs (file_search, web_search, computer, code_interpreter, etc.)."""
    body: _InputBody = {}

    call_id = get_property_value(input_value, "call_id") or get_property_value(
        input_value, "id"
    )
    if call_id:
        body["id"] = call_id

    name = get_property_value(input_value, "name")
    if name:
        body["name"] = name

    item_type = get_property_value(input_value, "type")
    if item_type:
        body["type"] = item_type

    if capture_content:
        query = get_property_value(input_value, "query")
        if query:
            body["query"] = query

        arguments = get_property_value(input_value, "arguments")
        if arguments:
            body["arguments"] = arguments

        code = get_property_value(input_value, "code")
        if code:
            body["content"] = code

    return "assistant", body


def _handle_tool_call_output_input(
    input_value: Any, capture_content: bool
) -> _InputHandlerResult:
    """Generic handler for tool call output inputs (tool results sent back to the model)."""
    body: _InputBody = {}

    call_id = get_property_value(input_value, "call_id") or get_property_value(
        input_value, "id"
    )
    if call_id:
        body["id"] = call_id

    if capture_content:
        output = get_property_value(input_value, "output")
        if output:
            if isinstance(output, str):
                body["content"] = output
            elif isinstance(output, list):
                text_content = _extract_text_from_content_parts(output)
                if text_content:
                    body["content"] = text_content
            elif (
                isinstance(output, dict) and output.get("type") == "screenshot"
            ):
                body["content"] = "[screenshot]"

    return "tool", body


def _handle_image_generation_call(
    input_value: Any, capture_content: bool
) -> _InputHandlerResult:
    """ImageGenerationCall: { id, result, status, type: "image_generation_call" }"""
    body: _InputBody = {}

    item_id = get_property_value(input_value, "id")
    if item_id:
        body["id"] = item_id

    status = get_property_value(input_value, "status")
    if status:
        body["status"] = status

    if capture_content:
        result = get_property_value(input_value, "result")
        if result:
            body["content"] = "[image_base64]"

    return "assistant", body


def _handle_generic_input(
    input_value: Any, capture_content: bool
) -> _InputHandlerResult:
    """Fallback handler for unknown input types."""
    role = get_property_value(input_value, "role") or "user"
    body: _InputBody = {}

    item_id = get_property_value(input_value, "id") or get_property_value(
        input_value, "call_id"
    )
    if item_id:
        body["id"] = item_id

    item_type = get_property_value(input_value, "type")
    if item_type:
        body["type"] = item_type

    if capture_content:
        content = get_property_value(input_value, "content")
        if content:
            if isinstance(content, str):
                body["content"] = content
            elif isinstance(content, list):
                text_content = _extract_text_from_content_parts(content)
                if text_content:
                    body["content"] = text_content

    return role, body


def _extract_text_from_content_parts(content_parts) -> str | None:
    """Extract text content from a list of content parts."""
    if not content_parts:
        return None

    if isinstance(content_parts, str):
        return content_parts

    # Handle non-iterable types gracefully
    if not isinstance(content_parts, (list, tuple)):
        return None

    text_content = []
    for part in content_parts:
        part_type = get_property_value(part, "type")
        text = None

        if part_type in ("input_text", "output_text", "text"):
            text = get_property_value(part, "text")
        elif part_type == "refusal":
            text = get_property_value(part, "refusal")

        if text is None:
            text = get_property_value(part, "text") or get_property_value(
                part, "content"
            )

        if text and isinstance(text, str):
            text_content.append(text)

    return "\n".join(text_content) if text_content else None
