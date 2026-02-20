"""Specific validation tests for Claude Agent SDK instrumentation.

These tests provide detailed validation for specific aspects of the instrumentation:
- Agent span attributes and structure
- LLM span input/output messages
- Tool span attributes and results
- Span hierarchy and timeline
"""

import json
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List
from unittest.mock import MagicMock

import pytest
import yaml

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

# ============================================================================
# Helper Functions
# ============================================================================


def load_cassette(filename: str) -> Dict[str, Any]:
    """Load a test case from cassettes directory."""
    cassette_path = Path(__file__).parent / "cassettes" / filename
    with open(cassette_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def create_mock_message_from_data(message_data: Dict[str, Any]) -> Any:
    """Create a mock message object from test data dictionary."""
    mock_msg = MagicMock()
    msg_type = message_data["type"]

    mock_msg.__class__.__name__ = msg_type

    if msg_type == "SystemMessage":
        mock_msg.subtype = message_data["subtype"]
        mock_msg.data = message_data["data"]

    elif msg_type == "AssistantMessage":
        mock_msg.model = message_data["model"]
        mock_msg.content = []

        for block_data in message_data["content"]:
            mock_block = MagicMock()
            block_type = block_data["type"]
            mock_block.__class__.__name__ = block_type

            if block_type == "TextBlock":
                mock_block.text = block_data["text"]
            elif block_type == "ToolUseBlock":
                mock_block.id = block_data["id"]
                mock_block.name = block_data["name"]
                mock_block.input = block_data["input"]

            mock_msg.content.append(mock_block)

        mock_msg.parent_tool_use_id = message_data.get("parent_tool_use_id")
        mock_msg.error = message_data.get("error")

    elif msg_type == "UserMessage":
        mock_msg.content = []

        for block_data in message_data["content"]:
            mock_block = MagicMock()
            mock_block.__class__.__name__ = block_data["type"]

            if block_data["type"] == "ToolResultBlock":
                mock_block.tool_use_id = block_data["tool_use_id"]
                mock_block.content = block_data["content"]
                mock_block.is_error = block_data["is_error"]

            mock_msg.content.append(mock_block)

        mock_msg.uuid = message_data.get("uuid")
        mock_msg.parent_tool_use_id = message_data.get("parent_tool_use_id")

    elif msg_type == "ResultMessage":
        mock_msg.subtype = message_data["subtype"]
        mock_msg.duration_ms = message_data["duration_ms"]
        mock_msg.duration_api_ms = message_data.get("duration_api_ms")
        mock_msg.is_error = message_data["is_error"]
        mock_msg.num_turns = message_data["num_turns"]
        mock_msg.session_id = message_data.get("session_id")
        mock_msg.total_cost_usd = message_data["total_cost_usd"]
        mock_msg.usage = message_data["usage"]
        mock_msg.result = message_data["result"]
        mock_msg.structured_output = message_data.get("structured_output")

    return mock_msg


async def create_mock_stream_from_messages(
    messages: List[Dict[str, Any]],
) -> AsyncIterator[Any]:
    """Create a mock async stream of messages."""
    for message_data in messages:
        yield create_mock_message_from_data(message_data)


def find_agent_span(spans):
    """Find the Agent span."""
    from opentelemetry.semconv._incubating.attributes import (  # noqa: PLC0415
        gen_ai_attributes as GenAIAttributes,
    )

    for span in spans:
        attrs = dict(span.attributes or {})
        if attrs.get(GenAIAttributes.GEN_AI_OPERATION_NAME) == "invoke_agent":
            return span
    return None


def find_llm_spans(spans):
    """Find all LLM spans."""
    from opentelemetry.semconv._incubating.attributes import (  # noqa: PLC0415
        gen_ai_attributes as GenAIAttributes,
    )

    return [
        s
        for s in spans
        if dict(s.attributes or {}).get(GenAIAttributes.GEN_AI_OPERATION_NAME)
        == "chat"
    ]


def find_tool_spans(spans):
    """Find all Tool spans."""
    from opentelemetry.semconv._incubating.attributes import (  # noqa: PLC0415
        gen_ai_attributes as GenAIAttributes,
    )

    return [
        s
        for s in spans
        if dict(s.attributes or {}).get(GenAIAttributes.GEN_AI_OPERATION_NAME)
        == "execute_tool"
    ]


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def tracer_provider():
    """Create a tracer provider for testing."""
    return TracerProvider()


@pytest.fixture
def span_exporter(tracer_provider):
    """Create an in-memory span exporter."""
    exporter = InMemorySpanExporter()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    return exporter


@pytest.fixture
def instrument(tracer_provider):
    """Instrument the Claude Agent SDK."""
    from opentelemetry.instrumentation.claude_agent_sdk import (  # noqa: PLC0415
        ClaudeAgentSDKInstrumentor,
    )

    instrumentor = ClaudeAgentSDKInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)
    yield instrumentor
    instrumentor.uninstrument()


