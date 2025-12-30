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

# pylint: disable=too-many-locals,too-many-lines

import logging
import os

import pytest
from openai import (
    NOT_GIVEN,
    APIConnectionError,
    NotFoundError,
    OpenAI,
)

try:
    from openai import not_given  # pylint: disable=no-name-in-module
except ImportError:
    not_given = NOT_GIVEN

from opentelemetry.semconv._incubating.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    openai_attributes as OpenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics
from opentelemetry.util.genai.utils import is_experimental_mode

from .test_utils import (
    DEFAULT_MODEL,
    USER_ONLY_EXPECTED_INPUT_MESSAGES,
    USER_ONLY_PROMPT,
    WEATHER_TOOL_EXPECTED_INPUT_MESSAGES,
    WEATHER_TOOL_PROMPT,
    assert_all_attributes,
    assert_message_in_logs,
    assert_messages_attribute,
    format_simple_expected_output_message,
    get_current_weather_tool_definition,
)


def test_chat_completion_with_content(
    span_exporter, log_exporter, openai_client, instrument_with_content, vcr
):
    latest_experimental_enabled = is_experimental_mode()
    print(
        f"latest_experimental_enabled={latest_experimental_enabled}, ENV_VAR={os.getenv('OTEL_SEMCONV_STABILITY_OPT_IN')}"
    )

    with vcr.use_cassette("test_chat_completion_with_content.yaml"):
        response = openai_client.chat.completions.create(
            messages=USER_ONLY_PROMPT,
            model=DEFAULT_MODEL,
            stream=False,
        )

    spans = span_exporter.get_finished_spans()
    assert_all_attributes(
        spans[0],
        DEFAULT_MODEL,
        latest_experimental_enabled,
        response.id,
        response.model,
        response.usage.prompt_tokens,
        response.usage.completion_tokens,
    )

    if latest_experimental_enabled:
        assert_messages_attribute(
            spans[0].attributes["gen_ai.input.messages"],
            USER_ONLY_EXPECTED_INPUT_MESSAGES,
        )
        assert_messages_attribute(
            spans[0].attributes["gen_ai.output.messages"],
            format_simple_expected_output_message(
                response.choices[0].message.content
            ),
        )
    else:
        logs = log_exporter.get_finished_logs()
        assert len(logs) == 2

        user_message = {"content": USER_ONLY_PROMPT[0]["content"]}
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
        assert_message_in_logs(
            logs[1], "gen_ai.choice", choice_event, spans[0]
        )


def test_chat_completion_handles_not_given(
    span_exporter,
    log_exporter,
    openai_client,
    instrument_no_content,
    vcr,
    caplog,
):
    caplog.set_level(logging.WARNING)
    latest_experimental_enabled = is_experimental_mode()

    with vcr.use_cassette("test_chat_completion_handles_not_given.yaml"):
        response = openai_client.chat.completions.create(
            messages=USER_ONLY_PROMPT,
            model=DEFAULT_MODEL,
            stream=False,
            top_p=NOT_GIVEN,
            max_tokens=not_given,
        )

    (span,) = span_exporter.get_finished_spans()
    assert_all_attributes(
        span,
        DEFAULT_MODEL,
        latest_experimental_enabled,
        response.id,
        response.model,
        response.usage.prompt_tokens,
        response.usage.completion_tokens,
        response_service_tier="default",
    )

    assert GenAIAttributes.GEN_AI_REQUEST_TOP_P not in span.attributes
    assert GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS not in span.attributes

    assert_no_invalid_type_warning(caplog)


def test_chat_completion_no_content(
    span_exporter, log_exporter, openai_client, instrument_no_content, vcr
):
    latest_experimental_enabled = is_experimental_mode()
    with vcr.use_cassette("test_chat_completion_no_content.yaml"):
        response = openai_client.chat.completions.create(
            messages=USER_ONLY_PROMPT, model=DEFAULT_MODEL, stream=False
        )

    spans = span_exporter.get_finished_spans()
    assert_all_attributes(
        spans[0],
        DEFAULT_MODEL,
        latest_experimental_enabled,
        response.id,
        response.model,
        response.usage.prompt_tokens,
        response.usage.completion_tokens,
    )

    logs = log_exporter.get_finished_logs()
    if latest_experimental_enabled:
        assert len(logs) == 0
        assert "gen_ai.input.messages" not in spans[0].attributes
        assert "gen_ai.output.messages" not in spans[0].attributes
    else:
        assert len(logs) == 2

        assert_message_in_logs(logs[0], "gen_ai.user.message", None, spans[0])

        choice_event = {
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant"},
        }
        assert_message_in_logs(
            logs[1], "gen_ai.choice", choice_event, spans[0]
        )


