from __future__ import annotations

import pytest
from google.api_core.exceptions import BadRequest, NotFound
from vertexai.generative_models import (
    Content,
    GenerationConfig,
    GenerativeModel,
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
def test_generate_content(
    span_exporter: InMemorySpanExporter,
    log_exporter: InMemoryLogRecordExporter,
    generate_content: callable,
    instrument_with_content: VertexAIInstrumentor,
):
    model = GenerativeModel("gemini-2.5-pro")
    generate_content(
        model,
        [
            Content(
                role="user",
                parts=[
                    Part.from_text("Say this is a test"),
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
        "gen_ai.system": "vertex_ai",
        "gen_ai.usage.input_tokens": 5,
        "gen_ai.usage.output_tokens": 5,
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
    }

    logs = log_exporter.get_finished_logs()

    # Emits user and choice events
    assert len(logs) == 2
    user_log, choice_log = [log_data.log_record for log_data in logs]

    span_context = spans[0].get_span_context()
    assert user_log.trace_id == span_context.trace_id
    assert user_log.span_id == span_context.span_id
    assert user_log.trace_flags == span_context.trace_flags
    assert user_log.attributes == {"gen_ai.system": "vertex_ai"}
    assert user_log.event_name == "gen_ai.user.message"
    assert user_log.body == {
        "content": [{"text": "Say this is a test"}],
        "role": "user",
    }

    assert choice_log.trace_id == span_context.trace_id
    assert choice_log.span_id == span_context.span_id
    assert choice_log.trace_flags == span_context.trace_flags
    assert choice_log.attributes == {"gen_ai.system": "vertex_ai"}
    assert choice_log.event_name == "gen_ai.choice"
    assert choice_log.body == {
        "finish_reason": "stop",
        "index": 0,
        "message": {
            "content": [{"text": "This is a test."}],
            "role": "model",
        },
    }


@pytest.mark.vcr()
def test_generate_content_without_events(
    span_exporter: InMemorySpanExporter,
    log_exporter: InMemoryLogRecordExporter,
    generate_content: callable,
    instrument_no_content: VertexAIInstrumentor,
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
        "gen_ai.request.model": "gemini-2.5-pro",
        "gen_ai.response.finish_reasons": ("stop",),
        "gen_ai.response.model": "gemini-2.5-pro",
        "gen_ai.system": "vertex_ai",
        "gen_ai.usage.input_tokens": 5,
        "gen_ai.usage.output_tokens": 5,
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
    }

    logs = log_exporter.get_finished_logs()
    # Emits user and choice event without body.content
    assert len(logs) == 2
    user_log, choice_log = [log_data.log_record for log_data in logs]
    assert user_log.attributes == {"gen_ai.system": "vertex_ai"}
    assert user_log.event_name == "gen_ai.user.message"
    assert user_log.body == {"role": "user"}

    assert choice_log.attributes == {"gen_ai.system": "vertex_ai"}
    assert choice_log.event_name == "gen_ai.choice"
    assert choice_log.body == {
        "finish_reason": "stop",
        "index": 0,
        "message": {"role": "model"},
    }


@pytest.mark.vcr()
def test_generate_content_empty_model(
    span_exporter: InMemorySpanExporter,
    generate_content: callable,
    instrument_with_content: VertexAIInstrumentor,
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
        "gen_ai.system": "vertex_ai",
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
    }
    assert_span_error(spans[0])


@pytest.mark.vcr()
def test_generate_content_missing_model(
    span_exporter: InMemorySpanExporter,
    generate_content: callable,
    instrument_with_content: VertexAIInstrumentor,
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
        "gen_ai.system": "vertex_ai",
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
    }
    assert_span_error(spans[0])


@pytest.mark.vcr()
def test_generate_content_invalid_temperature(
    span_exporter: InMemorySpanExporter,
    generate_content: callable,
    instrument_with_content: VertexAIInstrumentor,
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
        "gen_ai.system": "vertex_ai",
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
    }
    assert_span_error(spans[0])


@pytest.mark.vcr()
def test_generate_content_invalid_role(
    log_exporter: InMemoryLogRecordExporter,
    generate_content: callable,
    instrument_with_content: VertexAIInstrumentor,
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
        "gen_ai.system": "vertex_ai",
    }
    assert log.event_name == "gen_ai.user.message"
    assert log.body == {
        "content": [{"text": "Say this is a test"}],
        "role": "invalid_role",
    }


@pytest.mark.vcr()
def test_generate_content_extra_params(
    span_exporter,
    instrument_no_content,
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
        "gen_ai.request.seed": 12345,
        "gen_ai.request.model": "gemini-2.5-pro",
        "gen_ai.request.presence_penalty": -1.5,
        "gen_ai.request.stop_sequences": ("\n\n\n",),
        "gen_ai.request.temperature": 0.20000000298023224,
        "gen_ai.request.top_p": 0.949999988079071,
        "gen_ai.response.finish_reasons": ("length",),
        "gen_ai.response.model": "gemini-2.5-pro",
        "gen_ai.system": "vertex_ai",
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
    instrument_with_content: VertexAIInstrumentor,
):
    generate_content_all_input_events(
        GenerativeModel(
            "gemini-2.5-pro",
            system_instruction=Part.from_text(
                "You are a clever language model"
            ),
        ),
        log_exporter,
        instrument_with_content,
    )


@pytest.mark.vcr()
def test_preview_generate_content_all_input_events(
    log_exporter: InMemoryLogRecordExporter,
    generate_content: callable,
    instrument_with_content: VertexAIInstrumentor,
):
    generate_content_all_input_events(
        PreviewGenerativeModel(
            "gemini-2.5-pro",
            system_instruction=Part.from_text(
                "You are a clever language model"
            ),
        ),
        log_exporter,
        instrument_with_content,
    )


def generate_content_all_input_events(
    model: GenerativeModel | PreviewGenerativeModel,
    log_exporter: InMemoryLogRecordExporter,
    instrument_with_content: VertexAIInstrumentor,
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

    # Emits a system event, 2 users events, an assistant event, and the choice (response) event
    logs = log_exporter.get_finished_logs()
    assert len(logs) == 5
    system_log, user_log1, assistant_log, user_log2, choice_log = [
        log_data.log_record for log_data in logs
    ]

    assert system_log.attributes == {"gen_ai.system": "vertex_ai"}
    assert system_log.event_name == "gen_ai.system.message"
    assert system_log.body == {
        "content": [{"text": "You are a clever language model"}],
        # The API only allows user and model, so system instruction is considered a user role
        "role": "user",
    }

    assert user_log1.attributes == {"gen_ai.system": "vertex_ai"}
    assert user_log1.event_name == "gen_ai.user.message"
    assert user_log1.body == {
        "content": [{"text": "My name is OpenTelemetry"}],
        "role": "user",
    }

    assert assistant_log.attributes == {"gen_ai.system": "vertex_ai"}
    assert assistant_log.event_name == "gen_ai.assistant.message"
    assert assistant_log.body == {
        "content": [{"text": "Hello OpenTelemetry!"}],
        "role": "model",
    }

    assert user_log2.attributes == {"gen_ai.system": "vertex_ai"}
    assert user_log2.event_name == "gen_ai.user.message"
    assert user_log2.body == {
        "content": [{"text": "Address me by name and say this is a test"}],
        "role": "user",
    }

    assert choice_log.attributes == {"gen_ai.system": "vertex_ai"}
    assert choice_log.event_name == "gen_ai.choice"
    assert choice_log.body == {
        "finish_reason": "stop",
        "index": 0,
        "message": {
            "content": [{"text": "OpenTelemetry, this is a test."}],
            "role": "model",
        },
    }
