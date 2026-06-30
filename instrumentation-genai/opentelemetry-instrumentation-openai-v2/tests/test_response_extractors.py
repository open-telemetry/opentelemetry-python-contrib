# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
from unittest import mock

import pytest

from opentelemetry.instrumentation.openai_v2 import response_extractors
from opentelemetry.semconv._incubating.attributes import (
    openai_attributes as OpenAIAttributes,
)
from opentelemetry.util.genai.types import LLMInvocation

try:
    # Responses types are not available in the oldest supported OpenAI SDK.
    # pylint: disable-next=no-name-in-module
    from openai.types.responses.response import Response

    HAS_RESPONSES_TYPES = True
except ImportError:
    Response = None
    HAS_RESPONSES_TYPES = False

pytestmark = pytest.mark.skipif(
    not HAS_RESPONSES_TYPES,
    reason="Responses SDK types require a newer openai SDK",
)


@pytest.fixture(scope="module", name="loaded_module")
def _loaded_module_fixture():
    return response_extractors


def _make_response(output=None, **overrides):
    payload = {
        "id": "resp_123",
        "created_at": 0.0,
        "model": "gpt-4.1",
        "object": "response",
        "output": output or [],
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
        "temperature": 1.0,
        "top_p": 1.0,
        "usage": {
            "input_tokens": 11,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": 7,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 18,
        },
    }
    payload.update(overrides)
    return Response.model_validate(payload)


def test_extract_system_instruction_returns_text_for_string(loaded_module):
    params = loaded_module.extract_params(instructions="Be concise")
    instructions = loaded_module.get_system_instruction(params.instructions)

    assert [part.content for part in instructions] == ["Be concise"]


def test_extract_input_messages_supports_string_and_mixed_message_content(
    loaded_module,
):
    from_string = loaded_module.get_input_messages("Hello")
    from_list = loaded_module.get_input_messages(
        [
            {"role": "user", "content": "First"},
            SimpleNamespace(
                role="assistant",
                content=[
                    {"text": "Second"},
                    SimpleNamespace(text="Third"),
                    {"type": "input_image", "image_url": "ignored"},
                ],
            ),
            {"role": None, "content": "ignored"},
        ]
    )

    assert [
        (msg.role, [part.content for part in msg.parts]) for msg in from_string
    ] == [("user", ["Hello"])]
    assert [
        (msg.role, [part.content for part in msg.parts]) for msg in from_list
    ] == [
        ("user", ["First"]),
        ("assistant", ["Second", "Third"]),
    ]


def test_extract_output_messages_maps_parts_and_finish_reasons(loaded_module):
    response = _make_response(
        output=[
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {"type": "output_text", "text": "Done", "annotations": []},
                    {"type": "refusal", "refusal": "Cannot comply"},
                ],
            },
            {
                "id": "msg_2",
                "type": "message",
                "role": "assistant",
                "status": "incomplete",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Partial",
                        "annotations": [],
                    }
                ],
            },
            {
                "id": "msg_3",
                "type": "message",
                "role": "assistant",
                "status": "in_progress",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Pending",
                        "annotations": [],
                    }
                ],
            },
            {
                "id": "fc_1",
                "type": "function_call",
                "status": "completed",
                "name": "get_weather",
                "call_id": "call_123",
                "arguments": '{"city":"SF"}',
            },
            {
                "id": "rs_1",
                "type": "reasoning",
                "status": "completed",
                "summary": [{"type": "summary_text", "text": "Thought step"}],
                "content": None,
            },
        ]
    )

    messages = loaded_module.get_output_messages_from_response(response)

    assert [(msg.role, msg.finish_reason) for msg in messages] == [
        ("assistant", "stop"),
        ("assistant", "incomplete"),
        ("assistant", "tool_calls"),
        ("assistant", "stop"),
    ]
    assert [part.content for part in messages[0].parts] == [
        "Done",
        "Cannot comply",
    ]
    assert [part.content for part in messages[1].parts] == ["Partial"]
    assert messages[2].parts[0].type == "tool_call"
    assert messages[2].parts[0].name == "get_weather"
    assert messages[2].parts[0].arguments == {"city": "SF"}
    assert messages[3].parts[0].type == "reasoning"
    assert messages[3].parts[0].content == "Thought step"