def test_chat_completion_bad_endpoint(
    span_exporter, metric_reader, instrument_no_content, vcr
):
    latest_experimental_enabled = is_experimental_mode()

    client = OpenAI(base_url="http://localhost:4242")

    with vcr.use_cassette("test_chat_completion_bad_endpoint.yaml"):
        with pytest.raises(APIConnectionError):
            client.chat.completions.create(
                messages=USER_ONLY_PROMPT,
                model=DEFAULT_MODEL,
                timeout=0.1,
            )

    spans = span_exporter.get_finished_spans()
    assert_all_attributes(
        spans[0],
        DEFAULT_MODEL,
        latest_experimental_enabled,
        server_address="localhost",
    )
    assert 4242 == spans[0].attributes[ServerAttributes.SERVER_PORT]
    assert (
        "APIConnectionError" == spans[0].attributes[ErrorAttributes.ERROR_TYPE]
    )

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


def test_chat_completion_404(
    span_exporter, openai_client, metric_reader, instrument_no_content, vcr
):
    latest_experimental_enabled = is_experimental_mode()
    llm_model_value = "this-model-does-not-exist"

    with vcr.use_cassette("test_chat_completion_404.yaml"):
        with pytest.raises(NotFoundError):
            openai_client.chat.completions.create(
                messages=USER_ONLY_PROMPT,
                model=llm_model_value,
            )

    spans = span_exporter.get_finished_spans()

    assert_all_attributes(
        spans[0], llm_model_value, latest_experimental_enabled
    )
    assert "NotFoundError" == spans[0].attributes[ErrorAttributes.ERROR_TYPE]

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
        == "NotFoundError"
    )


def test_chat_completion_extra_params(
    span_exporter, openai_client, instrument_no_content, vcr
):
    latest_experimental_enabled = is_experimental_mode()

    with vcr.use_cassette("test_chat_completion_extra_params.yaml"):
        response = openai_client.chat.completions.create(
            n=2,
            messages=USER_ONLY_PROMPT,
            model=DEFAULT_MODEL,
            seed=42,
            temperature=0.5,
            max_tokens=50,
            stream=False,
            extra_body={"service_tier": "default"},
            response_format={"type": "text"},
            stop=["full", "stop"],
        )

    spans = span_exporter.get_finished_spans()
    assert_all_attributes(
        spans[0],
        DEFAULT_MODEL,
        latest_experimental_enabled,
        response.id,
        response.model,
        response.usage.prompt_tokens,
        response.usage.completion_tokens,
        request_service_tier="default",
        response_service_tier=getattr(response, "service_tier", None),
    )
    assert spans[0].attributes[GenAIAttributes.GEN_AI_REQUEST_SEED] == 42
    assert (
        spans[0].attributes[GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE] == 0.5
    )
    assert spans[0].attributes[GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS] == 50

    request_service_tier_attr_key = (
        OpenAIAttributes.OPENAI_REQUEST_SERVICE_TIER
        if latest_experimental_enabled
        else GenAIAttributes.GEN_AI_OPENAI_REQUEST_SERVICE_TIER
    )
    assert spans[0].attributes[request_service_tier_attr_key] == "default"

    output_type_attr_key = (
        GenAIAttributes.GEN_AI_OUTPUT_TYPE
        if latest_experimental_enabled
        else GenAIAttributes.GEN_AI_OPENAI_REQUEST_RESPONSE_FORMAT
    )
    assert spans[0].attributes[output_type_attr_key] == "text"
    assert spans[0].attributes[
        GenAIAttributes.GEN_AI_REQUEST_STOP_SEQUENCES
    ] == ("full", "stop")
    assert (
        spans[0].attributes[GenAIAttributes.GEN_AI_REQUEST_CHOICE_COUNT] == 2
    )


