from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import ToolCall


def test_tool_call_span_attributes():
    handler = get_telemetry_handler()
    call = ToolCall(
        name="summarize",
        id="tool-1",
        arguments={"text": "hello"},
        provider="provX",
    )
    handler.start_tool_call(call)
    assert call.span is not None
    # Attributes applied at start
    attrs = getattr(call.span, "attributes", None)
    if attrs is None:
        attrs = getattr(
            call.span, "_attributes", {}
        )  # fallback for SDK internals
    # Operation name
    assert attrs.get(GenAI.GEN_AI_OPERATION_NAME) == "tool_call"
    # Request model mapped to tool name
    assert attrs.get(GenAI.GEN_AI_REQUEST_MODEL) == "summarize"
    # Provider
    assert attrs.get("gen_ai.provider.name") == "provX"
    handler.stop_tool_call(call)
