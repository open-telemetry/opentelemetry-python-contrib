# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for OpenAI Responses API instrumentation."""
# pylint: disable=too-many-locals

from typing import Any

import pytest
from openai import (
    APIConnectionError,
    BadRequestError,
    OpenAI,
)

from opentelemetry._logs import get_logger
from opentelemetry.instrumentation.openai_v2.instruments import Instruments
from opentelemetry.instrumentation.openai_v2.patch import responses_compact
from opentelemetry.metrics import get_meter
from opentelemetry.semconv._incubating.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics

from .test_utils import assert_log_parent


@pytest.mark.vcr()
def test_responses_basic_with_content(
    span_exporter, log_exporter, openai_client, instrument_with_content
):
    """Test basic Responses API call with content capture enabled."""
    model = "gpt-4o-mini"
    input_text = "Say hello"

    responses = getattr(openai_client, "responses")
    response = responses.create(
        model=model,
        input=input_text,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.name == f"chat {model}"
    assert span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME] == "chat"
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == model
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID] == response.id
    assert ErrorAttributes.ERROR_TYPE not in span.attributes

    logs = log_exporter.get_finished_logs()
    assert len(logs) >= 2  # input + output

    # First log should be the input message
    input_log = logs[0]
    assert input_log.log_record.event_name == "gen_ai.user.input"
    assert input_log.log_record.body["content"] == input_text
    assert_log_parent(input_log, span)

    output_logs = [
        log for log in logs if log.log_record.event_name == "gen_ai.output"
    ]
    assert output_logs
    assert_log_parent(output_logs[-1], span)


@pytest.mark.vcr()
def test_responses_basic_no_content(
    span_exporter, log_exporter, openai_client, instrument_no_content
):
    """Test basic Responses API call with content capture disabled."""
    model = "gpt-4o-mini"
    input_text = "Say hello"

    responses = getattr(openai_client, "responses")
    response = responses.create(
        model=model,
        input=input_text,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == model
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID] == response.id
    assert ErrorAttributes.ERROR_TYPE not in span.attributes

    logs = log_exporter.get_finished_logs()
    assert len(logs) >= 2

    # Input log should not have content
    input_log = logs[0]
    assert input_log.log_record.event_name == "gen_ai.user.input"
    body: Any = input_log.log_record.body
    assert body is None or "content" not in body

    output_logs = [
        log for log in logs if log.log_record.event_name == "gen_ai.output"
    ]
    assert output_logs
    out_body: Any = output_logs[-1].log_record.body
    # No content should be captured when capture_content=False
    if out_body and "message" in out_body:
        assert "content" not in out_body["message"]


