import json
from typing import Optional

import pytest
from openai import OpenAI
from openai.resources.chat.completions import ChatCompletion

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.semconv._incubating.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    event_attributes as EventAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)

# TODO: ENABLE CONTENT FLAG!!!!!!


@pytest.mark.vcr()
def test_chat_completion(span_exporter, log_exporter, openai_client):
    llm_model_value = "gpt-4o-mini"
    messages_value = [{"role": "user", "content": "Say this is a test"}]

    response = openai_client.chat.completions.create(
        messages=messages_value, model=llm_model_value, stream=False
    )

    spans = span_exporter.get_finished_spans()
    assert_completion_attributes(spans[0], llm_model_value, response)

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 2

    user_message = {"content": messages_value[0]["content"]}
    assert_message_in_logs(
        logs[0], "gen_ai.user.message", user_message, spans[0]
    )

    choice_event = {
        "index": 0,
        "finish_reason": "stop",
        "message": {
            "role": "assistant",
            "content": response.choices[0].message.content,
        },
    }
    assert_message_in_logs(logs[1], "gen_ai.choice", choice_event, spans[0])


def test_chat_completion_bad_endpoint(
    span_exporter, log_exporter, openai_client
):
    llm_model_value = "gpt-4o-mini"
    messages_value = [{"role": "user", "content": "Say this is a test"}]

    client = OpenAI(base_url="http://localhost:4242")

    try:
        client.chat.completions.create(
            messages=messages_value,
            model=llm_model_value,
            timeout=0.1,
        )
        assert False, "Expected an exception"
    except Exception as ex:
        exception = ex

    spans = span_exporter.get_finished_spans()
    assert_all_attributes(
        spans[0], llm_model_value, server_address="localhost"
    )
    assert 4242 == spans[0].attributes[ServerAttributes.SERVER_PORT]
    assert (
        type(exception).__qualname__
        == spans[0].attributes[ErrorAttributes.ERROR_TYPE]
    )


@pytest.mark.vcr()
def test_chat_completion_404(span_exporter, log_exporter, openai_client):
    llm_model_value = "this-model-does-not-exist"
    messages_value = [{"role": "user", "content": "Say this is a test"}]

    try:
        openai_client.chat.completions.create(
            messages=messages_value,
            model=llm_model_value,
            timeout=0.1,
        )
        assert False, "Expected an exception"
    except Exception as ex:
        exception = ex

    spans = span_exporter.get_finished_spans()

    assert_all_attributes(spans[0], llm_model_value)
    assert (
        type(exception).__qualname__
        == spans[0].attributes[ErrorAttributes.ERROR_TYPE]
    )


@pytest.mark.vcr()
def test_chat_completion_extra_params(
    span_exporter, log_exporter, openai_client
):
    llm_model_value = "gpt-4o-mini"
    messages_value = [{"role": "user", "content": "Say this is a test"}]

    response = openai_client.chat.completions.create(
        messages=messages_value,
        model=llm_model_value,
        seed=42,
        temperature=0.5,
        max_tokens=50,
        stream=False,
        extra_body={"service_tier": "default"},
    )

    spans = span_exporter.get_finished_spans()
    assert_completion_attributes(spans[0], llm_model_value, response)
    assert (
        spans[0].attributes[GenAIAttributes.GEN_AI_OPENAI_REQUEST_SEED] == 42
    )
    assert (
        spans[0].attributes[GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE] == 0.5
    )
    assert spans[0].attributes[GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS] == 50
    assert (
        spans[0].attributes[GenAIAttributes.GEN_AI_OPENAI_REQUEST_SERVICE_TIER]
        == "default"
    )


@pytest.mark.vcr()
def test_chat_completion_multiple_choices(
    span_exporter, log_exporter, openai_client
):
    llm_model_value = "gpt-4o-mini"
    messages_value = [{"role": "user", "content": "Say this is a test"}]

    response = openai_client.chat.completions.create(
        messages=messages_value, model=llm_model_value, n=2, stream=False
    )

    spans = span_exporter.get_finished_spans()
    assert_completion_attributes(spans[0], llm_model_value, response)

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 3  # 1 user message + 2 choice messages

    user_message = {"content": messages_value[0]["content"]}
    assert_message_in_logs(
        logs[0], "gen_ai.user.message", user_message, spans[0]
    )

    choice_event_0 = {
        "index": 0,
        "finish_reason": "stop",
        "message": {
            "role": "assistant",
            "content": response.choices[0].message.content,
        },
    }
    assert_message_in_logs(logs[1], "gen_ai.choice", choice_event_0, spans[0])

    choice_event_1 = {
        "index": 1,
        "finish_reason": "stop",
        "message": {
            "role": "assistant",
            "content": response.choices[1].message.content,
        },
    }
    assert_message_in_logs(logs[2], "gen_ai.choice", choice_event_1, spans[0])