def test_chat_completion_n_1_is_not_reported(
    span_exporter, openai_client, instrument_no_content, vcr
):
    latest_experimental_enabled = is_experimental_mode()
    with vcr.use_cassette("test_chat_completion_n_1_is_not_reported.yaml"):
        response = openai_client.chat.completions.create(
            n=1,
            messages=USER_ONLY_PROMPT,
            model=DEFAULT_MODEL,
        )

    spans = span_exporter.get_finished_spans()
    assert_all_attributes(
        spans[0],
        DEFAULT_MODEL,
        latest_experimental_enabled,
        response.id,
        response.model,
        response.usage.prompt_tokens,
        response.usage.completion_tokens,
        response_service_tier=getattr(response, "service_tier", None),
    )
    assert (
        GenAIAttributes.GEN_AI_REQUEST_CHOICE_COUNT not in spans[0].attributes
    )


def test_chat_completion_handle_stop_sequences_as_string(
    span_exporter, openai_client, instrument_no_content, vcr
):
    latest_experimental_enabled = is_experimental_mode()
    with vcr.use_cassette(
        "test_chat_completion_handle_stop_sequences_as_string.yaml"
    ):
        response = openai_client.chat.completions.create(
            messages=USER_ONLY_PROMPT,
            model=DEFAULT_MODEL,
            stop="stop",
        )

    spans = span_exporter.get_finished_spans()
    assert_all_attributes(
        spans[0],
        DEFAULT_MODEL,
        latest_experimental_enabled,
        response.id,
        response.model,
        response.usage.prompt_tokens,
        response.usage.completion_tokens,
        response_service_tier=getattr(response, "service_tier", None),
    )
    assert spans[0].attributes[
        GenAIAttributes.GEN_AI_REQUEST_STOP_SEQUENCES
    ] == ("stop",)


def test_chat_completion_multiple_choices(
    span_exporter, log_exporter, openai_client, instrument_with_content, vcr
):
    latest_experimental_enabled = is_experimental_mode()
    with vcr.use_cassette("test_chat_completion_multiple_choices.yaml"):
        response = openai_client.chat.completions.create(
            messages=USER_ONLY_PROMPT, model=DEFAULT_MODEL, n=2, stream=False
        )

    spans = span_exporter.get_finished_spans()
    assert_all_attributes(
        spans[0],
        DEFAULT_MODEL,
        latest_experimental_enabled,
        response.id,
        response.model,
        response.usage.prompt_tokens,
        response.usage.completion_tokens,
    )

    assert (
        spans[0].attributes[GenAIAttributes.GEN_AI_REQUEST_CHOICE_COUNT] == 2
    )

    logs = log_exporter.get_finished_logs()
    if latest_experimental_enabled:
        expected_output_messages = [
            {
                "role": "assistant",
                "parts": [
                    {
                        "type": "text",
                        "content": response.choices[0].message.content,
                    }
                ],
                "finish_reason": "stop",
            },
            {
                "role": "assistant",
                "parts": [
                    {
                        "type": "text",
                        "content": response.choices[1].message.content,
                    }
                ],
                "finish_reason": "stop",
            },
        ]

        assert_messages_attribute(
            spans[0].attributes["gen_ai.input.messages"],
            USER_ONLY_EXPECTED_INPUT_MESSAGES,
        )
        assert_messages_attribute(
            spans[0].attributes["gen_ai.output.messages"],
            expected_output_messages,
        )
    else:
        assert len(logs) == 3  # 1 user message + 2 choice messages

        user_message = {"content": USER_ONLY_PROMPT[0]["content"]}
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
        assert_message_in_logs(
            logs[1], "gen_ai.choice", choice_event_0, spans[0]
        )

        choice_event_1 = {
            "index": 1,
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": response.choices[1].message.content,
            },
        }
        assert_message_in_logs(
            logs[2], "gen_ai.choice", choice_event_1, spans[0]
        )