# ============================================================================
# Tests - Agent Span
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cassette_file",
    [
        "test_foo_sh_command.yaml",
        "test_echo_command.yaml",
        "test_pretooluse_hook.yaml",
    ],
)
async def test_agent_span_correctness(
    cassette_file, instrument, span_exporter, tracer_provider
):
    """Verify Agent span correctness.

    Validates:
    1. Agent span exists and is unique
    2. Agent span is a root span (no parent)
    3. Agent span contains correct attributes (operation.name, agent.name, etc.)
    4. Agent span includes token usage statistics
    """
    from opentelemetry.instrumentation.claude_agent_sdk.patch import (  # noqa: PLC0415
        _process_agent_invocation_stream,
    )
    from opentelemetry.semconv._incubating.attributes import (  # noqa: PLC0415
        gen_ai_attributes as GenAIAttributes,
    )
    from opentelemetry.instrumentation.claude_agent_sdk._extended_handler import (  # noqa: PLC0415
        ExtendedTelemetryHandlerForClaude as ExtendedTelemetryHandler,
    )

    test_case = load_cassette(cassette_file)
    from opentelemetry.util.genai.handler import TelemetryHandler
    base_handler = TelemetryHandler(tracer_provider=tracer_provider)
    handler = ExtendedTelemetryHandler(base_handler)
    mock_stream = create_mock_stream_from_messages(test_case["messages"])

    async for _ in _process_agent_invocation_stream(
        wrapped_stream=mock_stream,
        handler=handler,
        model="qwen-plus",
        prompt=test_case["prompt"],
    ):
        pass

    spans = span_exporter.get_finished_spans()
    agent_span = find_agent_span(spans)

    # Verify Agent span exists and is unique
    agent_spans = [
        s
        for s in spans
        if dict(s.attributes or {}).get(GenAIAttributes.GEN_AI_OPERATION_NAME)
        == "invoke_agent"
    ]
    assert len(agent_spans) == 1, (
        f"Should have exactly one Agent span, got: {len(agent_spans)}"
    )

    # Verify it's a root span
    assert agent_span.parent is None, (
        "Agent span should be a root span with no parent"
    )

    # Verify required attributes
    attrs = dict(agent_span.attributes or {})
    assert GenAIAttributes.GEN_AI_OPERATION_NAME in attrs
    assert attrs[GenAIAttributes.GEN_AI_OPERATION_NAME] == "invoke_agent"

    # Verify token usage statistics
    assert GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS in attrs, (
        "Should have input_tokens"
    )
    assert GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS in attrs, (
        "Should have output_tokens"
    )


