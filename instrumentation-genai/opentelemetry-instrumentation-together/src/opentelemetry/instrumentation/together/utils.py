# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from os import environ
from typing import Any, Iterable, List, Mapping

import together
from httpx import URL

from opentelemetry._logs import LogRecord
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.semconv.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
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

# There is no ``together`` value in the semconv GenAI provider/system enums
# (``GenAiProviderNameValues`` / ``GenAiSystemValues``), so we use this literal.
# See https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai
GEN_AI_PROVIDER_TOGETHER = "together"

# ``NotGiven``/``Omit`` are sentinel "unset" types in newer ``together`` SDKs;
# older releases use ``None`` and do not export them, so resolve defensively.
_TogetherOmit = getattr(together, "Omit", None)
_TogetherNotGiven = getattr(together, "NotGiven", None)


def is_content_enabled() -> bool:
    capture_content = environ.get(
        OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, "false"
    )

    return capture_content.lower() == "true"


def extract_tool_calls(item: Any, capture_content: bool) -> list | None:
    tool_calls = get_property_value(item, "tool_calls")
    if tool_calls is None:
        return None

    calls = []
    for tool_call in tool_calls:
        tool_call_dict: dict[str, Any] = {}
        call_id = get_property_value(tool_call, "id")
        if call_id:
            tool_call_dict["id"] = call_id

        tool_type = get_property_value(tool_call, "type")
        if tool_type:
            tool_call_dict["type"] = tool_type

        func = get_property_value(tool_call, "function")
        if func:
            tool_call_dict["function"] = {}

            name = get_property_value(func, "name")
            if name:
                tool_call_dict["function"]["name"] = name

            arguments = get_property_value(func, "arguments")
            if capture_content and arguments:
                if isinstance(arguments, str):
                    arguments = arguments.replace("\n", "")
                tool_call_dict["function"]["arguments"] = arguments

        calls.append(tool_call_dict)
    return calls


def get_server_address_and_port(
    client_instance: Any,
) -> tuple[str | None, int | None]:
    base_client = getattr(client_instance, "_client", None)
    base_url = getattr(base_client, "base_url", None)
    if not base_url:
        return None, None
    address = None
    port = None
    if isinstance(base_url, URL):
        address = base_url.host
        port = base_url.port
    elif isinstance(base_url, str):
        from urllib.parse import urlparse  # noqa: PLC0415

        url = urlparse(base_url)
        address = url.hostname
        port = url.port

    if port == 443:
        port = None

    return address, port


