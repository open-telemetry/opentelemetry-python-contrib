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

from typing import Any, Mapping, Optional

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    openai_attributes as OpenAIAttributes,
)
from opentelemetry.util.genai.types import (
    InputMessage,
    LLMInvocation,
    OutputMessage,
    Text,
)

OPENAI = GenAIAttributes.GenAiSystemValues.OPENAI.value
GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS = "gen_ai.usage.cache_read.input_tokens"
GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS = (
    "gen_ai.usage.cache_creation.input_tokens"
)


def _extract_system_instruction(kwargs: dict):
    """Extract system instruction from the ``instructions`` parameter."""
    if Text is None:
        return []
    instructions = kwargs.get("instructions")
    if instructions is None:
        return []
    if isinstance(instructions, str):
        return [Text(content=instructions)]
    return []


def _extract_input_messages(kwargs: dict):
    """Extract input messages from Responses API kwargs."""
    if InputMessage is None or Text is None:
        return []
    raw_input = kwargs.get("input")
    if raw_input is None:
        return []

    if isinstance(raw_input, str):
        return [InputMessage(role="user", parts=[Text(content=raw_input)])]

    messages = []
    if isinstance(raw_input, list):
        for item in raw_input:
            role = getattr(item, "role", None) or (
                item.get("role") if isinstance(item, dict) else None
            )
            if not role:
                continue
            content = getattr(item, "content", None) or (
                item.get("content") if isinstance(item, dict) else None
            )
            if isinstance(content, str):
                messages.append(
                    InputMessage(role=role, parts=[Text(content=content)])
                )
            elif isinstance(content, list):
                parts = []
                for part in content:
                    text = getattr(part, "text", None) or (
                        part.get("text") if isinstance(part, dict) else None
                    )
                    if text:
                        parts.append(Text(content=text))
                if parts:
                    messages.append(InputMessage(role=role, parts=parts))
    return messages


def _extract_output_messages(result: Any):
    """Extract output messages from a Responses API result."""
    if OutputMessage is None or Text is None:
        return []
    if result is None:
        return []

    output_items = getattr(result, "output", None)
    if not output_items:
        return []

    messages = []
    for item in output_items:
        if getattr(item, "type", None) != "message":
            continue

        role = getattr(item, "role", "assistant")
        finish_reason = _finish_reason_from_status(
            getattr(item, "status", None)
        )
        parts = _extract_output_parts(getattr(item, "content", []), Text)

        messages.append(
            OutputMessage(role=role, parts=parts, finish_reason=finish_reason)
        )

    return messages


def _finish_reason_from_status(status):
    return "stop" if status == "completed" else (status or "stop")


def _extract_output_parts(content_blocks, text_type):
    parts = []
    for block in content_blocks:
        block_type = getattr(block, "type", None)
        if block_type == "output_text":
            text = getattr(block, "text", None)
            if text:
                parts.append(text_type(content=text))
        elif block_type == "refusal":
            refusal = getattr(block, "refusal", None)
            if refusal:
                parts.append(text_type(content=refusal))
    return parts


def _extract_finish_reasons(result: Any) -> list[str]:
    """Extract finish reasons from Responses API output items."""
    output_items = getattr(result, "output", None)
    if not output_items:
        return []

    finish_reasons = []
    for item in output_items:
        if getattr(item, "type", None) != "message":
            continue
        finish_reasons.append(
            _finish_reason_from_status(getattr(item, "status", None))
        )
    return finish_reasons


def _extract_output_type(kwargs: dict) -> Optional[str]:
    """Extract output type from Responses API request text.format."""
    text_config = kwargs.get("text")
    if not isinstance(text_config, Mapping):
        return None

    format_config = text_config.get("format")
    if isinstance(format_config, Mapping):
        format_type = format_config.get("type")
    else:
        format_type = None

    if format_type == "json_schema":
        return "json"
    return format_type


def _get_field(obj: Any, key: str):
    if isinstance(obj, Mapping):
        return obj.get(key)
    return getattr(obj, key, None)


def _set_optional_attribute(
    invocation: "LLMInvocation",
    result: Any,
    source_name: str,
    target_name: str,
):
    value = getattr(result, source_name, None)
    if value is not None:
        invocation.attributes[target_name] = value


def _set_invocation_usage_attributes(invocation: "LLMInvocation", usage: Any):
    input_tokens = _get_field(usage, "input_tokens")
    if input_tokens is None:
        input_tokens = _get_field(usage, "prompt_tokens")
    invocation.input_tokens = input_tokens

    output_tokens = _get_field(usage, "output_tokens")
    if output_tokens is None:
        output_tokens = _get_field(usage, "completion_tokens")
    invocation.output_tokens = output_tokens

    input_token_details = _get_field(usage, "input_tokens_details")
    if input_token_details is None:
        input_token_details = _get_field(usage, "prompt_tokens_details")

    cache_read_tokens = _get_field(input_token_details, "cached_tokens")
    if cache_read_tokens is not None:
        invocation.attributes[GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS] = (
            cache_read_tokens
        )

    cache_creation_tokens = _get_field(
        input_token_details, "cache_creation_input_tokens"
    )
    if cache_creation_tokens is not None:
        invocation.attributes[GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS] = (
            cache_creation_tokens
        )


def _set_invocation_response_attributes(
    invocation: "LLMInvocation",
    result: Any,
    capture_content: bool,
):
    if result is None:
        return

    if getattr(result, "model", None):
        invocation.response_model_name = result.model

    if getattr(result, "id", None):
        invocation.response_id = result.id

    _set_optional_attribute(
        invocation,
        result,
        "service_tier",
        OpenAIAttributes.OPENAI_RESPONSE_SERVICE_TIER,
    )

    usage = getattr(result, "usage", None)
    if usage:
        _set_invocation_usage_attributes(invocation, usage)

    finish_reasons = _extract_finish_reasons(result)
    if finish_reasons:
        invocation.finish_reasons = finish_reasons

    if capture_content:
        output_messages = _extract_output_messages(result)
        if output_messages:
            invocation.output_messages = output_messages
