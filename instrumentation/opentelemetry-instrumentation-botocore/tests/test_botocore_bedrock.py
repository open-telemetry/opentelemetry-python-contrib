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

# pylint:disable=too-many-lines

from __future__ import annotations

import io
import json
from unittest import mock

import boto3
import pytest
from botocore.eventstream import EventStream, EventStreamError
from botocore.response import StreamingBody

from opentelemetry.semconv._incubating.attributes.error_attributes import (
    ERROR_TYPE,
)
from opentelemetry.trace.status import StatusCode

from .bedrock_utils import (
    assert_completion_attributes_from_streaming_body,
    assert_converse_completion_attributes,
    assert_message_in_logs,
    assert_metrics,
    assert_stream_completion_attributes,
)

BOTO3_VERSION = tuple(int(x) for x in boto3.__version__.split("."))


def filter_message_keys(message, keys):
    return {k: v for k, v in message.items() if k in keys}


@pytest.mark.skipif(
    BOTO3_VERSION < (1, 35, 56), reason="Converse API not available"
)
@pytest.mark.vcr()
def test_converse_with_content(
    span_exporter,
    log_exporter,
    metric_reader,
    bedrock_runtime_client,
    instrument_with_content,
):
    # pylint:disable=too-many-locals
    messages = [{"role": "user", "content": [{"text": "Say this is a test"}]}]

    llm_model_value = "amazon.titan-text-lite-v1"
    max_tokens, temperature, top_p, stop_sequences = 10, 0.8, 1, ["|"]
    response = bedrock_runtime_client.converse(
        messages=messages,
        modelId=llm_model_value,
        inferenceConfig={
            "maxTokens": max_tokens,
            "temperature": temperature,
            "topP": top_p,
            "stopSequences": stop_sequences,
        },
    )

    (span,) = span_exporter.get_finished_spans()
    assert_converse_completion_attributes(
        span,
        llm_model_value,
        response,
        "chat",
        top_p,
        temperature,
        max_tokens,
        stop_sequences,
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 2
    user_content = filter_message_keys(messages[0], ["content"])
    assert_message_in_logs(logs[0], "gen_ai.user.message", user_content, span)
    choice_body = {
        "index": 0,
        "finish_reason": "max_tokens",
        "message": {
            "content": [{"text": "Hi, how can I help you"}],
            "role": "assistant",
        },
    }
    assert_message_in_logs(logs[1], "gen_ai.choice", choice_body, span)

    input_tokens = response["usage"]["inputTokens"]
    output_tokens = response["usage"]["outputTokens"]
    metrics = metric_reader.get_metrics_data().resource_metrics
    assert_metrics(
        metrics, "chat", llm_model_value, input_tokens, output_tokens
    )


@pytest.mark.skipif(
    BOTO3_VERSION < (1, 35, 56), reason="Converse API not available"
)
@pytest.mark.vcr()
def test_converse_with_content_different_events(
    span_exporter,
    log_exporter,
    metric_reader,
    bedrock_runtime_client,
    instrument_with_content,
):
    # pylint:disable=too-many-locals
    messages = anthropic_claude_converse_messages()
    llm_model_value = "anthropic.claude-v2"
    system_content = anthropic_claude_converse_system()
    response = bedrock_runtime_client.converse(
        system=system_content,
        messages=messages,
        modelId=llm_model_value,
    )

    (span,) = span_exporter.get_finished_spans()
    assert_converse_completion_attributes(
        span,
        llm_model_value,
        response,
        "chat",
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 5
    assert_message_in_logs(
        logs[0], "gen_ai.system.message", {"content": system_content}, span
    )
    user_message, assistant_message, last_user_message = messages
    user_content = filter_message_keys(user_message, ["content"])
    assert_message_in_logs(logs[1], "gen_ai.user.message", user_content, span)
    assistant_content = filter_message_keys(assistant_message, ["content"])
    assert_message_in_logs(
        logs[2], "gen_ai.assistant.message", assistant_content, span
    )
    last_user_content = filter_message_keys(last_user_message, ["content"])
    assert_message_in_logs(
        logs[3], "gen_ai.user.message", last_user_content, span
    )
    choice_body = {
        "index": 0,
        "finish_reason": "end_turn",
        "message": {
            "content": [{"text": "This is a test"}],
            "role": "assistant",
        },
    }
    assert_message_in_logs(logs[4], "gen_ai.choice", choice_body, span)

    input_tokens = response["usage"]["inputTokens"]
    output_tokens = response["usage"]["outputTokens"]
    metrics = metric_reader.get_metrics_data().resource_metrics
    assert_metrics(
        metrics, "chat", llm_model_value, input_tokens, output_tokens
    )


def converse_tool_call(
    span_exporter, log_exporter, bedrock_runtime_client, expect_content
):
    # pylint:disable=too-many-locals
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "text": "What is the weather in Seattle and San Francisco today?"
                }
            ],
        }
    ]

    tool_config = get_tool_config()
    llm_model_value = "amazon.nova-micro-v1:0"
    response_0 = bedrock_runtime_client.converse(
        messages=messages,
        modelId=llm_model_value,
        toolConfig=tool_config,
    )

    # first content block is model thinking, so skip it
    tool_requests_ids = [
        request["toolUse"]["toolUseId"]
        for request in response_0["output"]["message"]["content"]
        if "toolUse" in request
    ]
    assert len(tool_requests_ids) == 2
    tool_call_result = {
        "role": "user",
        "content": [
            {
                "toolResult": {
                    "content": [
                        {"json": {"weather": "50 degrees and raining"}}
                    ],
                    "toolUseId": tool_requests_ids[0],
                },
            },
            {
                "toolResult": {
                    "content": [{"json": {"weather": "70 degrees and sunny"}}],
                    "toolUseId": tool_requests_ids[1],
                },
            },
        ],
    }

    messages.append(response_0["output"]["message"])
    messages.append(tool_call_result)

    response_1 = bedrock_runtime_client.converse(
        messages=messages,
        modelId=llm_model_value,
        toolConfig=tool_config,
    )

    (span_0, span_1) = span_exporter.get_finished_spans()
    assert_converse_completion_attributes(
        span_0,
        llm_model_value,
        response_0,
        "chat",
    )
    assert_converse_completion_attributes(
        span_1,
        llm_model_value,
        response_1,
        "chat",
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 8

    # first span
    if expect_content:
        user_content = filter_message_keys(messages[0], ["content"])
    else:
        user_content = {}
    assert_message_in_logs(
        logs[0], "gen_ai.user.message", user_content, span_0
    )

    function_call_0 = {"name": "get_current_weather"}
    function_call_1 = {"name": "get_current_weather"}
    if expect_content:
        function_call_0["arguments"] = {"location": "Seattle"}
        function_call_1["arguments"] = {"location": "San Francisco"}
    choice_body = {
        "index": 0,
        "finish_reason": "tool_use",
        "message": {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": tool_requests_ids[0],
                    "type": "function",
                    "function": function_call_0,
                },
                {
                    "id": tool_requests_ids[1],
                    "type": "function",
                    "function": function_call_1,
                },
            ],
        },
    }
    assert_message_in_logs(logs[1], "gen_ai.choice", choice_body, span_0)

    # second span
    assert_message_in_logs(
        logs[2], "gen_ai.user.message", user_content, span_1
    )
    assistant_body = response_0["output"]["message"]
    assistant_body["tool_calls"] = choice_body["message"]["tool_calls"]
    assistant_body.pop("role")
    if not expect_content:
        assistant_body.pop("content")
    assert_message_in_logs(
        logs[3],
        "gen_ai.assistant.message",
        assistant_body,
        span_1,
    )
    tool_message_0 = {
        "id": tool_requests_ids[0],
        "content": tool_call_result["content"][0]["toolResult"]["content"]
        if expect_content
        else None,
    }
    assert_message_in_logs(
        logs[4], "gen_ai.tool.message", tool_message_0, span_1
    )
    tool_message_1 = {
        "id": tool_requests_ids[1],
        "content": tool_call_result["content"][1]["toolResult"]["content"]
        if expect_content
        else None,
    }
    assert_message_in_logs(
        logs[5], "gen_ai.tool.message", tool_message_1, span_1
    )

    user_message_body = tool_call_result
    user_message_body.pop("role")
    if not expect_content:
        user_message_body.pop("content")
    assert_message_in_logs(
        logs[6], "gen_ai.user.message", user_message_body, span_1
    )
    choice_body = {
        "index": 0,
        "finish_reason": "end_turn",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "text": "<thinking> I have received the weather information for both cities. Now I will compile this information and present it to the User.</thinking>\n\nThe current weather in Seattle is 50 degrees and it's raining. In San Francisco, it's 70 degrees and sunny today."
                }
            ],
        },
    }
    if not expect_content:
        choice_body["message"].pop("content")
    assert_message_in_logs(logs[7], "gen_ai.choice", choice_body, span_1)


@pytest.mark.skipif(
    BOTO3_VERSION < (1, 35, 56), reason="Converse API not available"
)
@pytest.mark.vcr()
def test_converse_tool_call_with_content(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_with_content,
):
    converse_tool_call(
        span_exporter,
        log_exporter,
        bedrock_runtime_client,
        expect_content=True,
    )


