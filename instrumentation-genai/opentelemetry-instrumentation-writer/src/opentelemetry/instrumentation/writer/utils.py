# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from typing import Any, Iterable, List, Mapping
from urllib.parse import urlparse

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.invocation import InferenceInvocation
from opentelemetry.util.genai.types import (
    FunctionToolDefinition,
    InputMessage,
    OutputMessage,
    Text,
    ToolCallRequest,
    ToolCallResponse,
    ToolDefinition,
)

# There is no Writer-specific member in ``GenAiProviderNameValues`` /
# ``GenAiSystemValues`` in the semconv package (unlike ``mistral_ai`` / ``groq``),
# so the raw string literal ``"writer"`` is used for ``gen_ai.provider.name``.
_WRITER_PROVIDER = "writer"

# writerai uses ``Omit`` / ``NotGiven`` sentinels for optional parameters that
# were not supplied. Values equal to those sentinels should be treated as "not
# provided".
try:
    from writerai import NotGiven as _WriterNotGiven
except Exception:  # pragma: no cover - defensive import
    _WriterNotGiven = None

try:
    from writerai import Omit as _WriterOmit
except Exception:  # pragma: no cover - defensive import
    _WriterOmit = None


def value_is_set(value: Any) -> bool:
    if value is None:
        return False
    if _WriterOmit is not None and isinstance(value, _WriterOmit):
        return False
    if _WriterNotGiven is not None and isinstance(value, _WriterNotGiven):
        return False
    return True


def get_value(value: Any) -> Any:
    if value_is_set(value):
        return value
    return None