@pytest.mark.vcr()
def test_chat_completion_tool_calls(
    span_exporter, log_exporter, openai_client
):
    llm_model_value = "gpt-4o-mini"
    messages_value = [
        {"role": "system", "content": "You're a helpful assistant."},
        {
            "role": "user",
            "content": "What's the weather in Seattle and San Francisco today?",
        },
    ]

    response_0 = openai_client.chat.completions.create(
        messages=messages_value,
        model=llm_model_value,
        tool_choice="auto",
        tools=[get_current_weather_tool_definition()],
    )

    # sanity check
    assert "tool_calls" in response_0.choices[0].finish_reason

    # final request
    messages_value.append(
        {
            "role": "assistant",
            "tool_calls": response_0.choices[0].message.to_dict()[
                "tool_calls"
            ],
        }
    )

    tool_call_result_0 = {
        "role": "tool",
        "content": "50 degrees and raining",
        "tool_call_id": response_0.choices[0].message.tool_calls[0].id,
    }
    tool_call_result_1 = {
        "role": "tool",
        "content": "70 degrees and sunny",
        "tool_call_id": response_0.choices[0].message.tool_calls[1].id,
    }

    messages_value.append(tool_call_result_0)
    messages_value.append(tool_call_result_1)

    response_1 = openai_client.chat.completions.create(
        messages=messages_value, model=llm_model_value
    )

    # sanity check
    assert "stop" in response_1.choices[0].finish_reason

    # validate both calls
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 2
    assert_completion_attributes(spans[0], llm_model_value, response_0)
    assert_completion_attributes(spans[1], llm_model_value, response_1)

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 9  # 3 logs for first completion, 6 for second

    # call one
    system_message = {"content": messages_value[0]["content"]}
    assert_message_in_logs(
        logs[0], "gen_ai.system.message", system_message, spans[0]
    )

    user_message = {"content": messages_value[1]["content"]}
    assert_message_in_logs(
        logs[1], "gen_ai.user.message", user_message, spans[0]
    )

    choice_event = {
        "index": 0,
        "finish_reason": "tool_calls",
        "message": {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": response_0.choices[0].message.tool_calls[0].id,
                    "type": "function",
                    "function": {
                        "name": "get_current_weather",
                        "arguments": response_0.choices[0]
                        .message.tool_calls[0]
                        .function.arguments.replace("\n", ""),
                    },
                },
                {
                    "id": response_0.choices[0].message.tool_calls[1].id,
                    "type": "function",
                    "function": {
                        "name": "get_current_weather",
                        "arguments": response_0.choices[0]
                        .message.tool_calls[1]
                        .function.arguments.replace("\n", ""),
                    },
                },
            ],
        },
    }
    assert_message_in_logs(logs[2], "gen_ai.choice", choice_event, spans[0])

    # call two
    system_message = {"content": messages_value[0]["content"]}
    assert_message_in_logs(
        logs[3], "gen_ai.system.message", system_message, spans[1]
    )

    user_message = {"content": messages_value[1]["content"]}
    assert_message_in_logs(
        logs[4], "gen_ai.user.message", user_message, spans[1]
    )

    assistant_tool_call = {"tool_calls": messages_value[2]["tool_calls"]}
    assert_message_in_logs(
        logs[5], "gen_ai.assistant.message", assistant_tool_call, spans[1]
    )

    tool_message_0 = {
        "content": tool_call_result_0["content"],
        "id": tool_call_result_0["tool_call_id"],
    }
    assert_message_in_logs(
        logs[6], "gen_ai.tool.message", tool_message_0, spans[1]
    )

    tool_message_1 = {
        "content": tool_call_result_1["content"],
        "id": tool_call_result_1["tool_call_id"],
    }
    assert_message_in_logs(
        logs[7], "gen_ai.tool.message", tool_message_1, spans[1]
    )

    choice = {
        "index": 0,
        "finish_reason": "stop",
        "message": {
            "role": "assistant",
            "content": response_1.choices[0].message.content,
        },
    }
    assert_message_in_logs(logs[8], "gen_ai.choice", choice, spans[1])


