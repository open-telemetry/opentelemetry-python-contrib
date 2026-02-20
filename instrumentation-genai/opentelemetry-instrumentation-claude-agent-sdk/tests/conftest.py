"""Unit tests configuration module."""

import os

import pytest

# Set up environment variables BEFORE any claude_agent_sdk modules are imported
# This is critical because claude_agent_sdk reads environment variables at module import time
if "ANTHROPIC_API_KEY" not in os.environ:
    # Use DashScope proxy for testing
    os.environ["ANTHROPIC_BASE_URL"] = (
        "https://dashscope.aliyuncs.com/apps/anthropic"
    )
    os.environ["ANTHROPIC_API_KEY"] = "test_anthropic_api_key"
    os.environ["DASHSCOPE_API_KEY"] = "test_dashscope_api_key"

# Set GenAI semantic conventions environment variables
os.environ.setdefault(
    "OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental"
)
os.environ.setdefault(
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "SPAN_ONLY"
)

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.claude_agent_sdk import (
    ClaudeAgentSDKInstrumentor,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
)


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "requires_cli: mark test as requiring Claude CLI executable (skipped in CI)",
    )


def pytest_collection_modifyitems(config, items):
    """Skip tests marked with 'requires_cli' if ANTHROPIC_API_KEY is not set or is mock."""
    # Check if we have a real API key (not the test mock)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    has_real_api = api_key and api_key != "test_anthropic_api_key"

    skip_cli = pytest.mark.skip(
        reason="Requires real ANTHROPIC_API_KEY and Claude CLI (not available in CI)"
    )

    for item in items:
        if "requires_cli" in item.keywords and not has_real_api:
            item.add_marker(skip_cli)


@pytest.fixture(scope="function", name="span_exporter")
def fixture_span_exporter():
    """Create an in-memory span exporter for testing."""
    exporter = InMemorySpanExporter()
    yield exporter


@pytest.fixture(scope="function", name="tracer_provider")
def fixture_tracer_provider(span_exporter):
    """Create a tracer provider with in-memory exporter."""
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    return provider


@pytest.fixture(scope="function")
def instrument(tracer_provider):
    """Instrument Claude Agent SDK for testing."""
    instrumentor = ClaudeAgentSDKInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)

    yield instrumentor

    instrumentor.uninstrument()


@pytest.fixture(scope="function")
def instrument_no_content(tracer_provider):
    """Instrument Claude Agent SDK with message content capture disabled."""
    # Reset global state to allow environment variable changes to take effect
    _OpenTelemetrySemanticConventionStability._initialized = False

    os.environ.update(
        {
            OTEL_SEMCONV_STABILITY_OPT_IN: "gen_ai_latest_experimental",
            OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "false",
        }
    )

    instrumentor = ClaudeAgentSDKInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)

    yield instrumentor

    os.environ.pop(OTEL_SEMCONV_STABILITY_OPT_IN, None)
    os.environ.pop(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None)
    instrumentor.uninstrument()
    # Reset global state after test
    _OpenTelemetrySemanticConventionStability._initialized = False


@pytest.fixture(scope="function")
def instrument_with_content(tracer_provider):
    """Instrument Claude Agent SDK with message content capture enabled."""
    # Reset global state to allow environment variable changes to take effect
    _OpenTelemetrySemanticConventionStability._initialized = False

    os.environ.update(
        {
            OTEL_SEMCONV_STABILITY_OPT_IN: "gen_ai_latest_experimental",
            OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "SPAN_ONLY",
        }
    )

    instrumentor = ClaudeAgentSDKInstrumentor()
    instrumentor.instrument(tracer_provider=tracer_provider)

    yield instrumentor

    os.environ.pop(OTEL_SEMCONV_STABILITY_OPT_IN, None)
    os.environ.pop(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, None)
    instrumentor.uninstrument()
    # Reset global state after test
    _OpenTelemetrySemanticConventionStability._initialized = False
