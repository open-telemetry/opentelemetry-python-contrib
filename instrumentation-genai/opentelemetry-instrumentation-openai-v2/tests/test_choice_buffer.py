# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for ChoiceBuffer and ToolCallBuffer classes."""

from openai.types.chat.chat_completion_chunk import (
    ChoiceDeltaToolCall,
    ChoiceDeltaToolCallFunction,
)

from opentelemetry.instrumentation.openai_v2.patch import (
    ChoiceBuffer,
    ToolCallBuffer,
)


def test_toolcallbuffer_append_arguments_with_string():
    buf = ToolCallBuffer(0, "call_1", "get_weather")
    buf.append_arguments('{"city":')
    buf.append_arguments(' "NYC"}')
    assert "".join(buf.arguments) == '{"city": "NYC"}'


def test_toolcallbuffer_append_arguments_with_none_is_skipped():
    """Regression test for issue #4344.

    Some OpenAI-compatible providers (vLLM, TGI, etc.) send
    arguments=None on tool-call delta chunks instead of arguments="".
    This must not crash when joining the arguments list.
    """
    buf = ToolCallBuffer(0, "call_1", "get_weather")
    buf.append_arguments(None)
    buf.append_arguments('{"city": "NYC"}')
    buf.append_arguments(None)
    assert "".join(buf.arguments) == '{"city": "NYC"}'


def test_toolcallbuffer_append_arguments_all_none():
    buf = ToolCallBuffer(0, "call_1", "get_weather")
    buf.append_arguments(None)
    buf.append_arguments(None)
    assert "".join(buf.arguments) == ""


def test_toolcallbuffer_append_arguments_empty_string():
    buf = ToolCallBuffer(0, "call_1", "get_weather")
    buf.append_arguments("")
    buf.append_arguments('{"city": "NYC"}')
    assert "".join(buf.arguments) == '{"city": "NYC"}'


def test_choicebuffer_append_tool_call_with_none_arguments():
    """End-to-end regression test for issue #4344.

    Simulates the exact scenario from the bug report where a provider
    sends arguments=None on the first tool-call delta chunk.
    """
    buf = ChoiceBuffer(0)
    buf.append_tool_call(
        ChoiceDeltaToolCall(
            index=0,
            id="call_1",
            type="function",
            function=ChoiceDeltaToolCallFunction(
                name="get_weather", arguments=None
            ),
        )
    )
    buf.append_tool_call(
        ChoiceDeltaToolCall(
            index=0,
            function=ChoiceDeltaToolCallFunction(arguments='{"city": "NYC"}'),
        )
    )

    # This must not raise TypeError
    result = "".join(buf.tool_calls_buffers[0].arguments)
    assert result == '{"city": "NYC"}'


def test_choicebuffer_append_tool_call_normal_flow():
    """Standard OpenAI flow where arguments="" on first delta."""
    buf = ChoiceBuffer(0)
    buf.append_tool_call(
        ChoiceDeltaToolCall(
            index=0,
            id="call_1",
            type="function",
            function=ChoiceDeltaToolCallFunction(
                name="get_weather", arguments=""
            ),
        )
    )
    buf.append_tool_call(
        ChoiceDeltaToolCall(
            index=0,
            function=ChoiceDeltaToolCallFunction(arguments='{"city": "NYC"}'),
        )
    )

    result = "".join(buf.tool_calls_buffers[0].arguments)
    assert result == '{"city": "NYC"}'


def test_choicebuffer_append_multiple_tool_calls_with_none_arguments():
    """Multiple tool calls where some have arguments=None."""
    buf = ChoiceBuffer(0)

    # First tool call
    buf.append_tool_call(
        ChoiceDeltaToolCall(
            index=0,
            id="call_1",
            type="function",
            function=ChoiceDeltaToolCallFunction(
                name="get_weather", arguments=None
            ),
        )
    )
    buf.append_tool_call(
        ChoiceDeltaToolCall(
            index=0,
            function=ChoiceDeltaToolCallFunction(arguments='{"city": "NYC"}'),
        )
    )

    # Second tool call
    buf.append_tool_call(
        ChoiceDeltaToolCall(
            index=1,
            id="call_2",
            type="function",
            function=ChoiceDeltaToolCallFunction(
                name="get_time", arguments=None
            ),
        )
    )
    buf.append_tool_call(
        ChoiceDeltaToolCall(
            index=1,
            function=ChoiceDeltaToolCallFunction(arguments='{"tz": "EST"}'),
        )
    )

    assert "".join(buf.tool_calls_buffers[0].arguments) == '{"city": "NYC"}'
    assert "".join(buf.tool_calls_buffers[1].arguments) == '{"tz": "EST"}'


def test_choicebuffer_append_tool_call_with_none_function():
    """Handle delta chunks where function is None."""
    buf = ChoiceBuffer(0)
    buf.append_tool_call(
        ChoiceDeltaToolCall(
            index=0,
            id="call_1",
            type="function",
            function=ChoiceDeltaToolCallFunction(
                name="get_weather", arguments='{"city": "NYC"}'
            ),
        )
    )
    # Subsequent delta with function=None should not crash
    buf.append_tool_call(
        ChoiceDeltaToolCall(
            index=0,
            function=None,
        )
    )

    result = "".join(buf.tool_calls_buffers[0].arguments)
    assert result == '{"city": "NYC"}'