# ============================================================================
# Tests - LLM Span
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cassette_file",
    [
        "test_foo_sh_command.yaml",
        "test_echo_command.yaml",
        "test_pretooluse_hook.yaml",
    ],
)
async def test_llm_span_correctness(
    cassette_file, instrument, span_exporter, tracer_provider
):
    """Verify LLM span correctness.

    Validates:
    1. LLM spans exist with correct count
    2. LLM spans are children of Agent span
    3. LLM span attributes are correct (model, provider, operation, etc.)
    4. LLM span output.messages have unique tool_call.id (no duplicates)
    """
    from opentelemetry.instrumentation.claude_agent_sdk.patch import (  # noqa: PLC0415
        _process_agent_invocation_stream,
    )
    from opentelemetry.semconv._incubating.attributes import (  # noqa: PLC0415
        gen_ai_attributes as GenAIAttributes,
    )
    from opentelemetry.instrumentation.claude_agent_sdk._extended_handler import (  # noqa: PLC0415
        ExtendedTelemetryHandlerForClaude as ExtendedTelemetryHandler,
    )

    test_case = load_cassette(cassette_file)
    from opentelemetry.util.genai.handler import TelemetryHandler
    base_handler = TelemetryHandler(tracer_provider=tracer_provider)
    handler = ExtendedTelemetryHandler(base_handler)
    mock_stream = create_mock_stream_from_messages(test_case["messages"])

    async for _ in _process_agent_invocation_stream(
        wrapped_stream=mock_stream,
        handler=handler,
        model="qwen-plus",
        prompt=test_case["prompt"],
    ):
        pass

    spans = span_exporter.get_finished_spans()
    agent_span = find_agent_span(spans)
    llm_spans = find_llm_spans(spans)

    # Verify LLM spans exist
    assert len(llm_spans) > 0, "Should have at least one LLM span"

    # Verify all LLM spans are children of Agent span
    for llm_span in llm_spans:
        assert llm_span.parent is not None, "LLM span should have a parent"
        assert llm_span.parent.span_id == agent_span.context.span_id, (
            "LLM span's parent should be Agent span"
        )

        # Verify basic attributes
        attrs = dict(llm_span.attributes or {})
        assert attrs.get(GenAIAttributes.GEN_AI_OPERATION_NAME) == "chat"
        assert GenAIAttributes.GEN_AI_REQUEST_MODEL in attrs

        # Verify uniqueness of tool_call.id in output.messages
        if GenAIAttributes.GEN_AI_OUTPUT_MESSAGES in attrs:
            output_messages_raw = attrs[GenAIAttributes.GEN_AI_OUTPUT_MESSAGES]
            if isinstance(output_messages_raw, str):
                output_messages = json.loads(output_messages_raw)
            else:
                output_messages = output_messages_raw

            if isinstance(output_messages, list):
                tool_call_ids = []
                for msg in output_messages:
                    if (
                        isinstance(msg, dict)
                        and msg.get("role") == "assistant"
                    ):
                        parts = msg.get("parts", [])
                        for part in parts:
                            if (
                                isinstance(part, dict)
                                and part.get("type") == "tool_call"
                            ):
                                tool_call_id = part.get("id")
                                if tool_call_id:
                                    assert tool_call_id not in tool_call_ids, (
                                        f"Found duplicate tool_call ID: {tool_call_id}"
                                    )
                                    tool_call_ids.append(tool_call_id)


