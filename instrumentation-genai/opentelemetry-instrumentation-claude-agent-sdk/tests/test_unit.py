"""Unit tests for Claude Agent SDK instrumentation without VCR."""

import os

from opentelemetry.instrumentation.claude_agent_sdk import (
    ClaudeAgentSDKInstrumentor,
)
from opentelemetry.instrumentation.claude_agent_sdk.utils import (
    extract_usage_metadata,
    infer_provider_from_base_url,
    sum_anthropic_tokens,
)
from opentelemetry.sdk.trace import TracerProvider


def test_instrumentor_init():
    """Test that instrumentor can be initialized."""
    instrumentor = ClaudeAgentSDKInstrumentor()
    assert instrumentor is not None


def test_instrument_and_uninstrument():
    """Test that instrumentation can be applied and removed."""
    tracer_provider = TracerProvider()
    instrumentor = ClaudeAgentSDKInstrumentor()

    # Should not raise
    instrumentor.instrument(tracer_provider=tracer_provider)

    # Should not raise
    instrumentor.uninstrument()


def test_instrumentation_dependencies():
    """Test that instrumentation dependencies are defined."""
    instrumentor = ClaudeAgentSDKInstrumentor()
    deps = instrumentor.instrumentation_dependencies()

    assert deps is not None
    assert len(deps) > 0
    assert "claude-agent-sdk" in deps[0]


def test_usage_extraction():
    """Test usage metadata extraction."""
    # Test with dict
    usage = {
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_read_input_tokens": 10,
        "cache_creation_input_tokens": 5,
    }

    result = extract_usage_metadata(usage)
    assert result["input_tokens"] == 100
    assert result["output_tokens"] == 50
    # Cache tokens are temporarily extracted for summing
    assert result["cache_read_input_tokens"] == 10
    assert result["cache_creation_input_tokens"] == 5


def test_sum_anthropic_tokens():
    """Test Anthropic token summation."""
    usage = {
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_read_input_tokens": 10,
        "cache_creation_input_tokens": 5,
    }

    result = sum_anthropic_tokens(usage)

    # Should sum all input tokens
    assert result["input_tokens"] == 115  # 100 + 10 + 5
    assert result["output_tokens"] == 50
    # Only standard OpenTelemetry fields in result
    assert "cache_read_input_tokens" not in result
    assert "cache_creation_input_tokens" not in result
    assert "total_tokens" not in result


def test_infer_provider_from_base_url():
    """Test provider inference from ANTHROPIC_BASE_URL."""
    # Save original env var
    original_url = os.environ.get("ANTHROPIC_BASE_URL")

    try:
        # Test DashScope (extended provider)
        os.environ["ANTHROPIC_BASE_URL"] = (
            "https://dashscope.aliyuncs.com/apps/anthropic"
        )
        assert infer_provider_from_base_url() == "dashscope"

        # Test aliyuncs (alternative check for dashscope)
        result = infer_provider_from_base_url("https://api.aliyuncs.com/v1")
        assert result == "dashscope"

        # Test Moonshot (extended provider)
        result = infer_provider_from_base_url("https://api.moonshot.cn/v1")
        assert result == "moonshot"

        # Test Anthropic (defaults to anthropic)
        os.environ["ANTHROPIC_BASE_URL"] = "https://api.anthropic.com"
        assert infer_provider_from_base_url() == "anthropic"

        # Test ZhipuAI (defaults to anthropic)
        os.environ["ANTHROPIC_BASE_URL"] = (
            "https://open.bigmodel.cn/api/anthropic"
        )
        assert infer_provider_from_base_url() == "anthropic"

        # Test custom/unknown provider (defaults to anthropic)
        result = infer_provider_from_base_url(
            "https://api.unknown-provider.com"
        )
        assert result == "anthropic"

        # Test empty (defaults to anthropic)
        if "ANTHROPIC_BASE_URL" in os.environ:
            del os.environ["ANTHROPIC_BASE_URL"]
        assert infer_provider_from_base_url() == "anthropic"

    finally:
        # Restore original env var
        if original_url is not None:
            os.environ["ANTHROPIC_BASE_URL"] = original_url
        elif "ANTHROPIC_BASE_URL" in os.environ:
            del os.environ["ANTHROPIC_BASE_URL"]