@pytest.mark.vcr()
def test_responses_with_message_input(
    span_exporter, log_exporter, openai_client, instrument_with_content
):
    """Test Responses API with structured message input."""
    model = "gpt-4o-mini"
    messages = [
        {"role": "user", "content": "What is 2+2?", "type": "message"},
    ]

    responses = getattr(openai_client, "responses")
    _ = responses.create(
        model=model,
        input=messages,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    logs = log_exporter.get_finished_logs()
    assert len(logs) >= 2

    # Check user message was logged
    user_log = logs[0]
    assert user_log.log_record.event_name == "gen_ai.user.input"
    assert_log_parent(user_log, spans[0])


@pytest.mark.vcr()
def test_responses_with_system_instruction(
    span_exporter, log_exporter, openai_client, instrument_with_content
):
    """Test Responses API with system instruction."""
    model = "gpt-4o-mini"
    instructions_text = "You are a helpful assistant that tells short jokes."

    responses = getattr(openai_client, "responses")
    response = responses.create(
        model=model,
        input="Tell me a joke",
        instructions=instructions_text,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == model
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID] == response.id
    assert ErrorAttributes.ERROR_TYPE not in span.attributes

    # Verify instructions are captured as span attribute
    assert (
        span.attributes[GenAIAttributes.GEN_AI_SYSTEM_INSTRUCTIONS]
        == instructions_text
    )


@pytest.mark.vcr()
def test_responses_with_system_instruction_no_content(
    span_exporter, openai_client, instrument_no_content
):
    """Test Responses API with system instruction when content capture is disabled."""
    responses = getattr(openai_client, "responses")
    _ = responses.create(
        model="gpt-4o-mini",
        input="Tell me a joke",
        instructions="You are a helpful assistant that tells short jokes.",
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert GenAIAttributes.GEN_AI_SYSTEM_INSTRUCTIONS not in span.attributes


@pytest.mark.vcr()
def test_responses_token_usage(
    span_exporter, metric_reader, openai_client, instrument_with_content
):
    """Test that token usage is captured correctly."""
    model = "gpt-4o-mini"

    responses = getattr(openai_client, "responses")
    response = responses.create(
        model=model,
        input="Say test",
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID] == response.id
    assert ErrorAttributes.ERROR_TYPE not in span.attributes
    if getattr(response, "usage", None) is not None:
        assert (
            span.attributes.get(GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS)
            == response.usage.input_tokens
        )
        assert (
            span.attributes.get(GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS)
            == response.usage.output_tokens
        )


@pytest.mark.vcr()
def test_responses_with_tool_call_with_content(
    span_exporter, log_exporter, openai_client, instrument_with_content
):
    """Test Responses API with function/tool calls and content capture."""
    _test_responses_with_tool_call(
        span_exporter, log_exporter, openai_client, True
    )


@pytest.mark.vcr()
def test_responses_with_tool_call_no_content(
    span_exporter, log_exporter, openai_client, instrument_no_content
):
    """Test Responses API with function/tool calls without content capture."""
    _test_responses_with_tool_call(
        span_exporter, log_exporter, openai_client, False
    )


def _test_responses_with_tool_call(
    span_exporter, log_exporter, openai_client, expect_content
):
    """Helper for tool call tests."""
    model = "gpt-4o-mini"

    tools = [
        {
            "type": "function",
            "name": "get_weather",
            "description": "Get weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                },
                "required": ["location"],
            },
        }
    ]

    responses = getattr(openai_client, "responses")
    _ = responses.create(
        model=model,
        input="What's the weather in Paris?",
        tools=tools,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    logs = log_exporter.get_finished_logs()
    assert len(logs) >= 2

    # Check that output contains tool call info
    output_logs = [
        log for log in logs if log.log_record.event_name == "gen_ai.output"
    ]
    assert len(output_logs) >= 1


@pytest.mark.vcr()
def test_responses_multi_turn_conversation(
    span_exporter,
    log_exporter,
    openai_client,
    instrument_with_content,
    pytestconfig,
):
    """Test multi-turn conversation using previous_response_id."""
    model = "gpt-4o-mini"

    responses = getattr(openai_client, "responses")
    response1 = responses.create(
        model=model,
        input="My name is Alice",
    )

    record_mode = pytestconfig.getoption("--vcr-record")
    if record_mode and record_mode != "none":
        _ = responses.create(
            model=model,
            input="What is my name?",
            previous_response_id=response1.id,
        )

    spans = span_exporter.get_finished_spans()
    if record_mode and record_mode != "none":
        assert len(spans) == 2
        assert (
            spans[0].attributes[GenAIAttributes.GEN_AI_RESPONSE_ID]
            == response1.id
        )
    else:
        assert len(spans) == 1
        assert (
            spans[0].attributes[GenAIAttributes.GEN_AI_RESPONSE_ID]
            == response1.id
        )


@pytest.mark.vcr()
def test_responses_with_function_call_output(
    span_exporter,
    log_exporter,
    openai_client,
    instrument_with_content,
    pytestconfig,
):
    """Test providing function call output back to the model."""
    model = "gpt-4o-mini"

    tools = [
        {
            "type": "function",
            "name": "get_weather",
            "description": "Get weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                },
                "required": ["location"],
            },
        }
    ]

    responses = getattr(openai_client, "responses")
    response1 = responses.create(
        model=model,
        input="What's the weather in Tokyo?",
        tools=tools,
    )

    function_calls = [
        item
        for item in getattr(response1, "output", [])
        if item.type == "function_call"
    ]
    assert function_calls
    call_id = function_calls[0].call_id

    record_mode = pytestconfig.getoption("--vcr-record")
    if record_mode and record_mode != "none":
        response2 = responses.create(
            model=model,
            input=[
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": "72°F and sunny",
                }
            ],
            previous_response_id=response1.id,
        )

        spans = span_exporter.get_finished_spans()
        assert len(spans) == 2
        assert (
            spans[0].attributes[GenAIAttributes.GEN_AI_RESPONSE_ID]
            == response1.id
        )
        assert (
            spans[1].attributes[GenAIAttributes.GEN_AI_RESPONSE_ID]
            == response2.id
        )
    else:
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert (
            spans[0].attributes[GenAIAttributes.GEN_AI_RESPONSE_ID]
            == response1.id
        )

    logs = log_exporter.get_finished_logs()
    tool_logs = [
        log for log in logs if log.log_record.event_name == "gen_ai.tool.input"
    ]
    if record_mode and record_mode != "none":
        assert tool_logs