@pytest.mark.skipif(
    BOTO3_VERSION < (1, 35, 56), reason="Converse API not available"
)
@pytest.mark.vcr()
def test_converse_no_content_different_events(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_no_content,
):
    messages = anthropic_claude_converse_messages()
    llm_model_value = "anthropic.claude-v2"
    system_content = anthropic_claude_converse_system()
    response = bedrock_runtime_client.converse(
        system=system_content,
        messages=messages,
        modelId=llm_model_value,
    )

    (span,) = span_exporter.get_finished_spans()
    assert_converse_completion_attributes(
        span,
        llm_model_value,
        response,
        "chat",
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 5
    assert_message_in_logs(logs[0], "gen_ai.system.message", None, span)
    assert_message_in_logs(logs[1], "gen_ai.user.message", None, span)
    assert_message_in_logs(logs[2], "gen_ai.assistant.message", None, span)
    assert_message_in_logs(logs[3], "gen_ai.user.message", None, span)
    choice_body = {
        "index": 0,
        "finish_reason": "end_turn",
        "message": {"role": "assistant"},
    }
    assert_message_in_logs(logs[4], "gen_ai.choice", choice_body, span)


@pytest.mark.skipif(
    BOTO3_VERSION < (1, 35, 56), reason="Converse API not available"
)
@pytest.mark.vcr()
def test_converse_no_content(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_no_content,
):
    messages = [{"role": "user", "content": [{"text": "Say this is a test"}]}]

    llm_model_value = "amazon.titan-text-lite-v1"
    max_tokens, temperature, top_p, stop_sequences = 10, 0.8, 1, ["|"]
    response = bedrock_runtime_client.converse(
        messages=messages,
        modelId=llm_model_value,
        inferenceConfig={
            "maxTokens": max_tokens,
            "temperature": temperature,
            "topP": top_p,
            "stopSequences": stop_sequences,
        },
    )

    (span,) = span_exporter.get_finished_spans()
    assert_converse_completion_attributes(
        span,
        llm_model_value,
        response,
        "chat",
        top_p,
        temperature,
        max_tokens,
        stop_sequences,
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 2
    assert_message_in_logs(logs[0], "gen_ai.user.message", None, span)
    choice_body = {
        "index": 0,
        "finish_reason": "max_tokens",
        "message": {"role": "assistant"},
    }
    assert_message_in_logs(logs[1], "gen_ai.choice", choice_body, span)


@pytest.mark.skipif(
    BOTO3_VERSION < (1, 35, 56), reason="Converse API not available"
)
@pytest.mark.vcr()
def test_converse_tool_call_no_content(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_no_content,
):
    converse_tool_call(
        span_exporter,
        log_exporter,
        bedrock_runtime_client,
        expect_content=False,
    )


@pytest.mark.skipif(
    BOTO3_VERSION < (1, 35, 56), reason="Converse API not available"
)
@pytest.mark.vcr()
def test_converse_with_invalid_model(
    span_exporter,
    log_exporter,
    metric_reader,
    bedrock_runtime_client,
    instrument_with_content,
):
    messages = [{"role": "user", "content": [{"text": "Say this is a test"}]}]

    llm_model_value = "does-not-exist"
    with pytest.raises(bedrock_runtime_client.exceptions.ValidationException):
        bedrock_runtime_client.converse(
            messages=messages,
            modelId=llm_model_value,
        )

    (span,) = span_exporter.get_finished_spans()
    assert_converse_completion_attributes(
        span,
        llm_model_value,
        None,
        "chat",
    )

    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes[ERROR_TYPE] == "ValidationException"

    logs = log_exporter.get_finished_logs()
    user_content = filter_message_keys(messages[0], ["content"])
    assert_message_in_logs(logs[0], "gen_ai.user.message", user_content, span)

    metrics = metric_reader.get_metrics_data().resource_metrics
    assert_metrics(
        metrics, "chat", llm_model_value, error_type="ValidationException"
    )


@pytest.mark.skipif(
    BOTO3_VERSION < (1, 35, 56), reason="ConverseStream API not available"
)
@pytest.mark.vcr()
def test_converse_stream_with_content(
    span_exporter,
    log_exporter,
    metric_reader,
    bedrock_runtime_client,
    instrument_with_content,
):
    # pylint:disable=too-many-locals
    messages = [{"role": "user", "content": [{"text": "Say this is a test"}]}]

    llm_model_value = "amazon.titan-text-lite-v1"
    max_tokens, temperature, top_p, stop_sequences = 10, 0.8, 1, ["|"]
    response = bedrock_runtime_client.converse_stream(
        messages=messages,
        modelId=llm_model_value,
        inferenceConfig={
            "maxTokens": max_tokens,
            "temperature": temperature,
            "topP": top_p,
            "stopSequences": stop_sequences,
        },
    )

    # consume the stream in order to have it traced
    finish_reason = None
    input_tokens, output_tokens = None, None
    text = ""
    for event in response["stream"]:
        if "contentBlockDelta" in event:
            text += event["contentBlockDelta"]["delta"]["text"]
        if "messageStop" in event:
            finish_reason = (event["messageStop"]["stopReason"],)
        if "metadata" in event:
            usage = event["metadata"]["usage"]
            input_tokens = usage["inputTokens"]
            output_tokens = usage["outputTokens"]

    assert text
    assert finish_reason
    assert input_tokens
    assert output_tokens

    (span,) = span_exporter.get_finished_spans()
    assert_stream_completion_attributes(
        span,
        llm_model_value,
        input_tokens,
        output_tokens,
        finish_reason,
        "chat",
        top_p,
        temperature,
        max_tokens,
        stop_sequences,
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 2
    user_content = filter_message_keys(messages[0], ["content"])
    assert_message_in_logs(logs[0], "gen_ai.user.message", user_content, span)
    choice_body = {
        "index": 0,
        "finish_reason": "max_tokens",
        "message": {
            "content": [{"text": "I am here and ready to assist"}],
            "role": "assistant",
        },
    }
    assert_message_in_logs(logs[1], "gen_ai.choice", choice_body, span)

    metrics = metric_reader.get_metrics_data().resource_metrics
    assert_metrics(
        metrics, "chat", llm_model_value, input_tokens, output_tokens
    )


@pytest.mark.skipif(
    BOTO3_VERSION < (1, 35, 56), reason="ConverseStream API not available"
)
@pytest.mark.vcr()
def test_converse_stream_with_content_different_events(
    span_exporter,
    log_exporter,
    metric_reader,
    bedrock_runtime_client,
    instrument_with_content,
):
    # pylint:disable=too-many-locals
    messages = anthropic_claude_converse_messages()
    llm_model_value = "anthropic.claude-v2"
    system_content = anthropic_claude_converse_system()
    response = bedrock_runtime_client.converse_stream(
        system=system_content,
        messages=messages,
        modelId=llm_model_value,
    )

    # consume the stream in order to have it traced
    for _ in response["stream"]:
        pass

    (span,) = span_exporter.get_finished_spans()
    assert_stream_completion_attributes(
        span,
        llm_model_value,
        input_tokens=mock.ANY,
        output_tokens=mock.ANY,
        finish_reason=("end_turn",),
        operation_name="chat",
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 5
    assert_message_in_logs(
        logs[0], "gen_ai.system.message", {"content": system_content}, span
    )
    user_message, assistant_message, last_user_message = messages
    user_content = filter_message_keys(user_message, ["content"])
    assert_message_in_logs(logs[1], "gen_ai.user.message", user_content, span)
    assistant_content = filter_message_keys(assistant_message, ["content"])
    assert_message_in_logs(
        logs[2], "gen_ai.assistant.message", assistant_content, span
    )
    last_user_content = filter_message_keys(last_user_message, ["content"])
    assert_message_in_logs(
        logs[3], "gen_ai.user.message", last_user_content, span
    )
    choice_body = {
        "index": 0,
        "finish_reason": "end_turn",
        "message": {
            "role": "assistant",
            "content": [{"text": "This is a test"}],
        },
    }
    assert_message_in_logs(logs[4], "gen_ai.choice", choice_body, span)

    metrics = metric_reader.get_metrics_data().resource_metrics
    assert_metrics(metrics, "chat", llm_model_value, mock.ANY, mock.ANY)


def _rebuild_stream_message(response):
    message = {"content": []}
    content_block = {}
    for stream_msg in response["stream"]:
        if "messageStart" in stream_msg:
            message.update(stream_msg["messageStart"])

        elif "contentBlockStart" in stream_msg:
            start = stream_msg["contentBlockStart"]["start"]
            if "toolUse" in start:
                # toolUse.input is already decoded by the wrapper
                content_block = {"toolUse": start["toolUse"]}

        elif "contentBlockDelta" in stream_msg:
            delta = stream_msg["contentBlockDelta"]["delta"]
            if "text" in delta:
                content_block.setdefault("text", "")
                content_block["text"] += delta["text"]
            elif "toolUse" in delta:
                # toolUse.input is already decoded by the wrapper
                content_block["toolUse"].update(delta["toolUse"])

        elif "contentBlockStop" in stream_msg:
            message["content"].append(content_block)

        elif "messageStop" in stream_msg:
            message.update(stream_msg["messageStop"])

    return message


def converse_stream_tool_call(
    span_exporter, log_exporter, bedrock_runtime_client, expect_content
):
    # pylint:disable=too-many-locals,too-many-statements
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "text": "What is the weather in Seattle and San Francisco today?"
                }
            ],
        }
    ]

    tool_config = get_tool_config()
    llm_model_value = "amazon.nova-micro-v1:0"
    response_0 = bedrock_runtime_client.converse_stream(
        messages=messages,
        modelId=llm_model_value,
        toolConfig=tool_config,
    )

    # consume the stream and assemble it as the non-streaming version
    response_0_message = _rebuild_stream_message(response_0)

    tool_requests_ids = [
        request["toolUse"]["toolUseId"]
        for request in response_0_message["content"]
        if "toolUse" in request
    ]
    assert len(tool_requests_ids) == 2

    tool_call_result = {
        "role": "user",
        "content": [
            {
                "toolResult": {
                    "content": [
                        {"json": {"weather": "50 degrees and raining"}}
                    ],
                    "toolUseId": tool_requests_ids[0],
                },
            },
            {
                "toolResult": {
                    "content": [{"json": {"weather": "70 degrees and sunny"}}],
                    "toolUseId": tool_requests_ids[1],
                },
            },
        ],
    }

    response_0_message.pop("stopReason")
    messages.append(response_0_message)
    messages.append(tool_call_result)

    response_1 = bedrock_runtime_client.converse_stream(
        messages=messages,
        modelId=llm_model_value,
        toolConfig=tool_config,
    )

    # consume the stream to have it traced
    _ = _rebuild_stream_message(response_1)

    (span_0, span_1) = span_exporter.get_finished_spans()
    assert_stream_completion_attributes(
        span_0,
        llm_model_value,
        input_tokens=mock.ANY,
        output_tokens=mock.ANY,
        finish_reason=("tool_use",),
        operation_name="chat",
    )
    assert_stream_completion_attributes(
        span_1,
        llm_model_value,
        input_tokens=mock.ANY,
        output_tokens=mock.ANY,
        finish_reason=("end_turn",),
        operation_name="chat",
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 8

    # first span
    if expect_content:
        user_content = filter_message_keys(messages[0], ["content"])
    else:
        user_content = {}
    assert_message_in_logs(
        logs[0], "gen_ai.user.message", user_content, span_0
    )

    function_call_0 = {"name": "get_current_weather"}
    function_call_1 = {"name": "get_current_weather"}
    if expect_content:
        function_call_0["arguments"] = {"location": "Seattle"}
        function_call_1["arguments"] = {"location": "San Francisco"}
    choice_body = {
        "index": 0,
        "finish_reason": "tool_use",
        "message": {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": tool_requests_ids[0],
                    "type": "function",
                    "function": function_call_0,
                },
                {
                    "id": tool_requests_ids[1],
                    "type": "function",
                    "function": function_call_1,
                },
            ],
        },
    }
    assert_message_in_logs(logs[1], "gen_ai.choice", choice_body, span_0)

    # second span
    assert_message_in_logs(
        logs[2], "gen_ai.user.message", user_content, span_1
    )
    assistant_body = response_0_message
    assistant_body["tool_calls"] = choice_body["message"]["tool_calls"]
    assistant_body.pop("role")
    if not expect_content:
        assistant_body.pop("content")
    assert_message_in_logs(
        logs[3],
        "gen_ai.assistant.message",
        assistant_body,
        span_1,
    )
    tool_message_0 = {
        "id": tool_requests_ids[0],
        "content": tool_call_result["content"][0]["toolResult"]["content"]
        if expect_content
        else None,
    }
    assert_message_in_logs(
        logs[4], "gen_ai.tool.message", tool_message_0, span_1
    )
    tool_message_1 = {
        "id": tool_requests_ids[1],
        "content": tool_call_result["content"][1]["toolResult"]["content"]
        if expect_content
        else None,
    }
    assert_message_in_logs(
        logs[5], "gen_ai.tool.message", tool_message_1, span_1
    )

    user_message_body = tool_call_result
    user_message_body.pop("role")
    if not expect_content:
        user_message_body.pop("content")
    assert_message_in_logs(
        logs[6], "gen_ai.user.message", user_message_body, span_1
    )
    choice_body = {
        "index": 0,
        "finish_reason": "end_turn",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "text": "<thinking> I have received the weather information for both cities. Now I will provide the details to the User.</thinking>\n\nThe current weather in Seattle is 50 degrees and raining. In San Francisco, the weather is 70 degrees and sunny."
                }
            ],
        },
    }
    if not expect_content:
        choice_body["message"].pop("content")
    assert_message_in_logs(logs[7], "gen_ai.choice", choice_body, span_1)


