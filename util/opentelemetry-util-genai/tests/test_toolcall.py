# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for ToolCallRequest and ToolInvocation inheritance structure"""

import pytest

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.sdk.trace.sampling import Decision, SamplingResult
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.invocation import GenAIInvocation
from opentelemetry.util.genai.types import (
    InputMessage,
    ServerToolCall,
    ServerToolCallResponse,
    ToolCallRequest,
)


def _make_handler() -> TelemetryHandler:
    return TelemetryHandler(tracer_provider=TracerProvider())


def test_toolcallrequest_is_message_part():
    """ToolCallRequest is for message parts only"""
    tcr = ToolCallRequest(
        arguments={"location": "Paris"}, name="get_weather", id="call_123"
    )
    msg = InputMessage(role="user", parts=[tcr])
    assert len(msg.parts) == 1


def test_toolcall_inherits_from_genaiinvocation():
    """ToolInvocation inherits from GenAIInvocation for lifecycle management"""
    handler = _make_handler()
    tc = handler.tool("get_weather", arguments={"city": "Paris"})
    assert isinstance(tc, GenAIInvocation)
    assert not isinstance(tc, ToolCallRequest)
    tc.stop()


def test_toolcall_has_attributes_dict():
    """ToolInvocation inherits attributes dict from GenAIInvocation"""
    handler = _make_handler()
    tc = handler.tool("test")
    tc.attributes["custom.key"] = "value"
    assert tc.attributes["custom.key"] == "value"
    tc.stop()


def test_toolcallrequest_in_message_part_union():
    """ToolCallRequest (not ToolInvocation) is the correct type for message parts"""
    tc = ToolCallRequest(
        name="get_weather", arguments={"city": "Paris"}, id="call_123"
    )
    msg = InputMessage(role="assistant", parts=[tc])
    assert len(msg.parts) == 1
    assert isinstance(msg.parts[0], ToolCallRequest)
    assert not isinstance(msg.parts[0], GenAIInvocation)


def test_toolcall_operation_name():
    """ToolInvocation operation_name is fixed to execute_tool"""
    handler = _make_handler()
    tc = handler.tool("my_tool")
    assert tc._operation_name == "execute_tool"
    tc.stop()


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


def test_start_tool_passes_sampling_attributes_at_span_creation():
    """Verify that sampling-relevant attributes are available at start_span() time for tools."""
    captured_attributes = {}

    class AttributeCapturingSampler:  # pylint: disable=no-self-use
        def should_sample(
            self,
            parent_context,
            trace_id,
            name,
            kind=None,
            attributes=None,
            links=None,
        ):
            captured_attributes.update(attributes or {})
            return SamplingResult(Decision.RECORD_AND_SAMPLE, attributes)

        def get_description(self):
            return "AttributeCapturingSampler"

    span_exporter = InMemorySpanExporter()
    sampler_provider = TracerProvider(sampler=AttributeCapturingSampler())
    sampler_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    handler = TelemetryHandler(tracer_provider=sampler_provider)

    invocation = handler.tool(
        "get_weather",
        tool_call_id="call_123",
        tool_type="function",
        tool_description="Gets weather for a location",
    )
    invocation.stop()

    assert captured_attributes[GenAI.GEN_AI_OPERATION_NAME] == "execute_tool"
    assert captured_attributes[GenAI.GEN_AI_TOOL_NAME] == "get_weather"
    assert captured_attributes[GenAI.GEN_AI_TOOL_CALL_ID] == "call_123"
    assert captured_attributes[GenAI.GEN_AI_TOOL_TYPE] == "function"
    assert (
        captured_attributes[GenAI.GEN_AI_TOOL_DESCRIPTION]
        == "Gets weather for a location"
    )
