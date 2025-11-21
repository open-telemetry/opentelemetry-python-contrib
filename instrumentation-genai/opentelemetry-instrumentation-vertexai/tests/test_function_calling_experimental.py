import json
import time
from typing import Any

import fsspec
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


def test_function_call_choice(
    span_exporter: InMemorySpanExporter,
    log_exporter: InMemoryLogRecordExporter,
    instrument_with_experimental_semconvs: VertexAIInstrumentor,
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
        "gen_ai.usage.input_tokens": 74,
        "gen_ai.usage.output_tokens": 16,
        "server.address": "us-central1-aiplatform.googleapis.com",
        "gen_ai.input.messages": '[{"role":"user","parts":[{"content":"Get weather details in New Delhi and San Francisco?","type":"text"}]}]',
        "gen_ai.output.messages": '[{"role":"model","parts":[{"arguments":{"location":"New Delhi"},"name":"get_current_weather","id":"get_current_weather_0","type":"tool_call"},{"arguments":{"location":"San Francisco"},"name":"get_current_weather","id":"get_current_weather_1","type":"tool_call"}],"finish_reason":"stop"}]',
        "server.port": 443,
    }

    # Emits user and choice events
    logs = log_exporter.get_finished_logs()
    assert len(logs) == 1
    log = logs[0].log_record
    assert log.attributes == {
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": "gemini-2.5-pro",
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
        "gen_ai.response.model": "gemini-2.5-pro",
        "gen_ai.response.finish_reasons": ("stop",),
        "gen_ai.usage.input_tokens": 74,
        "gen_ai.usage.output_tokens": 16,
        "gen_ai.input.messages": (
            {
                "role": "user",
                "parts": (
                    {
                        "type": "text",
                        "content": "Get weather details in New Delhi and San Francisco?",
                    },
                ),
            },
        ),
        "gen_ai.output.messages": (
            {
                "role": "model",
                "parts": (
                    {
                        "type": "tool_call",
                        "arguments": {"location": "New Delhi"},
                        "name": "get_current_weather",
                        "id": "get_current_weather_0",
                    },
                    {
                        "type": "tool_call",
                        "arguments": {"location": "San Francisco"},
                        "name": "get_current_weather",
                        "id": "get_current_weather_1",
                    },
                ),
                "finish_reason": "stop",
            },
        ),
    }


@pytest.mark.vcr()
def test_function_call_choice_no_content(
    log_exporter: InMemoryLogRecordExporter,
    instrument_no_content_with_experimental_semconvs: VertexAIInstrumentor,
    generate_content: callable,
):
    ask_about_weather(generate_content)

    # Emits user and choice events
    logs = log_exporter.get_finished_logs()
    assert len(logs) == 1
    log = logs[0].log_record
    assert log.attributes == {
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": "gemini-2.5-pro",
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
        "gen_ai.response.model": "gemini-2.5-pro",
        "gen_ai.response.finish_reasons": ("stop",),
        "gen_ai.usage.input_tokens": 74,
        "gen_ai.usage.output_tokens": 16,
    }


@pytest.mark.vcr()
def test_tool_events(
    span_exporter: InMemorySpanExporter,
    log_exporter: InMemoryLogRecordExporter,
    instrument_with_experimental_semconvs: VertexAIInstrumentor,
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
        "gen_ai.usage.input_tokens": 128,
        "gen_ai.usage.output_tokens": 26,
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
        "gen_ai.input.messages": '[{"role":"user","parts":[{"content":"Get weather details in New Delhi and San Francisco?","type":"text"}]},{"role":"model","parts":[{"arguments":{"location":"New Delhi"},"name":"get_current_weather","id":"get_current_weather_0","type":"tool_call"},{"arguments":{"location":"San Francisco"},"name":"get_current_weather","id":"get_current_weather_1","type":"tool_call"}]},{"role":"user","parts":[{"response":{"content":"{\\"temperature\\": 35, \\"unit\\": \\"C\\"}"},"id":"get_current_weather_0","type":"tool_call_response"},{"response":{"content":"{\\"temperature\\": 25, \\"unit\\": \\"C\\"}"},"id":"get_current_weather_1","type":"tool_call_response"}]}]',
        "gen_ai.output.messages": '[{"role":"model","parts":[{"content":"The current temperature in New Delhi is 35\\u00b0C, and in San Francisco, it is 25\\u00b0C.","type":"text"}],"finish_reason":"stop"}]',
    }
    logs = log_exporter.get_finished_logs()
    assert len(logs) == 1
    log = logs[0].log_record
    assert log.attributes == {
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": "gemini-2.5-pro",
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
        "gen_ai.response.model": "gemini-2.5-pro",
        "gen_ai.response.finish_reasons": ("stop",),
        "gen_ai.usage.input_tokens": 128,
        "gen_ai.usage.output_tokens": 26,
        "gen_ai.input.messages": (
            {
                "role": "user",
                "parts": (
                    {
                        "type": "text",
                        "content": "Get weather details in New Delhi and San Francisco?",
                    },
                ),
            },
            {
                "role": "model",
                "parts": (
                    {
                        "type": "tool_call",
                        "arguments": {"location": "New Delhi"},
                        "name": "get_current_weather",
                        "id": "get_current_weather_0",
                    },
                    {
                        "type": "tool_call",
                        "arguments": {"location": "San Francisco"},
                        "name": "get_current_weather",
                        "id": "get_current_weather_1",
                    },
                ),
            },
            {
                "role": "user",
                "parts": (
                    {
                        "type": "tool_call_response",
                        "response": {
                            "content": '{"temperature": 35, "unit": "C"}'
                        },
                        "id": "get_current_weather_0",
                    },
                    {
                        "type": "tool_call_response",
                        "response": {
                            "content": '{"temperature": 25, "unit": "C"}'
                        },
                        "id": "get_current_weather_1",
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
                        "content": "The current temperature in New Delhi is 35°C, and in San Francisco, it is 25°C.",
                    },
                ),
                "finish_reason": "stop",
            },
        ),
    }


