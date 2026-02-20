"""Mock-based tests for Claude Agent SDK instrumentation."""

from unittest.mock import Mock, patch

import pytest

from opentelemetry.instrumentation.claude_agent_sdk import (
    ClaudeAgentSDKInstrumentor,
)
from opentelemetry.instrumentation.claude_agent_sdk.utils import (
    extract_usage_from_result_message,
    extract_usage_metadata,
    sum_anthropic_tokens,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)


@pytest.mark.requires_cli
@pytest.mark.asyncio
async def test_agent_span_attributes_complete(instrument, span_exporter):
    """Test that agent span has all required attributes."""
    from claude_agent_sdk import query  # noqa: PLC0415
    from claude_agent_sdk.types import (  # noqa: PLC0415
        AssistantMessage,
        ClaudeAgentOptions,
        TextBlock,
    )

    # Mock the query function to return controlled data
    with patch("claude_agent_sdk.query") as mock_query:
        # Create mock messages
        mock_assistant_msg = Mock(spec=AssistantMessage)
        mock_assistant_msg.content = [Mock(spec=TextBlock, text="4")]

        async def mock_generator(*args, **kwargs):
            yield mock_assistant_msg

        mock_query.return_value = mock_generator()

        # Execute with instrumentation
        options = ClaudeAgentOptions(model="qwen-plus")
        messages = []
        async for msg in query(prompt="2+2?", options=options):
            messages.append(msg)

    # Get spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) > 0

    # Find agent span
    agent_spans = [s for s in spans if "invoke_agent" in s.name]
    if agent_spans:
        agent_span = agent_spans[0]

        # Verify all semantic convention attributes
        assert GenAIAttributes.GEN_AI_PROVIDER_NAME in agent_span.attributes
        assert GenAIAttributes.GEN_AI_REQUEST_MODEL in agent_span.attributes


def test_utils_extract_usage_with_none(instrument):
    """Test usage extraction with None input."""
    result = extract_usage_metadata(None)
    assert result == {}


def test_utils_extract_usage_with_empty_dict(instrument):
    """Test usage extraction with empty dict."""
    result = extract_usage_metadata({})
    assert result == {}


def test_utils_extract_usage_with_invalid_values(instrument):
    """Test usage extraction with invalid values."""
    usage = {
        "input_tokens": "invalid",
        "output_tokens": None,
        "cache_read_input_tokens": "not_a_number",
    }

    result = extract_usage_metadata(usage)
    # Should handle invalid values gracefully
    assert isinstance(result, dict)


def test_utils_sum_tokens_with_missing_fields(instrument):
    """Test token summation with missing fields."""
    # Missing output_tokens - should default to 0
    result = sum_anthropic_tokens({"input_tokens": 100})
    assert result["input_tokens"] == 100
    assert result["output_tokens"] == 0

    # Missing input_tokens - should default to 0
    result = sum_anthropic_tokens({"output_tokens": 50})
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 50


def test_utils_sum_tokens_with_cache_details(instrument):
    """Test token summation with cache details in different formats."""
    # Note: Current implementation doesn't support nested input_token_details
    # It only reads top-level cache_read_input_tokens and cache_creation_input_tokens

    # Format 1: nested input_token_details (NOT supported yet)
    usage1 = {
        "input_tokens": 100,
        "output_tokens": 50,
        "input_token_details": {
            "cache_read": 10,
            "cache_creation": 5,
        },
    }
    result1 = sum_anthropic_tokens(usage1)
    # Since nested format is not supported, only gets base input_tokens
    assert result1["input_tokens"] == 100  # No cache added
    assert result1["output_tokens"] == 50

    # Format 2: flat cache fields (supported)
    usage2 = {
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_read_input_tokens": 10,
        "cache_creation_input_tokens": 5,
    }
    result2 = sum_anthropic_tokens(usage2)
    assert result2["input_tokens"] == 115  # 100 + 10 + 5
    assert result2["output_tokens"] == 50


def test_instrumentor_double_instrument(instrument, tracer_provider):
    """Test that double instrumentation doesn't cause issues."""
    # First instrumentation already done by fixture
    # Try to instrument again
    instrumentor2 = ClaudeAgentSDKInstrumentor()
    instrumentor2.instrument(tracer_provider=tracer_provider)

    # Should not raise
    instrumentor2.uninstrument()


def test_instrumentor_uninstrument_without_instrument():
    """Test uninstrument without prior instrument."""
    instrumentor = ClaudeAgentSDKInstrumentor()
    # Should not raise even if not instrumented
    instrumentor.uninstrument()


def test_usage_extraction_from_result_message_no_usage(instrument):
    """Test usage extraction when result message has no usage."""
    # Mock message without usage
    mock_msg = Mock()
    mock_msg.usage = None

    result = extract_usage_from_result_message(mock_msg)
    assert result == {}


def test_usage_extraction_from_result_message_with_usage(instrument):
    """Test usage extraction with valid usage data."""
    # Mock message with usage
    mock_msg = Mock()
    mock_msg.usage = Mock()
    mock_msg.usage.input_tokens = 100
    mock_msg.usage.output_tokens = 50
    mock_msg.usage.cache_read_input_tokens = 10
    mock_msg.usage.cache_creation_input_tokens = 5

    result = extract_usage_from_result_message(mock_msg)
    # Cache tokens should be summed into input_tokens
    assert result["input_tokens"] == 115  # 100 + 10 + 5
    assert result["output_tokens"] == 50
    # Only standard OpenTelemetry fields
    assert "total_tokens" not in result
    assert "cache_read_input_tokens" not in result


def test_extract_usage_with_object_style_access(instrument):
    """Test usage extraction with object attribute access."""
    # Mock object with attributes
    mock_usage = Mock()
    mock_usage.input_tokens = 100
    mock_usage.output_tokens = 50

    result = extract_usage_metadata(mock_usage)
    assert result["input_tokens"] == 100
    assert result["output_tokens"] == 50