def get_property_value(obj: Any, property_name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(property_name, None)
    return getattr(obj, property_name, None)


def is_streaming(kwargs: Mapping[str, Any]) -> bool:
    return bool(get_value(kwargs.get("stream")))


def get_server_address_and_port(
    client_instance: Any,
) -> tuple[str | None, int | None]:
    """Extract the server host/port from a writerai resource instance.

    writerai resource classes (``ChatResource``, ``CompletionsResource``) hold a
    ``_client`` whose ``base_url`` is an ``httpx.URL``.
    """
    base_client = getattr(client_instance, "_client", None)
    base_url = getattr(base_client, "base_url", None)
    if not base_url:
        return None, None

    address: str | None = getattr(base_url, "host", None)
    port: int | None = getattr(base_url, "port", None)
    if address is None:
        parsed = urlparse(str(base_url))
        address = parsed.hostname
        port = parsed.port

    if port == 443:
        port = None
    return address, port


def _writer_response_format_to_output_type(response_format_type: str) -> str:
    if response_format_type in ("json_object", "json_schema"):
        return GenAIAttributes.GenAiOutputTypeValues.JSON.value
    return response_format_type


def _is_text_part(content: Any) -> bool:
    return isinstance(content, str)


def _extract_tool_call_requests(
    tool_calls: Iterable[Any],
) -> list[ToolCallRequest]:
    parts: list[ToolCallRequest] = []
    for tool_call in tool_calls:
        call_id = get_property_value(tool_call, "id")

        func_name = ""
        arguments: Any = None
        func = get_property_value(tool_call, "function")
        if func:
            func_name = get_property_value(func, "name") or ""
            raw_arguments = get_property_value(func, "arguments")
            if isinstance(raw_arguments, str) and raw_arguments:
                try:
                    arguments = json.loads(raw_arguments)
                except json.JSONDecodeError:
                    arguments = raw_arguments
            elif raw_arguments is not None:
                arguments = raw_arguments

        parts.append(
            ToolCallRequest(id=call_id, name=func_name, arguments=arguments)
        )
    return parts


def _prepare_input_messages(messages: Iterable[Any]) -> List[InputMessage]:
    chat_messages: list[InputMessage] = []
    for message in messages:
        role = get_property_value(message, "role")
        chat_message = InputMessage(role=str(role), parts=[])
        chat_messages.append(chat_message)

        content = get_property_value(message, "content")

        if role == "assistant":
            tool_calls = get_property_value(message, "tool_calls")
            if tool_calls:
                chat_message.parts += _extract_tool_call_requests(tool_calls)
            if _is_text_part(content):
                chat_message.parts.append(Text(content=str(content)))
        elif role == "tool":
            tool_call_id = get_property_value(message, "tool_call_id")
            chat_message.parts.append(
                ToolCallResponse(id=tool_call_id, response=content)
            )
        else:
            # system, user, fallback
            if _is_text_part(content):
                chat_message.parts.append(Text(content=str(content)))
    return chat_messages


def _prepare_tool_definitions(
    tools: Iterable[Any] | None,
) -> list[ToolDefinition] | None:
    if not tools:
        return None

    definitions: list[ToolDefinition] = []
    for tool in tools:
        tool_type = get_property_value(tool, "type")
        # writerai tool ``type`` defaults to "function".
        if tool_type in (None, "function"):
            func = get_property_value(tool, "function")
            if func:
                definitions.append(
                    FunctionToolDefinition(
                        name=get_property_value(func, "name") or "",
                        description=get_property_value(func, "description"),
                        parameters=get_property_value(func, "parameters"),
                    )
                )
    return definitions


def _prepare_output_messages(choices: Iterable[Any]) -> List[OutputMessage]:
    output_messages: list[OutputMessage] = []
    for choice in choices:
        message = get_property_value(choice, "message")
        if message is None:
            continue
        parts: list[Any] = []
        tool_calls = get_property_value(message, "tool_calls")
        if tool_calls:
            parts += _extract_tool_call_requests(tool_calls)
        content = get_property_value(message, "content")
        if _is_text_part(content):
            parts.append(Text(content=str(content)))

        role = get_property_value(message, "role") or "assistant"
        output_messages.append(
            OutputMessage(
                finish_reason=get_property_value(choice, "finish_reason")
                or "error",
                role=str(role),
                parts=parts,
            )
        )
    return output_messages


def create_chat_invocation(
    handler: TelemetryHandler,
    kwargs: Mapping[str, Any],
    client_instance: Any,
    capture_content: bool,
) -> InferenceInvocation:
    address, port = get_server_address_and_port(client_instance)
    invocation = handler.start_inference(
        _WRITER_PROVIDER,
        request_model=kwargs.get("model", ""),
        server_address=address if address else None,
        server_port=port if port else None,
    )
    invocation.temperature = get_value(kwargs.get("temperature"))
    invocation.top_p = get_value(kwargs.get("top_p"))
    invocation.max_tokens = get_value(kwargs.get("max_tokens"))

    if (stop_sequences := get_value(kwargs.get("stop"))) is not None:
        if isinstance(stop_sequences, str):
            stop_sequences = [stop_sequences]
        invocation.stop_sequences = list(stop_sequences)

    if (choice_count := get_value(kwargs.get("n"))) is not None:
        if isinstance(choice_count, int) and choice_count != 1:
            invocation.attributes[
                GenAIAttributes.GEN_AI_REQUEST_CHOICE_COUNT
            ] = choice_count

    if (
        response_format := get_value(kwargs.get("response_format"))
    ) is not None:
        response_format_type = get_property_value(response_format, "type")
        if response_format_type is not None:
            invocation.attributes[GenAIAttributes.GEN_AI_OUTPUT_TYPE] = (
                _writer_response_format_to_output_type(response_format_type)
            )

    if capture_content:  # optimization
        invocation.input_messages = _prepare_input_messages(
            kwargs.get("messages", [])
        )
        invocation.tool_definitions = _prepare_tool_definitions(
            get_value(kwargs.get("tools"))
        )
    return invocation


def create_completion_invocation(
    handler: TelemetryHandler,
    kwargs: Mapping[str, Any],
    client_instance: Any,
    capture_content: bool,
) -> InferenceInvocation:
    """Create an inference invocation for the text ``completions.create`` API.

    The Writer text-completion endpoint accepts a plain ``prompt`` string and
    returns ``choices[].text`` without an ``id`` or ``usage``, so this maps the
    prompt to a single user input message and records fewer response fields.
    """
    address, port = get_server_address_and_port(client_instance)
    invocation = handler.start_inference(
        _WRITER_PROVIDER,
        request_model=kwargs.get("model", ""),
        server_address=address if address else None,
        server_port=port if port else None,
        operation_name=GenAIAttributes.GenAiOperationNameValues.TEXT_COMPLETION.value,
    )
    invocation.temperature = get_value(kwargs.get("temperature"))
    invocation.top_p = get_value(kwargs.get("top_p"))
    invocation.max_tokens = get_value(kwargs.get("max_tokens"))
    # writerai names the completions seed parameter ``random_seed``.
    invocation.seed = get_value(kwargs.get("random_seed"))

    if (stop_sequences := get_value(kwargs.get("stop"))) is not None:
        if isinstance(stop_sequences, str):
            stop_sequences = [stop_sequences]
        invocation.stop_sequences = list(stop_sequences)

    if capture_content:  # optimization
        prompt = get_value(kwargs.get("prompt"))
        if prompt is not None:
            if isinstance(prompt, str):
                prompts: list[str] = [prompt]
            elif isinstance(prompt, Iterable):
                prompts = [str(part) for part in prompt]
            else:
                prompts = [str(prompt)]
            invocation.input_messages = [
                InputMessage(role="user", parts=[Text(content=text)])
                for text in prompts
            ]
    return invocation


__all__ = [
    "_WRITER_PROVIDER",
    "create_chat_invocation",
    "create_completion_invocation",
    "get_server_address_and_port",
    "is_streaming",
]
