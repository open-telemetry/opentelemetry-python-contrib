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

import asyncio
import functools
import json
import logging
import traceback
from os import environ
from typing import Any, Callable, Optional, TypeVar
from urllib.parse import urlparse

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
from opentelemetry.trace import Span
from opentelemetry.trace.status import Status, StatusCode

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# Environment variable for content capture
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = (
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
)

# Custom attribute names
LLM_REQUEST_STREAMING = "gen_ai.request.streaming"
LLM_USAGE_TOTAL_TOKENS = "llm.usage.total_tokens"
LLM_USAGE_CACHE_READ_INPUT_TOKENS = "gen_ai.usage.input_tokens_details.cached"
LLM_USAGE_CACHE_CREATION_INPUT_TOKENS = (
    "gen_ai.usage.cache_creation_input_tokens"
)
LLM_REQUEST_MESSAGES = "gen_ai.request.messages"
LLM_RESPONSE_CONTENT = "gen_ai.response.content"

# Anthropic system identifier
GEN_AI_SYSTEM_ANTHROPIC = "anthropic"


class Config:
    """Configuration for the Anthropic instrumentation."""

    exception_logger: Optional[Callable[[Exception], None]] = None


def is_content_enabled() -> bool:
    """Check if content capture is enabled via environment variable."""
    capture_content = environ.get(
        OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, "false"
    )
    return capture_content.lower() == "true"


def dont_throw(func: F) -> F:
    """Decorator that prevents exceptions from propagating.

    This ensures that instrumentation errors don't affect the application.
    Works for both synchronous and asynchronous functions.
    """
    func_logger = logging.getLogger(func.__module__)

    async def async_wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            _handle_exception(e, func, func_logger)

    def sync_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            _handle_exception(e, func, func_logger)

    def _handle_exception(e, func, func_logger):
        func_logger.debug(
            "Instrumentation failed in %s, error: %s",
            func.__name__,
            traceback.format_exc(),
        )
        if Config.exception_logger:
            Config.exception_logger(e)

    wrapper = (
        async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    )
    return functools.wraps(func)(wrapper)  # type: ignore[return-value]


def set_span_attribute(span: Span, name: str, value: Any) -> None:
    """Set a span attribute if the value is not None or empty."""
    if value is not None and value != "":
        span.set_attribute(name, value)


def get_property_value(obj: Any, property_name: str) -> Any:
    """Get a property value from an object or dict."""
    if isinstance(obj, dict):
        return obj.get(property_name, None)
    return getattr(obj, property_name, None)


def set_server_address_and_port(client_instance: Any, attributes: dict) -> None:
    """Extract and set server address and port from the client instance."""
    base_client = getattr(client_instance, "_client", None)
    base_url = getattr(base_client, "base_url", None)
    if not base_url:
        return

    port = -1
    if hasattr(base_url, "host"):
        # httpx URL object
        attributes[ServerAttributes.SERVER_ADDRESS] = base_url.host
        port = base_url.port
    elif isinstance(base_url, str):
        url = urlparse(base_url)
        attributes[ServerAttributes.SERVER_ADDRESS] = url.hostname
        port = url.port

    if port and port != 443 and port > 0:
        attributes[ServerAttributes.SERVER_PORT] = port


def extract_tool_calls(message: Any, capture_content: bool) -> Optional[list]:
    """Extract tool calls from a message."""
    content = get_property_value(message, "content")
    if not content or not isinstance(content, list):
        return None

    tool_calls = []
    for block in content:
        block_type = get_property_value(block, "type")
        if block_type == "tool_use":
            tool_call = {
                "id": get_property_value(block, "id"),
                "type": "function",
                "function": {
                    "name": get_property_value(block, "name"),
                },
            }
            if capture_content:
                input_data = get_property_value(block, "input")
                if input_data:
                    try:
                        tool_call["function"]["arguments"] = json.dumps(
                            input_data
                        )
                    except (TypeError, ValueError):
                        tool_call["function"]["arguments"] = str(input_data)
            tool_calls.append(tool_call)

    return tool_calls if tool_calls else None