def test_chat_completion_with_raw_response(
    span_exporter, log_exporter, openai_client, instrument_with_content, vcr
):
    latest_experimental_enabled = is_experimental_mode()
    with vcr.use_cassette("test_chat_completion_with_raw_response.yaml"):
        response = openai_client.chat.completions.with_raw_response.create(
            messages=USER_ONLY_PROMPT,
            model=DEFAULT_MODEL,
        )
    response = response.parse()
    spans = span_exporter.get_finished_spans()
    assert_all_attributes(
        spans[0],
        DEFAULT_MODEL,
        latest_experimental_enabled,
        response.id,
        response.model,
        response.usage.prompt_tokens,
        response.usage.completion_tokens,
    )

    if latest_experimental_enabled:
        assert_messages_attribute(
            spans[0].attributes["gen_ai.input.messages"],
            USER_ONLY_EXPECTED_INPUT_MESSAGES,
        )
        assert_messages_attribute(
            spans[0].attributes["gen_ai.output.messages"],
            format_simple_expected_output_message(
                response.choices[0].message.content
            ),
        )
    else:
        logs = log_exporter.get_finished_logs()
        assert len(logs) == 2

        user_message = {"content": USER_ONLY_PROMPT[0]["content"]}
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
        assert_message_in_logs(
            logs[1], "gen_ai.choice", choice_event, spans[0]
        )


def test_chat_completion_with_raw_response_streaming(
    span_exporter, log_exporter, openai_client, instrument_with_content, vcr
):
    latest_experimental_enabled = is_experimental_mode()
    with vcr.use_cassette(
        "test_chat_completion_with_raw_response_streaming.yaml"
    ):
        raw_response = openai_client.chat.completions.with_raw_response.create(
            messages=USER_ONLY_PROMPT,
            model=DEFAULT_MODEL,
            stream=True,
            stream_options={"include_usage": True},
        )
    response = raw_response.parse()

    message_content = ""
    for chunk in response:
        if chunk.choices:
            message_content += chunk.choices[0].delta.content or ""
        # get the last chunk
        if getattr(chunk, "usage", None):
            response_stream_usage = chunk.usage
            response_stream_model = chunk.model
            response_stream_id = chunk.id

    spans = span_exporter.get_finished_spans()
    assert_all_attributes(
        spans[0],
        DEFAULT_MODEL,
        latest_experimental_enabled,
        response_stream_id,
        response_stream_model,
        response_stream_usage.prompt_tokens,
        response_stream_usage.completion_tokens,
        response_service_tier="default",
    )

    logs = log_exporter.get_finished_logs()
    if latest_experimental_enabled:
        assert len(logs) == 0

        assert_messages_attribute(
            spans[0].attributes["gen_ai.input.messages"],
            USER_ONLY_EXPECTED_INPUT_MESSAGES,
        )
        assert_messages_attribute(
            spans[0].attributes["gen_ai.output.messages"],
            format_simple_expected_output_message(message_content),
        )
    else:
        assert len(logs) == 2

        user_message = {"content": USER_ONLY_PROMPT[0]["content"]}
        assert_message_in_logs(
            logs[0], "gen_ai.user.message", user_message, spans[0]
        )

        choice_event = {
            "index": 0,
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": message_content,
            },
        }
        assert_message_in_logs(
            logs[1], "gen_ai.choice", choice_event, spans[0]
        )


def test_chat_completion_tool_calls_with_content(
    span_exporter, log_exporter, openai_client, instrument_with_content, vcr
):
    with vcr.use_cassette("test_chat_completion_tool_calls_with_content.yaml"):
        chat_completion_tool_call(
            span_exporter,
            log_exporter,
            openai_client,
            True,
            is_experimental_mode(),
        )


def test_chat_completion_tool_calls_no_content(
    span_exporter, log_exporter, openai_client, instrument_no_content, vcr
):
    with vcr.use_cassette("test_chat_completion_tool_calls_no_content.yaml"):
        chat_completion_tool_call(
            span_exporter,
            log_exporter,
            openai_client,
            False,
            is_experimental_mode(),
        )


