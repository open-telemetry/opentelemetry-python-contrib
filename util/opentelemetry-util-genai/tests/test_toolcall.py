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

"""Tests for ToolCallRequest and ToolCall types"""

import pytest

from opentelemetry.util.genai.types import (
    InputMessage,
    OutputMessage,
    ToolCall,
    ToolCallRequest,
)


def test_toolcallrequest_basic():
    """Test basic ToolCallRequest instantiation"""
    tcr = ToolCallRequest(arguments=None, name="get_weather", id=None)
    assert tcr.name == "get_weather"
    assert tcr.type == "tool_call"
    assert tcr.arguments is None
    assert tcr.id is None


def test_toolcallrequest_with_all_fields():
    """Test ToolCallRequest with all fields"""
    tcr = ToolCallRequest(
        name="get_weather",
        arguments={"location": "Paris"},
        id="call_123",
    )
    assert tcr.name == "get_weather"
    assert tcr.arguments == {"location": "Paris"}
    assert tcr.id == "call_123"
    assert tcr.type == "tool_call"


def test_toolcallrequest_in_message():
    """Test ToolCallRequest works as message part"""
    tcr = ToolCallRequest(
        arguments={"location": "Paris"}, name="get_weather", id=None
    )
    msg = InputMessage(role="user", parts=[tcr])
    assert len(msg.parts) == 1
    assert msg.parts[0] == tcr


def test_toolcall_inherits_from_toolcallrequest():
    """Test that ToolCall inherits from ToolCallRequest"""
    tc = ToolCall(arguments=None, name="get_weather", id=None)
    assert isinstance(tc, ToolCallRequest)
    assert isinstance(tc, ToolCall)


def test_toolcall_has_execution_fields():
    """Test ToolCall has execution-only fields"""
    tc = ToolCall(arguments=None, name="get_weather", id=None)
    assert hasattr(tc, "tool_type")
    assert hasattr(tc, "tool_description")
    assert hasattr(tc, "tool_result")
    assert hasattr(tc, "error_type")


def test_toolcall_execution_fields_default_none():
    """Test ToolCall execution fields default to None"""
    tc = ToolCall(arguments=None, name="get_weather", id=None)
    assert tc.tool_type is None
    assert tc.tool_description is None
    assert tc.tool_result is None
    assert tc.error_type is None


def test_toolcall_with_execution_fields():
    """Test ToolCall with execution fields set"""
    tc = ToolCall(
        name="get_weather",
        arguments={"location": "Paris"},
        id="call_123",
        tool_type="function",
        tool_description="Get current weather",
        tool_result={"temp": 20, "condition": "sunny"},
    )
    assert tc.name == "get_weather"
    assert tc.tool_type == "function"
    assert tc.tool_description == "Get current weather"
    assert tc.tool_result == {"temp": 20, "condition": "sunny"}


def test_toolcall_with_error():
    """Test ToolCall with error_type set"""
    tc = ToolCall(
        arguments={"location": "Invalid"},
        name="get_weather",
        id=None,
        error_type="InvalidLocationError",
    )
    assert tc.error_type == "InvalidLocationError"
    assert tc.tool_result is None


def test_toolcall_backward_compatibility():
    """Test ToolCall still works as message part (backward compatibility)"""
    tc = ToolCall(
        name="get_weather",
        arguments={"location": "Paris"},
        id="call_123",
    )
    # Should work in messages
    msg = InputMessage(role="user", parts=[tc])
    assert len(msg.parts) == 1

    # Should work in output messages
    out_msg = OutputMessage(
        role="assistant", parts=[tc], finish_reason="tool_calls"
    )
    assert len(out_msg.parts) == 1


def test_toolcallrequest_no_execution_fields():
    """Test that ToolCallRequest doesn't have execution fields"""
    tcr = ToolCallRequest(arguments=None, name="get_weather", id=None)
    # ToolCallRequest should only have message part fields
    assert not hasattr(tcr, "tool_type")
    assert not hasattr(tcr, "tool_description")
    assert not hasattr(tcr, "tool_result")
    assert not hasattr(tcr, "error_type")


def test_mixed_types_in_message():
    """Test using both ToolCallRequest and ToolCall in messages"""
    tcr = ToolCallRequest(arguments=None, name="simple_tool", id=None)
    tc = ToolCall(
        arguments=None, name="complex_tool", id=None, tool_type="function"
    )

    msg = InputMessage(role="user", parts=[tcr, tc])
    assert len(msg.parts) == 2
    assert isinstance(msg.parts[0], ToolCallRequest)
    assert isinstance(msg.parts[1], ToolCall)
    # ToolCall is also a ToolCallRequest
    assert isinstance(msg.parts[1], ToolCallRequest)


def test_toolcall_tool_type_values():
    """Test valid tool_type values"""
    for tool_type in ["function", "extension", "datastore"]:
        tc = ToolCall(
            arguments=None, name="test", id=None, tool_type=tool_type
        )
        assert tc.tool_type == tool_type


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
