from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import Error, ToolCall


def test_tool_call_lifecycle():
    handler = get_telemetry_handler()
    call = ToolCall(
        name="translate",
        id="123",
        arguments={"text": "hola"},
        provider="translator",
    )
    # Start should assign span
    result = handler.start_tool_call(call)
    assert result is call
    assert call.span is not None
    # Stop should set end_time and end span
    handler.stop_tool_call(call)
    assert call.end_time is not None
    # Error on new call
    call2 = ToolCall(
        name="summarize", id=None, arguments={"text": "long"}, provider=None
    )
    handler.start_tool_call(call2)
    handler.fail_tool_call(call2, Error(message="fail", type=RuntimeError))
    assert call2.end_time is not None


def test_generic_start_finish_for_tool_call():
    handler = get_telemetry_handler()
    call = ToolCall(name="analyze", id="abc", arguments=None)
    # Generic methods should route to tool call lifecycle
    handler.start(call)
    handler.finish(call)
    handler.fail(call, Error(message="err", type=ValueError))
    assert call.span is not None
    assert call.end_time is not None