def chat_completion_tool_call(
    span_exporter,
    log_exporter,
    openai_client,
    expect_content,
    latest_experimental_enabled,
):
    messages_value = WEATHER_TOOL_PROMPT.copy()

    response_0 = openai_client.chat.completions.create(
        messages=messages_value,
        model=DEFAULT_MODEL,
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
        messages=messages_value, model=DEFAULT_MODEL
    )

    # sanity check
    assert "stop" in response_1.choices[0].finish_reason

    # validate both calls
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 2
    assert_all_attributes(
        spans[0],
        DEFAULT_MODEL,
        latest_experimental_enabled,
        response_0.id,
        response_0.model,
        response_0.usage.prompt_tokens,
        response_0.usage.completion_tokens,
    )
    assert_all_attributes(
        spans[1],
        DEFAULT_MODEL,
        latest_experimental_enabled,
        response_1.id,
        response_1.model,
        response_1.usage.prompt_tokens,
        response_1.usage.completion_tokens,
    )

    logs = log_exporter.get_finished_logs()
    if latest_experimental_enabled:
        if not expect_content:
            pass
        else:
            # first call
            assert_messages_attribute(
                spans[0].attributes["gen_ai.input.messages"],
                WEATHER_TOOL_EXPECTED_INPUT_MESSAGES,
            )

            first_output = [
                {
                    "role": "assistant",
                    "parts": [
                        {
                            "type": "tool_call",
                            "id": response_0.choices[0]
                            .message.tool_calls[0]
                            .id,
                            "name": "get_current_weather",
                            "arguments": {"location": "Seattle, WA"},
                        },
                        {
                            "type": "tool_call",
                            "id": response_0.choices[0]
                            .message.tool_calls[1]
                            .id,
                            "name": "get_current_weather",
                            "arguments": {"location": "San Francisco, CA"},
                        },
                    ],
                    "finish_reason": "tool_calls",
                }
            ]

            assert_messages_attribute(
                spans[0].attributes["gen_ai.output.messages"], first_output
            )

            # second call
            del first_output[0]["finish_reason"]
            second_input = []
            second_input += WEATHER_TOOL_EXPECTED_INPUT_MESSAGES.copy()
            second_input += first_output
            second_input += [
                {
                    "role": "tool",
                    "parts": [
                        {
                            "type": "tool_call_response",
                            "id": response_0.choices[0]
                            .message.tool_calls[0]
                            .id,
                            "response": tool_call_result_0["content"],
                        }
                    ],
                },
                {
                    "role": "tool",
                    "parts": [
                        {
                            "type": "tool_call_response",
                            "id": response_0.choices[0]
                            .message.tool_calls[1]
                            .id,
                            "response": tool_call_result_1["content"],
                        }
                    ],
                },
            ]

            assert_messages_attribute(
                spans[1].attributes["gen_ai.input.messages"], second_input
            )

            assert_messages_attribute(
                spans[1].attributes["gen_ai.output.messages"],
                format_simple_expected_output_message(
                    response_1.choices[0].message.content
                ),
            )
    else:
        assert len(logs) == 9  # 3 logs for first completion, 6 for second

        # call one
        system_message = (
            {"content": messages_value[0]["content"]}
            if expect_content
            else None
        )
        assert_message_in_logs(
            logs[0], "gen_ai.system.message", system_message, spans[0]
        )

        user_message = (
            {"content": messages_value[1]["content"]}
            if expect_content
            else None
        )
        assert_message_in_logs(
            logs[1], "gen_ai.user.message", user_message, spans[0]
        )

        function_call_0 = {"name": "get_current_weather"}
        function_call_1 = {"name": "get_current_weather"}
        if expect_content:
            function_call_0["arguments"] = (
                response_0.choices[0]
                .message.tool_calls[0]
                .function.arguments.replace("\n", "")
            )
            function_call_1["arguments"] = (
                response_0.choices[0]
                .message.tool_calls[1]
                .function.arguments.replace("\n", "")
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
                        "function": function_call_0,
                    },
                    {
                        "id": response_0.choices[0].message.tool_calls[1].id,
                        "type": "function",
                        "function": function_call_1,
                    },
                ],
            },
        }
        assert_message_in_logs(
            logs[2], "gen_ai.choice", choice_event, spans[0]
        )

        # call two
        system_message = (
            {"content": messages_value[0]["content"]}
            if expect_content
            else None
        )
        assert_message_in_logs(
            logs[3], "gen_ai.system.message", system_message, spans[1]
        )

        user_message = (
            {"content": messages_value[1]["content"]}
            if expect_content
            else None
        )
        assert_message_in_logs(
            logs[4], "gen_ai.user.message", user_message, spans[1]
        )

        assistant_tool_call = {"tool_calls": messages_value[2]["tool_calls"]}
        if not expect_content:
            assistant_tool_call["tool_calls"][0]["function"]["arguments"] = (
                None
            )
            assistant_tool_call["tool_calls"][1]["function"]["arguments"] = (
                None
            )

        assert_message_in_logs(
            logs[5], "gen_ai.assistant.message", assistant_tool_call, spans[1]
        )

        tool_message_0 = {
            "id": tool_call_result_0["tool_call_id"],
            "content": tool_call_result_0["content"]
            if expect_content
            else None,
        }

        assert_message_in_logs(
            logs[6], "gen_ai.tool.message", tool_message_0, spans[1]
        )

        tool_message_1 = {
            "id": tool_call_result_1["tool_call_id"],
            "content": tool_call_result_1["content"]
            if expect_content
            else None,
        }

        assert_message_in_logs(
            logs[7], "gen_ai.tool.message", tool_message_1, spans[1]
        )

        message = {
            "role": "assistant",
            "content": response_1.choices[0].message.content
            if expect_content
            else None,
        }
        choice = {
            "index": 0,
            "finish_reason": "stop",
            "message": message,
        }
        assert_message_in_logs(logs[8], "gen_ai.choice", choice, spans[1])


