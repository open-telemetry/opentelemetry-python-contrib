from __future__ import annotations

import sys
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent
stub_path = TESTS_ROOT / "stubs"
if str(stub_path) not in sys.path:
    sys.path.insert(0, str(stub_path))

from agents.tracing import (  # noqa: E402
    get_trace_provider,
    set_trace_processors,
)

from opentelemetry.instrumentation.openai_agents import (  # noqa: E402
    OpenAIAgentsInstrumentor,
)
from opentelemetry.instrumentation.openai_agents.package import (  # noqa: E402
    _instruments,
)
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402


def test_double_instrument_is_noop():
    set_trace_processors([])
    provider = TracerProvider()
    instrumentor = OpenAIAgentsInstrumentor()

    instrumentor.instrument(tracer_provider=provider)
    trace_provider = get_trace_provider()
    assert len(trace_provider._multi_processor._processors) == 1

    instrumentor.instrument(tracer_provider=provider)
    assert len(trace_provider._multi_processor._processors) == 1

    instrumentor.uninstrument()
    instrumentor.uninstrument()
    set_trace_processors([])


def test_instrumentation_dependencies_exposed():
    instrumentor = OpenAIAgentsInstrumentor()
    assert instrumentor.instrumentation_dependencies() == _instruments


def test_env_fallback_configuration(monkeypatch):
    set_trace_processors([])
    provider = TracerProvider()
    instrumentor = OpenAIAgentsInstrumentor()

    monkeypatch.setenv(
        "OTEL_INSTRUMENTATION_OPENAI_AGENTS_AGENT_NAME", "EnvAgent"
    )
    monkeypatch.setenv(
        "OTEL_INSTRUMENTATION_OPENAI_AGENTS_AGENT_ID", "agent-env"
    )
    monkeypatch.setenv(
        "OTEL_INSTRUMENTATION_OPENAI_AGENTS_AGENT_DESCRIPTION",
        "Env provided description",
    )
    monkeypatch.setenv(
        "OTEL_INSTRUMENTATION_OPENAI_AGENTS_BASE_URL",
        "https://env.example.com",
    )
    monkeypatch.setenv(
        "OTEL_INSTRUMENTATION_OPENAI_AGENTS_SERVER_ADDRESS", "env.example.com"
    )
    monkeypatch.setenv(
        "OTEL_INSTRUMENTATION_OPENAI_AGENTS_SERVER_PORT",
        "8080",
    )

    try:
        instrumentor.instrument(tracer_provider=provider)
        processor = instrumentor._processor
        assert processor is not None
        assert processor.agent_name == "EnvAgent"
        assert processor.agent_id == "agent-env"
        assert processor.agent_description == "Env provided description"
        assert processor.base_url == "https://env.example.com"
        assert processor.server_address == "env.example.com"
        assert processor.server_port == 8080
    finally:
        instrumentor.uninstrument()
        set_trace_processors([])
