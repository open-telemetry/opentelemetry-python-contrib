from __future__ import annotations

import pytest
from google.api_core.exceptions import BadRequest, NotFound
from vertexai.generative_models import (
    Content,
    GenerationConfig,
    GenerativeModel,
    Image,
    Part,
)
from vertexai.preview.generative_models import (
    GenerativeModel as PreviewGenerativeModel,
)

from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor

# Backward compatibility for InMemoryLogExporter -> InMemoryLogRecordExporter rename
try:
    from opentelemetry.sdk._logs._internal.export.in_memory_log_exporter import (  # pylint: disable=no-name-in-module
        InMemoryLogRecordExporter,
    )
except ImportError:
    # Fallback to old name for compatibility with older SDK versions
    from opentelemetry.sdk._logs._internal.export.in_memory_log_exporter import (
        InMemoryLogExporter as InMemoryLogRecordExporter,
    )
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import StatusCode


@pytest.mark.vcr()
def test_generate_content_with_files(
    span_exporter: InMemorySpanExporter,
    log_exporter: InMemoryLogRecordExporter,
    generate_content: callable,
    instrument_with_experimental_semconvs: VertexAIInstrumentor,
):
    model = GenerativeModel("gemini-2.5-pro")
    generate_content(
        model,
        [
            Content(
                role="user",
                parts=[
                    Part.from_text("Say this is a test"),
                    Part.from_uri(
                        mime_type="image/jpeg",
                        uri="https://images.pdimagearchive.org/collections/microscopic-delights/1lede-0021.jpg",
                    ),
                    Part.from_image(
                        Image.from_bytes(
                            "iVBORw0KGgoAAAANSUhEUgAAAAUAAAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO9TXL0Y4OHwAAAABJRU5ErkJggg=="
                        )
                    ),
                ],
            ),
        ],
    )

    # Emits span
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "chat gemini-2.5-pro"
    assert dict(spans[0].attributes) == {
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": "gemini-2.5-pro",
        "gen_ai.response.finish_reasons": ("stop",),
        "gen_ai.response.model": "gemini-2.5-pro",
        "gen_ai.usage.input_tokens": 521,
        "gen_ai.usage.output_tokens": 5,
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
        "gen_ai.input.messages": '[{"role":"user","parts":[{"content":"Say this is a test","type":"text"},{"mime_type":"image/jpeg","uri":"https://images.pdimagearchive.org/collections/microscopic-delights/1lede-0021.jpg","type":"file_data"},{"data":"iVBORw0KGgoAAAANSUhEUgAAAAUAAAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO9TXL0Y4OHwAAAABJRU5ErkJggg==","mime_type":"image/jpeg","type":"blob"}]}]',
        "gen_ai.output.messages": '[{"role":"model","parts":[{"content":"This is a test.","type":"text"}],"finish_reason":"stop"}]',
    }

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 1
    log = logs[0].log_record
    assert log.attributes == {
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": "gemini-2.5-pro",
        "gen_ai.response.model": "gemini-2.5-pro",
        "gen_ai.response.finish_reasons": ("stop",),
        "gen_ai.usage.input_tokens": 521,
        "gen_ai.usage.output_tokens": 5,
        "gen_ai.input.messages": (
            {
                "role": "user",
                "parts": (
                    {"content": "Say this is a test", "type": "text"},
                    {
                        "mime_type": "image/jpeg",
                        "uri": "https://images.pdimagearchive.org/collections/microscopic-delights/1lede-0021.jpg",
                        "type": "file_data",
                    },
                    {
                        "data": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x05\x00\x00\x00\x05\x08\x06\x00\x00\x00\x8do&\xe5\x00\x00\x00\x1cIDAT\x08\xd7c\xf8\xff\xff?\xc3\x7f\x06 \x05\xc3 \x12\x84\xd01\xf1\x82X\xcd\x04\x00\x0e\xf55\xcb\xd1\x8e\x0e\x1f\x00\x00\x00\x00IEND\xaeB`\x82",
                        "mime_type": "image/jpeg",
                        "type": "blob",
                    },
                ),
            },
        ),
        "gen_ai.output.messages": (
            {
                "role": "model",
                "parts": ({"content": "This is a test.", "type": "text"},),
                "finish_reason": "stop",
            },
        ),
    }


@pytest.mark.vcr()
def test_generate_content_without_events(
    span_exporter: InMemorySpanExporter,
    log_exporter: InMemoryLogRecordExporter,
    generate_content: callable,
    instrument_with_experimental_semconvs: VertexAIInstrumentor,
):
    model = GenerativeModel("gemini-2.5-pro")
    generate_content(
        model,
        [
            Content(role="user", parts=[Part.from_text("Say this is a test")]),
        ],
    )

    # Emits span
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "chat gemini-2.5-pro"
    assert dict(spans[0].attributes) == {
        "gen_ai.operation.name": "chat",
        "gen_ai.output.messages": '[{"role":"model","parts":[{"content":"This is a test.","type":"text"}],"finish_reason":"stop"}]',
        "gen_ai.input.messages": '[{"role":"user","parts":[{"content":"Say this is a test","type":"text"}]}]',
        "gen_ai.request.model": "gemini-2.5-pro",
        "gen_ai.response.finish_reasons": ("stop",),
        "gen_ai.response.model": "gemini-2.5-pro",
        "gen_ai.usage.input_tokens": 5,
        "gen_ai.usage.output_tokens": 5,
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
    }

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 1
    log = logs[0].log_record
    print(log.attributes)
    assert log.attributes == {
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": "gemini-2.5-pro",
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
        "gen_ai.response.model": "gemini-2.5-pro",
        "gen_ai.response.finish_reasons": ("stop",),
        "gen_ai.usage.input_tokens": 5,
        "gen_ai.usage.output_tokens": 5,
        "gen_ai.input.messages": (
            {
                "role": "user",
                "parts": ({"content": "Say this is a test", "type": "text"},),
            },
        ),
        "gen_ai.output.messages": (
            {
                "role": "model",
                "parts": ({"content": "This is a test.", "type": "text"},),
                "finish_reason": "stop",
            },
        ),
    }


@pytest.mark.vcr()
def test_generate_content_empty_model(
    span_exporter: InMemorySpanExporter,
    generate_content: callable,
    instrument_with_experimental_semconvs: VertexAIInstrumentor,
):
    model = GenerativeModel("")
    try:
        generate_content(
            model,
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
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
        "gen_ai.input.messages": '[{"role":"user","parts":[{"content":"Say this is a test","type":"text"}]}]',
    }
    assert_span_error(spans[0])


@pytest.mark.vcr()
def test_generate_content_missing_model(
    span_exporter: InMemorySpanExporter,
    generate_content: callable,
    instrument_with_experimental_semconvs: VertexAIInstrumentor,
):
    model = GenerativeModel("gemini-does-not-exist")
    try:
        generate_content(
            model,
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
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
        "gen_ai.input.messages": '[{"role":"user","parts":[{"content":"Say this is a test","type":"text"}]}]',
    }
    assert_span_error(spans[0])


@pytest.mark.vcr()
def test_generate_content_invalid_temperature(
    span_exporter: InMemorySpanExporter,
    generate_content: callable,
    instrument_with_experimental_semconvs: VertexAIInstrumentor,
):
    model = GenerativeModel("gemini-2.5-pro")
    try:
        # Temperature out of range causes error
        generate_content(
            model,
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
    assert spans[0].name == "chat gemini-2.5-pro"
    assert dict(spans[0].attributes) == {
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": "gemini-2.5-pro",
        "gen_ai.request.temperature": 1000.0,
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
        "gen_ai.input.messages": '[{"role":"user","parts":[{"content":"Say this is a test","type":"text"}]}]',
    }
    assert_span_error(spans[0])


@pytest.mark.vcr()
def test_generate_content_invalid_role(
    log_exporter: InMemoryLogRecordExporter,
    generate_content: callable,
    instrument_with_experimental_semconvs: VertexAIInstrumentor,
):
    model = GenerativeModel("gemini-2.5-pro")
    try:
        # Fails because role must be "user" or "model"
        generate_content(
            model,
            [
                Content(
                    role="invalid_role",
                    parts=[Part.from_text("Say this is a test")],
                )
            ],
        )
    except BadRequest:
        pass

    # Emits the faulty content which caused the request to fail
    logs = log_exporter.get_finished_logs()
    assert len(logs) == 1
    log = logs[0].log_record
    assert log.attributes == {
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": "gemini-2.5-pro",
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
        "gen_ai.input.messages": (
            {
                "role": "invalid_role",
                "parts": ({"type": "text", "content": "Say this is a test"},),
            },
        ),
    }


@pytest.mark.vcr()
def test_generate_content_extra_params(
    span_exporter,
    instrument_no_content_with_experimental_semconvs,
    generate_content: callable,
):
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
    model = GenerativeModel("gemini-2.5-pro")
    generate_content(
        model,
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
        "gen_ai.request.model": "gemini-2.5-pro",
        "gen_ai.request.presence_penalty": -1.5,
        "gen_ai.request.stop_sequences": ("\n\n\n",),
        "gen_ai.request.temperature": 0.20000000298023224,
        "gen_ai.request.top_p": 0.949999988079071,
        "gen_ai.response.finish_reasons": ("length",),
        "gen_ai.response.model": "gemini-2.5-pro",
        "gen_ai.request.seed": 12345,
        "gen_ai.usage.input_tokens": 5,
        "gen_ai.usage.output_tokens": 0,
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
    }


def assert_span_error(span: ReadableSpan) -> None:
    # Sets error status
    assert span.status.status_code == StatusCode.ERROR

    # TODO: check thate error.type is set
    # https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-spans.md

    # Records exception event
    error_events = [e for e in span.events if e.name == "exception"]
    assert error_events != []


@pytest.mark.vcr()
def test_generate_content_all_events(
    log_exporter: InMemoryLogRecordExporter,
    generate_content: callable,
    instrument_with_experimental_semconvs: VertexAIInstrumentor,
):
    generate_content_all_input_events(
        GenerativeModel(
            "gemini-2.5-pro",
            system_instruction=Part.from_text(
                "You are a clever language model"
            ),
        ),
        log_exporter,
        instrument_with_experimental_semconvs,
    )


@pytest.mark.vcr()
def test_preview_generate_content_all_input_events(
    log_exporter: InMemoryLogRecordExporter,
    generate_content: callable,
    instrument_with_experimental_semconvs: VertexAIInstrumentor,
):
    generate_content_all_input_events(
        PreviewGenerativeModel(
            "gemini-2.5-pro",
            system_instruction=Part.from_text(
                "You are a clever language model"
            ),
        ),
        log_exporter,
        instrument_with_experimental_semconvs,
    )


def generate_content_all_input_events(
    model: GenerativeModel | PreviewGenerativeModel,
    log_exporter: InMemoryLogRecordExporter,
    instrument_with_experimental_semconvs: VertexAIInstrumentor,
):
    model.generate_content(
        [
            Content(
                role="user", parts=[Part.from_text("My name is OpenTelemetry")]
            ),
            Content(
                role="model", parts=[Part.from_text("Hello OpenTelemetry!")]
            ),
            Content(
                role="user",
                parts=[
                    Part.from_text("Address me by name and say this is a test")
                ],
            ),
        ],
        generation_config=GenerationConfig(
            seed=12345, response_mime_type="text/plain"
        ),
    )
    # Emits a single log.
    logs = log_exporter.get_finished_logs()
    assert len(logs) == 1
    log = logs[0].log_record
    assert log.attributes == {
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": "gemini-2.5-pro",
        "gen_ai.request.seed": 12345,
        "gen_ai.output.type": "text",
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
        "gen_ai.response.model": "gemini-2.5-pro",
        "gen_ai.response.finish_reasons": ("stop",),
        "gen_ai.usage.input_tokens": 25,
        "gen_ai.usage.output_tokens": 8,
        "gen_ai.system_instructions": (
            {"type": "text", "content": "You are a clever language model"},
        ),
        "gen_ai.input.messages": (
            {
                "role": "user",
                "parts": (
                    {
                        "type": "text",
                        "content": "My name is OpenTelemetry",
                    },
                ),
            },
            {
                "role": "model",
                "parts": (
                    {"type": "text", "content": "Hello OpenTelemetry!"},
                ),
            },
            {
                "role": "user",
                "parts": (
                    {
                        "type": "text",
                        "content": "Address me by name and say this is a test",
                    },
                ),
            },
        ),
        "gen_ai.output.messages": (
            {
                "role": "model",
                "parts": (
                    {
                        "type": "text",
                        "content": "OpenTelemetry, this is a test.",
                    },
                ),
                "finish_reason": "stop",
            },
        ),
    }
