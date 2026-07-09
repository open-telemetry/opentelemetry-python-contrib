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
from opentelemetry.util.genai.invocation import (
    EmbeddingInvocation,
    InferenceInvocation,
)
from opentelemetry.util.genai.types import (
    FunctionToolDefinition,
    InputMessage,
    OutputMessage,
    Text,
    ToolCallRequest,
    ToolCallResponse,
    ToolDefinition,
)

# ``mistral_ai`` is a well-known value in ``GenAiProviderNameValues`` /
# ``GenAiSystemValues`` in the semconv package, so the generated enum member is
# used instead of a raw string literal.
_MISTRAL_AI_PROVIDER = GenAIAttributes.GenAiProviderNameValues.MISTRAL_AI.value

# mistralai uses an ``UNSET`` sentinel for optional-nullable fields. Values that
# equal the sentinel should be treated as "not provided".
try:
    from mistralai.types import UNSET as _MISTRAL_UNSET
except Exception:  # pragma: no cover - defensive import
    _MISTRAL_UNSET = None


def value_is_set(value: Any) -> bool:
    if _MISTRAL_UNSET is not None and value is _MISTRAL_UNSET:
        return False
    return value is not None


def get_value(value: Any) -> Any:
    if value_is_set(value):
        return value
    return None


def get_property_value(obj: Any, property_name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(property_name, None)
    return getattr(obj, property_name, None)


def is_streaming(method_name: str) -> bool:
    """Return True for the streaming chat entry points (``stream`` /
    ``stream_async``)."""
    return method_name in ("stream", "stream_async")


def get_server_address_and_port(
    client_instance: Any,
) -> tuple[str | None, int | None]:
    """Extract the server host/port from a mistralai resource instance.

    mistralai resource classes (``Chat``, ``Embeddings``) hold an
    ``sdk_configuration`` whose ``get_server_details()`` returns the base URL.
    """
    sdk_configuration = getattr(client_instance, "sdk_configuration", None)
    if sdk_configuration is None:
        return None, None

    base_url: str | None = None
    get_server_details = getattr(
        sdk_configuration, "get_server_details", None
    )
    if callable(get_server_details):
        try:
            base_url = get_server_details()[0]
        except Exception:  # pragma: no cover - defensive
            base_url = None
    if not base_url:
        base_url = getattr(sdk_configuration, "server_url", None) or None
    if not base_url:
        return None, None

    parsed = urlparse(base_url)
    address = parsed.hostname
    port = parsed.port
    if port == 443:
        port = None
    return address, port


def _mistral_response_format_to_output_type(response_format_type: str) -> str:
    if response_format_type in ("json_object", "json_schema"):
        return GenAIAttributes.GenAiOutputTypeValues.JSON.value
    return response_format_type


def _text_from_content(content: Any) -> str | None:
    """mistralai message content may be a plain string or a list of content
    chunks. Return the text representation when available."""
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, Iterable):
        texts: list[str] = []
        for part in content:
            text = get_property_value(part, "text")
            if isinstance(text, str):
                texts.append(text)
        if texts:
            return "".join(texts)
    return None


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
            text = _text_from_content(content)
            if text is not None:
                chat_message.parts.append(Text(content=text))
        elif role == "tool":
            tool_call_id = get_property_value(message, "tool_call_id")
            chat_message.parts.append(
                ToolCallResponse(id=tool_call_id, response=content)
            )
        else:
            # system, user, fallback
            text = _text_from_content(content)
            if text is not None:
                chat_message.parts.append(Text(content=text))
    return chat_messages


def _prepare_tool_definitions(
    tools: Iterable[Any] | None,
) -> list[ToolDefinition] | None:
    if not tools:
        return None

    definitions: list[ToolDefinition] = []
    for tool in tools:
        tool_type = get_property_value(tool, "type")
        # mistralai tool ``type`` defaults to "function" and may be omitted.
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
        text = _text_from_content(get_property_value(message, "content"))
        if text is not None:
            parts.append(Text(content=text))

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
        _MISTRAL_AI_PROVIDER,
        request_model=kwargs.get("model", ""),
        server_address=address if address else None,
        server_port=port if port else None,
    )
    invocation.temperature = get_value(kwargs.get("temperature"))
    invocation.top_p = get_value(kwargs.get("top_p"))
    invocation.max_tokens = get_value(kwargs.get("max_tokens"))
    invocation.presence_penalty = get_value(kwargs.get("presence_penalty"))
    invocation.frequency_penalty = get_value(kwargs.get("frequency_penalty"))
    # mistralai names the seed parameter ``random_seed``.
    invocation.seed = get_value(kwargs.get("random_seed"))

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
                _mistral_response_format_to_output_type(response_format_type)
            )

    if capture_content:  # optimization
        invocation.input_messages = _prepare_input_messages(
            kwargs.get("messages", [])
        )
        invocation.tool_definitions = _prepare_tool_definitions(
            get_value(kwargs.get("tools"))
        )
    return invocation


def create_embedding_invocation(
    handler: TelemetryHandler,
    kwargs: Mapping[str, Any],
    client_instance: Any,
) -> EmbeddingInvocation:
    address, port = get_server_address_and_port(client_instance)
    invocation = handler.start_embedding(
        _MISTRAL_AI_PROVIDER,
        request_model=kwargs.get("model", ""),
        server_address=address if address else None,
        server_port=port if port else None,
    )
    if (encoding_format := get_value(kwargs.get("encoding_format"))) is not None:
        if isinstance(encoding_format, str):
            encoding_format = [encoding_format]
        invocation.encoding_formats = list(encoding_format)
    if (
        output_dimension := get_value(kwargs.get("output_dimension"))
    ) is not None:
        invocation.dimension_count = output_dimension
    return invocation


__all__ = [
    "_MISTRAL_AI_PROVIDER",
    "create_chat_invocation",
    "create_embedding_invocation",
    "get_server_address_and_port",
    "is_streaming",
]
