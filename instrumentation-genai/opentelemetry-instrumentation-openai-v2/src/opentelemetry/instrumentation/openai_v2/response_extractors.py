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

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    openai_attributes as OpenAIAttributes,
)

from .utils import get_server_address_and_port

if TYPE_CHECKING:
    from opentelemetry.util.genai.types import (
        InputMessage,
        OutputMessage,
        Text,
    )

try:
    from opentelemetry.util.genai.types import (
        InputMessage,
        OutputMessage,
        Reasoning,
        Text,
    )
    from opentelemetry.util.genai.types import (
        ToolCallRequest as ToolCall,
    )
except ImportError:
    InputMessage = None
    LLMInvocation = None
    OutputMessage = None
    Reasoning = None
    Text = None
    ToolCall = None

GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS = "gen_ai.usage.cache_read.input_tokens"
GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS = (
    "gen_ai.usage.cache_creation.input_tokens"
)


@dataclass
class ResponseRequestParams:
    model: str | None = None
    instructions: str | None = None
    input: object | None = None
    system_instruction: list["Text"] = field(default_factory=list)
    input_messages: list["InputMessage"] = field(default_factory=list)
    max_output_tokens: int | None = None
    service_tier: str | None = None
    temperature: float | None = None
    output_type: str | None = None
    top_p: float | None = None


@dataclass
class UsageTokens:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None


def _get_field(value: object, field_name: str) -> object | None:
    if isinstance(value, Mapping):
        return value.get(field_name)
    return getattr(value, field_name, None)


def _get_sequence(value: object) -> Sequence[object]:
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return value
    return ()


def _get_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _get_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _extract_output_type_from_value(text_config: object) -> str | None:
    format_config = _get_field(text_config, "format")
    if format_config is None:
        return None

    format_type = _get_field(format_config, "type")
    if format_type == "json_schema":
        return "json"
    if isinstance(format_type, str):
        return format_type
    return None


def _extract_input_messages_from_value(
    input_value: object,
) -> list["InputMessage"]:
    if InputMessage is None or Text is None:
        return []

    if isinstance(input_value, str):
        return [InputMessage(role="user", parts=[Text(content=input_value)])]

    messages: list[InputMessage] = []
    for item in _get_sequence(input_value):
        role = _get_field(item, "role")
        if not isinstance(role, str):
            continue

        content = _get_field(item, "content")
        if isinstance(content, str):
            messages.append(
                InputMessage(role=role, parts=[Text(content=content)])
            )
            continue

        parts = []
        for part in _get_sequence(content):
            text = _get_field(part, "text")
            if isinstance(text, str):
                parts.append(Text(content=text))
        if parts:
            messages.append(InputMessage(role=role, parts=parts))

    return messages


def extract_params(**kwargs: object) -> ResponseRequestParams:
    model = kwargs.get("model")
    instructions = kwargs.get("instructions")
    input_value = kwargs.get("input")
    service_tier = kwargs.get("service_tier")

    params = ResponseRequestParams(
        model=model if isinstance(model, str) else None,
        instructions=instructions if isinstance(instructions, str) else None,
        input=input_value,
        max_output_tokens=_get_int(kwargs.get("max_output_tokens")),
        service_tier=(
            service_tier
            if isinstance(service_tier, str) and service_tier != "auto"
            else None
        ),
        temperature=_get_float(kwargs.get("temperature")),
        output_type=_extract_output_type_from_value(kwargs.get("text")),
        top_p=_get_float(kwargs.get("top_p")),
    )

    params.system_instruction = get_system_instruction(params.instructions)
    params.input_messages = get_input_messages(params.input)

    return params


def get_system_instruction(instructions: str | None) -> list["Text"]:
    if Text is None or instructions is None:
        return []
    return [Text(content=instructions)]


def get_input_messages(input_value: object) -> list["InputMessage"]:
    return _extract_input_messages_from_value(input_value)


def _extract_output_parts(
    content_blocks: Sequence[object],
) -> list["Text"]:
    if Text is None:
        return []

    parts: list[Text] = []
    for block in content_blocks:
        block_type = _get_field(block, "type")
        text = _get_field(block, "text")
        refusal = _get_field(block, "refusal")
        if block_type == "output_text" and isinstance(text, str):
            parts.append(Text(content=text))
        elif block_type == "refusal" and isinstance(refusal, str):
            parts.append(Text(content=refusal))
    return parts


def _parse_tool_call_arguments(arguments: str | None) -> object:
    if arguments is None:
        return None

    try:
        return json.loads(arguments)
    except (TypeError, ValueError):
        return arguments


