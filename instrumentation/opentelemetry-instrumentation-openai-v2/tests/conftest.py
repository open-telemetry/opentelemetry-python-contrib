"""Unit tests configuration module."""

import os

import pytest
from openai import OpenAI

from opentelemetry import _events, _logs, trace
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
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


@pytest.fixture(scope="session")
def span_exporter():
    exporter = InMemorySpanExporter()
    processor = SimpleSpanProcessor(exporter)

    provider = TracerProvider()
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    return exporter


@pytest.fixture(scope="session")
def log_exporter():
    exporter = InMemoryLogExporter()
    processor = SimpleLogRecordProcessor(exporter)

    provider = LoggerProvider()
    provider.add_log_record_processor(processor)

    event_provider = EventLoggerProvider(provider)

    _logs.set_logger_provider(provider)
    _events.set_event_logger_provider(event_provider)

    return exporter


@pytest.fixture(autouse=True)
def clear_exporter(span_exporter, log_exporter):
    span_exporter.clear()
    log_exporter.clear()


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


@pytest.fixture(scope="session", autouse=True)
def instrument():
    OpenAIInstrumentor().instrument()


@pytest.fixture(scope="session", autouse=True)
def uninstrument():
    # OpenAIInstrumentor().uninstrument()
    pass


def scrub_response_headers(response):
    """
    This scrubs sensitive response headers. Note they are case-sensitive!
    """
    response["headers"]["openai-organization"] = "test_organization"
    response["headers"]["Set-Cookie"] = "test_set_cookie"
    return response
