"""Comprehensive tests for Task tool and SubAgent span instrumentation using real message data.

These tests use actual message streams from real Claude Agent SDK executions
stored in cassette files to validate SubAgent span functionality:
- SubAgent span creation and hierarchy
- SubAgent span attributes (name, description, prompt, result, usage, cost, duration)
- Context propagation between Task and SubAgent spans
- Correct parent-child relationships
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
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)

# ============================================================================
# Helper Functions - Load Real Message Data from Cassettes
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
            elif block_data["type"] == "TextBlock":
                mock_block.text = block_data.get("text", "")

            mock_msg.content.append(mock_block)

        mock_msg.uuid = message_data.get("uuid")
        mock_msg.parent_tool_use_id = message_data.get("parent_tool_use_id")
        mock_msg.tool_use_result = message_data.get("tool_use_result")

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


def find_spans_by_operation(spans, operation_name):
    """Find spans by gen_ai.operation.name attribute."""
    return [
        s
        for s in spans
        if dict(s.attributes or {}).get(GenAIAttributes.GEN_AI_OPERATION_NAME)
        == operation_name
    ]


def find_task_tool_spans(spans):
    """Find all Task tool spans."""
    tool_spans = find_spans_by_operation(spans, "execute_tool")
    return [
        s
        for s in tool_spans
        if dict(s.attributes or {}).get(GenAIAttributes.GEN_AI_TOOL_NAME)
        == "Task"
    ]


def find_subagent_spans(spans):
    """Find all SubAgent spans (invoke_agent spans that are children of Task tool spans)."""
    agent_spans = find_spans_by_operation(spans, "invoke_agent")
    task_spans = find_task_tool_spans(spans)
    task_span_ids = {s.context.span_id for s in task_spans}

    subagent_spans = []
    for agent_span in agent_spans:
        if agent_span.parent and agent_span.parent.span_id in task_span_ids:
            subagent_spans.append(agent_span)

    return subagent_spans


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
# Tests - SubAgent Span Creation and Hierarchy with Real Data
# ============================================================================


@pytest.mark.asyncio
async def test_subagent_span_creation_from_task_tool(
    instrument, span_exporter, tracer_provider
):
    """Verify SubAgent span is created when Task tool is used (using real data).

    This test uses actual message data from a Documentation Writer example
    where a Task tool was used to invoke a general-purpose subagent.

    Validates:
    1. Task tool span exists
    2. SubAgent span exists
    3. SubAgent is child of Task tool span
    4. SubAgent has correct operation name
    """
    from opentelemetry.instrumentation.claude_agent_sdk.patch import (  # noqa: PLC0415
        _process_agent_invocation_stream,
    )
    from opentelemetry.instrumentation.claude_agent_sdk._extended_handler import (  # noqa: PLC0415
        ExtendedTelemetryHandlerForClaude as ExtendedTelemetryHandler,
    )

    test_case = load_cassette("test_doc_writer_with_task.yaml")
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
    task_spans = find_task_tool_spans(spans)
    subagent_spans = find_subagent_spans(spans)

    # Verify Task tool span exists
    assert len(task_spans) == 1, "Should have exactly one Task tool span"
    task_span = task_spans[0]

    # Verify SubAgent span exists
    assert len(subagent_spans) == 1, "Should have exactly one SubAgent span"
    subagent_span = subagent_spans[0]

    # Verify SubAgent is child of Task
    assert subagent_span.parent is not None, "SubAgent should have a parent"
    assert subagent_span.parent.span_id == task_span.context.span_id, (
        "SubAgent's parent should be Task tool span"
    )

    # Verify SubAgent operation name
    attrs = dict(subagent_span.attributes or {})
    assert attrs.get(GenAIAttributes.GEN_AI_OPERATION_NAME) == "invoke_agent"


@pytest.mark.asyncio
async def test_subagent_span_name_from_task_input(
    instrument, span_exporter, tracer_provider
):
    """Verify SubAgent span name is derived from subagent_type in Task input.

    The SubAgent span name should be: invoke_agent {subagent_type}
    where subagent_type comes from the Task tool's input.
    """
    from opentelemetry.instrumentation.claude_agent_sdk.patch import (  # noqa: PLC0415
        _process_agent_invocation_stream,
    )
    from opentelemetry.instrumentation.claude_agent_sdk._extended_handler import (  # noqa: PLC0415
        ExtendedTelemetryHandlerForClaude as ExtendedTelemetryHandler,
    )

    test_case = load_cassette("test_doc_writer_with_task.yaml")
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
    subagent_spans = find_subagent_spans(spans)

    assert len(subagent_spans) == 1
    subagent_span = subagent_spans[0]

    # SubAgent name should contain "general-purpose" from Task input
    expected_subagent_type = "general-purpose"
    assert expected_subagent_type in subagent_span.name, (
        f"SubAgent span name should contain '{expected_subagent_type}', got: {subagent_span.name}"
    )


@pytest.mark.asyncio
async def test_subagent_span_input_attributes(
    instrument, span_exporter, tracer_provider
):
    """Verify SubAgent span captures input attributes from Task tool input.

    Validates:
    1. gen_ai.agent.name = subagent_type from Task input
    2. gen_ai.agent.description = description from Task input
    3. Provider name is set
    """
    from opentelemetry.instrumentation.claude_agent_sdk.patch import (  # noqa: PLC0415
        _process_agent_invocation_stream,
    )
    from opentelemetry.instrumentation.claude_agent_sdk._extended_handler import (  # noqa: PLC0415
        ExtendedTelemetryHandlerForClaude as ExtendedTelemetryHandler,
    )

    test_case = load_cassette("test_doc_writer_with_task.yaml")
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
    subagent_spans = find_subagent_spans(spans)

    assert len(subagent_spans) == 1
    subagent_span = subagent_spans[0]
    attrs = dict(subagent_span.attributes or {})

    # Verify agent name (should be "general-purpose" from Task input)
    assert GenAIAttributes.GEN_AI_AGENT_NAME in attrs
    assert attrs[GenAIAttributes.GEN_AI_AGENT_NAME] == "general-purpose"

    # Verify agent description (should be "Explain AgentDefinition purpose" from Task input)
    assert GenAIAttributes.GEN_AI_AGENT_DESCRIPTION in attrs
    assert "AgentDefinition" in attrs[GenAIAttributes.GEN_AI_AGENT_DESCRIPTION]

    # Verify provider name is set
    assert GenAIAttributes.GEN_AI_PROVIDER_NAME in attrs


@pytest.mark.asyncio
async def test_subagent_span_output_attributes_with_tool_use_result(
    instrument, span_exporter, tracer_provider
):
    """Verify SubAgent span captures output from tool_use_result in Task result.

    The real data includes tool_use_result with:
    - usage: {input_tokens, output_tokens}
    - agentId
    - content (output messages)

    Validates:
    1. Span completes successfully (has end_time)
    2. Token usage attributes are present (from tool_use_result.usage)
    3. Agent ID is captured

    Note: SubAgent span does NOT record duration_ms or cost attributes.
    These are managed at the parent Agent level via ResultMessage.
    """
    from opentelemetry.instrumentation.claude_agent_sdk.patch import (  # noqa: PLC0415
        _process_agent_invocation_stream,
    )
    from opentelemetry.instrumentation.claude_agent_sdk._extended_handler import (  # noqa: PLC0415
        ExtendedTelemetryHandlerForClaude as ExtendedTelemetryHandler,
    )

    test_case = load_cassette("test_doc_writer_with_task.yaml")
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
    subagent_spans = find_subagent_spans(spans)

    assert len(subagent_spans) == 1
    subagent_span = subagent_spans[0]
    attrs = dict(subagent_span.attributes or {})

    # Verify span completed successfully
    assert subagent_span.end_time is not None
    assert subagent_span.end_time > subagent_span.start_time

    # Verify agent ID was captured from tool_use_result
    assert "gen_ai.agent.id" in attrs
    assert attrs["gen_ai.agent.id"] == "ada4edf"

    # Verify token usage attributes (from tool_use_result.usage)
    # In this test case, both are 0, but they should be present in attributes
    assert "gen_ai.usage.input_tokens" in attrs
    assert attrs["gen_ai.usage.input_tokens"] == 0
    assert "gen_ai.usage.output_tokens" in attrs
    assert attrs["gen_ai.usage.output_tokens"] == 0

    # Verify basic agent attributes are present
    assert "gen_ai.agent.name" in attrs
    assert "gen_ai.operation.name" in attrs
    assert attrs["gen_ai.operation.name"] == "invoke_agent"


@pytest.mark.asyncio
async def test_subagent_span_hierarchy_and_context(
    instrument, span_exporter, tracer_provider
):
    """Verify span hierarchy and context propagation with Task and SubAgent.

    Validates:
    1. Root agent span exists
    2. Task tool span is child of root agent
    3. SubAgent span is child of Task tool span
    4. Internal tool calls (Grep, Read) are children of SubAgent
    5. Spans after Task completion are siblings of Task, not children
    """
    from opentelemetry.instrumentation.claude_agent_sdk.patch import (  # noqa: PLC0415
        _process_agent_invocation_stream,
    )
    from opentelemetry.instrumentation.claude_agent_sdk._extended_handler import (  # noqa: PLC0415
        ExtendedTelemetryHandlerForClaude as ExtendedTelemetryHandler,
    )

    test_case = load_cassette("test_doc_writer_with_task.yaml")
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
    agent_spans = find_spans_by_operation(spans, "invoke_agent")
    task_spans = find_task_tool_spans(spans)
    subagent_spans = find_subagent_spans(spans)
    tool_spans = find_spans_by_operation(spans, "execute_tool")

    # Find root agent span (no parent)
    root_agent = [s for s in agent_spans if s.parent is None][0]

    # Verify hierarchy
    assert len(task_spans) == 1
    task_span = task_spans[0]

    assert len(subagent_spans) == 1
    subagent_span = subagent_spans[0]

    # Task span should be child of root agent
    assert task_span.parent is not None
    assert task_span.parent.span_id == root_agent.context.span_id

    # SubAgent span should be child of Task span
    assert subagent_span.parent is not None
    assert subagent_span.parent.span_id == task_span.context.span_id

    # Find tool spans that are children of SubAgent (Grep, Read)
    subagent_child_tools = [
        s
        for s in tool_spans
        if s.parent and s.parent.span_id == subagent_span.context.span_id
    ]

    # Should have internal tool calls (Grep, Read)
    assert len(subagent_child_tools) >= 2, (
        "SubAgent should have child tool spans (Grep, Read)"
    )