def _extract_reasoning_parts(
    item: object,
) -> list["Reasoning"]:
    if Reasoning is None:
        return []

    parts: list[Reasoning] = []
    for block in _get_sequence(_get_field(item, "summary")):
        text = _get_field(block, "text")
        if isinstance(text, str):
            parts.append(Reasoning(content=text))
    for block in _get_sequence(_get_field(item, "content")):
        if _get_field(block, "type") == "reasoning_text":
            text = _get_field(block, "text")
            if isinstance(text, str):
                parts.append(Reasoning(content=text))
    return parts


def _finish_reason_from_status(status: str | None) -> str | None:
    # Responses API output items expose lifecycle statuses rather than finish
    # reasons. We map the normal terminal state to the GenAI "stop" reason,
    # preserve the other terminal statuses verbatim, and drop non-terminal or
    # unknown states from the finish_reasons attribute.
    if status == "completed":
        return "stop"
    if status in {"failed", "cancelled", "incomplete"}:
        return status
    return None


def get_output_messages_from_response(
    response: object | None,
) -> list["OutputMessage"]:
    if OutputMessage is None or Text is None:
        return []

    messages: list[OutputMessage] = []
    for item in _get_sequence(_get_field(response, "output")):
        item_type = _get_field(item, "type")
        item_status = _get_field(item, "status")
        if item_type == "message":
            finish_reason = _finish_reason_from_status(item_status)
            if finish_reason is None:
                continue

            messages.append(
                OutputMessage(
                    role=(
                        _get_field(item, "role")
                        if isinstance(_get_field(item, "role"), str)
                        else "assistant"
                    ),
                    parts=_extract_output_parts(
                        _get_sequence(_get_field(item, "content"))
                    ),
                    finish_reason=finish_reason,
                )
            )
            continue

        if item_type == "function_call":
            item_name = _get_field(item, "name")
            if ToolCall is None or not isinstance(item_name, str):
                continue
            if item_status not in {"completed", "incomplete"}:
                continue

            messages.append(
                OutputMessage(
                    role="assistant",
                    parts=[
                        ToolCall(
                            id=_get_field(item, "call_id")
                            if _get_field(item, "call_id")
                            else _get_field(item, "id"),
                            name=item_name,
                            arguments=_parse_tool_call_arguments(
                                _get_field(item, "arguments")
                            ),
                        )
                    ],
                    finish_reason="tool_calls",
                )
            )
            continue

        if item_type == "reasoning":
            finish_reason = _finish_reason_from_status(item_status)
            if finish_reason is None:
                continue

            parts = _extract_reasoning_parts(item)
            if parts:
                messages.append(
                    OutputMessage(
                        role="assistant",
                        parts=parts,
                        finish_reason=finish_reason,
                    )
                )

    return messages


def extract_finish_reasons(response: object | None) -> list[str]:
    finish_reasons: list[str] = []
    for item in _get_sequence(_get_field(response, "output")):
        item_type = _get_field(item, "type")
        item_status = _get_field(item, "status")
        if item_type == "function_call" and item_status in {
            "completed",
            "incomplete",
        }:
            finish_reasons.append("tool_calls")
            continue

        if item_type != "message":
            continue
        finish_reason = _finish_reason_from_status(item_status)
        if finish_reason is not None:
            finish_reasons.append(finish_reason)
    return list(dict.fromkeys(finish_reasons))


def _extract_output_type(kwargs: Mapping[str, object]) -> str | None:
    """Extract output type from Responses API request text.format."""
    return extract_params(**kwargs).output_type


def _extract_request_service_tier(
    kwargs: Mapping[str, object],
) -> str | None:
    return extract_params(**kwargs).service_tier


def get_inference_creation_kwargs(
    params: ResponseRequestParams,
    client_instance: object,
) -> dict[str, object]:
    address, port = get_server_address_and_port(client_instance)

    creation_kwargs: dict[str, object] = {
        "provider": GenAIAttributes.GenAiProviderNameValues.OPENAI.value,
    }
    if params.model is not None:
        creation_kwargs["request_model"] = params.model
    if address is not None:
        creation_kwargs["server_address"] = address
    if port is not None:
        creation_kwargs["server_port"] = port
    return creation_kwargs