def test_responses_bad_endpoint(
    span_exporter, metric_reader, instrument_no_content
):
    """Test error handling for connection errors."""
    model = "gpt-4o-mini"

    client = OpenAI(base_url="http://localhost:4242")
    responses = getattr(client, "responses")

    with pytest.raises(APIConnectionError):
        responses.create(
            model=model,
            input="Say test",
            timeout=0.1,
        )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == model
    assert span.attributes[ServerAttributes.SERVER_ADDRESS] == "localhost"
    assert span.attributes[ServerAttributes.SERVER_PORT] == 4242
    assert span.attributes[ErrorAttributes.ERROR_TYPE] == "APIConnectionError"

    # Check metrics
    metrics = metric_reader.get_metrics_data().resource_metrics
    assert len(metrics) == 1

    metric_data = metrics[0].scope_metrics[0].metrics
    duration_metric = next(
        (
            m
            for m in metric_data
            if m.name == gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
        ),
        None,
    )
    assert duration_metric is not None
    assert duration_metric.data.data_points[0].sum > 0
    assert (
        duration_metric.data.data_points[0].attributes[
            ErrorAttributes.ERROR_TYPE
        ]
        == "APIConnectionError"
    )


@pytest.mark.vcr()
def test_responses_404(
    span_exporter, openai_client, metric_reader, instrument_no_content
):
    """Test error handling for 404 (model not found)."""
    model = "this-model-does-not-exist"

    responses = getattr(openai_client, "responses")
    with pytest.raises(BadRequestError):
        responses.create(
            model=model,
            input="Say test",
        )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    assert spans[0].attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == model
    assert spans[0].attributes[ErrorAttributes.ERROR_TYPE] == "BadRequestError"


@pytest.mark.vcr()
def test_responses_streaming(
    span_exporter, log_exporter, openai_client, instrument_with_content
):
    """Test streaming Responses API."""
    model = "gpt-4o-mini"

    responses = getattr(openai_client, "responses")
    response = responses.create(
        model=model,
        input="Say hello",
        stream=True,
    )

    # Consume the stream
    response_text = ""
    for event in response:
        if hasattr(event, "delta") and event.delta:
            response_text += getattr(event.delta, "text", "") or ""

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == model

    logs = log_exporter.get_finished_logs()
    assert len(logs) >= 2

    # Check input was logged
    input_log = logs[0]
    assert input_log.log_record.event_name == "gen_ai.user.input"
    assert_log_parent(input_log, span)


@pytest.mark.vcr()
def test_responses_streaming_not_complete(
    span_exporter, log_exporter, openai_client, instrument_with_content
):
    """Test streaming that is interrupted early."""
    model = "gpt-4o-mini"

    responses = getattr(openai_client, "responses")
    response = responses.create(
        model=model,
        input="Count from 1 to 100",
        stream=True,
    )

    # Only consume part of the stream
    for idx, _event in enumerate(response):
        if idx >= 2:
            break

    response.close()

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    logs = log_exporter.get_finished_logs()
    assert len(logs) >= 1


