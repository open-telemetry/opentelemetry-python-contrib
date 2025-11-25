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

from os import environ
from typing import Mapping
from urllib.parse import urlparse

from httpx import URL
from openai import NotGiven

from opentelemetry._logs import LogRecord
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.trace.status import Status, StatusCode

OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = (
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
)


def is_content_enabled() -> bool:
    capture_content = environ.get(
        OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, "false"
    )

    return capture_content.lower() == "true"


def extract_tool_calls(item, capture_content):
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
            if capture_content and arguments:
                if isinstance(arguments, str):
                    arguments = arguments.replace("\n", "")
                tool_call_dict["function"]["arguments"] = arguments

        calls.append(tool_call_dict)
    return calls


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


def message_to_event(message, capture_content):
    attributes = {
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value
    }
    role = get_property_value(message, "role")
    content = get_property_value(message, "content")

    body = {}
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


def choice_to_event(choice, capture_content):
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


def set_span_attributes(span, attributes: dict):
    for field, value in attributes.model_dump(by_alias=True).items():
        set_span_attribute(span, field, value)


def set_span_attribute(span, name, value):
    if non_numerical_value_is_set(value) is False:
        return

    span.set_attribute(name, value)


def is_streaming(kwargs):
    return non_numerical_value_is_set(kwargs.get("stream"))


def non_numerical_value_is_set(value: bool | str | NotGiven | None):
    return bool(value) and value_is_set(value)


def value_is_set(value):
    return value is not None and not isinstance(value, NotGiven)


def get_llm_request_attributes(
    kwargs,
    client_instance,
    operation_name=GenAIAttributes.GenAiOperationNameValues.CHAT.value,
):
    attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: operation_name,
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value,
        GenAIAttributes.GEN_AI_REQUEST_MODEL: kwargs.get("model"),
    }

    # Add chat-specific attributes only for chat operations
    if operation_name == GenAIAttributes.GenAiOperationNameValues.CHAT.value:
        attributes.update(
            {
                GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE: kwargs.get(
                    "temperature"
                ),
                GenAIAttributes.GEN_AI_REQUEST_TOP_P: kwargs.get("p")
                or kwargs.get("top_p"),
                GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS: kwargs.get(
                    "max_tokens"
                ),
                GenAIAttributes.GEN_AI_REQUEST_PRESENCE_PENALTY: kwargs.get(
                    "presence_penalty"
                ),
                GenAIAttributes.GEN_AI_REQUEST_FREQUENCY_PENALTY: kwargs.get(
                    "frequency_penalty"
                ),
                GenAIAttributes.GEN_AI_OPENAI_REQUEST_SEED: kwargs.get("seed"),
            }
        )

        if (response_format := kwargs.get("response_format")) is not None:
            # response_format may be string or object with a string in the `type` key
            if isinstance(response_format, Mapping):
                if (
                    response_format_type := response_format.get("type")
                ) is not None:
                    attributes[
                        GenAIAttributes.GEN_AI_OPENAI_REQUEST_RESPONSE_FORMAT
                    ] = response_format_type
            else:
                attributes[
                    GenAIAttributes.GEN_AI_OPENAI_REQUEST_RESPONSE_FORMAT
                ] = response_format

        # service_tier can be passed directly or in extra_body (in SDK 1.26.0 it's via extra_body)
        service_tier = kwargs.get("service_tier")
        if service_tier is None:
            extra_body = kwargs.get("extra_body")
            if isinstance(extra_body, Mapping):
                service_tier = extra_body.get("service_tier")
        attributes[GenAIAttributes.GEN_AI_OPENAI_REQUEST_SERVICE_TIER] = (
            service_tier if service_tier != "auto" else None
        )

    # Add embeddings-specific attributes
    elif (
        operation_name
        == GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value
    ):
        # Add embedding dimensions if specified
        if (dimensions := kwargs.get("dimensions")) is not None:
            attributes["gen_ai.embeddings.dimension.count"] = dimensions

        # Add encoding format if specified
        if "encoding_format" in kwargs:
            attributes["gen_ai.request.encoding_formats"] = [
                kwargs["encoding_format"]
            ]

    set_server_address_and_port(client_instance, attributes)

    # filter out values not set
    return {k: v for k, v in attributes.items() if value_is_set(v)}


def handle_span_exception(span, error):
    span.set_status(Status(StatusCode.ERROR, str(error)))
    if span.is_recording():
        span.set_attribute(
            ErrorAttributes.ERROR_TYPE, type(error).__qualname__
        )
    span.end()
