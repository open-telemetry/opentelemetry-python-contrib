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

import dataclasses
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
import logging
from os import environ
from typing import Any, List, Mapping, Optional, Union
from urllib.parse import urlparse

from httpx import URL
from openai import NOT_GIVEN

from opentelemetry._events import Event, EventLogger
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.trace import Span
from opentelemetry.trace.status import Status, StatusCode

OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = (
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
)
# TODO: reuse common code
OTEL_SEMCONV_STABILITY_OPT_IN = "OTEL_SEMCONV_STABILITY_OPT_IN"

logger = logging.getLogger(__name__)

class ContentCapturingMode(str, Enum):
    SPAN = "span"
    EVENT = "event"
    NONE = "none"
    
def get_content_mode(latest_experimental_enabled: bool) -> ContentCapturingMode:
    capture_content = environ.get(
        OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, "none"
    ).lower()

    if latest_experimental_enabled:
        try:
            return ContentCapturingMode(capture_content)
        except ValueError as ex:
            logger.warning("Error when parsing `%s` environment variable: {%s}", OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, str(ex))
            return ContentCapturingMode.NONE
     
    else:
        # back-compat
        return ContentCapturingMode.EVENT if capture_content == "true" else ContentCapturingMode.NONE


def is_latest_experimental_enabled() -> bool:
    stability_opt_in = environ.get(OTEL_SEMCONV_STABILITY_OPT_IN, None)

    return (
        stability_opt_in is not None
        and stability_opt_in.lower() == "gen_ai_latest_experimental"
    )


def extract_tool_calls_old(item, content_mode: ContentCapturingMode):
    tool_calls = get_property_value(item, "tool_calls")
    if tool_calls is None:
        return None

    calls = []
    for tool_call in tool_calls:
        tool_call_dict = {}
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
            if content_mode == ContentCapturingMode.EVENT and arguments:
                if isinstance(arguments, str):
                    arguments = arguments.replace("\n", "")
                tool_call_dict["function"]["arguments"] = arguments

        calls.append(tool_call_dict)
    return calls


def extract_tool_calls_new(tool_calls) -> list["ToolCallRequestPart"]:
    parts = []
    for tool_call in tool_calls:
        tool_call_part = ToolCallRequestPart()
        call_id = get_property_value(tool_call, "id")
        if call_id:
            tool_call_part.id = call_id

        func = get_property_value(tool_call, "function")
        if func:
            tool_call_part.function = {}
            name = get_property_value(func, "name")
            if name:
                tool_call_part.name = name

            arguments = get_property_value(func, "arguments")
            if arguments:
                try:
                    tool_call_part.arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    tool_call_part.arguments = arguments

        # TODO: support custom
        parts.append(tool_call_part)
    return parts


def set_server_address_and_port(client_instance, attributes):
    base_client = getattr(client_instance, "_client", None)
    base_url = getattr(base_client, "base_url", None)
    if not base_url:
        return

    port = -1
    if isinstance(base_url, URL):
        attributes[ServerAttributes.SERVER_ADDRESS] = base_url.host
        port = base_url.port
    elif isinstance(base_url, str):
        url = urlparse(base_url)
        attributes[ServerAttributes.SERVER_ADDRESS] = url.hostname
        port = url.port

    if port and port != 443 and port > 0:
        attributes[ServerAttributes.SERVER_PORT] = port


def get_property_value(obj, property_name):
    if isinstance(obj, dict):
        return obj.get(property_name, None)

    return getattr(obj, property_name, None)