@pytest.mark.skipif(
    BOTO3_VERSION < (1, 35, 56), reason="ConverseStream API not available"
)
@pytest.mark.vcr()
def test_converse_stream_with_content_tool_call(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_with_content,
):
    converse_stream_tool_call(
        span_exporter,
        log_exporter,
        bedrock_runtime_client,
        expect_content=True,
    )


@pytest.mark.skipif(
    BOTO3_VERSION < (1, 35, 56), reason="ConverseStream API not available"
)
@pytest.mark.vcr()
def test_converse_stream_no_content(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_no_content,
):
    # pylint:disable=too-many-locals
    messages = [{"role": "user", "content": [{"text": "Say this is a test"}]}]

    llm_model_value = "amazon.titan-text-lite-v1"
    max_tokens, temperature, top_p, stop_sequences = 10, 0.8, 1, ["|"]
    response = bedrock_runtime_client.converse_stream(
        messages=messages,
        modelId=llm_model_value,
        inferenceConfig={
            "maxTokens": max_tokens,
            "temperature": temperature,
            "topP": top_p,
            "stopSequences": stop_sequences,
        },
    )

    # consume the stream in order to have it traced
    finish_reason = None
    input_tokens, output_tokens = None, None
    text = ""
    for event in response["stream"]:
        if "contentBlockDelta" in event:
            text += event["contentBlockDelta"]["delta"]["text"]
        if "messageStop" in event:
            finish_reason = event["messageStop"]["stopReason"]
        if "metadata" in event:
            usage = event["metadata"]["usage"]
            input_tokens = usage["inputTokens"]
            output_tokens = usage["outputTokens"]

    assert text
    assert finish_reason
    assert input_tokens
    assert output_tokens

    (span,) = span_exporter.get_finished_spans()
    assert_stream_completion_attributes(
        span,
        llm_model_value,
        input_tokens,
        output_tokens,
        (finish_reason,),
        "chat",
        top_p,
        temperature,
        max_tokens,
        stop_sequences,
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 2
    assert_message_in_logs(logs[0], "gen_ai.user.message", None, span)
    choice_body = {
        "index": 0,
        "finish_reason": finish_reason,
        "message": {"role": "assistant"},
    }
    assert_message_in_logs(logs[1], "gen_ai.choice", choice_body, span)


@pytest.mark.skipif(
    BOTO3_VERSION < (1, 35, 56), reason="ConverseStream API not available"
)
@pytest.mark.vcr()
def test_converse_stream_no_content_different_events(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_no_content,
):
    messages = anthropic_claude_converse_messages()
    llm_model_value = "anthropic.claude-v2"
    system_content = anthropic_claude_converse_system()
    response = bedrock_runtime_client.converse_stream(
        system=system_content,
        messages=messages,
        modelId=llm_model_value,
    )

    # consume the stream in order to have it traced
    for _ in response["stream"]:
        pass

    (span,) = span_exporter.get_finished_spans()
    assert_stream_completion_attributes(
        span,
        llm_model_value,
        input_tokens=mock.ANY,
        output_tokens=mock.ANY,
        finish_reason=("end_turn",),
        operation_name="chat",
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 5
    assert_message_in_logs(logs[0], "gen_ai.system.message", None, span)
    assert_message_in_logs(logs[1], "gen_ai.user.message", None, span)
    assert_message_in_logs(logs[2], "gen_ai.assistant.message", None, span)
    assert_message_in_logs(logs[3], "gen_ai.user.message", None, span)
    choice_body = {
        "index": 0,
        "finish_reason": "end_turn",
        "message": {"role": "assistant"},
    }
    assert_message_in_logs(logs[4], "gen_ai.choice", choice_body, span)


@pytest.mark.skipif(
    BOTO3_VERSION < (1, 35, 56), reason="ConverseStream API not available"
)
@pytest.mark.vcr()
def test_converse_stream_no_content_tool_call(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_no_content,
):
    converse_stream_tool_call(
        span_exporter,
        log_exporter,
        bedrock_runtime_client,
        expect_content=False,
    )


@pytest.mark.skipif(
    BOTO3_VERSION < (1, 35, 56), reason="ConverseStream API not available"
)
@pytest.mark.vcr()
def test_converse_stream_handles_event_stream_error(
    span_exporter,
    log_exporter,
    metric_reader,
    bedrock_runtime_client,
    instrument_with_content,
):
    # pylint:disable=too-many-locals
    messages = [{"role": "user", "content": [{"text": "Say this is a test"}]}]

    llm_model_value = "amazon.titan-text-lite-v1"
    max_tokens, temperature, top_p, stop_sequences = 10, 0.8, 1, ["|"]
    response = bedrock_runtime_client.converse_stream(
        messages=messages,
        modelId=llm_model_value,
        inferenceConfig={
            "maxTokens": max_tokens,
            "temperature": temperature,
            "topP": top_p,
            "stopSequences": stop_sequences,
        },
    )

    with mock.patch.object(
        EventStream,
        "_parse_event",
        side_effect=EventStreamError(
            {"modelStreamErrorException": {}}, "ConverseStream"
        ),
    ):
        with pytest.raises(EventStreamError):
            for _event in response["stream"]:
                pass

    (span,) = span_exporter.get_finished_spans()
    input_tokens, output_tokens, finish_reason = None, None, None
    assert_stream_completion_attributes(
        span,
        llm_model_value,
        input_tokens,
        output_tokens,
        finish_reason,
        "chat",
        top_p,
        temperature,
        max_tokens,
        stop_sequences,
    )

    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes[ERROR_TYPE] == "EventStreamError"

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 1
    user_content = filter_message_keys(messages[0], ["content"])
    assert_message_in_logs(logs[0], "gen_ai.user.message", user_content, span)

    metrics = metric_reader.get_metrics_data().resource_metrics
    assert_metrics(
        metrics, "chat", llm_model_value, error_type="EventStreamError"
    )


@pytest.mark.skipif(
    BOTO3_VERSION < (1, 35, 56), reason="ConverseStream API not available"
)
@pytest.mark.vcr()
def test_converse_stream_with_invalid_model(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_with_content,
):
    messages = [{"role": "user", "content": [{"text": "Say this is a test"}]}]

    llm_model_value = "does-not-exist"
    with pytest.raises(bedrock_runtime_client.exceptions.ValidationException):
        bedrock_runtime_client.converse_stream(
            messages=messages,
            modelId=llm_model_value,
        )

    (span,) = span_exporter.get_finished_spans()
    assert_stream_completion_attributes(
        span,
        llm_model_value,
        operation_name="chat",
    )

    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes[ERROR_TYPE] == "ValidationException"

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 1
    user_content = filter_message_keys(messages[0], ["content"])
    assert_message_in_logs(logs[0], "gen_ai.user.message", user_content, span)


def get_invoke_model_body(
    llm_model,
    max_tokens=None,
    temperature=None,
    top_p=None,
    stop_sequences=None,
    system=None,
    messages=None,
    tools=None,
):
    def set_if_not_none(config, key, value):
        if value is not None:
            config[key] = value

    prompt = "Say this is a test"
    if llm_model == "amazon.nova-micro-v1:0":
        config = {}
        set_if_not_none(config, "max_new_tokens", max_tokens)
        set_if_not_none(config, "temperature", temperature)
        set_if_not_none(config, "topP", top_p)
        set_if_not_none(config, "stopSequences", stop_sequences)
        body = {
            "messages": messages
            if messages
            else [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": config,
            "schemaVersion": "messages-v1",
        }
        if system:
            body["system"] = system
        if tools:
            body["toolConfig"] = tools
    elif llm_model == "amazon.titan-text-lite-v1":
        config = {}
        set_if_not_none(config, "maxTokenCount", max_tokens)
        set_if_not_none(config, "temperature", temperature)
        set_if_not_none(config, "topP", top_p)
        set_if_not_none(config, "stopSequences", stop_sequences)
        body = {"inputText": prompt, "textGenerationConfig": config}
    elif "anthropic.claude" in llm_model:
        body = {
            "messages": messages
            if messages
            else [
                {"role": "user", "content": [{"text": prompt, "type": "text"}]}
            ],
            "anthropic_version": "bedrock-2023-05-31",
        }
        if system:
            body["system"] = system
        # tools are available since 3+
        if tools:
            body["tools"] = tools
        set_if_not_none(body, "max_tokens", max_tokens)
        set_if_not_none(body, "temperature", temperature)
        set_if_not_none(body, "top_p", top_p)
        set_if_not_none(body, "stop_sequences", stop_sequences)
    elif "cohere.command-r" in llm_model:
        body = {
            "message": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "p": top_p,
            "stop_sequences": stop_sequences
        }
    elif "cohere.command" in llm_model:
        body = {
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "p": top_p,
            "stop_sequences": stop_sequences
        }
    elif "meta.llama" in llm_model:
        body = {
            "prompt": prompt,
            "max_gen_len": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }
    elif "mistral.mistral" in llm_model:
        body = {
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stop": stop_sequences
        }
    else:
        raise ValueError(f"No config for {llm_model}")

    return json.dumps(body)


def get_model_name_from_family(llm_model):
    llm_model_name = {
        "amazon.titan": "amazon.titan-text-lite-v1",
        "amazon.nova": "amazon.nova-micro-v1:0",
        "anthropic.claude": "anthropic.claude-v2",
        "cohere.command-r": "cohere.command-r-v1:0",
        "cohere.command": "cohere.command-light-text-v14",
        "meta.llama": "meta.llama3-1-70b-instruct-v1:0",
        "mistral.mistral": "mistral.mistral-7b-instruct-v0:2",
    }
    return llm_model_name[llm_model]


@pytest.mark.parametrize(
    "model_family",
    ["amazon.nova", "amazon.titan", "anthropic.claude"],
)
@pytest.mark.vcr()
def test_invoke_model_with_content(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_with_content,
    model_family,
):
    # pylint:disable=too-many-locals
    llm_model_value = get_model_name_from_family(model_family)
    max_tokens, temperature, top_p, stop_sequences = 10, 0.8, 1, ["|"]
    body = get_invoke_model_body(
        llm_model_value, max_tokens, temperature, top_p, stop_sequences
    )
    response = bedrock_runtime_client.invoke_model(
        body=body,
        modelId=llm_model_value,
    )

    (span,) = span_exporter.get_finished_spans()
    assert_completion_attributes_from_streaming_body(
        span,
        llm_model_value,
        response,
        "text_completion" if model_family == "amazon.titan" else "chat",
        top_p,
        temperature,
        max_tokens,
        stop_sequences,
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 2
    if model_family == "anthropic.claude":
        user_content = {
            "content": [{"text": "Say this is a test", "type": "text"}]
        }
    else:
        user_content = {"content": [{"text": "Say this is a test"}]}
    if model_family == "amazon.titan":
        message = {"content": " comment\nHello! I am writing this as a"}
        finish_reason = "LENGTH"
    elif model_family == "amazon.nova":
        message = {
            "role": "assistant",
            "content": [{"text": "Certainly, here's a test:\n\n---\n\n**"}],
        }
        finish_reason = "max_tokens"
    elif model_family == "anthropic.claude":
        message = {
            "role": "assistant",
            "content": [
                {"type": "text", "text": 'Okay, I said "This is a test"'}
            ],
        }
        finish_reason = "max_tokens"
    assert_message_in_logs(logs[0], "gen_ai.user.message", user_content, span)
    choice_body = {
        "index": 0,
        "finish_reason": finish_reason,
        "message": message,
    }
    assert_message_in_logs(logs[1], "gen_ai.choice", choice_body, span)


@pytest.mark.vcr()
def test_invoke_model_with_content_user_content_as_string(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_with_content,
):
    llm_model_value = "us.anthropic.claude-3-5-sonnet-20240620-v1:0"
    max_tokens = 10
    body = json.dumps(
        {
            "messages": [{"role": "user", "content": "say this is a test"}],
            "max_tokens": max_tokens,
            "anthropic_version": "bedrock-2023-05-31",
        }
    )
    response = bedrock_runtime_client.invoke_model(
        body=body,
        modelId=llm_model_value,
    )

    (span,) = span_exporter.get_finished_spans()
    assert_completion_attributes_from_streaming_body(
        span,
        llm_model_value,
        response,
        "chat",
        request_max_tokens=max_tokens,
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 2
    user_content = {"content": "say this is a test"}
    assert_message_in_logs(logs[0], "gen_ai.user.message", user_content, span)

    message = {
        "role": "assistant",
        "content": [{"type": "text", "text": "This is a test."}],
    }
    choice_body = {
        "index": 0,
        "finish_reason": "end_turn",
        "message": message,
    }
    assert_message_in_logs(logs[1], "gen_ai.choice", choice_body, span)


@pytest.mark.parametrize(
    "model_family",
    ["amazon.nova", "anthropic.claude"],
)
@pytest.mark.vcr()
def test_invoke_model_with_content_different_events(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_with_content,
    model_family,
):
    # pylint:disable=too-many-locals
    llm_model_value = get_model_name_from_family(model_family)
    max_tokens = 10
    if llm_model_value == "amazon.nova-micro-v1:0":
        messages = amazon_nova_messages()
        system = amazon_nova_system()
        finish_reason = "max_tokens"
        choice_content = [{"text": "Again, this is a test. If you need"}]
    elif llm_model_value == "anthropic.claude-v2":
        messages = anthropic_claude_messages()
        system = anthropic_claude_system()
        finish_reason = "end_turn"
        choice_content = [{"type": "text", "text": "This is a test"}]

    body = get_invoke_model_body(
        llm_model_value,
        system=system,
        messages=messages,
        max_tokens=max_tokens,
    )
    response = bedrock_runtime_client.invoke_model(
        body=body,
        modelId=llm_model_value,
    )

    (span,) = span_exporter.get_finished_spans()
    assert_completion_attributes_from_streaming_body(
        span,
        llm_model_value,
        response,
        "chat",
        request_max_tokens=max_tokens,
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 5
    assert_message_in_logs(
        logs[0],
        "gen_ai.system.message",
        {"content": [{"text": "You are a friendly model"}]},
        span,
    )
    user_message, assistant_message, last_user_message = messages
    user_content = filter_message_keys(user_message, ["content"])
    assert_message_in_logs(logs[1], "gen_ai.user.message", user_content, span)
    assistant_content = filter_message_keys(assistant_message, ["content"])
    assert_message_in_logs(
        logs[2], "gen_ai.assistant.message", assistant_content, span
    )
    last_user_content = filter_message_keys(last_user_message, ["content"])
    assert_message_in_logs(
        logs[3], "gen_ai.user.message", last_user_content, span
    )
    choice_body = {
        "index": 0,
        "finish_reason": finish_reason,
        "message": {"role": "assistant", "content": choice_content},
    }
    assert_message_in_logs(logs[4], "gen_ai.choice", choice_body, span)


class AnthropicClaudeModel:
    @staticmethod
    def user_message(prompt: str):
        return {
            "text": prompt,
            "type": "text",
        }

    @staticmethod
    def tool_config():
        return get_anthropic_tool_config()

    @staticmethod
    def assistant_message(response):
        return {"role": response["role"], "content": response["content"]}

    @staticmethod
    def tool_requests_ids(response):
        return [
            content["id"]
            for content in response["content"]
            if content["type"] == "tool_use"
        ]

    @staticmethod
    def tool_requests_ids_from_stream(stream_content):
        return [
            item["id"] for item in stream_content if item["type"] == "tool_use"
        ]

    @staticmethod
    def tool_calls_results(tool_requests_ids):
        assert len(tool_requests_ids) == 2

        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_requests_ids[0],
                    "content": "50 degrees and raining",
                },
                {
                    "type": "tool_result",
                    "tool_use_id": tool_requests_ids[1],
                    "content": "70 degrees and sunny",
                },
            ],
        }

    @staticmethod
    def tool_messages(tool_requests_ids, tool_call_result, expect_content):
        tool_message_0 = {
            "id": tool_requests_ids[0],
            "content": tool_call_result["content"][0]["content"]
            if expect_content
            else None,
        }
        tool_message_1 = {
            "id": tool_requests_ids[1],
            "content": tool_call_result["content"][1]["content"]
            if expect_content
            else None,
        }
        return tool_message_0, tool_message_1

    @staticmethod
    def choice_content(response):
        return response["content"]

    @staticmethod
    def get_stream_body_content(body):
        content = []
        content_block = {}
        input_json_buf = ""
        for event in body:
            json_bytes = event["chunk"].get("bytes", b"")
            decoded = json_bytes.decode("utf-8")
            chunk = json.loads(decoded)

            if (message_type := chunk.get("type")) is not None:
                if message_type == "content_block_start":
                    content_block = chunk["content_block"]
                elif message_type == "content_block_delta":
                    if chunk["delta"]["type"] == "text_delta":
                        content_block["text"] += chunk["delta"]["text"]
                    elif chunk["delta"]["type"] == "input_json_delta":
                        input_json_buf += chunk["delta"]["partial_json"]
                elif message_type == "content_block_stop":
                    if input_json_buf:
                        content_block["input"] = json.loads(input_json_buf)
                    content.append(content_block)
                    content_block = None
                    input_json_buf = ""

        return content


class AmazonNovaModel:
    @staticmethod
    def user_message(prompt: str):
        return {
            "text": prompt,
        }

    @staticmethod
    def assistant_message(response):
        return response["output"]["message"]

    @staticmethod
    def tool_config():
        return get_tool_config()

    @staticmethod
    def tool_requests_ids(response):
        return [
            content["toolUse"]["toolUseId"]
            for content in response["output"]["message"]["content"]
            if "toolUse" in content
        ]

    @staticmethod
    def tool_requests_ids_from_stream(stream_content):
        return [
            item["toolUse"]["toolUseId"]
            for item in stream_content
            if "toolUse" in item
        ]

    @staticmethod
    def tool_calls_results(tool_requests_ids):
        assert len(tool_requests_ids) == 2

        return {
            "role": "user",
            "content": [
                {
                    "toolResult": {
                        "toolUseId": tool_requests_ids[0],
                        "content": [
                            {"json": {"weather": "50 degrees and raining"}}
                        ],
                    }
                },
                {
                    "toolResult": {
                        "toolUseId": tool_requests_ids[1],
                        "content": [
                            {"json": {"weather": "70 degrees and sunny"}}
                        ],
                    }
                },
            ],
        }

    @staticmethod
    def tool_messages(tool_requests_ids, tool_call_result, expect_content):
        tool_message_0 = {
            "id": tool_requests_ids[0],
            "content": tool_call_result["content"][0]["toolResult"]["content"]
            if expect_content
            else None,
        }
        tool_message_1 = {
            "id": tool_requests_ids[1],
            "content": tool_call_result["content"][1]["toolResult"]["content"]
            if expect_content
            else None,
        }
        return tool_message_0, tool_message_1

    @staticmethod
    def choice_content(response):
        return response["output"]["message"]["content"]

    @staticmethod
    def get_stream_body_content(body):
        content = []
        content_block = {}
        tool_use = {}
        for event in body:
            json_bytes = event["chunk"].get("bytes", b"")
            decoded = json_bytes.decode("utf-8")
            chunk = json.loads(decoded)

            if "contentBlockDelta" in chunk:
                delta = chunk["contentBlockDelta"]["delta"]
                if "text" in delta:
                    content_block.setdefault("text", "")
                    content_block["text"] += delta["text"]
                elif "toolUse" in delta:
                    tool_use["toolUse"]["input"] = json.loads(
                        delta["toolUse"]["input"]
                    )
            elif "contentBlockStart" in chunk:
                if content_block:
                    content.append(content_block)
                    content_block = {}
                start = chunk["contentBlockStart"]["start"]
                if "toolUse" in start:
                    tool_use = start
            elif "contentBlockStop" in chunk:
                if tool_use:
                    content.append(tool_use)
                    tool_use = {}
            elif "messageStop" in chunk:
                if content_block:
                    content.append(content_block)
                    content_block = {}

        return content


def invoke_model_tool_call(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    llm_model_value,
    llm_model_config,
    expect_content,
):
    # pylint:disable=too-many-locals,too-many-statements
    user_prompt = "What is the weather in Seattle and San Francisco today? Please expect one tool call for Seattle and one for San Francisco"
    user_msg = llm_model_config.user_message(user_prompt)
    messages = [{"role": "user", "content": [user_msg]}]

    max_tokens = 1000
    tool_config = llm_model_config.tool_config()
    body = get_invoke_model_body(
        llm_model_value,
        messages=messages,
        tools=tool_config,
        max_tokens=max_tokens,
    )
    response_0 = bedrock_runtime_client.invoke_model(
        body=body,
        modelId=llm_model_value,
    )

    response_0_raw_body = response_0["body"].read()
    response_0_body = json.loads(response_0_raw_body)
    # replenish body for span assertions
    new_stream = io.BytesIO(response_0_raw_body)
    response_0["body"] = StreamingBody(new_stream, len(response_0_raw_body))

    tool_requests_ids = llm_model_config.tool_requests_ids(response_0_body)
    assert len(tool_requests_ids) == 2

    assistant_message = llm_model_config.assistant_message(response_0_body)
    tool_call_result = llm_model_config.tool_calls_results(tool_requests_ids)

    messages.append(assistant_message)
    messages.append(tool_call_result)

    body = get_invoke_model_body(
        llm_model_value,
        messages=messages,
        max_tokens=max_tokens,
        tools=tool_config,
    )
    response_1 = bedrock_runtime_client.invoke_model(
        body=body,
        modelId=llm_model_value,
    )

    response_1_raw_body = response_1["body"].read()
    response_1_body = json.loads(response_1_raw_body)
    # replenish body for span assertions
    new_stream = io.BytesIO(response_1_raw_body)
    response_1["body"] = StreamingBody(new_stream, len(response_1_raw_body))

    (span_0, span_1) = span_exporter.get_finished_spans()
    assert_completion_attributes_from_streaming_body(
        span_0,
        llm_model_value,
        response_0,
        "chat",
        request_max_tokens=max_tokens,
    )
    assert_completion_attributes_from_streaming_body(
        span_1,
        llm_model_value,
        response_1,
        "chat",
        request_max_tokens=max_tokens,
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 8

    # first span
    if expect_content:
        user_content = filter_message_keys(messages[0], ["content"])
    else:
        user_content = {}
    assert_message_in_logs(
        logs[0], "gen_ai.user.message", user_content, span_0
    )

    function_call_0 = {"name": "get_current_weather"}
    function_call_1 = {"name": "get_current_weather"}
    if expect_content:
        function_call_0["arguments"] = {"location": "Seattle"}
        function_call_1["arguments"] = {"location": "San Francisco"}
    choice_body = {
        "index": 0,
        "finish_reason": "tool_use",
        "message": {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": tool_requests_ids[0],
                    "type": "function",
                    "function": function_call_0,
                },
                {
                    "id": tool_requests_ids[1],
                    "type": "function",
                    "function": function_call_1,
                },
            ],
        },
    }
    assert_message_in_logs(logs[1], "gen_ai.choice", choice_body, span_0)

    # second span
    assert_message_in_logs(
        logs[2], "gen_ai.user.message", user_content, span_1
    )
    assistant_body = assistant_message
    assistant_body["tool_calls"] = choice_body["message"]["tool_calls"]
    assistant_body.pop("role")
    if not expect_content:
        assistant_body.pop("content")
    assert_message_in_logs(
        logs[3],
        "gen_ai.assistant.message",
        assistant_body,
        span_1,
    )

    tool_message_0, tool_message_1 = llm_model_config.tool_messages(
        tool_requests_ids, tool_call_result, expect_content
    )

    assert_message_in_logs(
        logs[4], "gen_ai.tool.message", tool_message_0, span_1
    )
    assert_message_in_logs(
        logs[5], "gen_ai.tool.message", tool_message_1, span_1
    )

    user_message_body = tool_call_result
    user_message_body.pop("role")
    if not expect_content:
        user_message_body.pop("content")
    assert_message_in_logs(
        logs[6], "gen_ai.user.message", user_message_body, span_1
    )
    choice_content = llm_model_config.choice_content(response_1_body)
    choice_body = {
        "index": 0,
        "finish_reason": "end_turn",
        "message": {
            "role": "assistant",
            "content": choice_content,
        },
    }
    if not expect_content:
        choice_body["message"].pop("content")
    assert_message_in_logs(logs[7], "gen_ai.choice", choice_body, span_1)


@pytest.mark.parametrize(
    "model_family",
    ["amazon.nova", "anthropic.claude"],
)
@pytest.mark.vcr()
def test_invoke_model_with_content_tool_call(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_with_content,
    model_family,
):
    if model_family == "amazon.nova":
        llm_model_value = "amazon.nova-micro-v1:0"
        llm_model_config = AmazonNovaModel
    elif model_family == "anthropic.claude":
        llm_model_value = "us.anthropic.claude-3-5-sonnet-20240620-v1:0"
        llm_model_config = AnthropicClaudeModel

    invoke_model_tool_call(
        span_exporter,
        log_exporter,
        bedrock_runtime_client,
        llm_model_value,
        llm_model_config,
        expect_content=True,
    )


@pytest.mark.parametrize(
    "model_family",
    ["amazon.nova", "amazon.titan", "anthropic.claude", "cohere.command-r", "cohere.command", "meta.llama", "mistral.mistral"],
)
@pytest.mark.vcr()
def test_invoke_model_no_content(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_no_content,
    model_family,
):
    # pylint:disable=too-many-locals
    llm_model_value = get_model_name_from_family(model_family)
    max_tokens, temperature, top_p, stop_sequences = 10, 0.8, 0.99 if model_family == "cohere.command-r" else 1, ["|"]
    body = get_invoke_model_body(
        llm_model_value, max_tokens, temperature, top_p, stop_sequences
    )
    response = bedrock_runtime_client.invoke_model(
        body=body,
        modelId=llm_model_value,
    )

    (span,) = span_exporter.get_finished_spans()
    assert_completion_attributes_from_streaming_body(
        span,
        llm_model_value,
        response,
        "text_completion" if model_family == "amazon.titan" else "chat",
        top_p,
        temperature,
        max_tokens,
        None if model_family == "meta.llama" else stop_sequences,
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 2
    assert_message_in_logs(logs[0], "gen_ai.user.message", None, span)
    if model_family == "anthropic.claude":
        choice_message = {"role": "assistant"}
        finish_reason = "max_tokens"
    elif model_family == "amazon.nova":
        choice_message = {"role": "assistant"}
        finish_reason = "max_tokens"
    elif model_family == "amazon.titan":
        choice_message = {}
        finish_reason = "LENGTH"
    choice_body = {
        "index": 0,
        "finish_reason": finish_reason,
        "message": choice_message,
    }
    assert_message_in_logs(logs[1], "gen_ai.choice", choice_body, span)


@pytest.mark.parametrize(
    "model_family",
    ["amazon.nova", "anthropic.claude"],
)
@pytest.mark.vcr()
def test_invoke_model_no_content_different_events(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_no_content,
    model_family,
):
    llm_model_value = get_model_name_from_family(model_family)
    max_tokens = 10
    if llm_model_value == "amazon.nova-micro-v1:0":
        messages = amazon_nova_messages()
        system = amazon_nova_system()
        finish_reason = "max_tokens"
    elif llm_model_value == "anthropic.claude-v2":
        messages = anthropic_claude_messages()
        system = anthropic_claude_system()
        finish_reason = "end_turn"

    body = get_invoke_model_body(
        llm_model_value,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    response = bedrock_runtime_client.invoke_model(
        body=body,
        modelId=llm_model_value,
    )

    (span,) = span_exporter.get_finished_spans()
    assert_completion_attributes_from_streaming_body(
        span,
        llm_model_value,
        response,
        "chat",
        request_max_tokens=max_tokens,
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 5
    assert_message_in_logs(logs[0], "gen_ai.system.message", None, span)
    assert_message_in_logs(logs[1], "gen_ai.user.message", None, span)
    assert_message_in_logs(logs[2], "gen_ai.assistant.message", None, span)
    assert_message_in_logs(logs[3], "gen_ai.user.message", None, span)
    choice_body = {
        "index": 0,
        "finish_reason": finish_reason,
        "message": {"role": "assistant"},
    }
    assert_message_in_logs(logs[4], "gen_ai.choice", choice_body, span)


@pytest.mark.parametrize(
    "model_family",
    ["amazon.nova", "anthropic.claude"],
)
@pytest.mark.vcr()
def test_invoke_model_no_content_tool_call(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_no_content,
    model_family,
):
    if model_family == "amazon.nova":
        llm_model_value = "amazon.nova-micro-v1:0"
        llm_model_config = AmazonNovaModel
    elif model_family == "anthropic.claude":
        llm_model_value = "us.anthropic.claude-3-5-sonnet-20240620-v1:0"
        llm_model_config = AnthropicClaudeModel

    invoke_model_tool_call(
        span_exporter,
        log_exporter,
        bedrock_runtime_client,
        llm_model_value,
        llm_model_config,
        expect_content=False,
    )


@pytest.mark.vcr()
def test_invoke_model_with_invalid_model(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_with_content,
):
    llm_model_value = "does-not-exist"
    with pytest.raises(bedrock_runtime_client.exceptions.ClientError):
        bedrock_runtime_client.invoke_model(
            body=b"",
            modelId=llm_model_value,
        )

    (span,) = span_exporter.get_finished_spans()
    assert_completion_attributes_from_streaming_body(
        span,
        llm_model_value,
        None,
        "chat",
    )

    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes[ERROR_TYPE] == "ValidationException"

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 0


@pytest.mark.parametrize(
    "model_family",
    ["amazon.nova", "amazon.titan", "anthropic.claude"],
)
@pytest.mark.vcr()
def test_invoke_model_with_response_stream_with_content(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_with_content,
    model_family,
):
    # pylint:disable=too-many-locals,too-many-branches,too-many-statements
    llm_model_value = get_model_name_from_family(model_family)
    max_tokens, temperature, top_p, stop_sequences = 10, 0.8, 1, ["|"]
    body = get_invoke_model_body(
        llm_model_value, max_tokens, temperature, top_p, stop_sequences
    )
    response = bedrock_runtime_client.invoke_model_with_response_stream(
        body=body,
        modelId=llm_model_value,
    )

    # consume the stream in order to have it traced
    finish_reason = None
    input_tokens, output_tokens = None, None
    text = ""
    for event in response["body"]:
        json_bytes = event["chunk"].get("bytes", b"")
        decoded = json_bytes.decode("utf-8")
        chunk = json.loads(decoded)

        # amazon.titan
        if (stop_reason := chunk.get("completionReason")) is not None:
            finish_reason = stop_reason

        if (output_text := chunk.get("outputText")) is not None:
            text += output_text

        # amazon.titan, anthropic.claude
        if invocation_metrics := chunk.get("amazon-bedrock-invocationMetrics"):
            input_tokens = invocation_metrics["inputTokenCount"]
            output_tokens = invocation_metrics["outputTokenCount"]

        # anthropic.claude
        if (message_type := chunk.get("type")) is not None:
            if message_type == "content_block_start":
                text += chunk["content_block"]["text"]
            elif message_type == "content_block_delta":
                text += chunk["delta"]["text"]
            elif message_type == "message_delta":
                finish_reason = chunk["delta"]["stop_reason"]

        # amazon nova
        if "contentBlockDelta" in chunk:
            text += chunk["contentBlockDelta"]["delta"]["text"]
        if "messageStop" in chunk:
            finish_reason = chunk["messageStop"]["stopReason"]
        if "metadata" in chunk:
            usage = chunk["metadata"]["usage"]
            input_tokens = usage["inputTokens"]
            output_tokens = usage["outputTokens"]

    assert text
    assert finish_reason
    assert input_tokens
    assert output_tokens

    (span,) = span_exporter.get_finished_spans()
    assert_stream_completion_attributes(
        span,
        llm_model_value,
        input_tokens,
        output_tokens,
        (finish_reason,),
        "text_completion" if model_family == "amazon.titan" else "chat",
        top_p,
        temperature,
        max_tokens,
        stop_sequences,
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 2
    if model_family == "anthropic.claude":
        user_content = {
            "content": [{"text": "Say this is a test", "type": "text"}]
        }
    else:
        user_content = {"content": [{"text": "Say this is a test"}]}
    assert_message_in_logs(logs[0], "gen_ai.user.message", user_content, span)

    if model_family == "anthropic.claude":
        choice_message = {
            "content": [
                {"text": "Okay, I will repeat: This is a test", "type": "text"}
            ],
            "role": "assistant",
        }
    elif model_family == "amazon.nova":
        choice_message = {
            "content": [
                {"text": "It sounds like you're initiating a message or"}
            ],
            "role": "assistant",
        }
    elif model_family == "amazon.titan":
        choice_message = {
            "content": [
                {"text": "\nHello! I am a computer program designed to"}
            ]
        }
    choice_body = {
        "index": 0,
        "finish_reason": finish_reason,
        "message": choice_message,
    }
    assert_message_in_logs(logs[1], "gen_ai.choice", choice_body, span)


@pytest.mark.parametrize(
    "model_family",
    ["amazon.nova", "anthropic.claude"],
)
@pytest.mark.vcr()
def test_invoke_model_with_response_stream_with_content_different_events(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_with_content,
    model_family,
):
    # pylint:disable=too-many-locals
    llm_model_value = get_model_name_from_family(model_family)
    if llm_model_value == "amazon.nova-micro-v1:0":
        messages = amazon_nova_messages()
        system = amazon_nova_system()
        finish_reason = "max_tokens"
        choice_content = [{"text": "This is a test again. If you need any"}]
    elif llm_model_value == "anthropic.claude-v2":
        messages = anthropic_claude_messages()
        system = anthropic_claude_system()
        finish_reason = "end_turn"
        choice_content = [{"text": "This is a test", "type": "text"}]

    max_tokens = 10
    body = get_invoke_model_body(
        llm_model_value,
        system=system,
        messages=messages,
        max_tokens=max_tokens,
    )
    response = bedrock_runtime_client.invoke_model_with_response_stream(
        body=body,
        modelId=llm_model_value,
    )

    # consume the stream in order to have it traced
    for _ in response["body"]:
        pass

    (span,) = span_exporter.get_finished_spans()
    assert_stream_completion_attributes(
        span,
        llm_model_value,
        input_tokens=mock.ANY,
        output_tokens=mock.ANY,
        request_max_tokens=max_tokens,
        finish_reason=(finish_reason,),
        operation_name="chat",
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 5
    assert_message_in_logs(
        logs[0],
        "gen_ai.system.message",
        {"content": [{"text": "You are a friendly model"}]},
        span,
    )
    user_message, assistant_message, last_user_message = messages
    user_content = filter_message_keys(user_message, ["content"])
    assert_message_in_logs(logs[1], "gen_ai.user.message", user_content, span)
    assistant_content = filter_message_keys(assistant_message, ["content"])
    assert_message_in_logs(
        logs[2], "gen_ai.assistant.message", assistant_content, span
    )
    last_user_content = filter_message_keys(last_user_message, ["content"])
    assert_message_in_logs(
        logs[3], "gen_ai.user.message", last_user_content, span
    )
    choice_body = {
        "index": 0,
        "finish_reason": finish_reason,
        "message": {"content": choice_content, "role": "assistant"},
    }
    assert_message_in_logs(logs[4], "gen_ai.choice", choice_body, span)


def invoke_model_with_response_stream_tool_call(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    llm_model_value,
    llm_model_config,
    expect_content,
):
    # pylint:disable=too-many-locals,too-many-statements,too-many-branches
    user_prompt = "What is the weather in Seattle and San Francisco today? Please give one tool call for Seattle and one for San Francisco"
    user_msg_content = llm_model_config.user_message(user_prompt)
    messages = [{"role": "user", "content": [user_msg_content]}]

    max_tokens = 1000
    tool_config = llm_model_config.tool_config()

    body = get_invoke_model_body(
        llm_model_value,
        messages=messages,
        tools=tool_config,
        max_tokens=max_tokens,
    )
    response_0 = bedrock_runtime_client.invoke_model_with_response_stream(
        body=body,
        modelId=llm_model_value,
    )

    content = llm_model_config.get_stream_body_content(response_0["body"])
    assert content

    tool_requests_ids = llm_model_config.tool_requests_ids_from_stream(content)
    assert len(tool_requests_ids) == 2
    tool_call_result = llm_model_config.tool_calls_results(tool_requests_ids)

    # remove extra attributes from response
    messages.append({"role": "assistant", "content": content})
    messages.append(tool_call_result)

    body = get_invoke_model_body(
        llm_model_value,
        messages=messages,
        max_tokens=max_tokens,
        tools=tool_config,
    )
    response_1 = bedrock_runtime_client.invoke_model_with_response_stream(
        body=body,
        modelId=llm_model_value,
    )

    response_1_content = llm_model_config.get_stream_body_content(
        response_1["body"]
    )
    assert response_1_content

    (span_0, span_1) = span_exporter.get_finished_spans()
    assert_stream_completion_attributes(
        span_0,
        llm_model_value,
        input_tokens=mock.ANY,
        output_tokens=mock.ANY,
        request_max_tokens=max_tokens,
        finish_reason=("tool_use",),
        operation_name="chat",
    )
    assert_stream_completion_attributes(
        span_1,
        llm_model_value,
        input_tokens=mock.ANY,
        output_tokens=mock.ANY,
        request_max_tokens=max_tokens,
        finish_reason=("end_turn",),
        operation_name="chat",
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 8

    # first span
    if expect_content:
        user_content = filter_message_keys(messages[0], ["content"])
    else:
        user_content = {}
    assert_message_in_logs(
        logs[0], "gen_ai.user.message", user_content, span_0
    )

    function_call_0 = {"name": "get_current_weather"}
    function_call_1 = {"name": "get_current_weather"}
    if expect_content:
        function_call_0["arguments"] = {"location": "Seattle"}
        function_call_1["arguments"] = {"location": "San Francisco"}
    choice_body = {
        "index": 0,
        "finish_reason": "tool_use",
        "message": {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": tool_requests_ids[0],
                    "type": "function",
                    "function": function_call_0,
                },
                {
                    "id": tool_requests_ids[1],
                    "type": "function",
                    "function": function_call_1,
                },
            ],
        },
    }
    assert_message_in_logs(logs[1], "gen_ai.choice", choice_body, span_0)

    # second span
    assert_message_in_logs(
        logs[2], "gen_ai.user.message", user_content, span_1
    )
    assistant_body = {"role": "assistant", "content": content}
    assistant_body["tool_calls"] = choice_body["message"]["tool_calls"]
    assistant_body.pop("role")
    if not expect_content:
        assistant_body.pop("content")
    assert_message_in_logs(
        logs[3],
        "gen_ai.assistant.message",
        assistant_body,
        span_1,
    )

    tool_message_0, tool_message_1 = llm_model_config.tool_messages(
        tool_requests_ids, tool_call_result, expect_content
    )
    assert_message_in_logs(
        logs[4], "gen_ai.tool.message", tool_message_0, span_1
    )

    assert_message_in_logs(
        logs[5], "gen_ai.tool.message", tool_message_1, span_1
    )

    user_message_body = tool_call_result
    user_message_body.pop("role")
    if not expect_content:
        user_message_body.pop("content")
    assert_message_in_logs(
        logs[6], "gen_ai.user.message", user_message_body, span_1
    )
    choice_body = {
        "index": 0,
        "finish_reason": "end_turn",
        "message": {
            "role": "assistant",
            "content": response_1_content,
        },
    }
    if not expect_content:
        choice_body["message"].pop("content")
    assert_message_in_logs(logs[7], "gen_ai.choice", choice_body, span_1)


@pytest.mark.parametrize(
    "model_family",
    ["amazon.nova", "anthropic.claude"],
)
@pytest.mark.vcr()
def test_invoke_model_with_response_stream_with_content_tool_call(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_with_content,
    model_family,
):
    if model_family == "amazon.nova":
        llm_model_value = "amazon.nova-micro-v1:0"
        llm_model_config = AmazonNovaModel
    elif model_family == "anthropic.claude":
        llm_model_value = "us.anthropic.claude-3-5-sonnet-20240620-v1:0"
        llm_model_config = AnthropicClaudeModel

    invoke_model_with_response_stream_tool_call(
        span_exporter,
        log_exporter,
        bedrock_runtime_client,
        llm_model_value,
        llm_model_config,
        expect_content=True,
    )


@pytest.mark.parametrize(
    "model_family",
    ["amazon.nova", "amazon.titan", "anthropic.claude"],
)
@pytest.mark.vcr()
def test_invoke_model_with_response_stream_no_content(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_no_content,
    model_family,
):
    # pylint:disable=too-many-locals,too-many-branches
    llm_model_value = get_model_name_from_family(model_family)
    max_tokens, temperature, top_p, stop_sequences = 10, 0.8, 1, ["|"]
    body = get_invoke_model_body(
        llm_model_value, max_tokens, temperature, top_p, stop_sequences
    )
    response = bedrock_runtime_client.invoke_model_with_response_stream(
        body=body,
        modelId=llm_model_value,
    )

    # consume the stream in order to have it traced
    finish_reason = None
    input_tokens, output_tokens = None, None
    text = ""
    for event in response["body"]:
        json_bytes = event["chunk"].get("bytes", b"")
        decoded = json_bytes.decode("utf-8")
        chunk = json.loads(decoded)

        # amazon.titan
        if (stop_reason := chunk.get("completionReason")) is not None:
            finish_reason = stop_reason

        if (output_text := chunk.get("outputText")) is not None:
            text += output_text

        # amazon.titan, anthropic.claude
        if invocation_metrics := chunk.get("amazon-bedrock-invocationMetrics"):
            input_tokens = invocation_metrics["inputTokenCount"]
            output_tokens = invocation_metrics["outputTokenCount"]

        # anthropic.claude
        if (message_type := chunk.get("type")) is not None:
            if message_type == "content_block_start":
                text += chunk["content_block"]["text"]
            elif message_type == "content_block_delta":
                text += chunk["delta"]["text"]
            elif message_type == "message_delta":
                finish_reason = chunk["delta"]["stop_reason"]

        # amazon nova
        if "contentBlockDelta" in chunk:
            text += chunk["contentBlockDelta"]["delta"]["text"]
        if "messageStop" in chunk:
            finish_reason = chunk["messageStop"]["stopReason"]
        if "metadata" in chunk:
            usage = chunk["metadata"]["usage"]
            input_tokens = usage["inputTokens"]
            output_tokens = usage["outputTokens"]

    assert text
    assert finish_reason
    assert input_tokens
    assert output_tokens

    (span,) = span_exporter.get_finished_spans()
    assert_stream_completion_attributes(
        span,
        llm_model_value,
        input_tokens,
        output_tokens,
        (finish_reason,),
        "text_completion" if model_family == "amazon.titan" else "chat",
        top_p,
        temperature,
        max_tokens,
        stop_sequences,
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 2
    assert_message_in_logs(logs[0], "gen_ai.user.message", None, span)
    message = {} if model_family == "amazon.titan" else {"role": "assistant"}
    choice_body = {
        "index": 0,
        "finish_reason": finish_reason,
        "message": message,
    }
    assert_message_in_logs(logs[1], "gen_ai.choice", choice_body, span)


@pytest.mark.parametrize(
    "model_family",
    ["amazon.nova", "anthropic.claude"],
)
@pytest.mark.vcr()
def test_invoke_model_with_response_stream_no_content_different_events(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_no_content,
    model_family,
):
    llm_model_value = get_model_name_from_family(model_family)
    if llm_model_value == "amazon.nova-micro-v1:0":
        messages = amazon_nova_messages()
        system = amazon_nova_system()
        finish_reason = "max_tokens"
    elif llm_model_value == "anthropic.claude-v2":
        messages = anthropic_claude_messages()
        system = anthropic_claude_system()
        finish_reason = "end_turn"

    max_tokens = 10
    body = get_invoke_model_body(
        llm_model_value,
        system=system,
        messages=messages,
        max_tokens=max_tokens,
    )
    response = bedrock_runtime_client.invoke_model_with_response_stream(
        body=body,
        modelId=llm_model_value,
    )

    # consume the stream in order to have it traced
    for _ in response["body"]:
        pass

    (span,) = span_exporter.get_finished_spans()
    assert_stream_completion_attributes(
        span,
        llm_model_value,
        input_tokens=mock.ANY,
        output_tokens=mock.ANY,
        request_max_tokens=max_tokens,
        finish_reason=(finish_reason,),
        operation_name="chat",
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 5
    assert_message_in_logs(logs[0], "gen_ai.system.message", None, span)
    assert_message_in_logs(logs[1], "gen_ai.user.message", None, span)
    assert_message_in_logs(logs[2], "gen_ai.assistant.message", None, span)
    assert_message_in_logs(logs[3], "gen_ai.user.message", None, span)
    choice_body = {
        "index": 0,
        "finish_reason": finish_reason,
        "message": {"role": "assistant"},
    }
    assert_message_in_logs(logs[4], "gen_ai.choice", choice_body, span)


@pytest.mark.parametrize(
    "model_family",
    ["amazon.nova", "anthropic.claude"],
)
@pytest.mark.vcr()
def test_invoke_model_with_response_stream_no_content_tool_call(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_no_content,
    model_family,
):
    if model_family == "amazon.nova":
        llm_model_value = "amazon.nova-micro-v1:0"
        llm_model_config = AmazonNovaModel
    elif model_family == "anthropic.claude":
        llm_model_value = "us.anthropic.claude-3-5-sonnet-20240620-v1:0"
        llm_model_config = AnthropicClaudeModel

    invoke_model_with_response_stream_tool_call(
        span_exporter,
        log_exporter,
        bedrock_runtime_client,
        llm_model_value,
        llm_model_config,
        expect_content=False,
    )


@pytest.mark.vcr()
def test_invoke_model_with_response_stream_handles_stream_error(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_with_content,
):
    # pylint:disable=too-many-locals
    llm_model_value = "amazon.titan-text-lite-v1"
    max_tokens, temperature, top_p, stop_sequences = 10, 0.8, 1, ["|"]
    body = get_invoke_model_body(
        llm_model_value, max_tokens, temperature, top_p, stop_sequences
    )
    response = bedrock_runtime_client.invoke_model_with_response_stream(
        body=body,
        modelId=llm_model_value,
    )

    # consume the stream in order to have it traced
    finish_reason = None
    input_tokens, output_tokens = None, None
    with mock.patch.object(
        EventStream,
        "_parse_event",
        side_effect=EventStreamError(
            {"modelStreamErrorException": {}}, "InvokeModelWithResponseStream"
        ),
    ):
        with pytest.raises(EventStreamError):
            for _event in response["body"]:
                pass

    (span,) = span_exporter.get_finished_spans()
    assert_stream_completion_attributes(
        span,
        llm_model_value,
        input_tokens,
        output_tokens,
        finish_reason,
        "text_completion",
        top_p,
        temperature,
        max_tokens,
        stop_sequences,
    )

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 1
    user_content = {"content": [{"text": "Say this is a test"}]}
    assert_message_in_logs(logs[0], "gen_ai.user.message", user_content, span)


@pytest.mark.vcr()
def test_invoke_model_with_response_stream_invalid_model(
    span_exporter,
    log_exporter,
    bedrock_runtime_client,
    instrument_with_content,
):
    llm_model_value = "does-not-exist"
    with pytest.raises(bedrock_runtime_client.exceptions.ClientError):
        bedrock_runtime_client.invoke_model_with_response_stream(
            body=b"",
            modelId=llm_model_value,
        )

    (span,) = span_exporter.get_finished_spans()
    assert_completion_attributes_from_streaming_body(
        span,
        llm_model_value,
        None,
        "chat",
    )

    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes[ERROR_TYPE] == "ValidationException"

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 0


def amazon_nova_messages():
    return [
        {"role": "user", "content": [{"text": "Say this is a test"}]},
        {"role": "assistant", "content": [{"text": "This is a test"}]},
        {
            "role": "user",
            "content": [{"text": "Say again this is a test"}],
        },
    ]


def amazon_nova_system():
    return [
        {"text": "You are a friendly model"},
    ]


def anthropic_claude_converse_messages():
    return amazon_nova_messages()


def anthropic_claude_converse_system():
    return amazon_nova_system()


def anthropic_claude_messages():
    return [
        {
            "role": "user",
            "content": [{"text": "Say this is a test", "type": "text"}],
        },
        {
            "role": "assistant",
            "content": [{"text": "This is a test", "type": "text"}],
        },
        {
            "role": "user",
            "content": [{"text": "Say again this is a test", "type": "text"}],
        },
    ]


def anthropic_claude_system():
    return "You are a friendly model"


def get_tool_config():
    return {
        "tools": [
            {
                "toolSpec": {
                    "name": "get_current_weather",
                    "description": "Get the current weather in a given location.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "location": {
                                    "type": "string",
                                    "description": "The name of the city",
                                }
                            },
                            "required": ["location"],
                        }
                    },
                }
            }
        ]
    }


def get_anthropic_tool_config():
    return [
        {
            "name": "get_current_weather",
            "description": "Get the current weather in a given location.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The name of the city",
                    }
                },
                "required": ["location"],
            },
        }
    ]