def test_chat_completion_streaming(
    span_exporter, log_exporter, openai_client, instrument_with_content, vcr
):
    latest_experimental_enabled = is_experimental_mode()
    kwargs = {
        "model": DEFAULT_MODEL,
        "messages": USER_ONLY_PROMPT,
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    response_stream_usage = None
    response_stream_model = None
    response_stream_id = None
    response_stream_result = ""

    with vcr.use_cassette("test_chat_completion_streaming.yaml"):
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
        DEFAULT_MODEL,
        latest_experimental_enabled,
        response_stream_id,
        response_stream_model,
        response_stream_usage.prompt_tokens,
        response_stream_usage.completion_tokens,
    )

    logs = log_exporter.get_finished_logs()
    if latest_experimental_enabled:
        assert_messages_attribute(
            spans[0].attributes["gen_ai.input.messages"],
            USER_ONLY_EXPECTED_INPUT_MESSAGES,
        )
        assert_messages_attribute(
            spans[0].attributes["gen_ai.output.messages"],
            format_simple_expected_output_message(response_stream_result),
        )
    else:
        assert len(logs) == 2

        user_message = {"content": "Say this is a test"}
        assert_message_in_logs(
            logs[0], "gen_ai.user.message", user_message, spans[0]
        )

        choice_event = {
            "index": 0,
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": response_stream_result,
            },
        }
        assert_message_in_logs(
            logs[1], "gen_ai.choice", choice_event, spans[0]
        )


def test_chat_completion_streaming_not_complete(
    span_exporter, log_exporter, openai_client, instrument_with_content, vcr
):
    latest_experimental_enabled = is_experimental_mode()
    kwargs = {
        "model": DEFAULT_MODEL,
        "messages": USER_ONLY_PROMPT,
        "stream": True,
    }

    response_stream_model = None
    response_stream_id = None
    response_stream_result = ""

    with vcr.use_cassette("test_chat_completion_streaming_not_complete.yaml"):
        response = openai_client.chat.completions.create(**kwargs)
        for idx, chunk in enumerate(response):
            if chunk.choices:
                response_stream_result += chunk.choices[0].delta.content or ""
            if idx == 1:
                # fake a stop
                break

            if chunk.model:
                response_stream_model = chunk.model
            if chunk.id:
                response_stream_id = chunk.id

    response.close()
    spans = span_exporter.get_finished_spans()
    assert_all_attributes(
        spans[0],
        DEFAULT_MODEL,
        latest_experimental_enabled,
        response_stream_id,
        response_stream_model,
    )

    logs = log_exporter.get_finished_logs()
    if latest_experimental_enabled:
        assert_messages_attribute(
            spans[0].attributes["gen_ai.input.messages"],
            USER_ONLY_EXPECTED_INPUT_MESSAGES,
        )
        assert_messages_attribute(
            spans[0].attributes["gen_ai.output.messages"],
            format_simple_expected_output_message(
                response_stream_result, finish_reason="error"
            ),
        )
    else:
        assert len(logs) == 2

        user_message = {"content": "Say this is a test"}
        assert_message_in_logs(
            logs[0], "gen_ai.user.message", user_message, spans[0]
        )

        choice_event = {
            "index": 0,
            "finish_reason": "error",
            "message": {
                "role": "assistant",
                "content": response_stream_result,
            },
        }
        assert_message_in_logs(
            logs[1], "gen_ai.choice", choice_event, spans[0]
        )