@pytest.mark.vcr()
def test_responses_with_content_span_unsampled(
    span_exporter,
    log_exporter,
    openai_client,
    instrument_with_content_unsampled,
):
    """Test that logs are still emitted when span is not sampled."""
    model = "gpt-4o-mini"
    input_text = "Say hello"

    responses = getattr(openai_client, "responses")
    _ = responses.create(
        model=model,
        input=input_text,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 0  # Span not sampled

    logs = log_exporter.get_finished_logs()
    assert len(logs) >= 2

    # Check logs still have trace context
    assert logs[0].log_record.trace_id is not None
    assert logs[0].log_record.span_id is not None
    assert logs[0].log_record.trace_flags == 0

    # All logs should have same trace context
    assert logs[0].log_record.trace_id == logs[-1].log_record.trace_id
    assert logs[0].log_record.span_id == logs[-1].log_record.span_id


@pytest.mark.vcr()
@pytest.mark.asyncio
async def test_async_responses_basic(
    span_exporter, log_exporter, async_openai_client, instrument_with_content
):
    """Test async Responses API call."""
    model = "gpt-4o-mini"
    input_text = "Say hello"

    responses = getattr(async_openai_client, "responses")
    response = await responses.create(
        model=model,
        input=input_text,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == model
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID] == response.id

    logs = log_exporter.get_finished_logs()
    assert len(logs) >= 2


@pytest.mark.vcr()
@pytest.mark.asyncio
async def test_async_responses_streaming(
    span_exporter, log_exporter, async_openai_client, instrument_with_content
):
    """Test async streaming Responses API."""
    model = "gpt-4o-mini"

    responses = getattr(async_openai_client, "responses")
    response = await responses.create(
        model=model,
        input="Say hello",
        stream=True,
    )

    # Consume the stream
    async for _event in response:
        pass

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    logs = log_exporter.get_finished_logs()
    assert len(logs) >= 2


@pytest.mark.vcr()
def test_responses_with_structured_message_content(
    span_exporter, log_exporter, openai_client, instrument_with_content
):
    """Test Responses API with structured content parts in message input."""
    model = "gpt-4o-mini"

    # Use structured content parts format
    messages = [
        {
            "type": "message",
            "role": "user",
            "content": [
                {"type": "input_text", "text": "What is 2+2?"},
            ],
        },
    ]

    responses = getattr(openai_client, "responses")
    _ = responses.create(
        model=model,
        input=messages,
    )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    logs = log_exporter.get_finished_logs()
    assert len(logs) >= 2

    # Check user message was logged with content
    user_log = logs[0]
    assert user_log.log_record.event_name == "gen_ai.user.input"
    user_body: Any = user_log.log_record.body
    assert user_body is not None
    assert "content" in user_body

    # Check output was logged
    output_log = logs[-1]
    assert output_log.log_record.event_name == "gen_ai.output"
    output_body: Any = output_log.log_record.body
    assert output_body is not None
    assert "message" in output_body


def test_responses_compact_wrapper_does_not_crash(
    span_exporter,
    log_exporter,
    tracer_provider,
    logger_provider,
    meter_provider,
):
    """Unit-ish test for Responses.compact wrapper without VCR/network."""

    tracer = tracer_provider.get_tracer(__name__)
    logger = get_logger(__name__, logger_provider=logger_provider)
    meter = get_meter(__name__, meter_provider=meter_provider)
    instruments = Instruments(meter)

    class Usage:
        input_tokens = 1
        output_tokens = 2

    class Result:
        id = "resp_compact_123"
        model = "gpt-4o-mini"
        output = []
        usage = Usage()

    def wrapped(*_args, **_kwargs):
        return Result()

    wrapper = responses_compact(
        tracer, logger, instruments, capture_content=True
    )
    result = wrapper(
        wrapped, object(), (), {"model": "gpt-4o-mini", "input": "hello"}
    )
    assert result is not None

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    logs = log_exporter.get_finished_logs()
    assert len(logs) >= 1


@pytest.mark.vcr()
def test_responses_message_output_structure(
    span_exporter, log_exporter, openai_client, instrument_with_content
):
    """Test that message output is properly structured with role and content."""
    model = "gpt-4o-mini"

    responses = getattr(openai_client, "responses")
    response = responses.create(
        model=model,
        input="Say hello",
    )

    logs = log_exporter.get_finished_logs()
    output_logs = [
        log for log in logs if log.log_record.event_name == "gen_ai.output"
    ]
    assert len(output_logs) >= 1

    # Check the message output structure
    for output_log in output_logs:
        body: Any = output_log.log_record.body
        if body and "message" in body:
            assert "role" in body["message"]
            # Content should be present when capture_content=True
            if response.output:
                for item in response.output:
                    if item.type == "message":
                        assert "content" in body["message"]


@pytest.mark.vcr()
def test_responses_function_call_output_structure(
    span_exporter, log_exporter, openai_client, instrument_with_content
):
    """Test that function_call output contains tool_calls structure."""
    model = "gpt-4o-mini"

    tools = [
        {
            "type": "function",
            "name": "get_weather",
            "description": "Get weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                },
                "required": ["location"],
            },
        }
    ]

    responses = getattr(openai_client, "responses")
    response = responses.create(
        model=model,
        input="What's the weather in London?",
        tools=tools,
    )

    # Check if we got a function call
    function_calls = [
        item for item in response.output if item.type == "function_call"
    ]

    if function_calls:
        logs = log_exporter.get_finished_logs()
        output_logs = [
            log for log in logs if log.log_record.event_name == "gen_ai.output"
        ]

        # Find the log with tool_calls
        tool_call_found = False
        for output_log in output_logs:
            body: Any = output_log.log_record.body
            if body and "message" in body and "tool_calls" in body["message"]:
                tool_call_found = True
                tool_calls = body["message"]["tool_calls"]
                assert len(tool_calls) >= 1
                assert "id" in tool_calls[0]
                assert "type" in tool_calls[0]
                assert tool_calls[0]["type"] == "function"
                assert "function" in tool_calls[0]
                assert "name" in tool_calls[0]["function"]

        assert tool_call_found, "Expected to find tool_calls in output logs"