def get_property_value(obj: Any, property_name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(property_name, None)

    return getattr(obj, property_name, None)


def message_to_event(message: Any, capture_content: bool) -> LogRecord:
    attributes = {
        GenAIAttributes.GEN_AI_SYSTEM: GEN_AI_PROVIDER_TOGETHER
    }
    role = get_property_value(message, "role")
    content = get_property_value(message, "content")

    body: dict[str, Any] = {}
    if capture_content and content:
        body["content"] = content
    if role == "assistant":
        tool_calls = extract_tool_calls(message, capture_content)
        if tool_calls:
            body = {"tool_calls": tool_calls}
    elif role == "tool":
        tool_call_id = get_property_value(message, "tool_call_id")
        if tool_call_id:
            body["id"] = tool_call_id

    return LogRecord(
        event_name=f"gen_ai.{role}.message",
        attributes=attributes,
        body=body if body else None,
    )


def choice_to_event(choice: Any, capture_content: bool) -> LogRecord:
    attributes = {
        GenAIAttributes.GEN_AI_SYSTEM: GEN_AI_PROVIDER_TOGETHER
    }

    body: dict[str, Any] = {
        "index": choice.index,
        "finish_reason": choice.finish_reason or "error",
    }

    if choice.message:
        message = {
            "role": (
                choice.message.role
                if choice.message and choice.message.role
                else None
            )
        }
        tool_calls = extract_tool_calls(choice.message, capture_content)
        if tool_calls:
            message["tool_calls"] = tool_calls
        content = get_property_value(choice.message, "content")
        if capture_content and content:
            message["content"] = content
        body["message"] = message

    return LogRecord(
        event_name="gen_ai.choice",
        attributes=attributes,
        body=body,
    )


def set_span_attribute(span: Any, name: str, value: Any) -> None:
    if non_numerical_value_is_set(value) is False:
        return

    span.set_attribute(name, value)


def is_streaming(kwargs: Mapping[str, Any]) -> bool:
    return non_numerical_value_is_set(kwargs.get("stream"))


def non_numerical_value_is_set(value: Any) -> bool:
    return bool(value) and value_is_set(value)


def value_is_set(value: Any) -> bool:
    if _TogetherOmit is not None and isinstance(value, _TogetherOmit):
        return False
    if _TogetherNotGiven is not None and isinstance(value, _TogetherNotGiven):
        return False
    return value is not None


def _response_format_to_output_type(response_format_type: str) -> str:
    if response_format_type in ("json_object", "json_schema"):
        return GenAIAttributes.GenAiOutputTypeValues.JSON.value
    return response_format_type


def get_llm_request_attributes(
    kwargs: Mapping[str, Any],
    client_instance: Any,
    latest_experimental_enabled: bool,
    operation_name: str = GenAIAttributes.GenAiOperationNameValues.CHAT.value,
) -> dict[str, Any]:
    # pylint: disable=too-many-branches

    attributes: dict[str, Any] = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: operation_name,
    }

    model = kwargs.get("model")
    if model:
        attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] = model

    if latest_experimental_enabled:
        attributes[GenAIAttributes.GEN_AI_PROVIDER_NAME] = (
            GEN_AI_PROVIDER_TOGETHER
        )
    else:
        attributes[GenAIAttributes.GEN_AI_SYSTEM] = GEN_AI_PROVIDER_TOGETHER

    if operation_name == GenAIAttributes.GenAiOperationNameValues.CHAT.value:
        attributes.update(
            {
                GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE: kwargs.get(
                    "temperature"
                ),
                GenAIAttributes.GEN_AI_REQUEST_TOP_P: kwargs.get("top_p"),
                GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS: kwargs.get(
                    "max_tokens"
                ),
                GenAIAttributes.GEN_AI_REQUEST_PRESENCE_PENALTY: kwargs.get(
                    "presence_penalty"
                ),
                GenAIAttributes.GEN_AI_REQUEST_FREQUENCY_PENALTY: kwargs.get(
                    "frequency_penalty"
                ),
                GenAIAttributes.GEN_AI_REQUEST_SEED: kwargs.get("seed"),
            }
        )

        if (choice_count := kwargs.get("n")) is not None:
            if isinstance(choice_count, int) and choice_count != 1:
                attributes[GenAIAttributes.GEN_AI_REQUEST_CHOICE_COUNT] = (
                    choice_count
                )

        if (stop_sequences := kwargs.get("stop")) is not None:
            if isinstance(stop_sequences, str):
                stop_sequences = [stop_sequences]
            attributes[GenAIAttributes.GEN_AI_REQUEST_STOP_SEQUENCES] = (
                stop_sequences
            )

        if latest_experimental_enabled and (
            response_format := kwargs.get("response_format")
        ) is not None:
            if isinstance(response_format, Mapping):
                if (
                    response_format_type := response_format.get("type")
                ) is not None:
                    attributes[GenAIAttributes.GEN_AI_OUTPUT_TYPE] = (
                        _response_format_to_output_type(response_format_type)
                    )
            elif isinstance(response_format, str):
                attributes[GenAIAttributes.GEN_AI_OUTPUT_TYPE] = (
                    _response_format_to_output_type(response_format)
                )

    address, port = get_server_address_and_port(client_instance)
    if address:
        attributes[ServerAttributes.SERVER_ADDRESS] = address
    if port:
        attributes[ServerAttributes.SERVER_PORT] = port

    # filter out values not set
    return {k: v for k, v in attributes.items() if value_is_set(v)}


