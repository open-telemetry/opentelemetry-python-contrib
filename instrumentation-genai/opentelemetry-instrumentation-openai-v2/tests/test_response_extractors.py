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

import builtins
import functools
import importlib.util
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from opentelemetry.semconv._incubating.attributes import (
    openai_attributes as OpenAIAttributes,
)
from opentelemetry.util.genai.types import LLMInvocation

_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "opentelemetry"
    / "instrumentation"
    / "openai_v2"
    / "response_extractors.py"
)


def _load_module(block_genai_types_import=False):
    spec = importlib.util.spec_from_file_location(
        "test_response_extractors_module", _MODULE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    if not block_genai_types_import:
        spec.loader.exec_module(module)
        return module

    original_import = builtins.__import__

    def _patched_import(
        name, globalns=None, localns=None, fromlist=(), level=0
    ):
        if name == "opentelemetry.util.genai.types":
            raise ImportError("simulated missing genai types")
        return original_import(name, globalns, localns, fromlist, level)

    with mock.patch("builtins.__import__", side_effect=_patched_import):
        spec.loader.exec_module(module)
    return module


@functools.lru_cache(maxsize=None)
def _module(block_genai_types_import=False):
    return _load_module(block_genai_types_import)


@pytest.fixture(scope="module", name="loaded_module")
def _loaded_module_fixture():
    return _module()


@pytest.fixture(
    scope="module", name="gen_ai_usage_cache_creation_input_tokens"
)
def _gen_ai_usage_cache_creation_input_tokens_fixture(loaded_module):
    return loaded_module.GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS


@pytest.fixture(scope="module", name="gen_ai_usage_cache_read_input_tokens")
def _gen_ai_usage_cache_read_input_tokens_fixture(loaded_module):
    return loaded_module.GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS


def test_extract_system_instruction_returns_text_for_string(loaded_module):
    instructions = loaded_module._extract_system_instruction(
        {"instructions": "Be concise"}
    )

    assert [part.content for part in instructions] == ["Be concise"]


def test_extract_input_messages_supports_string_and_mixed_message_content(
    loaded_module,
):
    from_string = loaded_module._extract_input_messages({"input": "Hello"})
    from_list = loaded_module._extract_input_messages(
        {
            "input": [
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
        }
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
    result = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="message",
                role="assistant",
                status="completed",
                content=[
                    SimpleNamespace(type="output_text", text="Done"),
                    SimpleNamespace(type="refusal", refusal="Cannot comply"),
                    SimpleNamespace(type="summary", text="ignored"),
                ],
            ),
            SimpleNamespace(
                type="message",
                status="incomplete",
                content=[SimpleNamespace(type="output_text", text="Partial")],
            ),
            SimpleNamespace(
                type="message",
                status="queued",
                content=[SimpleNamespace(type="output_text", text="Pending")],
            ),
            SimpleNamespace(type="tool_call", status="completed", content=[]),
        ]
    )

    messages = loaded_module._extract_output_messages(result)

    assert [(msg.role, msg.finish_reason) for msg in messages] == [
        ("assistant", "stop"),
        ("assistant", "incomplete"),
    ]
    assert [[part.content for part in msg.parts] for msg in messages] == [
        ["Done", "Cannot comply"],
        ["Partial"],
    ]


def test_extract_finish_reasons_only_reads_message_items(loaded_module):
    result = SimpleNamespace(
        output=[
            SimpleNamespace(type="message", status="completed"),
            SimpleNamespace(type="message", status=None),
            SimpleNamespace(type="message", status="in_progress"),
            SimpleNamespace(type="tool_call", status="incomplete"),
        ]
    )

    assert loaded_module._extract_finish_reasons(result) == ["stop"]


def test_extract_output_type_handles_text_format_mapping(loaded_module):
    assert (
        loaded_module._extract_output_type(
            {"text": {"format": {"type": "json_schema"}}}
        )
        == "json"
    )
    assert (
        loaded_module._extract_output_type(
            {"text": {"format": {"type": "text"}}}
        )
        == "text"
    )
    assert (
        loaded_module._extract_output_type(
            {
                "text": SimpleNamespace(
                    format=SimpleNamespace(type="json_schema")
                )
            }
        )
        == "json"
    )
    assert (
        loaded_module._extract_output_type(
            {"text": SimpleNamespace(format=SimpleNamespace(type="text"))}
        )
        == "text"
    )
    # Invalid request shapes should degrade to no extracted output type rather
    # than surfacing validation errors from instrumentation.
    assert (
        loaded_module._extract_output_type({"text": {"format": "plain"}})
        is None
    )
    assert loaded_module._extract_output_type({"text": "plain"}) is None