def test_extract_finish_reasons_maps_terminal_message_and_tool_items(
    loaded_module,
):
    response = _make_response(
        output=[
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [],
            },
            {
                "id": "msg_2",
                "type": "message",
                "role": "assistant",
                "status": "in_progress",
                "content": [],
            },
            {
                "id": "fc_1",
                "type": "function_call",
                "status": "incomplete",
                "name": "tool",
                "call_id": "call_1",
                "arguments": "{}",
            },
        ]
    )

    assert loaded_module.extract_finish_reasons(response) == [
        "stop",
        "tool_calls",
    ]


def test_extract_output_type_handles_text_format_mapping(loaded_module):
    assert (
        loaded_module.extract_params(
            text={"format": {"type": "json_schema"}}
        ).output_type
        == "json"
    )
    assert (
        loaded_module.extract_params(
            text={"format": {"type": "text"}}
        ).output_type
        == "text"
    )
    assert (
        loaded_module.extract_params(
            text=SimpleNamespace(format=SimpleNamespace(type="json_schema"))
        ).output_type
        == "json"
    )
    assert (
        loaded_module.extract_params(
            text=SimpleNamespace(format=SimpleNamespace(type="text"))
        ).output_type
        == "text"
    )
    assert (
        loaded_module.extract_params(text={"format": "plain"}).output_type
        is None
    )
    assert loaded_module.extract_params(text="plain").output_type is None


def test_extractors_handle_missing_genai_types_import(loaded_module):
    with (
        mock.patch.object(loaded_module, "Text", None),
        mock.patch.object(loaded_module, "InputMessage", None),
        mock.patch.object(loaded_module, "OutputMessage", None),
    ):
        assert loaded_module.get_system_instruction("hi") == []
        assert loaded_module.get_input_messages("hi") == []
        assert (
            loaded_module.get_output_messages_from_response(
                _make_response(
                    output=[
                        {
                            "id": "msg_1",
                            "type": "message",
                            "role": "assistant",
                            "status": "completed",
                            "content": [],
                        }
                    ]
                )
            )
            == []
        )


def test_set_invocation_response_attributes_populates_usage_and_metadata(
    loaded_module,
):
    invocation = LLMInvocation(request_model="gpt-4o-mini")
    result = _make_response(
        service_tier="scale",
        usage={
            "input_tokens": 11,
            "input_tokens_details": {
                "cached_tokens": 3,
                "cache_creation_input_tokens": 5,
            },
            "output_tokens": 7,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 18,
        },
    )

    loaded_module.set_invocation_response_attributes(
        invocation, result, capture_content=False
    )

    assert invocation.response_model_name == "gpt-4.1"
    assert invocation.response_id == "resp_123"
    assert invocation.input_tokens == 11
    assert invocation.output_tokens == 7
    assert getattr(invocation, "cache_read_input_tokens") == 3
    assert getattr(invocation, "cache_creation_input_tokens") == 5
    assert invocation.attributes == {
        OpenAIAttributes.OPENAI_RESPONSE_SERVICE_TIER: "scale",
    }


def test_set_invocation_response_attributes_populates_output_messages(
    loaded_module,
):
    invocation = LLMInvocation(request_model="gpt-4o-mini")
    result = _make_response(
        output=[
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {"type": "output_text", "text": "Done", "annotations": []}
                ],
            }
        ]
    )

    loaded_module.set_invocation_response_attributes(
        invocation, result, capture_content=True
    )

    assert invocation.finish_reasons == ["stop"]
    assert [
        (message.role, message.finish_reason)
        for message in invocation.output_messages
    ] == [("assistant", "stop")]
    assert [
        [part.content for part in message.parts]
        for message in invocation.output_messages
    ] == [["Done"]]


def test_extractors_ignore_invalid_request_shapes_without_validation(
    loaded_module,
):
    params = loaded_module.extract_params(
        instructions=["not-a-string"], input=42, text={"format": {"type": 42}}
    )
    assert loaded_module.get_system_instruction(params.instructions) == []
    assert loaded_module.get_input_messages(params.input) == []
    assert params.output_type is None


def test_response_extractors_ignore_invalid_shapes_without_validation(
    loaded_module,
):
    invocation = LLMInvocation(request_model="gpt-4o-mini")
    invalid_result = SimpleNamespace(output=42, usage=42)

    assert (
        loaded_module.get_output_messages_from_response(invalid_result) == []
    )
    assert loaded_module.extract_finish_reasons(invalid_result) == []

    loaded_module.set_invocation_response_attributes(
        invocation, invalid_result, capture_content=True
    )

    assert invocation.response_model_name is None
    assert invocation.response_id is None
    assert invocation.input_tokens is None
    assert invocation.output_tokens is None
    assert invocation.finish_reasons is None
    assert not invocation.output_messages
    assert not invocation.attributes
