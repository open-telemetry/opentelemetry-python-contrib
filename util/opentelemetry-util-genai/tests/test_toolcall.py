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

"""Tests for Enhanced ToolCall Type Definition"""

import pytest

from opentelemetry.util.genai.types import (
    InputMessage,
    OutputMessage,
    ToolCall,
)


def test_toolcall_backward_compatibility():
    """Test backward compatibility as message part"""
    tc = ToolCall(
        name="get_weather",
        arguments={"location": "Paris"},
        id="call_123",
    )
    assert tc.name == "get_weather"
    assert tc.arguments == {"location": "Paris"}
    assert tc.id == "call_123"
    assert tc.type == "tool_call"


def test_toolcall_in_message():
    """Test ToolCall works as message part in InputMessage"""
    tc = ToolCall(name="get_weather", arguments={"location": "Paris"})
    msg = InputMessage(role="user", parts=[tc])
    assert len(msg.parts) == 1
    assert msg.parts[0] == tc


def test_toolcall_full_lifecycle():
    """Test complete tool call lifecycle with all fields"""
    # Start with tool call request
    tc = ToolCall(
        name="get_weather",
        arguments={"location": "Paris", "units": "metric"},
        id="call_abc123",
        tool_type="function",
        tool_description="Retrieves current weather for a location",
    )

    # Simulate successful execution - set result
    tc.tool_result = {"temperature": 15, "condition": "cloudy"}

    assert tc.name == "get_weather"
    assert tc.tool_type == "function"
    assert tc.tool_result is not None
    assert tc.error_type is None

    # Simulate failed execution - set error
    tc_failed = ToolCall(
        name="get_weather",
        arguments={"location": "Invalid"},
        id="call_xyz789",
        tool_type="function",
    )
    tc_failed.error_type = "InvalidLocationError"

    assert tc_failed.error_type == "InvalidLocationError"
    assert tc_failed.tool_result is None


def test_toolcall_with_output_message():
    """Test ToolCall in OutputMessage (backward compatibility)"""
    tc = ToolCall(
        name="get_weather",
        arguments={"location": "Paris"},
        id="call_123",
    )
    msg = OutputMessage(
        role="assistant", parts=[tc], finish_reason="tool_calls"
    )

    assert len(msg.parts) == 1
    assert msg.parts[0].name == "get_weather"
    assert msg.finish_reason == "tool_calls"


def test_toolcall_field_values():
    """Test that ToolCall fields can be set and retrieved correctly"""
    tc = ToolCall(
        name="get_weather",
        id="call_123",
        tool_type="function",
        tool_description="Weather tool",
        arguments={"location": "Paris"},
        tool_result={"temp": 20},
    )

    # Verify all field values are set correctly
    assert tc.name == "get_weather"
    assert tc.id == "call_123"
    assert tc.tool_type == "function"
    assert tc.tool_description == "Weather tool"
    assert tc.arguments == {"location": "Paris"}
    assert tc.tool_result == {"temp": 20}
    assert tc.error_type is None

    # Verify these fields map to semantic convention attributes:
    # - name -> gen_ai.tool.name
    # - id -> gen_ai.tool.call.id
    # - tool_type -> gen_ai.tool.type
    # - tool_description -> gen_ai.tool.description
    # - arguments -> gen_ai.tool.call.arguments (Opt-In)
    # - tool_result -> gen_ai.tool.call.result (Opt-In)
    # - error_type -> error.type


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