def apply_request_attributes(
    invocation,
    params: ResponseRequestParams,
    capture_content: bool,
) -> None:
    invocation.temperature = params.temperature
    invocation.top_p = params.top_p
    invocation.max_tokens = params.max_output_tokens

    if params.service_tier is not None:
        invocation.attributes[OpenAIAttributes.OPENAI_REQUEST_SERVICE_TIER] = (
            params.service_tier
        )

    if params.output_type is not None:
        invocation.attributes[GenAIAttributes.GEN_AI_OUTPUT_TYPE] = (
            params.output_type
        )

    if capture_content:
        invocation.system_instruction = params.system_instruction
        invocation.input_messages = params.input_messages


def extract_usage_tokens(usage: object | None) -> UsageTokens:
    if usage is None:
        return UsageTokens()

    input_tokens = _get_int(_get_field(usage, "input_tokens"))
    output_tokens = _get_int(_get_field(usage, "output_tokens"))
    prompt_tokens = _get_int(_get_field(usage, "prompt_tokens"))
    completion_tokens = _get_int(_get_field(usage, "completion_tokens"))
    details = (
        _get_field(usage, "input_tokens_details")
        if _get_field(usage, "input_tokens_details") is not None
        else _get_field(usage, "prompt_tokens_details")
    )
    return UsageTokens(
        input_tokens=input_tokens
        if input_tokens is not None
        else prompt_tokens,
        output_tokens=(
            output_tokens if output_tokens is not None else completion_tokens
        ),
        cache_read_input_tokens=_get_int(_get_field(details, "cached_tokens")),
        cache_creation_input_tokens=_get_int(
            _get_field(details, "cache_creation_input_tokens")
        ),
    )


def set_invocation_response_attributes(
    invocation,
    response: object | None,
    capture_content: bool,
) -> None:
    if response is None:
        return

    model = _get_field(response, "model")
    if isinstance(model, str):
        invocation.response_model_name = model

    response_id = _get_field(response, "id")
    if isinstance(response_id, str):
        invocation.response_id = response_id

    service_tier = _get_field(response, "service_tier")
    if service_tier is not None:
        invocation.attributes[
            OpenAIAttributes.OPENAI_RESPONSE_SERVICE_TIER
        ] = service_tier

    tokens = extract_usage_tokens(_get_field(response, "usage"))
    invocation.input_tokens = tokens.input_tokens
    invocation.output_tokens = tokens.output_tokens
    if tokens.cache_creation_input_tokens is not None:
        invocation.attributes[GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS] = (
            tokens.cache_creation_input_tokens
        )
    if tokens.cache_read_input_tokens is not None:
        invocation.attributes[GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS] = (
            tokens.cache_read_input_tokens
        )

    finish_reasons = extract_finish_reasons(response)
    if finish_reasons:
        invocation.finish_reasons = finish_reasons

    if capture_content:
        output_messages = get_output_messages_from_response(response)
        if output_messages:
            invocation.output_messages = output_messages


def _extract_request_params(
    kwargs: Mapping[str, object],
) -> ResponseRequestParams:
    return extract_params(**kwargs)


def _extract_system_instruction(kwargs: Mapping[str, object]) -> list["Text"]:
    return get_system_instruction(_extract_request_params(kwargs).instructions)


def _extract_input_messages(
    kwargs: Mapping[str, object],
) -> list["InputMessage"]:
    return get_input_messages(_extract_request_params(kwargs).input)


def _extract_output_messages(result: object | None) -> list["OutputMessage"]:
    return get_output_messages_from_response(result)


def _extract_finish_reasons(result: object | None) -> list[str]:
    return extract_finish_reasons(result)


def _get_inference_creation_kwargs(
    kwargs: Mapping[str, object],
    client_instance: object,
) -> dict[str, object]:
    return get_inference_creation_kwargs(
        _extract_request_params(kwargs), client_instance
    )


def _apply_request_attributes(
    invocation,
    kwargs: Mapping[str, object],
    capture_content: bool,
) -> None:
    apply_request_attributes(
        invocation, _extract_request_params(kwargs), capture_content
    )


def _set_invocation_usage_attributes(invocation, usage: object) -> None:
    tokens = extract_usage_tokens(usage)
    invocation.input_tokens = tokens.input_tokens
    invocation.output_tokens = tokens.output_tokens
    if tokens.cache_creation_input_tokens is not None:
        invocation.attributes[GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS] = (
            tokens.cache_creation_input_tokens
        )
    if tokens.cache_read_input_tokens is not None:
        invocation.attributes[GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS] = (
            tokens.cache_read_input_tokens
        )


def _set_invocation_response_attributes(
    invocation,
    result: object | None,
    capture_content: bool,
) -> None:
    set_invocation_response_attributes(invocation, result, capture_content)