def record_input_messages(
    messages,
    content_mode: ContentCapturingMode,
    latest_experimental_enabled: bool,
    span: Span,
    event_logger: EventLogger,
):
    if latest_experimental_enabled:
        if (content_mode == ContentCapturingMode.NONE or 
            (content_mode == ContentCapturingMode.SPAN and not span.is_recording())):
            return

        chat_messages = []
        for message in messages:
            role = get_property_value(message, "role")
            chat_message = ChatMessage(role=role, parts=[])
            chat_messages.append(chat_message)

            content = get_property_value(message, "content")

            if role == "assistant":
                tool_calls = get_property_value(message, "tool_calls")
                if tool_calls:
                    chat_message.parts += extract_tool_calls_new(tool_calls)
                if _is_text_part(content):
                    chat_message.parts.append(TextPart(content=content))

            elif role == "tool":
                tool_call_id = get_property_value(message, "tool_call_id")
                chat_message.parts.append(
                    ToolCallResponsePart(id=tool_call_id, response=content)
                )

            else:
                # system, developer, user, fallback
                if _is_text_part(content):
                    chat_message.parts.append(TextPart(content=content))
                    # continue?

        if span.is_recording() and content_mode == ContentCapturingMode.SPAN:
            span.set_attribute(
                "gen_ai.input.messages",
                json.dumps(
                    chat_messages, ensure_ascii=False, cls=DataclassEncoder
                ),
            )
        # TODO: events
    else:
        for message in messages:
            event_logger.emit(_message_to_event(message, content_mode))


def _is_text_part(content: Any) -> bool:
    return isinstance(content, str) or (
        isinstance(content, Iterable)
        and all(isinstance(part, str) for part in content)
    )


def record_output_messages(
    choices,
    content_mode: ContentCapturingMode,
    latest_experimental_enabled: bool,
    span: Span,
    event_logger: EventLogger,
):
    if latest_experimental_enabled:
        if (content_mode == ContentCapturingMode.NONE or 
           (content_mode == ContentCapturingMode.SPAN and not span.is_recording())):
            return

        output_messages = []
        for choice in choices:
            message = OutputMessage(
                finish_reason=choice.finish_reason or "error",
                role=(
                    choice.message.role
                    if choice.message and choice.message.role
                    else None
                ),
            )
            output_messages.append(message)

            if choice.message:
                tool_calls = get_property_value(choice.message, "tool_calls")
                if tool_calls:
                    message.parts += extract_tool_calls_new(tool_calls)
                content = get_property_value(choice.message, "content")
                if _is_text_part(content):
                    message.parts.append(TextPart(content=content))


        if span.is_recording() and content_mode == ContentCapturingMode.SPAN:
            span.set_attribute(
                "gen_ai.output.messages",
                json.dumps(
                    output_messages, ensure_ascii=False, cls=DataclassEncoder
                ),
            )
        # TODO: events
    else:
        for choice in choices:
            event_logger.emit(_choice_to_event(choice, content_mode))


def _message_to_event(message, content_mode: ContentCapturingMode):
    attributes = {
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value
    }
    role = get_property_value(message, "role")
    content = get_property_value(message, "content")

    body = {}
    if content_mode == ContentCapturingMode.EVENT and content:
        body["content"] = content
    if role == "assistant":
        tool_calls = extract_tool_calls_old(message, content_mode)
        if tool_calls:
            body = {"tool_calls": tool_calls}
    elif role == "tool":
        tool_call_id = get_property_value(message, "tool_call_id")
        if tool_call_id:
            body["id"] = tool_call_id

    return Event(
        name=f"gen_ai.{role}.message",
        attributes=attributes,
        body=body if body else None,
    )


