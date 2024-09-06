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

import json
import logging
from typing import Optional, Union
from openai import NOT_GIVEN
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)

from opentelemetry.trace import Span


def silently_fail(func):
    """
    A decorator that catches exceptions thrown by the decorated function and logs them as warnings.
    """

    logger = logging.getLogger(func.__module__)

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exception:
            logger.warning(
                "Failed to execute %s, error: %s",
                func.__name__,
                str(exception),
            )

    return wrapper


def extract_content(choice):
    if getattr(choice, "message", None) is None:
        return ""

    # Check if choice.message exists and has a content attribute
    message = choice.message
    if getattr(message, "content", None):
        return choice.message.content

    # Check if choice.message has tool_calls and extract information accordingly
    elif getattr(message, "tool_calls", None):
        result = [
            {
                "id": tool_call.id,
                "type": tool_call.type,
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                },
            }
            for tool_call in choice.message.tool_calls
        ]
        return result

    # Check if choice.message has a function_call and extract information accordingly
    elif getattr(message, "function_call", None):
        return {
            "name": choice.message.function_call.name,
            "arguments": choice.message.function_call.arguments,
        }

    # Return an empty string if none of the above conditions are met
    else:
        return ""


def extract_tools_prompt(item):
    tool_calls = getattr(item, "tool_calls", None)
    if tool_calls is None:
        return

    calls = []
    for tool_call in tool_calls:
        tool_call_dict = {
            "id": getattr(tool_call, "id", ""),
            "type": getattr(tool_call, "type", ""),
        }

        if hasattr(tool_call, "function"):
            tool_call_dict["function"] = {
                "name": getattr(tool_call.function, "name", ""),
                "arguments": getattr(tool_call.function, "arguments", ""),
            }
        calls.append(tool_call_dict)
    return calls


def set_event_prompt(span: Span, prompt):
    span.add_event(
        name="gen_ai.content.prompt",
        attributes={
            GenAIAttributes.GEN_AI_PROMPT: prompt,
        },
    )


def set_span_attributes(span: Span, attributes: dict):
    for field, value in attributes.model_dump(by_alias=True).items():
        set_span_attribute(span, field, value)


def set_event_completion(span: Span, result_content):
    span.add_event(
        name="gen_ai.content.completion",
        attributes={
            GenAIAttributes.GEN_AI_COMPLETION: json.dumps(result_content),
        },
    )


def set_span_attribute(span: Span, name, value):
    if non_numerical_value_is_set(value) is False:
        return

    span.set_attribute(name, value)


def is_streaming(kwargs):
    return non_numerical_value_is_set(kwargs.get("stream"))


def non_numerical_value_is_set(value: Optional[Union[bool, str]]):
    return bool(value) and value != NOT_GIVEN


def get_llm_request_attributes(
    kwargs,
    model=None,
    operation_name=GenAIAttributes.GenAiOperationNameValues.CHAT.value,
):

    return {
        GenAIAttributes.GEN_AI_OPERATION_NAME: operation_name,
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value,
        GenAIAttributes.GEN_AI_REQUEST_MODEL: model or kwargs.get("model"),
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
    }