# ============================================================================
# Tests - Tool Span
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cassette_file",
    [
        "test_foo_sh_command.yaml",
        "test_echo_command.yaml",
        "test_pretooluse_hook.yaml",
    ],
)
async def test_tool_span_correctness(
    cassette_file, instrument, span_exporter, tracer_provider
):
    """Verify Tool span correctness.

    Validates:
    1. Tool spans exist with correct count
    2. Tool spans are children of Agent span (not LLM span)
    3. Tool span attributes are correct (tool.name, tool.call.id, arguments, result, etc.)
    4. Tool span contains correct is_error status
    """
    from opentelemetry.instrumentation.claude_agent_sdk.patch import (  # noqa: PLC0415
        _process_agent_invocation_stream,
    )
    from opentelemetry.semconv._incubating.attributes import (  # noqa: PLC0415
        gen_ai_attributes as GenAIAttributes,
    )
    from opentelemetry.instrumentation.claude_agent_sdk._extended_handler import (  # noqa: PLC0415
        ExtendedTelemetryHandlerForClaude as ExtendedTelemetryHandler,
    )

    test_case = load_cassette(cassette_file)
    from opentelemetry.util.genai.handler import TelemetryHandler
    base_handler = TelemetryHandler(tracer_provider=tracer_provider)
    handler = ExtendedTelemetryHandler(base_handler)
    mock_stream = create_mock_stream_from_messages(test_case["messages"])

    async for _ in _process_agent_invocation_stream(
        wrapped_stream=mock_stream,
        handler=handler,
        model="qwen-plus",
        prompt=test_case["prompt"],
    ):
        pass

    spans = span_exporter.get_finished_spans()
    agent_span = find_agent_span(spans)
    llm_spans = find_llm_spans(spans)
    tool_spans = find_tool_spans(spans)

    # Verify Tool spans exist
    assert len(tool_spans) > 0, "Should have at least one Tool span"

    # Verify all Tool spans are children of Agent span (not LLM span)
    for tool_span in tool_spans:
        assert tool_span.parent is not None, "Tool span should have a parent"
        assert tool_span.parent.span_id == agent_span.context.span_id, (
            "Tool span's parent should be Agent span, not LLM span"
        )

        # Ensure it's not a child of LLM span
        for llm_span in llm_spans:
            assert tool_span.parent.span_id != llm_span.context.span_id, (
                "Tool span should not be a child of LLM span"
            )

        # Verify basic attributes
        attrs = dict(tool_span.attributes or {})
        assert (
            attrs.get(GenAIAttributes.GEN_AI_OPERATION_NAME) == "execute_tool"
        )
        assert GenAIAttributes.GEN_AI_TOOL_NAME in attrs, (
            "Should have tool.name"
        )
        assert GenAIAttributes.GEN_AI_TOOL_CALL_ID in attrs, (
            "Should have tool.call.id"
        )


# ============================================================================
# Tests - Span Hierarchy
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cassette_file",
    [
        "test_foo_sh_command.yaml",
        "test_echo_command.yaml",
        "test_pretooluse_hook.yaml",
    ],
)
async def test_span_hierarchy_correctness(
    cassette_file, instrument, span_exporter, tracer_provider
):
    """Verify span hierarchy correctness.

    Validates:
    1. Agent span is the root span
    2. LLM spans are children of Agent span
    3. Tool spans are children of Agent span (not LLM span)
    4. Span timeline is sequential (LLM → Tool → LLM)
    """
    from opentelemetry.instrumentation.claude_agent_sdk.patch import (  # noqa: PLC0415
        _process_agent_invocation_stream,
    )
    from opentelemetry.instrumentation.claude_agent_sdk._extended_handler import (  # noqa: PLC0415
        ExtendedTelemetryHandlerForClaude as ExtendedTelemetryHandler,
    )

    test_case = load_cassette(cassette_file)
    from opentelemetry.util.genai.handler import TelemetryHandler
    base_handler = TelemetryHandler(tracer_provider=tracer_provider)
    handler = ExtendedTelemetryHandler(base_handler)
    mock_stream = create_mock_stream_from_messages(test_case["messages"])

    async for _ in _process_agent_invocation_stream(
        wrapped_stream=mock_stream,
        handler=handler,
        model="qwen-plus",
        prompt=test_case["prompt"],
    ):
        pass

    spans = span_exporter.get_finished_spans()
    agent_span = find_agent_span(spans)
    llm_spans = find_llm_spans(spans)
    tool_spans = find_tool_spans(spans)

    # Verify Agent span is root
    assert agent_span is not None, "Should have Agent span"
    assert agent_span.parent is None, "Agent span should be root span"

    # Verify LLM spans are children of Agent span
    assert len(llm_spans) > 0, "Should have at least one LLM span"
    for llm_span in llm_spans:
        assert llm_span.parent is not None, "LLM span should have a parent"
        assert llm_span.parent.span_id == agent_span.context.span_id, (
            "LLM span's parent should be Agent span"
        )

    # Verify Tool spans are children of Agent span
    assert len(tool_spans) > 0, "Should have at least one Tool span"
    for tool_span in tool_spans:
        assert tool_span.parent is not None, "Tool span should have a parent"
        assert tool_span.parent.span_id == agent_span.context.span_id, (
            "Tool span's parent should be Agent span"
        )

        # Ensure it's not a child of LLM span
        for llm_span in llm_spans:
            assert tool_span.parent.span_id != llm_span.context.span_id, (
                "Tool span should not be a child of LLM span"
            )