def test_chat_completion_multiple_choices_streaming(
    span_exporter, log_exporter, openai_client, instrument_with_content, vcr
):
    latest_experimental_enabled = is_experimental_mode()
    with vcr.use_cassette(
        "test_chat_completion_multiple_choices_streaming.yaml"
    ):
        response_0 = openai_client.chat.completions.create(
            messages=WEATHER_TOOL_PROMPT,
            model=DEFAULT_MODEL,
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
        DEFAULT_MODEL,
        latest_experimental_enabled,
        response_stream_id,
        response_stream_model,
        response_stream_usage.prompt_tokens,
        response_stream_usage.completion_tokens,
    )

    logs = log_exporter.get_finished_logs()
    if latest_experimental_enabled:
        expected_output_messages = [
            {
                "role": "assistant",
                "parts": [
                    {
                        "type": "text",
                        "content": "".join(response_stream_result[0]),
                    }
                ],
                "finish_reason": "stop",
            },
            {
                "role": "assistant",
                "parts": [
                    {
                        "type": "text",
                        "content": "".join(response_stream_result[1]),
                    }
                ],
                "finish_reason": "stop",
            },
        ]
        assert_messages_attribute(
            spans[0].attributes["gen_ai.input.messages"],
            WEATHER_TOOL_EXPECTED_INPUT_MESSAGES,
        )
        assert_messages_attribute(
            spans[0].attributes["gen_ai.output.messages"],
            expected_output_messages,
        )
    else:
        assert len(logs) == 4

        system_message = {"content": WEATHER_TOOL_PROMPT[0]["content"]}
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
        assert_message_in_logs(
            logs[2], "gen_ai.choice", choice_event_0, spans[0]
        )

        choice_event_1 = {
            "index": 1,
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": "".join(response_stream_result[1]),
            },
        }
        assert_message_in_logs(
            logs[3], "gen_ai.choice", choice_event_1, spans[0]
        )


def test_chat_completion_multiple_tools_streaming_with_content(
    span_exporter, log_exporter, openai_client, instrument_with_content, vcr
):
    with vcr.use_cassette(
        "test_chat_completion_multiple_tools_streaming_with_content.yaml"
    ):
        chat_completion_multiple_tools_streaming(
            span_exporter,
            log_exporter,
            openai_client,
            True,
            is_experimental_mode(),
        )


def test_chat_completion_multiple_tools_streaming_no_content(
    span_exporter, log_exporter, openai_client, instrument_no_content, vcr
):
    with vcr.use_cassette(
        "test_chat_completion_multiple_tools_streaming_no_content.yaml"
    ):
        chat_completion_multiple_tools_streaming(
            span_exporter,
            log_exporter,
            openai_client,
            False,
            is_experimental_mode(),
        )


def test_chat_completion_with_content_span_unsampled(
    span_exporter,
    log_exporter,
    openai_client,
    instrument_with_content_unsampled,
    vcr,
):
    latest_experimental_enabled = is_experimental_mode()
    with vcr.use_cassette(
        "test_chat_completion_with_content_span_unsampled.yaml"
    ):
        response = openai_client.chat.completions.create(
            messages=USER_ONLY_PROMPT, model=DEFAULT_MODEL, stream=False
        )

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 0

    logs = log_exporter.get_finished_logs()
    if not latest_experimental_enabled:
        assert len(logs) == 2

        user_message = {"content": USER_ONLY_PROMPT[0]["content"]}
        assert_message_in_logs(
            logs[0], "gen_ai.user.message", user_message, None
        )

        choice_event = {
            "index": 0,
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": response.choices[0].message.content,
            },
        }
        assert_message_in_logs(logs[1], "gen_ai.choice", choice_event, None)

        assert logs[0].log_record.trace_id is not None
        assert logs[0].log_record.span_id is not None
        assert logs[0].log_record.trace_flags == 0

        assert logs[0].log_record.trace_id == logs[1].log_record.trace_id
        assert logs[0].log_record.span_id == logs[1].log_record.span_id
        assert logs[0].log_record.trace_flags == logs[1].log_record.trace_flags


