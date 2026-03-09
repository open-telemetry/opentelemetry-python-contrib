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

"""Tests for ToolCallRequest and ToolCall inheritance structure"""

import pytest

from opentelemetry.util.genai.types import (
    GenAIInvocation,
    InputMessage,
    ServerToolCall,
    ServerToolCallResponse,
    ToolCall,
    ToolCallRequest,
)


def test_toolcallrequest_is_message_part():
    """ToolCallRequest is for message parts only"""
    tcr = ToolCallRequest(
        arguments={"location": "Paris"}, name="get_weather", id="call_123"
    )
    msg = InputMessage(role="user", parts=[tcr])
    assert len(msg.parts) == 1


def test_toolcall_inherits_from_genaiinvocation():
    """ToolCall inherits from GenAIInvocation for lifecycle management"""
    tc = ToolCall(name="get_weather", arguments={"city": "Paris"})
    assert isinstance(tc, GenAIInvocation)
    assert not isinstance(tc, ToolCallRequest)


def test_toolcall_has_attributes_dict():
    """ToolCall inherits attributes dict from GenAIInvocation"""
    tc = ToolCall(name="test")
    tc.attributes["custom.key"] = "value"
    assert tc.attributes["custom.key"] == "value"


def test_toolcall_in_message_part_union():
    """ToolCall can be used in messages despite not inheriting from ToolCallRequest"""
    tc = ToolCall(name="get_weather", arguments={"city": "Paris"})
    msg = InputMessage(role="assistant", parts=[tc])
    assert len(msg.parts) == 1
    assert isinstance(msg.parts[0], GenAIInvocation)


def test_server_tool_call_basic():
    """ServerToolCall can be created with required fields"""
    stc = ServerToolCall(
        name="code_interpreter",
        server_tool_call={"type": "code_interpreter", "code": "print(1)"},
    )
    assert stc.name == "code_interpreter"
    assert stc.server_tool_call == {
        "type": "code_interpreter",
        "code": "print(1)",
    }
    assert stc.id is None
    assert stc.type == "server_tool_call"


def test_server_tool_call_with_id():
    """ServerToolCall can have an optional id"""
    stc = ServerToolCall(
        name="web_search",
        server_tool_call={"type": "web_search", "query": "weather"},
        id="stc_001",
    )
    assert stc.id == "stc_001"


def test_server_tool_call_response_basic():
    """ServerToolCallResponse can be created with required fields"""
    stcr = ServerToolCallResponse(
        server_tool_call_response={
            "type": "code_interpreter",
            "output": "1\n",
        },
    )
    assert stcr.server_tool_call_response == {
        "type": "code_interpreter",
        "output": "1\n",
    }
    assert stcr.id is None
    assert stcr.type == "server_tool_call_response"


def test_server_tool_call_in_message():
    """ServerToolCall and ServerToolCallResponse work as MessageParts"""
    stc = ServerToolCall(
        name="code_interpreter",
        server_tool_call={"type": "code_interpreter", "code": "x = 1"},
    )
    stcr = ServerToolCallResponse(
        server_tool_call_response={"type": "code_interpreter", "output": ""},
        id="stc_001",
    )
    msg = InputMessage(role="assistant", parts=[stc, stcr])
    assert len(msg.parts) == 2
    assert isinstance(msg.parts[0], ServerToolCall)
    assert isinstance(msg.parts[1], ServerToolCallResponse)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