@pytest.mark.vcr()
def test_chat_completion_streaming(span_exporter, log_exporter, openai_client):
    llm_model_value = "gpt-4"
    messages_value = [{"role": "user", "content": "Say this is a test"}]

    kwargs = {
        "model": llm_model_value,
        "messages": messages_value,
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    response_stream_usage = None
    response_stream_model = None
    response_stream_id = None
    response_stream_result = ""
    response = openai_client.chat.completions.create(**kwargs)
    for chunk in response:
        if chunk.choices:
            response_stream_result += chunk.choices[0].delta.content or ""

        # get the last chunk
        if getattr(chunk, "usage", None):
            response_stream_usage = chunk.usage
            response_stream_model = chunk.model
            response_stream_id = chunk.id

    spans = span_exporter.get_finished_spans()
    assert_all_attributes(
        spans[0],
        llm_model_value,
        response_stream_id,
        response_stream_model,
        response_stream_usage.prompt_tokens,
        response_stream_usage.completion_tokens,
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 2

    user_message = {"content": "Say this is a test"}
    assert_message_in_logs(
        logs[0], "gen_ai.user.message", user_message, spans[0]
    )

    choice_event = {
        "index": 0,
        "finish_reason": "stop",
        "message": {"role": "assistant", "content": response_stream_result},
    }
    assert_message_in_logs(logs[1], "gen_ai.choice", choice_event, spans[0])


@pytest.mark.vcr()
def test_chat_completion_streaming_not_complete(
    span_exporter, log_exporter, openai_client
):
    llm_model_value = "gpt-4"
    messages_value = [{"role": "user", "content": "Say this is a test"}]

    kwargs = {
        "model": llm_model_value,
        "messages": messages_value,
        "stream": True,
    }

    response_stream_model = None
    response_stream_id = None
    response_stream_result = ""
    response = openai_client.chat.completions.create(**kwargs)
    for i, chunk in enumerate(response):
        if chunk.choices:
            response_stream_result += chunk.choices[0].delta.content or ""
        if i == 1:
            # fake a stop
            break

        if chunk.model:
            response_stream_model = chunk.model
        if chunk.id:
            response_stream_id = chunk.id

    response.close()
    spans = span_exporter.get_finished_spans()
    assert_all_attributes(
        spans[0], llm_model_value, response_stream_id, response_stream_model
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 2

    user_message = {"content": "Say this is a test"}
    assert_message_in_logs(
        logs[0], "gen_ai.user.message", user_message, spans[0]
    )

    choice_event = {
        "index": 0,
        "finish_reason": "error",
        "message": {"role": "assistant", "content": response_stream_result},
    }
    assert_message_in_logs(logs[1], "gen_ai.choice", choice_event, spans[0])


@pytest.mark.vcr()
def test_chat_completion_multiple_choices_streaming(
    span_exporter, log_exporter, openai_client
):
    llm_model_value = "gpt-4o-mini"
    messages_value = [
        {"role": "system", "content": "You're a helpful assistant."},
        {
            "role": "user",
            "content": "What's the weather in Seattle and San Francisco today?",
        },
    ]

    response_0 = openai_client.chat.completions.create(
        messages=messages_value,
        model=llm_model_value,
        n=2,
        stream=True,
        stream_options={"include_usage": True},
    )

    # two strings for each choice
    response_stream_result = ["", ""]
    finish_reasons = ["", ""]
    for chunk in response_0:
        if chunk.choices:
            for choice in chunk.choices:
                response_stream_result[choice.index] += (
                    choice.delta.content or ""
                )
                if choice.finish_reason:
                    finish_reasons[choice.index] = choice.finish_reason

        # get the last chunk
        if getattr(chunk, "usage", None):
            response_stream_usage = chunk.usage
            response_stream_model = chunk.model
            response_stream_id = chunk.id

    # sanity check
    assert "stop" == finish_reasons[0]

    spans = span_exporter.get_finished_spans()
    assert_all_attributes(
        spans[0],
        llm_model_value,
        response_stream_id,
        response_stream_model,
        response_stream_usage.prompt_tokens,
        response_stream_usage.completion_tokens,
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 4

    system_message = {"content": messages_value[0]["content"]}
    assert_message_in_logs(
        logs[0], "gen_ai.system.message", system_message, spans[0]
    )

    user_message = {
        "content": "What's the weather in Seattle and San Francisco today?"
    }
    assert_message_in_logs(
        logs[1], "gen_ai.user.message", user_message, spans[0]
    )

    choice_event_0 = {
        "index": 0,
        "finish_reason": "stop",
        "message": {
            "role": "assistant",
            "content": "".join(response_stream_result[0]),
        },
    }
    assert_message_in_logs(logs[2], "gen_ai.choice", choice_event_0, spans[0])

    choice_event_1 = {
        "index": 1,
        "finish_reason": "stop",
        "message": {
            "role": "assistant",
            "content": "".join(response_stream_result[1]),
        },
    }
    assert_message_in_logs(logs[3], "gen_ai.choice", choice_event_1, spans[0])


@pytest.mark.vcr()
def test_chat_completion_multiple_tools_streaming(
    span_exporter, log_exporter, openai_client
):
    llm_model_value = "gpt-4o-mini"
    messages_value = [
        {"role": "system", "content": "You're a helpful assistant."},
        {
            "role": "user",
            "content": "What's the weather in Seattle and San Francisco today?",
        },
    ]

    response = openai_client.chat.completions.create(
        messages=messages_value,
        model=llm_model_value,
        tool_choice="auto",
        tools=[get_current_weather_tool_definition()],
        stream=True,
        stream_options={"include_usage": True},
    )

    finish_reason = None
    # two tools
    tool_names = ["", ""]
    tool_call_ids = ["", ""]
    tool_args = ["", ""]
    for chunk in response:
        if chunk.choices:
            if chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason
            for tool_call in chunk.choices[0].delta.tool_calls or []:
                t_idx = tool_call.index
                if tool_call.id:
                    tool_call_ids[t_idx] = tool_call.id
                if tool_call.function:
                    if tool_call.function.arguments:
                        tool_args[t_idx] += tool_call.function.arguments
                    if tool_call.function.name:
                        tool_names[t_idx] = tool_call.function.name

        # get the last chunk
        if getattr(chunk, "usage", None):
            response_stream_usage = chunk.usage
            response_stream_model = chunk.model
            response_stream_id = chunk.id

    # sanity check
    assert "tool_calls" == finish_reason

    spans = span_exporter.get_finished_spans()
    assert_all_attributes(
        spans[0],
        llm_model_value,
        response_stream_id,
        response_stream_model,
        response_stream_usage.prompt_tokens,
        response_stream_usage.completion_tokens,
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 3

    system_message = {"content": messages_value[0]["content"]}
    assert_message_in_logs(
        logs[0], "gen_ai.system.message", system_message, spans[0]
    )

    user_message = {
        "content": "What's the weather in Seattle and San Francisco today?"
    }
    assert_message_in_logs(
        logs[1], "gen_ai.user.message", user_message, spans[0]
    )

    choice_event = {
        "index": 0,
        "finish_reason": "tool_calls",
        "message": {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": tool_call_ids[0],
                    "type": "function",
                    "function": {
                        "name": tool_names[0],
                        "arguments": tool_args[0].replace("\n", ""),
                    },
                },
                {
                    "id": tool_call_ids[1],
                    "type": "function",
                    "function": {
                        "name": tool_names[1],
                        "arguments": tool_args[1].replace("\n", ""),
                    },
                },
            ],
        },
    }
    assert_message_in_logs(logs[2], "gen_ai.choice", choice_event, spans[0])


def assert_message_in_logs(log, event_name, expected_content, parent_span):
    assert log.log_record.attributes[EventAttributes.EVENT_NAME] == event_name
    assert (
        log.log_record.attributes[GenAIAttributes.GEN_AI_SYSTEM]
        == GenAIAttributes.GenAiSystemValues.OPENAI.value
    )
    assert json.dumps(log.log_record.body, sort_keys=True) == json.dumps(
        expected_content, sort_keys=True
    )
    assert_log_parent(log, parent_span)


def assert_completion_attributes(
    span: ReadableSpan,
    request_model: str,
    response: ChatCompletion,
    operation_name: str = "chat",
    server_address: str = "api.openai.com",
):
    return assert_all_attributes(
        span,
        request_model,
        response.id,
        response.model,
        response.usage.prompt_tokens,
        response.usage.completion_tokens,
        operation_name,
        server_address,
    )


def assert_all_attributes(
    span: ReadableSpan,
    request_model: str,
    response_id: str = None,
    response_model: str = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    operation_name: str = "chat",
    server_address: str = "api.openai.com",
):
    assert span.name == f"{operation_name} {request_model}"
    assert (
        operation_name
        == span.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
    )
    assert (
        GenAIAttributes.GenAiSystemValues.OPENAI.value
        == span.attributes[GenAIAttributes.GEN_AI_SYSTEM]
    )
    assert (
        request_model == span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
    )
    if response_model:
        assert (
            response_model
            == span.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL]
        )
    else:
        assert GenAIAttributes.GEN_AI_RESPONSE_MODEL not in span.attributes

    if response_id:
        assert (
            response_id == span.attributes[GenAIAttributes.GEN_AI_RESPONSE_ID]
        )
    else:
        assert GenAIAttributes.GEN_AI_RESPONSE_ID not in span.attributes

    if input_tokens:
        assert (
            input_tokens
            == span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
        )
    else:
        assert GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS not in span.attributes

    if output_tokens:
        assert (
            output_tokens
            == span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
        )
    else:
        assert (
            GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS not in span.attributes
        )

    assert server_address == span.attributes[ServerAttributes.SERVER_ADDRESS]


def assert_log_parent(log, span):
    assert log.log_record.trace_id == span.get_span_context().trace_id
    assert log.log_record.span_id == span.get_span_context().span_id
    assert log.log_record.trace_flags == span.get_span_context().trace_flags


def get_current_weather_tool_definition():
    return {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "Get the current weather in a given location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. Boston, MA",
                    },
                },
                "required": ["location"],
                "additionalProperties": False,
            },
        },
    }
