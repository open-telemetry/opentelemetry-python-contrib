import pytest
from google.api_core.exceptions import BadRequest, NotFound
from vertexai.generative_models import (
    Content,
    GenerationConfig,
    GenerativeModel,
    Part,
)

from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import StatusCode


@pytest.mark.vcr
def test_generate_content(
    span_exporter: InMemorySpanExporter,
    instrument_with_content: VertexAIInstrumentor,
):
    model = GenerativeModel("gemini-1.5-flash-002")
    model.generate_content(
        [
            Content(role="user", parts=[Part.from_text("Say this is a test")]),
        ]
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "chat gemini-1.5-flash-002"
    assert dict(spans[0].attributes) == {
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": "gemini-1.5-flash-002",
        "gen_ai.system": "vertex_ai",
    }


@pytest.mark.vcr
def test_generate_content_empty_model(
    span_exporter: InMemorySpanExporter,
    instrument_with_content: VertexAIInstrumentor,
):
    model = GenerativeModel("")
    try:
        model.generate_content(
            [
                Content(
                    role="user", parts=[Part.from_text("Say this is a test")]
                )
            ],
        )
    except ValueError:
        pass

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "chat"
    # Captures invalid params
    assert dict(spans[0].attributes) == {
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": "",
        "gen_ai.system": "vertex_ai",
    }
    assert_span_error(spans[0])


@pytest.mark.vcr
def test_generate_content_missing_model(
    span_exporter: InMemorySpanExporter,
    instrument_with_content: VertexAIInstrumentor,
):
    model = GenerativeModel("gemini-does-not-exist")
    try:
        model.generate_content(
            [
                Content(
                    role="user", parts=[Part.from_text("Say this is a test")]
                )
            ],
        )
    except NotFound:
        pass

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "chat gemini-does-not-exist"
    # Captures invalid params
    assert dict(spans[0].attributes) == {
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": "gemini-does-not-exist",
        "gen_ai.system": "vertex_ai",
    }
    assert_span_error(spans[0])


@pytest.mark.vcr
def test_generate_content_invalid_temperature(
    span_exporter: InMemorySpanExporter,
    instrument_with_content: VertexAIInstrumentor,
):
    model = GenerativeModel("gemini-1.5-flash-002")
    try:
        # Temperature out of range causes error
        model.generate_content(
            [
                Content(
                    role="user", parts=[Part.from_text("Say this is a test")]
                )
            ],
            generation_config=GenerationConfig(temperature=1000),
        )
    except BadRequest:
        pass

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "chat gemini-1.5-flash-002"
    assert dict(spans[0].attributes) == {
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": "gemini-1.5-flash-002",
        "gen_ai.request.temperature": 1000.0,
        "gen_ai.system": "vertex_ai",
    }
    assert_span_error(spans[0])


@pytest.mark.vcr()
def test_generate_content_extra_params(span_exporter, instrument_no_content):
    generation_config = GenerationConfig(
        top_k=2,
        top_p=0.95,
        temperature=0.2,
        stop_sequences=["\n\n\n"],
        max_output_tokens=5,
        presence_penalty=-1.5,
        frequency_penalty=1.0,
        seed=12345,
    )
    model = GenerativeModel("gemini-1.5-flash-002")
    model.generate_content(
        [
            Content(role="user", parts=[Part.from_text("Say this is a test")]),
        ],
        generation_config=generation_config,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert dict(spans[0].attributes) == {
        "gen_ai.operation.name": "chat",
        "gen_ai.request.frequency_penalty": 1.0,
        "gen_ai.request.max_tokens": 5,
        "gen_ai.request.model": "gemini-1.5-flash-002",
        "gen_ai.request.presence_penalty": -1.5,
        "gen_ai.request.stop_sequences": ("\n\n\n",),
        "gen_ai.request.temperature": 0.20000000298023224,
        "gen_ai.request.top_p": 0.949999988079071,
        "gen_ai.system": "vertex_ai",
    }


def assert_span_error(span: ReadableSpan) -> None:
    # Sets error status
    assert span.status.status_code == StatusCode.ERROR
    # Records exception event
    error_events = [e for e in span.events if e.name == "exception"]
    assert error_events != []