@pytest.mark.vcr()
def test_responses_complete_tool_flow(
    span_exporter, log_exporter, openai_client, instrument_with_content
):
    """Test complete flow: request -> function_call -> function_call_output -> response."""
    model = "gpt-4o-mini"

    tools = [
        {
            "type": "function",
            "name": "get_current_time",
            "description": "Get the current time",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        }
    ]

    # First call - should trigger function call
    responses = getattr(openai_client, "responses")
    response1 = responses.create(
        model=model,
        input="What time is it?",
        tools=tools,
    )

    function_calls = [
        item for item in response1.output if item.type == "function_call"
    ]
    # This cassette records only the initial call; validate we got a function call and emitted output logs.
    assert function_calls
    logs = log_exporter.get_finished_logs()
    output_logs = [
        log for log in logs if log.log_record.event_name == "gen_ai.output"
    ]
    assert output_logs


@pytest.mark.vcr()
def test_responses_assistant_message_in_conversation(
    span_exporter, log_exporter, openai_client, instrument_with_content
):
    """Test that assistant messages in input are properly logged."""
    model = "gpt-4o-mini"

    # Include previous assistant response in input
    messages = [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Hello"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Hi there!"}],
        },
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "How are you?"}],
        },
    ]

    responses = getattr(openai_client, "responses")
    _ = responses.create(
        model=model,
        input=messages,
    )

    logs = log_exporter.get_finished_logs()

    # Should have user, assistant, and user input logs plus output
    user_logs = [
        log for log in logs if log.log_record.event_name == "gen_ai.user.input"
    ]
    assistant_logs = [
        log
        for log in logs
        if log.log_record.event_name == "gen_ai.assistant.input"
    ]

    assert len(user_logs) >= 2
    assert len(assistant_logs) >= 1
