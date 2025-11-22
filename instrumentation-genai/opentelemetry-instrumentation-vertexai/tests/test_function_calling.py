import pytest
from tests.shared_test_utils import (
    ask_about_weather,
    ask_about_weather_function_response,
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
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


@pytest.mark.vcr()
def test_function_call_choice(
    span_exporter: InMemorySpanExporter,
    log_exporter: InMemoryLogRecordExporter,
    instrument_with_content: VertexAIInstrumentor,
    generate_content: callable,
):
    ask_about_weather(generate_content)

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
        "gen_ai.usage.input_tokens": 74,
        "gen_ai.usage.output_tokens": 16,
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
    }

    # Emits user and choice events
    logs = log_exporter.get_finished_logs()
    assert len(logs) == 2
    user_log, choice_log = [log_data.log_record for log_data in logs]
    assert user_log.attributes == {"gen_ai.system": "vertex_ai"}
    assert user_log.event_name == "gen_ai.user.message"
    assert user_log.body == {
        "content": [
            {"text": "Get weather details in New Delhi and San Francisco?"}
        ],
        "role": "user",
    }

    assert choice_log.attributes == {"gen_ai.system": "vertex_ai"}
    assert choice_log.event_name == "gen_ai.choice"
    assert choice_log.body == {
        "finish_reason": "stop",
        "index": 0,
        "message": {
            "content": [
                {
                    "function_call": {
                        "args": {"location": "New Delhi"},
                        "name": "get_current_weather",
                    }
                },
                {
                    "function_call": {
                        "args": {"location": "San Francisco"},
                        "name": "get_current_weather",
                    }
                },
            ],
            "role": "model",
        },
        "tool_calls": [
            {
                "function": {
                    "arguments": {"location": "New Delhi"},
                    "name": "get_current_weather",
                },
                "id": "get_current_weather_0",
                "type": "function",
            },
            {
                "function": {
                    "arguments": {"location": "San Francisco"},
                    "name": "get_current_weather",
                },
                "id": "get_current_weather_1",
                "type": "function",
            },
        ],
    }


@pytest.mark.vcr()
def test_function_call_choice_no_content(
    log_exporter: InMemoryLogRecordExporter,
    instrument_no_content: VertexAIInstrumentor,
    generate_content: callable,
):
    ask_about_weather(generate_content)

    # Emits user and choice events
    logs = log_exporter.get_finished_logs()
    assert len(logs) == 2
    user_log, choice_log = [log_data.log_record for log_data in logs]
    assert user_log.attributes == {"gen_ai.system": "vertex_ai"}
    assert user_log.event_name == "gen_ai.user.message"
    assert user_log.body == {
        "role": "user",
    }

    assert choice_log.attributes == {"gen_ai.system": "vertex_ai"}
    assert choice_log.event_name == "gen_ai.choice"
    assert choice_log.body == {
        "finish_reason": "stop",
        "index": 0,
        "message": {"role": "model"},
        "tool_calls": [
            {
                "function": {"name": "get_current_weather"},
                "id": "get_current_weather_0",
                "type": "function",
            },
            {
                "function": {"name": "get_current_weather"},
                "id": "get_current_weather_1",
                "type": "function",
            },
        ],
    }


@pytest.mark.vcr()
def test_tool_events(
    span_exporter: InMemorySpanExporter,
    log_exporter: InMemoryLogRecordExporter,
    instrument_with_content: VertexAIInstrumentor,
    generate_content: callable,
):
    ask_about_weather_function_response(generate_content)

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
        "gen_ai.usage.input_tokens": 128,
        "gen_ai.usage.output_tokens": 26,
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
    }
    logs = log_exporter.get_finished_logs()
    # Emits user, assistant, two tool, and choice events
    assert len(logs) == 5
    user_log, assistant_log, tool_log1, tool_log2, choice_log = [
        log_data.log_record for log_data in logs
    ]
    assert user_log.attributes == {"gen_ai.system": "vertex_ai"}
    assert user_log.event_name == "gen_ai.user.message"
    assert user_log.body == {
        "content": [
            {"text": "Get weather details in New Delhi and San Francisco?"}
        ],
        "role": "user",
    }

    assert assistant_log.attributes == {"gen_ai.system": "vertex_ai"}
    assert assistant_log.event_name == "gen_ai.assistant.message"
    assert assistant_log.body == {
        "role": "model",
        "content": [
            {
                "function_call": {
                    "name": "get_current_weather",
                    "args": {"location": "New Delhi"},
                }
            },
            {
                "function_call": {
                    "name": "get_current_weather",
                    "args": {"location": "San Francisco"},
                }
            },
        ],
    }

    assert tool_log1.attributes == {"gen_ai.system": "vertex_ai"}
    assert tool_log1.event_name == "gen_ai.tool.message"

    assert tool_log1.body == {
        "role": "user",
        "id": "get_current_weather_0",
        "content": {"content": '{"temperature": 35, "unit": "C"}'},
    }

    assert tool_log2.attributes == {"gen_ai.system": "vertex_ai"}
    assert tool_log2.event_name == "gen_ai.tool.message"
    assert tool_log2.body == {
        "role": "user",
        "id": "get_current_weather_1",
        "content": {"content": '{"temperature": 25, "unit": "C"}'},
    }

    assert choice_log.attributes == {"gen_ai.system": "vertex_ai"}
    assert choice_log.event_name == "gen_ai.choice"
    assert choice_log.body == {
        "finish_reason": "stop",
        "index": 0,
        "message": {
            "content": [
                {
                    "text": "The current temperature in New Delhi is 35°C, and in San Francisco, it is 25°C."
                }
            ],
            "role": "model",
        },
    }


@pytest.mark.vcr()
def test_tool_events_no_content(
    span_exporter: InMemorySpanExporter,
    log_exporter: InMemoryLogRecordExporter,
    instrument_no_content: VertexAIInstrumentor,
    generate_content: callable,
):
    ask_about_weather_function_response(generate_content)

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
        "gen_ai.usage.input_tokens": 128,
        "gen_ai.usage.output_tokens": 22,
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
    }
    logs = log_exporter.get_finished_logs()
    # Emits user, assistant, two tool, and choice events
    assert len(logs) == 5
    user_log, assistant_log, tool_log1, tool_log2, choice_log = [
        log_data.log_record for log_data in logs
    ]
    assert user_log.attributes == {"gen_ai.system": "vertex_ai"}
    assert user_log.event_name == "gen_ai.user.message"
    assert user_log.body == {"role": "user"}

    assert assistant_log.attributes == {"gen_ai.system": "vertex_ai"}
    assert assistant_log.event_name == "gen_ai.assistant.message"
    assert assistant_log.body == {"role": "model"}

    assert tool_log1.attributes == {
        "gen_ai.system": "vertex_ai",
    }
    assert tool_log1.event_name == "gen_ai.tool.message"
    assert tool_log1.body == {
        "role": "user",
        "id": "get_current_weather_0",
    }
    assert tool_log1.event_name == "gen_ai.tool.message"

    assert tool_log2.attributes == {"gen_ai.system": "vertex_ai"}

    assert tool_log2.body == {
        "role": "user",
        "id": "get_current_weather_1",
    }
    assert tool_log2.event_name == "gen_ai.tool.message"

    assert choice_log.attributes == {"gen_ai.system": "vertex_ai"}
    assert choice_log.event_name == "gen_ai.choice"
    assert choice_log.body == {
        "finish_reason": "stop",
        "index": 0,
        "message": {"role": "model"},
    }