def test_extractors_handle_missing_genai_types_import():
    module = _module(block_genai_types_import=True)

    assert module.Text is None
    assert module.InputMessage is None
    assert module.OutputMessage is None
    assert module._extract_system_instruction({"instructions": "hi"}) == []
    assert module._extract_input_messages({"input": "hi"}) == []
    assert (
        module._extract_output_messages(
            SimpleNamespace(
                output=[SimpleNamespace(type="message", content=[])]
            )
        )
        == []
    )


def test_set_invocation_response_attributes_populates_usage_and_metadata(
    loaded_module,
    gen_ai_usage_cache_creation_input_tokens,
    gen_ai_usage_cache_read_input_tokens,
):
    invocation = LLMInvocation(request_model="gpt-4o-mini")
    result = SimpleNamespace(
        model="gpt-4.1",
        id="resp_123",
        service_tier="scale",
        usage=SimpleNamespace(
            prompt_tokens=11,
            completion_tokens=7,
            prompt_tokens_details=SimpleNamespace(
                cached_tokens=3,
                cache_creation_input_tokens=5,
            ),
        ),
    )

    loaded_module._set_invocation_response_attributes(
        invocation, result, capture_content=False
    )

    assert invocation.response_model_name == "gpt-4.1"
    assert invocation.response_id == "resp_123"
    assert invocation.input_tokens == 11
    assert invocation.output_tokens == 7
    assert invocation.attributes == {
        OpenAIAttributes.OPENAI_RESPONSE_SERVICE_TIER: "scale",
        gen_ai_usage_cache_read_input_tokens: 3,
        gen_ai_usage_cache_creation_input_tokens: 5,
    }


def test_set_invocation_response_attributes_accepts_mapping_usage(
    loaded_module,
    gen_ai_usage_cache_creation_input_tokens,
    gen_ai_usage_cache_read_input_tokens,
):
    invocation = LLMInvocation(request_model="gpt-4o-mini")
    result = SimpleNamespace(
        usage={
            "input_tokens": 13,
            "output_tokens": 8,
            "input_tokens_details": {
                "cached_tokens": 2,
                "cache_creation_input_tokens": 4,
            },
        }
    )

    loaded_module._set_invocation_response_attributes(
        invocation, result, capture_content=False
    )

    assert invocation.input_tokens == 13
    assert invocation.output_tokens == 8
    assert invocation.attributes == {
        gen_ai_usage_cache_read_input_tokens: 2,
        gen_ai_usage_cache_creation_input_tokens: 4,
    }


def test_set_invocation_response_attributes_populates_output_messages(
    loaded_module,
):
    invocation = LLMInvocation(request_model="gpt-4o-mini")
    result = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="message",
                role="assistant",
                status="completed",
                content=[SimpleNamespace(type="output_text", text="Done")],
            )
        ]
    )

    loaded_module._set_invocation_response_attributes(
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


def test_prevalidated_response_model_skips_revalidation(
    loaded_module, monkeypatch
):
    validated_result = loaded_module._ResponsesResultModel.model_validate(
        SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="message",
                    status="completed",
                    content=[SimpleNamespace(type="output_text", text="Done")],
                )
            ]
        )
    )

    def _unexpected_validation(_result):
        raise AssertionError("unexpected response revalidation")

    monkeypatch.setattr(
        loaded_module, "_validate_response_result", _unexpected_validation
    )

    assert loaded_module._extract_finish_reasons(validated_result) == ["stop"]
    messages = loaded_module._extract_output_messages(validated_result)
    assert [part.content for part in messages[0].parts] == ["Done"]


@pytest.mark.parametrize(
    ("kwargs", "extractor_name"),
    [
        ({"instructions": ["not-a-string"]}, "_extract_system_instruction"),
        ({"input": 42}, "_extract_input_messages"),
        ({"text": {"format": 42}}, "_extract_output_type"),
    ],
)
def test_request_validation_errors_are_logged_and_ignored(
    loaded_module, caplog, kwargs, extractor_name
):
    caplog.set_level(logging.DEBUG, logger=loaded_module.__name__)
    extractor = getattr(loaded_module, extractor_name)

    result = extractor(kwargs)

    assert result in ([], None)
    assert "OpenAI responses extractor validation failed" in caplog.text


def test_response_validation_errors_are_logged_and_ignored(
    loaded_module, caplog
):
    caplog.set_level(logging.DEBUG, logger=loaded_module.__name__)
    invocation = LLMInvocation(request_model="gpt-4o-mini")
    invalid_result = SimpleNamespace(output=42, usage=42)

    assert loaded_module._extract_output_messages(invalid_result) == []
    assert loaded_module._extract_finish_reasons(invalid_result) == []

    loaded_module._set_invocation_response_attributes(
        invocation, invalid_result, capture_content=True
    )

    assert invocation.response_model_name is None
    assert invocation.response_id is None
    assert invocation.input_tokens is None
    assert invocation.output_tokens is None
    assert invocation.finish_reasons is None
    assert not invocation.output_messages
    assert not invocation.attributes
    assert "OpenAI responses extractor validation failed" in caplog.text
