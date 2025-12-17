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

"""Resilience tests for Responses input/output conversion helpers."""

from dataclasses import dataclass
from typing import Any, Optional, cast

import pytest
from openai.types.responses import ResponseOutputItem
from openai.types.responses import ResponseInputItemParam

from opentelemetry.instrumentation.openai_v2.responses import (
    output_to_event,
    responses_input_to_event,
)
from opentelemetry.instrumentation.openai_v2.responses_patch import (
    _log_responses_inputs,
)
from opentelemetry._logs import Logger


@dataclass
class OutputItemMock:
    type: str
    id: Optional[str] = None
    call_id: Optional[str] = None
    name: Optional[str] = None
    status: Optional[str] = None
    index: Optional[int] = None
    role: Optional[str] = None
    content: Any = None
    arguments: Optional[str] = None


class _CapturingLogger:
    def __init__(self) -> None:
        self.emitted: list[Any] = []

    def emit(self, record: Any) -> None:
        self.emitted.append(record)


def _as_output_item(value: Any) -> ResponseOutputItem:
    # These tests intentionally pass minimal "shape-only" objects to exercise
    # resilience for new/unknown output types. Cast keeps type-checkers happy
    # without weakening the production signature.
    return cast(ResponseOutputItem, value)


@pytest.mark.parametrize(
    "input_data",
    [
        # Message types
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Hello"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Hi"}],
        },
        {"type": "message", "role": "system", "content": "System prompt"},
        # Tool call outputs (user providing results back to model)
        {
            "type": "function_call_output",
            "call_id": "call_123",
            "output": "result",
        },
        {
            "type": "computer_call_output",
            "call_id": "call_123",
            "output": {"type": "screenshot"},
        },
        {
            "type": "shell_call_output",
            "call_id": "call_123",
            "output": [{"text": "output"}],
        },
        {
            "type": "local_shell_call_output",
            "id": "id_123",
            "output": "shell output",
        },
        {
            "type": "apply_patch_call_output",
            "call_id": "call_123",
            "output": "patched",
        },
        # Tool calls (model requesting actions)
        {
            "type": "function_call",
            "call_id": "call_123",
            "name": "get_weather",
            "arguments": "{}",
        },
        {"type": "file_search_call", "id": "id_123", "query": "search term"},
        {"type": "web_search_call", "id": "id_123", "query": "search term"},
        {"type": "computer_call", "id": "id_123", "arguments": "{}"},
        {
            "type": "code_interpreter_call",
            "id": "id_123",
            "code": "print('hello')",
        },
        {"type": "local_shell_call", "id": "id_123", "arguments": "ls -la"},
        {"type": "shell_call", "id": "id_123", "arguments": "ls"},
        {
            "type": "apply_patch_call",
            "id": "id_123",
            "arguments": "patch data",
        },
        # MCP (Model Context Protocol)
        {
            "type": "mcp_call",
            "id": "id_123",
            "name": "tool_name",
            "arguments": {},
        },
        {"type": "mcp_list_tools", "id": "id_123"},
        {"type": "mcp_approval_request", "id": "id_123"},
        {
            "type": "mcp_approval_response",
            "id": "id_123",
            "output": "approved",
        },
        # Other
        {
            "type": "reasoning",
            "id": "id_123",
            "summary": [{"type": "text", "text": "thinking..."}],
        },
        {
            "type": "image_generation_call",
            "id": "id_123",
            "status": "completed",
            "result": "base64data",
        },
        {"type": "item_reference", "id": "item_123"},
        {"type": "compaction", "id": "id_123"},
    ],
)
def test_input_type_handler_does_not_crash(input_data):
    """Each known input type should be processed without exceptions."""
    assert (
        responses_input_to_event(
            cast(ResponseInputItemParam, input_data), capture_content=True
        )
        is not None
    )
    assert (
        responses_input_to_event(
            cast(ResponseInputItemParam, input_data), capture_content=False
        )
        is not None
    )


def test_string_input_does_not_crash():
    assert (
        responses_input_to_event("Hello world", capture_content=True)
        is not None
    )
    assert (
        responses_input_to_event("Hello world", capture_content=False)
        is not None
    )


def test_responses_create_input_none_is_noop_for_logging():
    logger = _CapturingLogger()

    _log_responses_inputs(cast(Logger, logger), {"input": None}, capture_content=True)
    _log_responses_inputs(cast(Logger, logger), {"input": None}, capture_content=False)

    assert not logger.emitted


def test_responses_create_input_omitted_is_noop_for_logging():
    logger = _CapturingLogger()

    _log_responses_inputs(cast(Logger, logger), {}, capture_content=True)
    _log_responses_inputs(cast(Logger, logger), {}, capture_content=False)

    assert not logger.emitted


