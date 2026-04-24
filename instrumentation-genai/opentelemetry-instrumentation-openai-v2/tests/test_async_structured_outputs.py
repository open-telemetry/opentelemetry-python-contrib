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

"""Tests for async OpenAI structured outputs (chat.completions.parse) instrumentation."""

import pytest

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.util.genai.utils import is_experimental_mode

from .structured_outputs_utils import (
    STRUCTURED_OUTPUT_EXPECTED_INPUT_MESSAGES,
    STRUCTURED_OUTPUT_PROMPT,
    CalendarEvent,
)
from .test_utils import (
    DEFAULT_MODEL,
    assert_all_attributes,
    assert_message_in_logs,
    assert_messages_attribute,
    format_simple_expected_output_message,
)


@pytest.mark.asyncio()
async def test_async_structured_output_with_content(
    span_exporter,
    log_exporter,
    async_openai_client,
    instrument_with_content,
    vcr,
):
    latest_experimental_enabled = is_experimental_mode()

    with vcr.use_cassette("test_async_structured_output_with_content.yaml"):
        response = await async_openai_client.chat.completions.parse(
            messages=STRUCTURED_OUTPUT_PROMPT,
            model=DEFAULT_MODEL,
            response_format=CalendarEvent,
        )

    # Verify wrapper doesn't interfere with parse() return
    assert response.choices[0].message.parsed is not None

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert_all_attributes(
        spans[0],
        DEFAULT_MODEL,
        latest_experimental_enabled,
        response.id,
        response.model,
        response.usage.prompt_tokens,
        response.usage.completion_tokens,
    )

    output_type_attr_key = (
        GenAIAttributes.GEN_AI_OUTPUT_TYPE
        if latest_experimental_enabled
        else GenAIAttributes.GEN_AI_OPENAI_REQUEST_RESPONSE_FORMAT
    )
    expected_value = "json" if latest_experimental_enabled else "json_schema"
    assert spans[0].attributes[output_type_attr_key] == expected_value

    if latest_experimental_enabled:
        assert_messages_attribute(
            spans[0].attributes["gen_ai.input.messages"],
            STRUCTURED_OUTPUT_EXPECTED_INPUT_MESSAGES,
        )
        assert_messages_attribute(
            spans[0].attributes["gen_ai.output.messages"],
            format_simple_expected_output_message(response.choices[0].message.content),
        )
    else:
        logs = log_exporter.get_finished_logs()
        assert len(logs) == 2

        user_message = {"content": STRUCTURED_OUTPUT_PROMPT[0]["content"]}
        assert_message_in_logs(logs[0], "gen_ai.user.message", user_message, spans[0])

        choice_event = {
            "index": 0,
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": response.choices[0].message.content,
            },
        }
        assert_message_in_logs(logs[1], "gen_ai.choice", choice_event, spans[0])


@pytest.mark.asyncio()
async def test_async_structured_output_no_content(
    span_exporter,
    log_exporter,
    async_openai_client,
    instrument_no_content,
    vcr,
):
    latest_experimental_enabled = is_experimental_mode()

    with vcr.use_cassette("test_async_structured_output_no_content.yaml"):
        response = await async_openai_client.chat.completions.parse(
            messages=STRUCTURED_OUTPUT_PROMPT,
            model=DEFAULT_MODEL,
            response_format=CalendarEvent,
        )

    # Verify wrapper doesn't interfere with parse() return
    assert response.choices[0].message.parsed is not None

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert_all_attributes(
        spans[0],
        DEFAULT_MODEL,
        latest_experimental_enabled,
        response.id,
        response.model,
        response.usage.prompt_tokens,
        response.usage.completion_tokens,
    )

    output_type_attr_key = (
        GenAIAttributes.GEN_AI_OUTPUT_TYPE
        if latest_experimental_enabled
        else GenAIAttributes.GEN_AI_OPENAI_REQUEST_RESPONSE_FORMAT
    )
    expected_value = "json" if latest_experimental_enabled else "json_schema"
    assert spans[0].attributes[output_type_attr_key] == expected_value

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
        assert_message_in_logs(logs[1], "gen_ai.choice", choice_event, spans[0])