def test_chat_completion_with_context_manager_streaming(
    span_exporter, log_exporter, openai_client, instrument_with_content, vcr
):
    latest_experimental_enabled = is_experimental_mode()
    with vcr.use_cassette(
        "test_chat_completion_with_context_manager_streaming.yaml"
    ):
        with openai_client.chat.completions.create(
            messages=USER_ONLY_PROMPT,
            model=DEFAULT_MODEL,
            stream=True,
            stream_options={"include_usage": True},
        ) as response:
            message_content = ""
            for chunk in response:
                if chunk.choices:
                    message_content += chunk.choices[0].delta.content or ""
                # get the last chunk
                if getattr(chunk, "usage", None):
                    response_stream_usage = chunk.usage
                    response_stream_model = chunk.model
                    response_stream_id = chunk.id

    spans = span_exporter.get_finished_spans()
    assert_all_attributes(
        spans[0],
        DEFAULT_MODEL,
        latest_experimental_enabled,
        response_stream_id,
        response_stream_model,
        response_stream_usage.prompt_tokens,
        response_stream_usage.completion_tokens,
        response_service_tier="default",
    )

    logs = log_exporter.get_finished_logs()
    if latest_experimental_enabled:
        assert len(logs) == 0

        assert_messages_attribute(
            spans[0].attributes["gen_ai.input.messages"],
            USER_ONLY_EXPECTED_INPUT_MESSAGES,
        )
        assert_messages_attribute(
            spans[0].attributes["gen_ai.output.messages"],
            format_simple_expected_output_message(message_content),
        )
    else:
        assert len(logs) == 2

        user_message = {"content": USER_ONLY_PROMPT[0]["content"]}
        assert_message_in_logs(
            logs[0], "gen_ai.user.message", user_message, spans[0]
        )

        choice_event = {
            "index": 0,
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": message_content,
            },
        }
        assert_message_in_logs(
            logs[1], "gen_ai.choice", choice_event, spans[0]
        )


def chat_completion_multiple_tools_streaming(
    span_exporter,
    log_exporter,
    openai_client,
    expect_content,
    latest_experimental_enabled,
):
    response = openai_client.chat.completions.create(
        messages=WEATHER_TOOL_PROMPT,
        model=DEFAULT_MODEL,
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
        DEFAULT_MODEL,
        latest_experimental_enabled,
        response_stream_id,
        response_stream_model,
        response_stream_usage.prompt_tokens,
        response_stream_usage.completion_tokens,
    )

    logs = log_exporter.get_finished_logs()
    if latest_experimental_enabled:
        if expect_content:
            # first call
            assert_messages_attribute(
                spans[0].attributes["gen_ai.input.messages"],
                WEATHER_TOOL_EXPECTED_INPUT_MESSAGES,
            )

            first_output = [
                {
                    "role": "assistant",
                    "parts": [
                        {
                            "type": "tool_call",
                            "id": tool_call_ids[0],
                            "name": "get_current_weather",
                            "arguments": {"location": "Seattle, WA"},
                        },
                        {
                            "type": "tool_call",
                            "id": tool_call_ids[1],
                            "name": "get_current_weather",
                            "arguments": {"location": "San Francisco, CA"},
                        },
                    ],
                    "finish_reason": "tool_calls",
                }
            ]
            assert_messages_attribute(
                spans[0].attributes["gen_ai.output.messages"], first_output
            )
    else:
        assert len(logs) == 3

        system_message = (
            {"content": WEATHER_TOOL_PROMPT[0]["content"]}
            if expect_content
            else None
        )
        assert_message_in_logs(
            logs[0], "gen_ai.system.message", system_message, spans[0]
        )

        user_message = (
            {
                "content": "What's the weather in Seattle and San Francisco today?"
            }
            if expect_content
            else None
        )
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
                            "arguments": tool_args[0].replace("\n", "")
                            if expect_content
                            else None,
                        },
                    },
                    {
                        "id": tool_call_ids[1],
                        "type": "function",
                        "function": {
                            "name": tool_names[1],
                            "arguments": tool_args[1].replace("\n", "")
                            if expect_content
                            else None,
                        },
                    },
                ],
            },
        }
        assert_message_in_logs(
            logs[2], "gen_ai.choice", choice_event, spans[0]
        )


def assert_no_invalid_type_warning(caplog):
    assert "Invalid type" not in caplog.text