def _choice_to_event(choice, content_mode: ContentCapturingMode):
    attributes = {
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value
    }

    body = {
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
        tool_calls = extract_tool_calls_old(choice.message, content_mode)
        if tool_calls:
            message["tool_calls"] = tool_calls
        content = get_property_value(choice.message, "content")
        if content_mode == ContentCapturingMode.EVENT and content:
            message["content"] = content
        body["message"] = message

    return Event(
        name="gen_ai.choice",
        attributes=attributes,
        body=body,
    )


def set_span_attributes(span, attributes: dict):
    for field, value in attributes.model_dump(by_alias=True).items():
        set_span_attribute(span, field, value)


def set_span_attribute(span, name, value):
    if non_numerical_value_is_set(value) is False:
        return

    span.set_attribute(name, value)


def is_streaming(kwargs):
    return non_numerical_value_is_set(kwargs.get("stream"))


def non_numerical_value_is_set(value: Optional[Union[bool, str]]):
    return bool(value) and value != NOT_GIVEN


def get_llm_request_attributes(
    kwargs, client_instance, operation_name, latest_experimental_enabled
):
    provider_name_attr_key = (
        "gen_ai.provider.name"
        if latest_experimental_enabled
        else GenAIAttributes.GEN_AI_SYSTEM
    )
    request_seed_attr_key = (
        "gen_ai.request.seed"
        if latest_experimental_enabled
        else GenAIAttributes.GEN_AI_OPENAI_REQUEST_SEED
    )
    attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: operation_name,
        provider_name_attr_key: GenAIAttributes.GenAiSystemValues.OPENAI.value,
        GenAIAttributes.GEN_AI_REQUEST_MODEL: kwargs.get("model"),
        GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE: kwargs.get("temperature"),
        GenAIAttributes.GEN_AI_REQUEST_TOP_P: kwargs.get("p")
        or kwargs.get("top_p"),
        GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS: kwargs.get("max_tokens"),
        GenAIAttributes.GEN_AI_REQUEST_PRESENCE_PENALTY: kwargs.get(
            "presence_penalty"
        ),
        GenAIAttributes.GEN_AI_REQUEST_FREQUENCY_PENALTY: kwargs.get(
            "frequency_penalty"
        ),
        request_seed_attr_key: kwargs.get("seed"),
    }

    output_type_attr_key = (
        "gen_ai.output.type"
        if latest_experimental_enabled
        else GenAIAttributes.GEN_AI_OPENAI_REQUEST_RESPONSE_FORMAT
    )
    if (response_format := kwargs.get("response_format")) is not None:
        # response_format may be string or object with a string in the `type` key
        if isinstance(response_format, Mapping):
            if (
                response_format_type := response_format.get("type")
            ) is not None:
                if response_format_type == "text":
                    attributes[output_type_attr_key] = (
                        "text"  # TODO there should be an enum in semconv package
                    )
                elif (
                    response_format_type == "json_schema"
                    or response_format_type == "json_object"
                ):
                    attributes[output_type_attr_key] = "json"
                else:
                    # should never happen with chat completion API
                    pass
        else:
            # should never happen with chat completion API
            attributes[output_type_attr_key] = response_format

    set_server_address_and_port(client_instance, attributes)

    service_tier_attribute_key = (
        "openai.request.service_tier"
        if latest_experimental_enabled
        else GenAIAttributes.GEN_AI_OPENAI_REQUEST_SERVICE_TIER
    )

    extra_body = kwargs.get("extra_body", None)
    if extra_body and isinstance(extra_body, dict):
        service_tier = extra_body.get("service_tier", None)
    else:
        service_tier = kwargs.get("service_tier", None)

    attributes[service_tier_attribute_key] = (
        service_tier if service_tier != "auto" else None
    )

    # filter out None values
    return {k: v for k, v in attributes.items() if v is not None}


def handle_span_exception(span, error):
    span.set_status(Status(StatusCode.ERROR, str(error)))
    if span.is_recording():
        span.set_attribute(
            ErrorAttributes.ERROR_TYPE, type(error).__qualname__
        )
    span.end()


@dataclass
class TextPart:
    type: str = "text"
    content: str = None


@dataclass
class ToolCallRequestPart:
    type: str = "tool_call"
    id: Optional[str] = None
    name: str = ""
    arguments: Any = None


@dataclass
class ToolCallResponsePart:
    type: str = "tool_call_response"
    id: Optional[str] = None
    response: Any = None


@dataclass
class GenericPart:
    type: str = ""


MessagePart = Union[
    TextPart,
    ToolCallRequestPart,
    ToolCallResponsePart,
    GenericPart,
]


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ChatMessage:
    role: Union[Role, str]
    parts: List[MessagePart] = field(default_factory=list)


@dataclass
class InputMessages:
    messages: List[ChatMessage] = field(default_factory=list)


class FinishReason(str, Enum):
    STOP = "stop"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"
    TOOL_CALL = "tool_call"
    ERROR = "error"


@dataclass
class OutputMessage(ChatMessage):
    finish_reason: Union[FinishReason, str] = ""


@dataclass
class OutputMessages:
    messages: List[OutputMessage] = field(default_factory=list)


class DataclassEncoder(json.JSONEncoder):
    def default(self, obj):
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        else:
            return super(DataclassEncoder, self).default(obj)