@pytest.mark.vcr()
def test_tool_events_no_content(
    span_exporter: InMemorySpanExporter,
    log_exporter: InMemoryLogRecordExporter,
    instrument_no_content_with_experimental_semconvs: VertexAIInstrumentor,
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
        "gen_ai.usage.input_tokens": 128,
        "gen_ai.usage.output_tokens": 22,
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
    }
    logs = log_exporter.get_finished_logs()
    assert len(logs) == 1
    log = logs[0].log_record
    assert log.attributes == {
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": "gemini-2.5-pro",
        "server.address": "us-central1-aiplatform.googleapis.com",
        "server.port": 443,
        "gen_ai.response.model": "gemini-2.5-pro",
        "gen_ai.response.finish_reasons": ("stop",),
        "gen_ai.usage.input_tokens": 128,
        "gen_ai.usage.output_tokens": 22,
    }


def assert_fsspec_equal(path: str, value: Any) -> None:
    # Hide this function and its calls from traceback.
    __tracebackhide__ = True  # pylint: disable=unused-variable
    with fsspec.open(path, "r") as file:
        assert json.load(file) == value


@pytest.mark.vcr()
def test_tool_events_with_completion_hook(
    span_exporter: InMemorySpanExporter,
    log_exporter: InMemoryLogRecordExporter,
    instrument_with_upload_hook: VertexAIInstrumentor,
    generate_content: callable,
):
    ask_about_weather_function_response(generate_content)

    # Emits span
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    logs = log_exporter.get_finished_logs()
    assert len(logs) == 1
    # File upload takes a few seconds sometimes.
    time.sleep(3)

    # Both log and span have the same reference attributes from upload hook
    for key in "gen_ai.input.messages_ref", "gen_ai.output.messages_ref":
        assert spans[0].attributes.get(key)
        assert logs[0].log_record.attributes.get(key)

        assert spans[0].attributes[key] == logs[0].log_record.attributes[key]

    assert_fsspec_equal(
        spans[0].attributes["gen_ai.output.messages_ref"],
        [
            {
                "role": "model",
                "parts": [
                    {
                        "content": "The weather in New Delhi is 35°C and in San Francisco is 25°C.",
                        "type": "text",
                    }
                ],
                "finish_reason": "stop",
            }
        ],
    )
    assert_fsspec_equal(
        spans[0].attributes["gen_ai.input.messages_ref"],
        [
            {
                "parts": [
                    {
                        "content": "Get weather details in New Delhi and San Francisco?",
                        "type": "text",
                    }
                ],
                "role": "user",
            },
            {
                "parts": [
                    {
                        "arguments": {"location": "New Delhi"},
                        "id": "get_current_weather_0",
                        "name": "get_current_weather",
                        "type": "tool_call",
                    },
                    {
                        "arguments": {"location": "San Francisco"},
                        "id": "get_current_weather_1",
                        "name": "get_current_weather",
                        "type": "tool_call",
                    },
                ],
                "role": "model",
            },
            {
                "parts": [
                    {
                        "id": "get_current_weather_0",
                        "response": {
                            "content": '{"temperature": 35, "unit": "C"}'
                        },
                        "type": "tool_call_response",
                    },
                    {
                        "id": "get_current_weather_1",
                        "response": {
                            "content": '{"temperature": 25, "unit": "C"}'
                        },
                        "type": "tool_call_response",
                    },
                ],
                "role": "user",
            },
        ],
    )
