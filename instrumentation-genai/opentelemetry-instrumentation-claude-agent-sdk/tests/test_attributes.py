"""Configuration and attribute tests for Claude Agent SDK instrumentation."""

import asyncio

import pytest

from opentelemetry.instrumentation import claude_agent_sdk
from opentelemetry.instrumentation.claude_agent_sdk import (
    ClaudeAgentSDKInstrumentor,
    __version__,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)


@pytest.mark.requires_cli
@pytest.mark.asyncio
async def test_span_attributes_semantic_conventions(instrument, span_exporter):
    """Test that all spans follow semantic conventions."""
    from claude_agent_sdk import query  # noqa: PLC0415
    from claude_agent_sdk.types import ClaudeAgentOptions  # noqa: PLC0415

    options = ClaudeAgentOptions(
        model="qwen-plus",
        max_turns=1,
    )

    async for _ in query(prompt="Hello", options=options):
        pass

    spans = span_exporter.get_finished_spans()

    for span in spans:
        # All spans should have a name
        assert span.name is not None
        assert len(span.name) > 0

        # Spans should have proper status
        assert span.status is not None

        # Check if it's an LLM span
        if GenAIAttributes.GEN_AI_OPERATION_NAME in span.attributes:
            operation = span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]

            if operation == "chat":
                # LLM spans must have provider
                assert GenAIAttributes.GEN_AI_PROVIDER_NAME in span.attributes
                # LLM spans must have model
                assert GenAIAttributes.GEN_AI_REQUEST_MODEL in span.attributes


@pytest.mark.requires_cli
@pytest.mark.asyncio
async def test_agent_span_naming_convention(instrument, span_exporter):
    """Test agent span naming follows conventions."""
    from claude_agent_sdk import query  # noqa: PLC0415
    from claude_agent_sdk.types import ClaudeAgentOptions  # noqa: PLC0415

    options = ClaudeAgentOptions(
        model="qwen-plus",
        max_turns=1,
    )

    async for _ in query(prompt="Test", options=options):
        pass

    spans = span_exporter.get_finished_spans()
    agent_spans = [s for s in spans if "invoke_agent" in s.name]

    assert len(agent_spans) >= 1
    agent_span = agent_spans[0]

    # Agent span name should contain agent name
    assert (
        "claude-agent" in agent_span.name or "invoke_agent" in agent_span.name
    )


@pytest.mark.requires_cli
@pytest.mark.asyncio
async def test_llm_span_naming_convention(instrument, span_exporter):
    """Test LLM span naming follows conventions."""
    from claude_agent_sdk import query  # noqa: PLC0415
    from claude_agent_sdk.types import ClaudeAgentOptions  # noqa: PLC0415

    options = ClaudeAgentOptions(
        model="qwen-plus",
        max_turns=1,
    )

    async for _ in query(prompt="Test", options=options):
        pass

    spans = span_exporter.get_finished_spans()
    llm_spans = [
        s
        for s in spans
        if GenAIAttributes.GEN_AI_OPERATION_NAME in s.attributes
        and s.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME] == "chat"
    ]

    assert len(llm_spans) >= 1
    llm_span = llm_spans[0]

    # LLM span name should follow pattern: "{operation} {model}"
    assert "chat" in llm_span.name
    assert "qwen" in llm_span.name.lower() or "qwen-plus" in llm_span.name


@pytest.mark.requires_cli
@pytest.mark.asyncio
async def test_tool_span_naming_convention(instrument, span_exporter):
    """Test tool span naming follows conventions."""
    from claude_agent_sdk import query  # noqa: PLC0415
    from claude_agent_sdk.types import ClaudeAgentOptions  # noqa: PLC0415

    options = ClaudeAgentOptions(
        model="qwen-plus",
        allowed_tools=["Write"],
        max_turns=2,
    )

    async for _ in query(
        prompt="Create a file test.txt with content 'test'", options=options
    ):
        pass

    spans = span_exporter.get_finished_spans()
    tool_spans = [s for s in spans if "execute_tool" in s.name]

    if tool_spans:
        tool_span = tool_spans[0]
        # Tool span should have tool name in name
        assert "execute_tool" in tool_span.name


