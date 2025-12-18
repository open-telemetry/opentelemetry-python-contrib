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


def _put(body: dict[str, Any], key: str, value: Any) -> None:
    """Set `body[key] = value` only when value is meaningfully present."""
    if value is None:
        return
    if isinstance(value, str) and not value:
        return
    body[key] = value


def _create_log_record(
    event_name: str, body: Mapping[str, Any] | None
) -> LogRecord:
    return LogRecord(
        event_name=event_name,
        attributes=_GEN_AI_SYSTEM_ATTRIBUTES,
        body=dict(body) if body else None,
    )


def _tool_item_id(value: Any) -> Any:
    return get_property_value(value, "call_id") or get_property_value(value, "id")


def _tool_item_base_body(
    value: Any, *, include_name: bool = False, include_type: bool = False
) -> _InputBody:
    body: _InputBody = {}
    _put(body, "id", _tool_item_id(value))
    if include_name:
        _put(body, "name", get_property_value(value, "name"))
    if include_type:
        _put(body, "type", get_property_value(value, "type"))
    return body


def responses_input_to_event(
    input_value: str | ResponseInputItemParam, capture_content: bool
) -> LogRecord | None:
    """Convert one Responses input item into a `gen_ai.<role>.input` `LogRecord`."""
    if isinstance(input_value, str):
        body = {"content": input_value} if capture_content else {}
        return _create_log_record(
            _EVENT_NAME_INPUT_FMT.format(role="user"),
            body,
        )

    item_type = get_property_value(input_value, "type")

    # Pattern-based routing avoids having to enumerate every OpenAI `type` string.
    handler: _InputHandler = _input_generic
    if isinstance(item_type, str) and item_type:
        if item_type == "message":
            handler = _input_message
        elif item_type == "function_call":
            handler = _input_function_tool_call
        elif item_type == "mcp_call":
            handler = _input_mcp_call
        elif item_type == "reasoning":
            handler = _input_reasoning
        elif item_type == "image_generation_call":
            handler = _input_image_generation_call
        elif (
            item_type.endswith("_call_output")
            or item_type.endswith("_output")
            or item_type.endswith("_response")
        ):
            handler = _input_tool_call_output
        elif item_type.endswith("_call") or item_type.startswith("mcp_"):
            handler = _input_tool_call

    role, body = handler(input_value, capture_content)
    return _create_log_record(_EVENT_NAME_INPUT_FMT.format(role=role), body)


def output_to_event(
    output: ResponseOutputItem, capture_content: bool
) -> LogRecord | None:
    """Convert one Responses output item into a `gen_ai.output` `LogRecord`."""
    body = _base_output_body(output)
    output_type = getattr(output, "type", None)
    handler = _OUTPUT_TYPE_HANDLERS.get(output_type, _output_unknown_body)
    body.update(handler(output, capture_content))
    return _create_log_record(_EVENT_NAME_OUTPUT, body)


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

    _put(body, "id", getattr(output, "id", None))

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
    _put(body, "id", call_id)
    _put(body, "name", getattr(output, "name", None))

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
    **{t: _output_tool_call_body for t in _TOOL_CALL_OUTPUT_TYPES},
}

def _input_message(
    input_value: Any, capture_content: bool
) -> _InputHandlerResult:
    role = get_property_value(input_value, "role") or "user"
    body: _InputBody = {}

    if capture_content:
        content_parts = get_property_value(input_value, "content")
        if content_parts:
            text_content = _extract_text_from_content_parts(content_parts)
            if text_content:
                body["content"] = text_content

    return role, body


def _input_mcp_call(
    input_value: Any, capture_content: bool
) -> _InputHandlerResult:
    body = _tool_item_base_body(input_value, include_name=True)

    if capture_content:
        _put(body, "arguments", get_property_value(input_value, "arguments"))

        output = get_property_value(input_value, "output")
        if output and isinstance(output, str):
            body["content"] = output

    return "tool", body


def _input_function_tool_call(
    input_value: Any, capture_content: bool
) -> _InputHandlerResult:
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


def _input_reasoning(
    input_value: Any, capture_content: bool
) -> _InputHandlerResult:
    body: _InputBody = {}
    _put(body, "id", get_property_value(input_value, "id"))

    if capture_content:
        summary = get_property_value(input_value, "summary")
        if summary:
            text_content = _extract_text_from_content_parts(summary)
            if text_content:
                body["content"] = text_content

    return "assistant", body


def _input_tool_call(
    input_value: Any, capture_content: bool
) -> _InputHandlerResult:
    body = _tool_item_base_body(input_value, include_name=True, include_type=True)

    if capture_content:
        _put(body, "query", get_property_value(input_value, "query"))
        _put(body, "arguments", get_property_value(input_value, "arguments"))
        _put(body, "content", get_property_value(input_value, "code"))

    return "assistant", body


def _input_tool_call_output(
    input_value: Any, capture_content: bool
) -> _InputHandlerResult:
    body = _tool_item_base_body(input_value)

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


def _input_image_generation_call(
    input_value: Any, capture_content: bool
) -> _InputHandlerResult:
    body: _InputBody = {}
    _put(body, "id", get_property_value(input_value, "id"))
    _put(body, "status", get_property_value(input_value, "status"))

    if capture_content:
        result = get_property_value(input_value, "result")
        if result:
            body["content"] = "[image_base64]"

    return "assistant", body


def _input_generic(
    input_value: Any, capture_content: bool
) -> _InputHandlerResult:
    role = get_property_value(input_value, "role") or "user"
    body: _InputBody = {}
    _put(body, "id", get_property_value(input_value, "id") or get_property_value(input_value, "call_id"))
    _put(body, "type", get_property_value(input_value, "type"))

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
    if not content_parts:
        return None

    if isinstance(content_parts, str):
        return content_parts

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
