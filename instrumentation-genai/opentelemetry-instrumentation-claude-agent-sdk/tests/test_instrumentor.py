# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ClaudeAgentSDKInstrumentor class."""

from opentelemetry.instrumentation.claude_agent_sdk import (
    ClaudeAgentSDKInstrumentor,
)


def test_instrumentor_instantiation():
    """Test that the instrumentor can be instantiated."""
    instrumentor = ClaudeAgentSDKInstrumentor()
    assert instrumentor is not None
    assert isinstance(instrumentor, ClaudeAgentSDKInstrumentor)


def test_instrumentation_dependencies():
    """Test that instrumentation dependencies are correctly reported."""
    instrumentor = ClaudeAgentSDKInstrumentor()
    dependencies = instrumentor.instrumentation_dependencies()

    assert dependencies is not None
    assert len(dependencies) > 0
    assert "claude-agent-sdk >= 0.1.14" in dependencies


def test_instrument_uninstrument_cycle(
    tracer_provider, logger_provider, meter_provider
):
    """Test that instrument() and uninstrument() can be called multiple times."""
    instrumentor = ClaudeAgentSDKInstrumentor()

    # First instrumentation
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )

    # First uninstrumentation
    instrumentor.uninstrument()

    # Second instrumentation (should work)
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )

    # Second uninstrumentation
    instrumentor.uninstrument()


def test_multiple_instrumentation_calls(
    tracer_provider, logger_provider, meter_provider
):
    """Test that multiple instrument() calls don't cause issues."""
    instrumentor = ClaudeAgentSDKInstrumentor()

    # First call
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )

    # Second call (should be idempotent or handle gracefully)
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )

    # Clean up
    instrumentor.uninstrument()


def test_uninstrument_without_instrument():
    """Test that uninstrument() can be called without prior instrument()."""
    instrumentor = ClaudeAgentSDKInstrumentor()

    # This should not raise an error
    instrumentor.uninstrument()


def test_instrument_with_no_providers():
    """Test that instrument() works without explicit providers."""
    instrumentor = ClaudeAgentSDKInstrumentor()

    # Should use global providers
    instrumentor.instrument()

    # Clean up
    instrumentor.uninstrument()


def test_instrumentor_has_required_attributes():
    """Test that the instrumentor has the required methods."""
    instrumentor = ClaudeAgentSDKInstrumentor()

    assert hasattr(instrumentor, "instrument")
    assert hasattr(instrumentor, "uninstrument")
    assert hasattr(instrumentor, "instrumentation_dependencies")
    assert callable(instrumentor.instrument)
    assert callable(instrumentor.uninstrument)
    assert callable(instrumentor.instrumentation_dependencies)
