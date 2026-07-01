# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    openai_attributes as OpenAIAttributes,
)

from .utils import (
    _openai_response_format_to_output_type,
    get_server_address_and_port,
)

if TYPE_CHECKING:
    from openai.types.responses.response import Response
    from openai.types.responses.response_usage import ResponseUsage

    from opentelemetry.util.genai.types import (
        InputMessage,
        OutputMessage,
        Text,
    )

try:
    from openai.types.responses.response import Response
    from openai.types.responses.response_function_tool_call import (
        ResponseFunctionToolCall,
    )
    from openai.types.responses.response_output_message import (
        ResponseOutputMessage,
    )
    from openai.types.responses.response_output_refusal import (
        ResponseOutputRefusal,
    )
    from openai.types.responses.response_output_text import ResponseOutputText
    from openai.types.responses.response_reasoning_item import (
        ResponseReasoningItem,
    )
    from openai.types.responses.response_usage import ResponseUsage
except ImportError:
    Response = None
    ResponseFunctionToolCall = None
    ResponseOutputMessage = None
    ResponseOutputRefusal = None
    ResponseOutputText = None
    ResponseReasoningItem = None
    ResponseUsage = None

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
    OutputMessage = None
    Reasoning = None
    Text = None
    ToolCall = None


@dataclass
class ResponseRequestParams:
    model: str | None = None
    instructions: str | None = None
    input: str | Sequence[object] | None = None
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
    if isinstance(format_type, str):
        return _openai_response_format_to_output_type(format_type)
    return None


def extract_params(
    *,
    model: str | None = None,
    instructions: str | None = None,
    input_items: str | Sequence[object] | None = None,
    max_output_tokens: int | None = None,
    service_tier: str | None = None,
    temperature: float | None = None,
    text: object | None = None,
    top_p: float | None = None,
    **_kwargs: object,
) -> ResponseRequestParams:
    if input_items is None and "input" in _kwargs:
        input_items = _kwargs["input"]

    return ResponseRequestParams(
        model=model if isinstance(model, str) else None,
        instructions=instructions if isinstance(instructions, str) else None,
        input=(
            input_items
            if isinstance(input_items, str)
            or (
                isinstance(input_items, Sequence)
                and not isinstance(input_items, (str, bytes, bytearray))
            )
            else None
        ),
        max_output_tokens=_get_int(max_output_tokens),
        service_tier=(
            service_tier
            if isinstance(service_tier, str) and service_tier != "auto"
            else None
        ),
        temperature=_get_float(temperature),
        output_type=_extract_output_type_from_value(text),
        top_p=_get_float(top_p),
    )


def get_system_instruction(instructions: str | None) -> list["Text"]:
    if Text is None or instructions is None:
        return []
    return [Text(content=instructions)]


