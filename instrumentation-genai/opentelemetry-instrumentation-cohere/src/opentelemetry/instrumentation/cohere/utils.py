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

# Cohere is covered by the well-known value ``cohere`` in
# ``GenAiProviderNameValues``. There is no cohere-specific ``gen_ai.system`` /
# ``gen_ai.provider.name`` attribute module in semconv (unlike
# ``openai_attributes``).
_COHERE_PROVIDER = GenAIAttributes.GenAiProviderNameValues.COHERE.value


def get_property_value(obj: Any, property_name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(property_name, None)
    return getattr(obj, property_name, None)


def get_server_address_and_port(
    client_instance: Any,
) -> tuple[str | None, int | None]:
    """Derive server address/port from a Cohere client's base URL.

    Cohere v5+ clients expose their base URL through
    ``client._client_wrapper.get_base_url()``.
    """
    client_wrapper = getattr(client_instance, "_client_wrapper", None)
    base_url: str | None = None
    if client_wrapper is not None:
        getter = getattr(client_wrapper, "get_base_url", None)
        if callable(getter):
            try:
                base_url = getter()
            except Exception:  # pylint: disable=broad-exception-caught
                base_url = None
        if base_url is None:
            base_url = getattr(client_wrapper, "_base_url", None)

    if not base_url or not isinstance(base_url, str):
        return None, None

    parsed = urlparse(base_url)
    address = parsed.hostname
    port = parsed.port
    if port == 443:
        port = None
    return address, port


def _get_request_model(kwargs: Mapping[str, Any]) -> str:
    model = kwargs.get("model")
    return model if isinstance(model, str) else ""


def _stop_sequences(kwargs: Mapping[str, Any]) -> list[str] | None:
    stop_sequences = kwargs.get("stop_sequences")
    if stop_sequences is None:
        return None
    if isinstance(stop_sequences, str):
        return [stop_sequences]
    if isinstance(stop_sequences, Iterable):
        return [str(item) for item in stop_sequences]
    return None


def create_chat_invocation(
    handler: TelemetryHandler,
    kwargs: Mapping[str, Any],
    client_instance: Any,
    capture_content: bool,
) -> InferenceInvocation:
    address, port = get_server_address_and_port(client_instance)
    invocation = handler.start_inference(
        _COHERE_PROVIDER,
        request_model=_get_request_model(kwargs),
        server_address=address if address else None,
        server_port=port if port else None,
    )
    invocation.temperature = kwargs.get("temperature")
    # Cohere uses ``p`` for nucleus sampling in both V1 and V2.
    invocation.top_p = kwargs.get("p", kwargs.get("top_p"))
    invocation.max_tokens = kwargs.get("max_tokens")
    invocation.presence_penalty = kwargs.get("presence_penalty")
    invocation.frequency_penalty = kwargs.get("frequency_penalty")
    invocation.seed = kwargs.get("seed")

    stop_sequences = _stop_sequences(kwargs)
    if stop_sequences is not None:
        invocation.stop_sequences = stop_sequences

    if capture_content:  # optimization
        invocation.input_messages = _prepare_input_messages(kwargs)
        invocation.tool_definitions = _prepare_tool_definitions(
            kwargs.get("tools")
        )
    return invocation


def create_embedding_invocation(
    handler: TelemetryHandler,
    kwargs: Mapping[str, Any],
    client_instance: Any,
) -> EmbeddingInvocation:
    address, port = get_server_address_and_port(client_instance)
    invocation = handler.start_embedding(
        _COHERE_PROVIDER,
        request_model=_get_request_model(kwargs),
        server_address=address if address else None,
        server_port=port if port else None,
    )
    encoding_formats = kwargs.get("embedding_types")
    if encoding_formats is not None:
        if isinstance(encoding_formats, str):
            encoding_formats = [encoding_formats]
        elif isinstance(encoding_formats, Iterable):
            encoding_formats = [str(fmt) for fmt in encoding_formats]
        invocation.encoding_formats = encoding_formats
    return invocation


def _is_text_part(content: Any) -> bool:
    return isinstance(content, str)


def _content_to_text(content: Any) -> str | None:
    """Normalize Cohere message content (str or list of parts) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, Iterable):
        parts: list[str] = []
        for item in content:
            item_type = get_property_value(item, "type")
            text = get_property_value(item, "text")
            if item_type in (None, "text") and isinstance(text, str):
                parts.append(text)
        if parts:
            return "".join(parts)
    return None


def _prepare_input_messages(
    kwargs: Mapping[str, Any],
) -> List[InputMessage]:
    chat_messages: list[InputMessage] = []

    # Cohere V2 uses an OpenAI-style ``messages`` list.
    messages = kwargs.get("messages")
    if messages:
        for message in messages:
            role = get_property_value(message, "role")
            parts: list[Any] = []
            content = get_property_value(message, "content")

            if role == "assistant":
                tool_calls = get_property_value(message, "tool_calls")
                if tool_calls:
                    parts += _extract_tool_calls(tool_calls)
                text = _content_to_text(content)
                if text is not None:
                    parts.append(Text(content=text))
            elif role == "tool":
                tool_call_id = get_property_value(message, "tool_call_id")
                parts.append(
                    ToolCallResponse(id=tool_call_id, response=content)
                )
            else:
                text = _content_to_text(content)
                if text is not None:
                    parts.append(Text(content=text))

            chat_messages.append(InputMessage(role=str(role), parts=parts))
        return chat_messages

    # Cohere V1 uses ``preamble`` (system) + ``message`` (single user turn),
    # optionally preceded by a ``chat_history`` list.
    preamble = kwargs.get("preamble")
    if _is_text_part(preamble):
        chat_messages.append(
            InputMessage(role="system", parts=[Text(content=str(preamble))])
        )

    for history_message in kwargs.get("chat_history", []) or []:
        role = get_property_value(history_message, "role")
        text = _content_to_text(get_property_value(history_message, "message"))
        parts = [Text(content=text)] if text is not None else []
        chat_messages.append(
            InputMessage(role=str(role).lower() or "user", parts=parts)
        )

    message = kwargs.get("message")
    if _is_text_part(message):
        chat_messages.append(
            InputMessage(role="user", parts=[Text(content=str(message))])
        )
    return chat_messages


def _extract_tool_calls(
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
            arguments_raw = get_property_value(func, "arguments")
            if isinstance(arguments_raw, str) and arguments_raw:
                try:
                    arguments = json.loads(arguments_raw)
                except json.JSONDecodeError:
                    arguments = arguments_raw
            elif arguments_raw is not None:
                arguments = arguments_raw
        parts.append(
            ToolCallRequest(id=call_id, name=func_name, arguments=arguments)
        )
    return parts


def _prepare_tool_definitions(
    tools: Iterable[Any] | None,
) -> list[ToolDefinition] | None:
    if not tools:
        return None
    definitions: list[ToolDefinition] = []
    for tool in tools:
        tool_type = get_property_value(tool, "type")
        func = get_property_value(tool, "function")
        if tool_type in (None, "function") and func:
            definitions.append(
                FunctionToolDefinition(
                    name=get_property_value(func, "name") or "",
                    description=get_property_value(func, "description"),
                    parameters=get_property_value(func, "parameters"),
                )
            )
    return definitions


def _billed_units_tokens(usage: Any) -> tuple[int | None, int | None]:
    """Return (input_tokens, output_tokens) from a Cohere usage/meta object.

    Cohere reports billed token counts as floats under
    ``usage.billed_units`` (V2) or ``meta.billed_units`` (V1).
    """
    billed_units = get_property_value(usage, "billed_units")
    if billed_units is None:
        return None, None
    input_tokens = get_property_value(billed_units, "input_tokens")
    output_tokens = get_property_value(billed_units, "output_tokens")
    return (
        int(input_tokens) if input_tokens is not None else None,
        int(output_tokens) if output_tokens is not None else None,
    )


def _output_text_from_message(message: Any) -> str | None:
    """Extract assistant text from a V2 ``AssistantMessageResponse``."""
    content = get_property_value(message, "content")
    if content is None:
        return None
    return _content_to_text(content)


def prepare_output_messages_v2(response: Any) -> List[OutputMessage]:
    message = get_property_value(response, "message")
    finish_reason = get_property_value(response, "finish_reason") or "error"
    parts: list[Any] = []
    if message is not None:
        tool_calls = get_property_value(message, "tool_calls")
        if tool_calls:
            parts += _extract_tool_calls(tool_calls)
        text = _output_text_from_message(message)
        if text is not None:
            parts.append(Text(content=text))
    return [
        OutputMessage(
            role="assistant",
            finish_reason=str(finish_reason),
            parts=parts,
        )
    ]


def prepare_output_messages_v1(response: Any) -> List[OutputMessage]:
    text = get_property_value(response, "text")
    finish_reason = get_property_value(response, "finish_reason") or "error"
    parts: list[Any] = []
    if isinstance(text, str):
        parts.append(Text(content=text))
    return [
        OutputMessage(
            role="assistant",
            finish_reason=str(finish_reason),
            parts=parts,
        )
    ]
