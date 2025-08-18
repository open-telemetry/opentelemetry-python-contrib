from uuid import uuid4

import pytest

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.util.genai.client import (
    llm_start,
    llm_stop,
)
from opentelemetry.util.genai.types import (
    ChatGeneration,
    Message,
)


@pytest.fixture
def telemetry_setup():
    """Set up telemetry providers for testing"""
    # Set up in-memory span exporter to capture spans
    memory_exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(memory_exporter))

    # Set the tracer provider
    trace.set_tracer_provider(tracer_provider)

    yield memory_exporter

    # Cleanup
    memory_exporter.clear()
    # Reset to default tracer provider
    trace.set_tracer_provider(trace.NoOpTracerProvider())


def test_llm_start_and_stop_creates_span(telemetry_setup):
    memory_exporter = telemetry_setup

    run_id = uuid4()
    message = Message(content="hello world", type="Human", name="message name")
    chat_generation = ChatGeneration(content="hello back", type="AI")

    # Start and stop LLM invocation
    llm_start(
        [message], run_id=run_id, custom_attr="value", system="test-system"
    )
    invocation = llm_stop(
        run_id, chat_generations=[chat_generation], extra="info"
    )

    # Get the spans that were created
    spans = memory_exporter.get_finished_spans()

    # Verify span was created
    assert len(spans) == 1
    span = spans[0]

    # Verify span properties
    assert span.name == "test-system.chat"
    assert span.kind == trace.SpanKind.CLIENT

    # Verify span attributes
    assert span.attributes.get("gen_ai.operation.name") == "chat"
    assert span.attributes.get("gen_ai.system") == "test-system"
    # Add more attribute checks as needed

    # Verify span timing
    assert span.start_time > 0
    assert span.end_time > span.start_time

    # Verify invocation data
    assert invocation.run_id == run_id
    assert invocation.attributes.get("custom_attr") == "value"
    assert invocation.attributes.get("extra") == "info"