@pytest.mark.parametrize(
    "unexpected_input",
    [
        # Unknown types
        {"type": "unknown_future_type", "id": "id_123", "data": "some data"},
        {"type": "new_tool_call", "call_id": "call_123"},
        {"type": "custom_extension", "payload": {"nested": "data"}},
        # Missing type field
        {"role": "user", "content": "no type field"},
        {"id": "id_123", "data": "no type"},
        # Empty/minimal objects
        {},
        {"type": None},
        {"type": ""},
        # Unexpected data structures
        {"type": "message", "content": None},
        {"type": "message", "content": 12345},
        {"type": "function_call", "arguments": {"nested": "object"}},
        {"type": "message", "role": None, "content": []},
    ],
)
def test_unexpected_input_does_not_crash(unexpected_input):
    # Should not raise
    responses_input_to_event(
        cast(ResponseInputItemParam, unexpected_input), capture_content=True
    )


def test_deeply_nested_content_does_not_crash():
    nested_input: Any = {
        "type": "message",
        "role": "user",
        "content": [
            {"type": "input_text", "text": "text1"},
            {"type": "input_text", "text": "text2"},
            {"type": "image", "url": "http://example.com/img.jpg"},
            {
                "type": "unknown_part",
                "data": {"deeply": {"nested": {"object": True}}},
            },
        ],
    }
    assert (
        responses_input_to_event(
            cast(ResponseInputItemParam, nested_input), capture_content=True
        )
        is not None
    )


def test_future_union_types_are_best_effort():
    """
    Guardrail: if OpenAI adds new union members/types, we should still emit a
    best-effort event (and never crash) without needing to update a static list
    of known type strings.
    """
    # New tool call request (model -> tool): routed by `*_call`
    future_call = {
        "type": "future_provider_tool_call",
        "id": "id_123",
        "name": "some_tool",
        "arguments": {"x": 1},
    }
    event = responses_input_to_event(
        cast(ResponseInputItemParam, future_call), capture_content=True
    )
    assert event is not None
    assert event.event_name == "gen_ai.assistant.input"
    body: Any = event.body
    assert body and body.get("type") == "future_provider_tool_call"

    # New tool call output (tool -> model): routed by `*_call_output`
    future_call_output = {
        "type": "future_provider_tool_call_output",
        "call_id": "call_123",
        "output": "ok",
    }
    event = responses_input_to_event(
        cast(ResponseInputItemParam, future_call_output), capture_content=True
    )
    assert event is not None
    assert event.event_name == "gen_ai.tool.input"
    body = event.body
    assert body and body.get("id") == "call_123"

    # Another output naming style: routed by `*_output`
    future_output_alt = {
        "type": "future_provider_tool_output",
        "id": "id_999",
        "output": [{"type": "text", "text": "ok"}],
    }
    event = responses_input_to_event(
        cast(ResponseInputItemParam, future_output_alt), capture_content=True
    )
    assert event is not None
    assert event.event_name == "gen_ai.tool.input"


def test_message_output_does_not_crash():
    class ContentPart:
        type = "output_text"
        text = "Hello!"

    class MockOutput:
        type = "message"
        role = "assistant"
        status = "completed"
        content = [ContentPart()]
        index = 0

    assert (
        output_to_event(_as_output_item(MockOutput()), capture_content=True)
        is not None
    )
    assert (
        output_to_event(_as_output_item(MockOutput()), capture_content=False)
        is not None
    )


def test_function_call_output_does_not_crash():
    class MockOutput:
        type = "function_call"
        call_id = "call_123"
        name = "get_weather"
        arguments = '{"location": "Tokyo"}'
        status = "completed"
        index = 0

    assert (
        output_to_event(_as_output_item(MockOutput()), capture_content=True)
        is not None
    )


def test_reasoning_output_does_not_crash():
    class Part:
        type = "text"
        text = "Step 1: ..."

    class MockOutput:
        type = "reasoning"
        id = "reasoning_123"
        status = "completed"
        summary = [Part()]

    assert (
        output_to_event(_as_output_item(MockOutput()), capture_content=True)
        is not None
    )


@pytest.mark.parametrize(
    "output_type",
    [
        "file_search_call",
        "web_search_call",
        "computer_call",
        "code_interpreter_call",
        "mcp_call",
        "image_generation_call",
    ],
)
def test_tool_call_outputs_do_not_crash(output_type):
    mock = OutputItemMock(
        type=output_type,
        id="id_123",
        call_id="call_123",
        name="tool_name",
        status="completed",
    )
    assert output_to_event(_as_output_item(mock), capture_content=True) is not None


def test_unknown_output_type_does_not_crash():
    class MockOutput:
        type = "unknown_future_output_type"
        id = "id_123"
        status = "completed"

    assert (
        output_to_event(_as_output_item(MockOutput()), capture_content=True)
        is not None
    )


def test_minimal_output_does_not_crash():
    class MockOutput:
        type = "message"

    assert (
        output_to_event(_as_output_item(MockOutput()), capture_content=True)
        is not None
    )


def test_output_with_none_values_does_not_crash():
    class MockOutput:
        type = "message"
        role = None
        status = None
        content = None
        index = None

    assert (
        output_to_event(_as_output_item(MockOutput()), capture_content=True)
        is not None
    )