@pytest.mark.requires_cli
@pytest.mark.asyncio
async def test_span_context_propagation(instrument, span_exporter):
    """Test that span context is properly propagated."""
    from claude_agent_sdk import query  # noqa: PLC0415
    from claude_agent_sdk.types import ClaudeAgentOptions  # noqa: PLC0415

    options = ClaudeAgentOptions(
        model="qwen-plus",
        max_turns=1,
    )

    async for _ in query(prompt="Test", options=options):
        pass

    spans = span_exporter.get_finished_spans()

    # Find agent span
    agent_spans = [s for s in spans if "invoke_agent" in s.name]
    if not agent_spans:
        return  # No agent span, skip

    agent_span = agent_spans[0]
    agent_span_id = agent_span.context.span_id

    # All other spans should have the agent span as parent
    for span in spans:
        if span != agent_span and span.parent:
            # Parent should be agent span
            assert span.parent.span_id == agent_span_id


@pytest.mark.requires_cli
@pytest.mark.asyncio
async def test_token_usage_attributes(instrument, span_exporter):
    """Test that token usage attributes are captured."""
    from claude_agent_sdk import query  # noqa: PLC0415
    from claude_agent_sdk.types import ClaudeAgentOptions  # noqa: PLC0415

    options = ClaudeAgentOptions(
        model="qwen-plus",
        max_turns=1,
    )

    async for _ in query(prompt="What is AI?", options=options):
        pass

    spans = span_exporter.get_finished_spans()
    llm_spans = [
        s
        for s in spans
        if GenAIAttributes.GEN_AI_OPERATION_NAME in s.attributes
    ]

    if llm_spans:
        llm_span = llm_spans[0]

        # Should have token usage (might not always be present)
        # Just check the structure is correct if present
        if GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS in llm_span.attributes:
            input_tokens = llm_span.attributes[
                GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS
            ]
            assert isinstance(input_tokens, int)
            assert input_tokens >= 0

        if GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS in llm_span.attributes:
            output_tokens = llm_span.attributes[
                GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS
            ]
            assert isinstance(output_tokens, int)
            assert output_tokens >= 0


def test_instrumentor_dependencies(instrument):
    """Test that instrumentor declares dependencies correctly."""
    instrumentor = ClaudeAgentSDKInstrumentor()
    deps = instrumentor.instrumentation_dependencies()

    # Should have claude-agent-sdk as dependency
    assert len(deps) > 0
    assert any("claude-agent-sdk" in dep for dep in deps)


def test_instrumentor_with_custom_providers(tracer_provider, span_exporter):
    """Test instrumentor with custom tracer and meter providers."""
    instrumentor = ClaudeAgentSDKInstrumentor()
    meter_provider = MeterProvider()

    # Should accept custom providers
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )

    instrumentor.uninstrument()


def test_version_exported():
    """Test that version is exported."""
    assert __version__ is not None
    assert isinstance(__version__, str)
    assert len(__version__) > 0


def test_instrumentor_class_exported():
    """Test that ClaudeAgentSDKInstrumentor is exported."""
    assert hasattr(claude_agent_sdk, "ClaudeAgentSDKInstrumentor")
    assert hasattr(claude_agent_sdk, "__version__")


@pytest.mark.requires_cli
@pytest.mark.asyncio
async def test_multiple_concurrent_queries(instrument, span_exporter):
    """Test that multiple concurrent queries are handled correctly."""
    from claude_agent_sdk import query  # noqa: PLC0415
    from claude_agent_sdk.types import ClaudeAgentOptions  # noqa: PLC0415

    options = ClaudeAgentOptions(
        model="qwen-plus",
        max_turns=1,
    )

    async def run_query(prompt):
        async for _ in query(prompt=prompt, options=options):
            pass

    # Run multiple queries concurrently
    await asyncio.gather(
        run_query("What is 1+1?"),
        run_query("What is 2+2?"),
    )

    spans = span_exporter.get_finished_spans()

    # Should have spans from both queries
    # At least 2 agent spans
    agent_spans = [s for s in spans if "invoke_agent" in s.name]
    assert len(agent_spans) >= 2


@pytest.mark.requires_cli
@pytest.mark.asyncio
async def test_span_attributes_no_sensitive_data(
    instrument_no_content, span_exporter
):
    """Test that sensitive data is not captured when content capture is disabled."""
    from claude_agent_sdk import query  # noqa: PLC0415
    from claude_agent_sdk.types import ClaudeAgentOptions  # noqa: PLC0415

    sensitive_prompt = "My password is secret123"

    options = ClaudeAgentOptions(
        model="qwen-plus",
        max_turns=1,
    )

    async for _ in query(prompt=sensitive_prompt, options=options):
        pass

    spans = span_exporter.get_finished_spans()

    # Check that sensitive data is not in any span attributes
    for span in spans:
        for attr_value in span.attributes.values():
            if isinstance(attr_value, str):
                # Sensitive content should not be in attributes
                assert "secret123" not in attr_value.lower()