def create_chat_invocation(
    handler: TelemetryHandler,
    kwargs: Mapping[str, Any],
    client_instance: Any,
    capture_content: bool,
) -> InferenceInvocation:
    address, port = get_server_address_and_port(client_instance)
    invocation = handler.start_inference(
        GEN_AI_PROVIDER_TOGETHER,
        request_model=kwargs.get("model", ""),
        server_address=address if address else None,
        server_port=port if port else None,
    )
    invocation.temperature = get_value(kwargs.get("temperature"))
    invocation.top_p = get_value(kwargs.get("top_p"))
    invocation.max_tokens = get_value(kwargs.get("max_tokens"))
    invocation.presence_penalty = get_value(kwargs.get("presence_penalty"))
    invocation.frequency_penalty = get_value(kwargs.get("frequency_penalty"))
    invocation.seed = get_value(kwargs.get("seed"))
    if (stop_sequences := get_value(kwargs.get("stop"))) is not None:
        if isinstance(stop_sequences, str):
            stop_sequences = [stop_sequences]
        invocation.stop_sequences = stop_sequences

    if (choice_count := get_value(kwargs.get("n"))) is not None:
        if isinstance(choice_count, int) and choice_count != 1:
            invocation.attributes[
                GenAIAttributes.GEN_AI_REQUEST_CHOICE_COUNT
            ] = choice_count

    if (
        response_format := get_value(kwargs.get("response_format"))
    ) is not None:
        if isinstance(response_format, Mapping):
            if (
                response_format_type := get_value(response_format.get("type"))
            ) is not None:
                invocation.attributes[GenAIAttributes.GEN_AI_OUTPUT_TYPE] = (
                    _response_format_to_output_type(response_format_type)
                )
        elif isinstance(response_format, str):
            invocation.attributes[GenAIAttributes.GEN_AI_OUTPUT_TYPE] = (
                _response_format_to_output_type(response_format)
            )

    if capture_content:  # optimization
        invocation.input_messages = _prepare_input_messages(
            kwargs.get("messages", [])
        )
        invocation.tool_definitions = _prepare_tool_definitions(
            kwargs.get("tools")
        )
    return invocation


def get_value(v: Any) -> Any:
    if value_is_set(v):
        return v
    return None


def handle_span_exception(span: Any, error: BaseException) -> None:
    span.set_status(Status(StatusCode.ERROR, str(error)))
    if span.is_recording():
        span.set_attribute(
            ErrorAttributes.ERROR_TYPE, type(error).__qualname__
        )
    span.end()


def _is_text_part(content: Any) -> bool:
    return isinstance(content, str) or (
        isinstance(content, Iterable)
        and all(isinstance(part, str) for part in content)
    )


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
                chat_message.parts += extract_tool_calls_new(tool_calls)
            if _is_text_part(content):
                chat_message.parts.append(Text(content=str(content)))

        elif role == "tool":
            tool_call_id = get_property_value(message, "tool_call_id")
            chat_message.parts.append(
                ToolCallResponse(id=tool_call_id, response=content)
            )

        else:
            # system, developer, user, fallback
            if _is_text_part(content):
                chat_message.parts.append(Text(content=str(content)))
    return chat_messages


def extract_tool_calls_new(tool_calls: Iterable[Any]) -> list[ToolCallRequest]:
    parts: list[ToolCallRequest] = []
    for tool_call in tool_calls:
        call_id = get_property_value(tool_call, "id")

        func_name = ""
        arguments = None
        func = get_property_value(tool_call, "function")
        if func:
            func_name = get_property_value(func, "name") or ""
            arguments_str = get_property_value(func, "arguments")
            if arguments_str:
                try:
                    arguments = json.loads(arguments_str)
                except json.JSONDecodeError:
                    arguments = arguments_str

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
        if tool_type == "function":
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
        if choice.message:
            parts: list[Any] = []
            tool_calls = get_property_value(choice.message, "tool_calls")
            if tool_calls:
                parts += extract_tool_calls_new(tool_calls)
            content = get_property_value(choice.message, "content")
            if _is_text_part(content):
                parts.append(Text(content=str(content)))

            message = OutputMessage(
                finish_reason=choice.finish_reason or "error",
                role=(
                    choice.message.role
                    if choice.message and choice.message.role
                    else ""
                ),
                parts=parts,
            )
            output_messages.append(message)

    return output_messages