def get_llm_request_attributes(
    kwargs: dict,
    client_instance: Any,
    operation_name: str = GenAIAttributes.GenAiOperationNameValues.CHAT.value,
) -> dict:
    """Build request attributes dictionary from kwargs and client."""
    attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: operation_name,
        GenAIAttributes.GEN_AI_SYSTEM: GEN_AI_SYSTEM_ANTHROPIC,
        GenAIAttributes.GEN_AI_REQUEST_MODEL: kwargs.get("model"),
    }

    # Add streaming indicator
    stream = kwargs.get("stream")
    if stream is not None:
        attributes[LLM_REQUEST_STREAMING] = bool(stream)

    # Add chat-specific attributes
    if operation_name == GenAIAttributes.GenAiOperationNameValues.CHAT.value:
        if (temp := kwargs.get("temperature")) is not None:
            attributes[GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE] = temp

        if (top_p := kwargs.get("top_p")) is not None:
            attributes[GenAIAttributes.GEN_AI_REQUEST_TOP_P] = top_p

        if (max_tokens := kwargs.get("max_tokens")) is not None:
            attributes[GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS] = max_tokens

        if (stop_sequences := kwargs.get("stop_sequences")) is not None:
            if isinstance(stop_sequences, list):
                attributes[GenAIAttributes.GEN_AI_REQUEST_STOP_SEQUENCES] = (
                    stop_sequences
                )

    set_server_address_and_port(client_instance, attributes)

    # Filter out None values
    return {k: v for k, v in attributes.items() if v is not None}


def set_tools_attributes(span: Span, kwargs: dict) -> None:
    """Set span attributes for tool/function definitions in the request."""
    tools = kwargs.get("tools")
    if not tools:
        return

    for i, tool in enumerate(tools):
        prefix = f"gen_ai.request.tools.{i}"

        name = get_property_value(tool, "name")
        description = get_property_value(tool, "description")
        input_schema = get_property_value(tool, "input_schema")

        if name:
            span.set_attribute(f"{prefix}.name", name)
        if description:
            span.set_attribute(f"{prefix}.description", description)
        if input_schema:
            try:
                span.set_attribute(f"{prefix}.parameters", json.dumps(input_schema))
            except (TypeError, ValueError):
                pass


def set_response_attributes(span: Span, response: Any) -> None:
    """Set common response attributes on a span."""
    if not span.is_recording():
        return

    # Handle with_raw_response wrapped responses
    if hasattr(response, "parse") and callable(response.parse):
        try:
            response = response.parse()
        except Exception:
            return

    if (model := getattr(response, "model", None)) is not None:
        set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, model)

    if (response_id := getattr(response, "id", None)) is not None:
        set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_ID, response_id)

    if (stop_reason := getattr(response, "stop_reason", None)) is not None:
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS,
            [stop_reason],
        )

    # Set usage attributes
    usage = getattr(response, "usage", None)
    if usage:
        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)

        if input_tokens is not None:
            set_span_attribute(
                span, GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS, input_tokens
            )

        if output_tokens is not None:
            set_span_attribute(
                span, GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS, output_tokens
            )

        # Set total tokens
        if input_tokens is not None and output_tokens is not None:
            set_span_attribute(
                span, LLM_USAGE_TOTAL_TOKENS, input_tokens + output_tokens
            )

        # Set cached tokens
        cache_read_tokens = getattr(usage, "cache_read_input_tokens", None)
        if cache_read_tokens is not None and cache_read_tokens > 0:
            set_span_attribute(
                span, LLM_USAGE_CACHE_READ_INPUT_TOKENS, cache_read_tokens
            )

        # Set cache creation tokens
        cache_creation_tokens = getattr(
            usage, "cache_creation_input_tokens", None
        )
        if cache_creation_tokens is not None and cache_creation_tokens > 0:
            set_span_attribute(
                span, LLM_USAGE_CACHE_CREATION_INPUT_TOKENS, cache_creation_tokens
            )