def get_input_messages(
    input_value: str | Sequence[object] | None,
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


def _extract_output_parts(content_blocks: Sequence[object]) -> list["Text"]:
    if (
        Text is None
        or ResponseOutputText is None
        or ResponseOutputRefusal is None
    ):
        return []

    parts: list[Text] = []
    for block in content_blocks:
        if isinstance(block, ResponseOutputText):
            parts.append(Text(content=block.text))
        elif isinstance(block, ResponseOutputRefusal):
            parts.append(Text(content=block.refusal))
    return parts


def _parse_tool_call_arguments(arguments: str | None) -> object:
    if arguments is None:
        return None

    try:
        return json.loads(arguments)
    except (TypeError, ValueError):
        return arguments


def _extract_reasoning_parts(
    item: "ResponseReasoningItem",
) -> list["Reasoning"]:
    if Reasoning is None:
        return []

    parts: list[Reasoning] = []
    for block in item.summary:
        if isinstance(block.text, str):
            parts.append(Reasoning(content=block.text))
    for block in item.content or []:
        if getattr(block, "type", None) == "reasoning_text" and isinstance(
            getattr(block, "text", None), str
        ):
            parts.append(Reasoning(content=block.text))
    return parts


def _finish_reason_from_status(status: str | None) -> str | None:
    if status == "completed":
        return "stop"
    if status in {"failed", "cancelled", "incomplete"}:
        return status
    return None


def _response_types_available() -> bool:
    return (
        Response is not None
        and ResponseOutputMessage is not None
        and ResponseFunctionToolCall is not None
        and ResponseReasoningItem is not None
    )


def get_output_messages_from_response(
    response: "Response | None",
) -> list["OutputMessage"]:
    if (
        not _response_types_available()
        or not isinstance(response, Response)
        or OutputMessage is None
        or Text is None
    ):
        return []

    messages: list[OutputMessage] = []
    for item in response.output:
        if isinstance(item, ResponseOutputMessage):
            finish_reason = _finish_reason_from_status(item.status)
            if finish_reason is None:
                continue

            messages.append(
                OutputMessage(
                    role=item.role,
                    parts=_extract_output_parts(item.content),
                    finish_reason=finish_reason,
                )
            )
            continue

        if isinstance(item, ResponseFunctionToolCall):
            if ToolCall is None or item.status not in {
                "completed",
                "incomplete",
            }:
                continue

            messages.append(
                OutputMessage(
                    role="assistant",
                    parts=[
                        ToolCall(
                            id=item.call_id if item.call_id else item.id,
                            name=item.name,
                            arguments=_parse_tool_call_arguments(
                                item.arguments
                            ),
                        )
                    ],
                    finish_reason="tool_calls",
                )
            )
            continue

        if isinstance(item, ResponseReasoningItem):
            finish_reason = _finish_reason_from_status(item.status)
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


def extract_finish_reasons(response: "Response | None") -> list[str]:
    if (
        Response is None
        or ResponseOutputMessage is None
        or ResponseFunctionToolCall is None
        or not isinstance(response, Response)
    ):
        return []

    finish_reasons: list[str] = []
    for item in response.output:
        if isinstance(item, ResponseFunctionToolCall) and item.status in {
            "completed",
            "incomplete",
        }:
            finish_reasons.append("tool_calls")
            continue

        if not isinstance(item, ResponseOutputMessage):
            continue
        finish_reason = _finish_reason_from_status(item.status)
        if finish_reason is not None:
            finish_reasons.append(finish_reason)
    return list(dict.fromkeys(finish_reasons))


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
        invocation.system_instruction = get_system_instruction(
            params.instructions
        )
        invocation.input_messages = get_input_messages(params.input)


def extract_usage_tokens(usage: "ResponseUsage | None") -> UsageTokens:
    if (
        ResponseUsage is None
        or usage is None
        or not isinstance(usage, ResponseUsage)
    ):
        return UsageTokens()

    details = usage.input_tokens_details
    return UsageTokens(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        # `cache_creation_input_tokens` is not present on every SDK version's
        # input token details model, so keep this attribute access guarded for
        # compatibility across the supported OpenAI range.
        cache_creation_input_tokens=(
            details.cache_creation_input_tokens
            if details is not None
            and hasattr(details, "cache_creation_input_tokens")
            else None
        ),
        cache_read_input_tokens=(
            details.cached_tokens if details is not None else None
        ),
    )


def set_invocation_response_attributes(
    invocation,
    response: "Response | None",
    capture_content: bool,
) -> None:
    if Response is None or not isinstance(response, Response):
        return

    invocation.response_model_name = response.model
    invocation.response_id = response.id

    if response.service_tier is not None:
        invocation.attributes[
            OpenAIAttributes.OPENAI_RESPONSE_SERVICE_TIER
        ] = response.service_tier

    tokens = extract_usage_tokens(response.usage)
    invocation.input_tokens = tokens.input_tokens
    invocation.output_tokens = tokens.output_tokens
    invocation.cache_creation_input_tokens = tokens.cache_creation_input_tokens
    invocation.cache_read_input_tokens = tokens.cache_read_input_tokens

    finish_reasons = extract_finish_reasons(response)
    if finish_reasons:
        invocation.finish_reasons = finish_reasons

    if capture_content:
        output_messages = get_output_messages_from_response(response)
        if output_messages:
            invocation.output_messages = output_messages
