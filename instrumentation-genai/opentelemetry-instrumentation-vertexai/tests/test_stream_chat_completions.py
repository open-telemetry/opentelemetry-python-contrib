from __future__ import annotations

import pytest
from google.api_core.exceptions import BadRequest
from vertexai.generative_models import (
    Content,
    GenerativeModel,
    Part,
)

from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor
from opentelemetry.sdk._logs._internal.export.in_memory_log_exporter import (
    InMemoryLogExporter,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


@pytest.mark.vcr
def test_stream_generate_content(
    span_exporter: InMemorySpanExporter,
    log_exporter: InMemoryLogExporter,
    instrument_with_content: VertexAIInstrumentor,
):
    model = GenerativeModel("gemini-1.5-flash-002")
    list(
        model.generate_content(
            [
                Content(
                    role="user", parts=[Part.from_text("Say this is a test")]
                ),
            ],
            stream=True,
        )
    )

    # Emits span
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "chat gemini-1.5-flash-002"
    assert dict(spans[0].attributes) == {
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": "gemini-1.5-flash-002",
        "gen_ai.response.finish_reasons": ("stop",),
        "gen_ai.response.model": "gemini-1.5-flash-002",
        "gen_ai.system": "vertex_ai",
        "gen_ai.usage.input_tokens": 5,
        "gen_ai.usage.output_tokens": 19,
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
    }

    # Emits user and multiple choice events
    logs = log_exporter.get_finished_logs()
    assert len(logs) == 4
    user_log, *choice_logs = [log_data.log_record for log_data in logs]

    span_context = spans[0].get_span_context()
    assert user_log.trace_id == span_context.trace_id
    assert user_log.span_id == span_context.span_id
    assert user_log.trace_flags == span_context.trace_flags
    assert user_log.attributes == {
        "gen_ai.system": "vertex_ai",
        "event.name": "gen_ai.user.message",
    }
    assert user_log.body == {
        "content": [{"text": "Say this is a test"}],
        "role": "user",
    }

    for choice_log in choice_logs:
        assert choice_log.trace_id == span_context.trace_id
        assert choice_log.span_id == span_context.span_id
        assert choice_log.trace_flags == span_context.trace_flags
        assert choice_log.attributes == {
            "gen_ai.system": "vertex_ai",
            "event.name": "gen_ai.choice",
        }

    assert choice_logs[0].body == {
        "index": 0,
        "message": {"content": [{"text": "Okay"}], "role": "model"},
    }
    assert choice_logs[1].body == {
        "index": 0,
        "message": {
            "content": [
                {
                    "text": ", I understand.  I'm ready for your test.  "
                    "Please proceed"
                }
            ],
            "role": "model",
        },
    }
    assert choice_logs[2].body == {
        "finish_reason": "stop",
        "index": 0,
        "message": {"content": [{"text": ".\n"}], "role": "model"},
    }


@pytest.mark.vcr
@pytest.mark.skip(
    "Bug in client library "
    "https://github.com/googleapis/python-aiplatform/issues/5010"
)
def test_stream_generate_content_invalid_role(
    log_exporter: InMemoryLogExporter,
    instrument_with_content: VertexAIInstrumentor,
):
    model = GenerativeModel("gemini-1.5-flash-002")
    try:
        # Fails because role must be "user" or "model"
        list(
            model.generate_content(
                [
                    Content(
                        role="invalid_role",
                        parts=[Part.from_text("Say this is a test")],
                    )
                ],
                stream=True,
            )
        )
    except BadRequest:
        pass

    # Emits the faulty content which caused the request to fail
    logs = log_exporter.get_finished_logs()
    assert len(logs) == 1
    assert logs[0].log_record.attributes == {
        "gen_ai.system": "vertex_ai",
        "event.name": "gen_ai.user.message",
    }
    assert logs[0].log_record.body == {
        "content": [{"text": "Say this is a test"}],
        "role": "invalid_role",
    }


@pytest.mark.vcr
def test_stream_generate_content_all_events(
    log_exporter: InMemoryLogExporter,
    instrument_with_content: VertexAIInstrumentor,
):
    model = GenerativeModel(
        "gemini-1.5-flash-002",
        system_instruction=Part.from_text("You are a clever language model"),
    )
    list(
        model.generate_content(
            [
                Content(
                    role="user",
                    parts=[Part.from_text("My name is OpenTelemetry")],
                ),
                Content(
                    role="model",
                    parts=[Part.from_text("Hello OpenTelemetry!")],
                ),
                Content(
                    role="user",
                    parts=[
                        Part.from_text(
                            "Address me by name and say this is a test"
                        )
                    ],
                ),
            ],
            stream=True,
        )
    )

    # Emits a system event, 2 users events, an assistant event, and the choice (response) event
    logs = log_exporter.get_finished_logs()
    assert len(logs) == 6
    (
        system_log,
        user_log1,
        assistant_log,
        user_log2,
        choice_log1,
        choice_log2,
    ) = [log_data.log_record for log_data in logs]

    assert system_log.attributes == {
        "gen_ai.system": "vertex_ai",
        "event.name": "gen_ai.system.message",
    }
    assert system_log.body == {
        "content": [{"text": "You are a clever language model"}],
        # The API only allows user and model, so system instruction is considered a user role
        "role": "user",
    }

    assert user_log1.attributes == {
        "gen_ai.system": "vertex_ai",
        "event.name": "gen_ai.user.message",
    }
    assert user_log1.body == {
        "content": [{"text": "My name is OpenTelemetry"}],
        "role": "user",
    }

    assert assistant_log.attributes == {
        "gen_ai.system": "vertex_ai",
        "event.name": "gen_ai.assistant.message",
    }
    assert assistant_log.body == {
        "content": [{"text": "Hello OpenTelemetry!"}],
        "role": "model",
    }

    assert user_log2.attributes == {
        "gen_ai.system": "vertex_ai",
        "event.name": "gen_ai.user.message",
    }
    assert user_log2.body == {
        "content": [{"text": "Address me by name and say this is a test"}],
        "role": "user",
    }

    assert choice_log1.attributes == {
        "gen_ai.system": "vertex_ai",
        "event.name": "gen_ai.choice",
    }
    assert choice_log1.body == {
        "index": 0,
        "message": {"content": [{"text": "Open"}], "role": "model"},
    }
    assert choice_log2.attributes == {
        "gen_ai.system": "vertex_ai",
        "event.name": "gen_ai.choice",
    }
    assert choice_log2.body == {
        "finish_reason": "stop",
        "index": 0,
        "message": {
            "content": [{"text": "Telemetry, this is a test.\n"}],
            "role": "model",
        },
    }
