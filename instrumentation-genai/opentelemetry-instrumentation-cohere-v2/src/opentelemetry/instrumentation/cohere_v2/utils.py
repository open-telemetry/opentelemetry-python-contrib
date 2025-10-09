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
import cohere

from typing import List, Optional, Union
from urllib.parse import urlparse

from opentelemetry._events import Event, EventLogger
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.trace import Span


def extract_tool_calls(item: Union[cohere.types.ChatMessageV2, cohere.AssistantMessageResponse], capture_content: bool):
    tool_calls: Optional[List[cohere.ToolCallV2]] = get_property_value(item, "tool_calls")
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


def get_property_value(obj, property_name):
    if isinstance(obj, dict):
        return obj.get(property_name, None)

    return getattr(obj, property_name, None)


def set_server_address_and_port(client_instance: cohere.client_v2.V2Client, attributes):
    base_client = getattr(client_instance, "_client_wrapper", None)
    base_url = getattr(base_client, "_base_url", None)
    if not base_url:
        return

    port = -1
    url = urlparse(base_url)
    attributes[ServerAttributes.SERVER_ADDRESS] = url.hostname
    port = url.port

    if port and port != 443 and port > 0:
        attributes[ServerAttributes.SERVER_PORT] = port


def get_genai_request_attributes(
    kwargs,
    client_instance: cohere.client_v2.V2Client,
    operation_name=GenAIAttributes.GenAiOperationNameValues.CHAT.value,
):
    attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: operation_name,
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.COHERE.value,
        GenAIAttributes.GEN_AI_REQUEST_MODEL: kwargs.get("model"),
        GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS: kwargs.get("max_tokens"),
        GenAIAttributes.GEN_AI_REQUEST_STOP_SEQUENCES: kwargs.get(
            "stop_sequences"
        ),
        GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE: kwargs.get("temperature"),
        # TODO: Add to sem conv
        "gen_ai.cohere.request.seed": kwargs.get("seed"),
        GenAIAttributes.GEN_AI_REQUEST_PRESENCE_PENALTY: kwargs.get(
            "presence_penalty"
        ),
        GenAIAttributes.GEN_AI_REQUEST_FREQUENCY_PENALTY: kwargs.get(
            "frequency_penalty"
        ),
        GenAIAttributes.GEN_AI_REQUEST_TOP_K: kwargs.get("k"),
        GenAIAttributes.GEN_AI_REQUEST_TOP_P: kwargs.get("p"),
    }
    response_format = kwargs.get("response_format")
    if response_format:
        # TODO: Add to sem conv
        attributes["gen_ai.cohere.request.response_format"] = response_format.type

    set_server_address_and_port(client_instance, attributes)

    # filter out None values
    return {k: v for k, v in attributes.items() if v is not None}


def message_to_event(message: cohere.types.ChatMessageV2, capture_content: bool) -> Event:
    attributes = {
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.COHERE.value
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

    return Event(
        name=f"gen_ai.{role}.message",
        attributes=attributes,
        body=body if body else None,
    )


def set_response_attributes(
    span: Span, result: cohere.ChatResponse, event_logger: EventLogger, capture_content: bool
):
    event_logger.emit(_response_to_event(result, capture_content))

    span.set_attribute(
        GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS,
        [result.finish_reason],
    )

    if getattr(result, "id", None):
        span.set_attribute(GenAIAttributes.GEN_AI_RESPONSE_ID, result.id)

    # Get the usage
    if getattr(result, "usage", None):
        if getattr(result.usage, "tokens"):
            span.set_attribute(
                GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
                result.usage.tokens.input_tokens,
            )
            span.set_attribute(
                GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS,
                result.usage.tokens.output_tokens,
            )


def _response_to_event(response: cohere.ChatResponse, capture_content):
    attributes = {
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.COHERE.value
    }

    body = {
        "id": response.id,
        "finish_reason": response.finish_reason or "error",
    }

    if response.message:
        message = {}
        if response.message.role and response.message.role != "assistant":
            message["role"] = response.message.role
        tool_calls = extract_tool_calls(response.message, capture_content)
        if tool_calls:
            message["tool_calls"] = tool_calls
        content: List[cohere.AssistantMessageResponseContentItem] = get_property_value(response.message, "content")
        if capture_content and content:
            message["content"] = content
        body["message"] = message

    return Event(
        name="gen_ai.choice",
        attributes=attributes,
        body=body,
    )