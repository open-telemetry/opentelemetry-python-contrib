"""Unit tests configuration module."""

import os

import pytest
from openai import OpenAI

from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
from opentelemetry.instrumentation.openai_v2.utils import (
    OTEL_INSTRUMENTATION_OPENAI_CAPTURE_MESSAGE_CONTENT,
)
from opentelemetry.sdk._events import EventLoggerProvider
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    InMemoryLogExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


@pytest.fixture(scope="function")
def span_exporter():
    exporter = InMemorySpanExporter()
    yield exporter


@pytest.fixture(scope="function")
def log_exporter():
    exporter = InMemoryLogExporter()
    yield exporter


@pytest.fixture(scope="function")
def tracer_provider(span_exporter):
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    return provider


@pytest.fixture(scope="function")
def event_provider(log_exporter):
    provider = LoggerProvider()
    provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))
    event_provider = EventLoggerProvider(provider)

    return event_provider


@pytest.fixture(autouse=True)
def environment():
    if not os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = "test-api-key"


@pytest.fixture
def openai_client():
    return OpenAI()


@pytest.fixture(scope="module")
def vcr_config():
    return {
        "filter_headers": ["authorization", "api-key"],
        "decode_compressed_response": True,
        "before_record_response": scrub_response_headers,
    }


@pytest.fixture(scope="function")
def instrument_no_content(tracer_provider, event_provider):
    instrumentor = OpenAIInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider, event_provider=event_provider
    )

    yield instrumentor
    instrumentor.uninstrument()


@pytest.fixture(scope="function")
def instrument_with_content(tracer_provider, event_provider):
    os.environ.update(
        {OTEL_INSTRUMENTATION_OPENAI_CAPTURE_MESSAGE_CONTENT: "True"}
    )
    instrumentor = OpenAIInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider, event_provider=event_provider
    )

    yield instrumentor
    os.environ.pop(OTEL_INSTRUMENTATION_OPENAI_CAPTURE_MESSAGE_CONTENT, None)
    instrumentor.uninstrument()


def scrub_response_headers(response):
    """
    This scrubs sensitive response headers. Note they are case-sensitive!
    """
    response["headers"]["openai-organization"] = "test_organization"
    response["headers"]["Set-Cookie"] = "test_set_cookie"
    return response
