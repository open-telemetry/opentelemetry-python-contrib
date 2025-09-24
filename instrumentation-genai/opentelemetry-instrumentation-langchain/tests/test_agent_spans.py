"""Tests for agent-related spans in LangChain instrumentation."""

from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest
from langchain_core.agents import AgentAction, AgentFinish

from opentelemetry.instrumentation.langchain.callback_handler import (
    OpenTelemetryLangChainCallbackHandler,
)
from opentelemetry.semconv._incubating.attributes import gen_ai_attributes as GenAI
from opentelemetry.trace import SpanKind


@pytest.fixture
def callback_handler(tracer_provider):
    tracer = tracer_provider.get_tracer("test")
    return OpenTelemetryLangChainCallbackHandler(tracer=tracer)


def test_agent_chain_span(callback_handler, span_exporter):
    """Test that agent chains create proper invoke_agent spans."""
    run_id = uuid4()
    parent_run_id = uuid4()

    # Start a chain that represents an agent
    callback_handler.on_chain_start(
        serialized={"name": "TestAgent", "id": ["langchain", "agents", "TestAgent"]},
        inputs={"input": "What is the capital of France?"},
        run_id=run_id,
        parent_run_id=parent_run_id,
        metadata={"agent_name": "TestAgent"},
    )

    # End the chain
    callback_handler.on_chain_end(
        outputs={"output": "The capital of France is Paris."},
        run_id=run_id,
        parent_run_id=parent_run_id,
    )

    # Verify the span
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.name == "chain TestAgent"
    assert span.kind == SpanKind.INTERNAL
    assert span.attributes.get(GenAI.GEN_AI_AGENT_NAME) == "TestAgent"
    assert span.attributes.get(GenAI.GEN_AI_OPERATION_NAME) == "invoke_agent"


def test_agent_action_tracking(callback_handler, span_exporter):
    """Test that agent actions are properly tracked."""
    run_id = uuid4()
    parent_run_id = uuid4()

    # Start a chain
    callback_handler.on_chain_start(
        serialized={"name": "Agent"},
        inputs={"input": "What is 2 + 2?"},
        run_id=run_id,
        parent_run_id=parent_run_id,
    )

    # Agent takes an action
    action = MagicMock(spec=AgentAction)
    action.tool = "calculator"
    action.tool_input = "2 + 2"

    callback_handler.on_agent_action(
        action=action,
        run_id=run_id,
        parent_run_id=parent_run_id,
    )

    # Agent finishes
    finish = MagicMock(spec=AgentFinish)
    finish.return_values = {"output": "The answer is 4"}

    callback_handler.on_agent_finish(
        finish=finish,
        run_id=run_id,
        parent_run_id=parent_run_id,
    )

    # End the chain
    callback_handler.on_chain_end(
        outputs={"output": "The answer is 4"},
        run_id=run_id,
        parent_run_id=parent_run_id,
    )

    # Verify the span
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.attributes.get("langchain.agent.action.tool") == "calculator"
    assert span.attributes.get("langchain.agent.action.tool_input") == "2 + 2"
    assert span.attributes.get("langchain.agent.finish.output") == "The answer is 4"


def test_regular_chain_without_agent(callback_handler, span_exporter):
    """Test that regular chains don't get agent attributes."""
    run_id = uuid4()
    parent_run_id = uuid4()

    # Start a regular chain (not an agent)
    callback_handler.on_chain_start(
        serialized={"name": "RegularChain"},
        inputs={"input": "Test input"},
        run_id=run_id,
        parent_run_id=parent_run_id,
        metadata={},  # No agent_name in metadata
    )

    # End the chain
    callback_handler.on_chain_end(
        outputs={"output": "Test output"},
        run_id=run_id,
        parent_run_id=parent_run_id,
    )

    # Verify the span
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.name == "chain RegularChain"
    assert span.kind == SpanKind.INTERNAL
    assert GenAI.GEN_AI_AGENT_NAME not in span.attributes
    assert GenAI.GEN_AI_OPERATION_NAME not in span.attributes  # Regular chains don't have operation name


def test_chain_error_handling(callback_handler, span_exporter):
    """Test that chain errors are properly handled."""
    run_id = uuid4()
    parent_run_id = uuid4()

    # Start a chain
    callback_handler.on_chain_start(
        serialized={"name": "ErrorChain"},
        inputs={"input": "Test input"},
        run_id=run_id,
        parent_run_id=parent_run_id,
    )

    # Chain encounters an error
    error = ValueError("Test error")
    callback_handler.on_chain_error(
        error=error,
        run_id=run_id,
        parent_run_id=parent_run_id,
    )

    # Verify the span
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.name == "chain ErrorChain"
    assert span.status.status_code.name == "ERROR"
    assert span.attributes.get("error.type") == "ValueError"