def message_to_event(message: dict, capture_content: bool) -> LogRecord:
    """Convert a message to a log event record."""
    attributes = {
        GenAIAttributes.GEN_AI_SYSTEM: GEN_AI_SYSTEM_ANTHROPIC,
    }

    role = message.get("role", "user")
    content = message.get("content")

    body = {}
    if capture_content and content:
        if isinstance(content, str):
            body["content"] = content
        elif isinstance(content, list):
            # Handle multi-part content (text, images, etc.)
            text_parts = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
            if text_parts:
                body["content"] = "\n".join(text_parts)

    return LogRecord(
        event_name=f"gen_ai.{role}.message",
        attributes=attributes,
        body=body if body else None,
    )


def choice_to_event(
    content_block: Any, index: int, capture_content: bool
) -> LogRecord:
    """Convert a response content block to a log event record."""
    attributes = {
        GenAIAttributes.GEN_AI_SYSTEM: GEN_AI_SYSTEM_ANTHROPIC,
    }

    block_type = get_property_value(content_block, "type")
    body = {
        "index": index,
        "finish_reason": "stop",  # Anthropic doesn't have per-block finish reasons
    }

    message = {"role": "assistant"}

    if block_type == "text":
        text = get_property_value(content_block, "text")
        if capture_content and text:
            message["content"] = text
    elif block_type == "tool_use":
        tool_call = {
            "id": get_property_value(content_block, "id"),
            "type": "function",
            "function": {
                "name": get_property_value(content_block, "name"),
            },
        }
        if capture_content:
            input_data = get_property_value(content_block, "input")
            if input_data:
                try:
                    tool_call["function"]["arguments"] = json.dumps(input_data)
                except (TypeError, ValueError):
                    pass
        message["tool_calls"] = [tool_call]
    elif block_type == "thinking":
        thinking = get_property_value(content_block, "thinking")
        if capture_content and thinking:
            message["content"] = f"[Thinking]: {thinking}"

    body["message"] = message

    return LogRecord(
        event_name="gen_ai.choice",
        attributes=attributes,
        body=body,
    )


def handle_span_exception(span: Span, error: Exception) -> None:
    """Handle an exception by setting span status and error attributes."""
    span.set_status(Status(StatusCode.ERROR, str(error)))
    if span.is_recording():
        span.set_attribute(
            ErrorAttributes.ERROR_TYPE, type(error).__qualname__
        )
    span.end()


def set_request_content_on_span(
    span: Span, kwargs: dict, capture_content: bool
) -> None:
    """Set request messages as span attributes when content capture is enabled."""
    if not capture_content or not span.is_recording():
        return

    messages = kwargs.get("messages")
    if messages:
        try:
            messages_str = json.dumps(messages, default=str)
            span.set_attribute(LLM_REQUEST_MESSAGES, messages_str)
        except (TypeError, ValueError):
            pass


def set_response_content_on_span(
    span: Span, response: Any, capture_content: bool
) -> None:
    """Set response content as span attributes when content capture is enabled."""
    if not capture_content or not span.is_recording():
        return

    # Handle with_raw_response wrapped responses
    if hasattr(response, "parse") and callable(response.parse):
        try:
            response = response.parse()
        except Exception:
            return

    content = getattr(response, "content", None)
    if content and isinstance(content, list):
        response_parts = []
        for block in content:
            block_type = get_property_value(block, "type")
            if block_type == "text":
                text = get_property_value(block, "text")
                if text:
                    response_parts.append(text)
            elif block_type == "tool_use":
                name = get_property_value(block, "name")
                input_data = get_property_value(block, "input")
                try:
                    args = json.dumps(input_data) if input_data else ""
                except (TypeError, ValueError):
                    args = str(input_data)
                response_parts.append(f"[Tool: {name}({args})]")
            elif block_type == "thinking":
                thinking = get_property_value(block, "thinking")
                if thinking:
                    response_parts.append(f"[Thinking]: {thinking}")

        if response_parts:
            span.set_attribute(
                LLM_RESPONSE_CONTENT, "\n---\n".join(response_parts)
            )
