"""Tests for Claude Agent SDK instrumentation using cassette-based test data.

This test module uses YAML cassettes to test the _process_agent_invocation_stream
function with real message sequences from claude-agent-sdk-python examples.
"""

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
# Cassette Loading
# ============================================================================


def load_cassette(filename: str) -> Dict[str, Any]:
    """Load test case from cassettes directory."""
    cassette_path = Path(__file__).parent / "cassettes" / filename

    with open(cassette_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_all_cassettes() -> List[str]:
    """Get all cassette file names."""
    cassettes_dir = Path(__file__).parent / "cassettes"
    return sorted([f.name for f in cassettes_dir.glob("test_*.yaml")])


# ============================================================================
# Mock Message Helpers
# ============================================================================


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


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def tracer_provider():
    """Create a tracer provider for testing."""
    provider = TracerProvider()
    return provider


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
# Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("cassette_file", get_all_cassettes())
async def test_agent_invocation_with_cassette(
    cassette_file, instrument, span_exporter, tracer_provider
):
    """Test agent invocation with cassette data.

    This test:
    1. Loads real message sequences from cassette file
    2. Processes messages using _process_agent_invocation_stream
    3. Verifies the number and basic properties of generated spans

    For detailed span validation, see test_span_validation.py
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

    # Load cassette
    test_case = load_cassette(cassette_file)

    from opentelemetry.util.genai.handler import TelemetryHandler
    base_handler = TelemetryHandler(tracer_provider=tracer_provider)
    handler = ExtendedTelemetryHandler(base_handler)
    mock_stream = create_mock_stream_from_messages(test_case["messages"])

    # Process message stream
    async for _ in _process_agent_invocation_stream(
        wrapped_stream=mock_stream,
        handler=handler,
        model="qwen-plus",
        prompt=test_case["prompt"],
    ):
        pass

    # Verify generated spans
    spans = span_exporter.get_finished_spans()

    # Basic validation
    assert len(spans) > 0, (
        f"Should generate at least one span for {cassette_file}"
    )

    # Verify Agent span exists
    # Note: When Task tool is used, there will be a root agent + SubAgent span
    agent_spans = [
        s
        for s in spans
        if dict(s.attributes or {}).get(GenAIAttributes.GEN_AI_OPERATION_NAME)
        == "invoke_agent"
    ]

    # Find Task tool spans to determine if SubAgent is expected
    tool_spans = [
        s
        for s in spans
        if dict(s.attributes or {}).get(GenAIAttributes.GEN_AI_OPERATION_NAME)
        == "execute_tool"
    ]
    task_spans = [
        s
        for s in tool_spans
        if dict(s.attributes or {}).get(GenAIAttributes.GEN_AI_TOOL_NAME)
        == "Task"
    ]

    # If Task tool is used, expect root agent + SubAgent spans
    if len(task_spans) > 0:
        assert len(agent_spans) >= 1, (
            f"Should have at least one Agent span for {cassette_file}"
        )
    else:
        # No Task tool, expect only root agent
        assert len(agent_spans) == 1, (
            f"Should have one Agent span for {cassette_file}"
        )

    # Verify LLM spans exist
    llm_spans = [
        s
        for s in spans
        if dict(s.attributes or {}).get(GenAIAttributes.GEN_AI_OPERATION_NAME)
        == "chat"
    ]
    assert len(llm_spans) > 0, (
        f"Should have at least one LLM span for {cassette_file}"
    )
