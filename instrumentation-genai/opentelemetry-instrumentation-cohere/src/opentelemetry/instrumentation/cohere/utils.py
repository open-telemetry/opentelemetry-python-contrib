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

from typing import Any, List, Optional

from opentelemetry.util.genai.types import (
    InputMessage,
    LLMInvocation,
    OutputMessage,
    Text,
    ToolCallRequest,
)

COHERE_PROVIDER_NAME = "cohere"

# Mapping from Cohere finish reasons to GenAI semantic convention finish reasons
_FINISH_REASON_MAP = {
    "COMPLETE": "stop",
    "STOP_SEQUENCE": "stop",
    "MAX_TOKENS": "length",
    "TOOL_CALL": "tool_calls",
    "ERROR": "error",
    "TIMEOUT": "error",
}


def map_finish_reason(cohere_reason: Optional[str]) -> str:
    if cohere_reason is None:
        return "error"
    return _FINISH_REASON_MAP.get(str(cohere_reason), str(cohere_reason).lower())


def get_server_address_and_port(
    client_instance: Any,
) -> tuple[Optional[str], Optional[int]]:
    """Extract server address and port from the Cohere client instance."""
    base_url = getattr(client_instance, "base_url", None)
    if base_url is None:
        # Check nested _client pattern
        inner = getattr(client_instance, "_client", None)
        if inner is not None:
            base_url = getattr(inner, "base_url", None)

    if base_url is None:
        return "api.cohere.com", None

    if isinstance(base_url, str):
        from urllib.parse import urlparse

        parsed = urlparse(base_url)
        address = parsed.hostname or "api.cohere.com"
        port = parsed.port
        if port == 443:
            port = None
        return address, port

    return "api.cohere.com", None


def create_chat_invocation(
    kwargs: dict[str, Any],
    client_instance: Any,
    capture_content: bool,
) -> LLMInvocation:
    """Create an LLMInvocation from Cohere chat kwargs."""
    invocation = LLMInvocation(request_model=kwargs.get("model", ""))
    invocation.provider = COHERE_PROVIDER_NAME
    invocation.temperature = kwargs.get("temperature")
    invocation.top_p = kwargs.get("p")
    invocation.max_tokens = kwargs.get("max_tokens")
    invocation.frequency_penalty = kwargs.get("frequency_penalty")
    invocation.presence_penalty = kwargs.get("presence_penalty")
    invocation.seed = kwargs.get("seed")

    stop_sequences = kwargs.get("stop_sequences")
    if stop_sequences is not None:
        if isinstance(stop_sequences, str):
            stop_sequences = [stop_sequences]
        invocation.stop_sequences = list(stop_sequences)

    address, port = get_server_address_and_port(client_instance)
    if address:
        invocation.server_address = address
    if port:
        invocation.server_port = port

    if capture_content:
        invocation.input_messages = _extract_input_messages(
            kwargs.get("messages", [])
        )

    return invocation


def set_response_attributes(
    invocation: LLMInvocation,
    response: Any,
    capture_content: bool,
) -> None:
    """Populate invocation attributes from a Cohere V2ChatResponse."""
    if response is None:
        return

    response_id = getattr(response, "id", None)
    if response_id:
        invocation.response_id = response_id

    finish_reason = getattr(response, "finish_reason", None)
    if finish_reason is not None:
        invocation.finish_reasons = [map_finish_reason(finish_reason)]

    usage = getattr(response, "usage", None)
    if usage is not None:
        _set_usage(invocation, usage)

    if capture_content:
        message = getattr(response, "message", None)
        if message is not None:
            invocation.output_messages = _extract_output_messages(
                message, finish_reason
            )


def _set_usage(invocation: LLMInvocation, usage: Any) -> None:
    """Extract token usage from Cohere Usage object."""
    tokens = getattr(usage, "tokens", None)
    if tokens is not None:
        input_tokens = getattr(tokens, "input_tokens", None)
        if input_tokens is not None:
            invocation.input_tokens = int(input_tokens)
        output_tokens = getattr(tokens, "output_tokens", None)
        if output_tokens is not None:
            invocation.output_tokens = int(output_tokens)
        return

    # Fallback to billed_units
    billed = getattr(usage, "billed_units", None)
    if billed is not None:
        input_tokens = getattr(billed, "input_tokens", None)
        if input_tokens is not None:
            invocation.input_tokens = int(input_tokens)
        output_tokens = getattr(billed, "output_tokens", None)
        if output_tokens is not None:
            invocation.output_tokens = int(output_tokens)


def _extract_input_messages(
    messages: List[Any],
) -> List[InputMessage]:
    """Convert Cohere chat messages to InputMessage list."""
    result = []
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role", "user")
            content = msg.get("content", "")
        else:
            role = getattr(msg, "role", "user")
            content = getattr(msg, "content", "")

        parts: list = []
        if isinstance(content, str):
            parts.append(Text(content=content))
        elif isinstance(content, list):
            # Handle structured content items
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text", "")
                    if text:
                        parts.append(Text(content=text))
                elif isinstance(item, str):
                    parts.append(Text(content=item))
                else:
                    text = getattr(item, "text", None)
                    if text:
                        parts.append(Text(content=str(text)))

        result.append(InputMessage(role=str(role), parts=parts))
    return result


def _extract_output_messages(
    message: Any,
    finish_reason: Any,
) -> List[OutputMessage]:
    """Convert a Cohere AssistantMessageResponse to OutputMessage list."""
    parts: list = []

    content_items = getattr(message, "content", None)
    if content_items:
        for item in content_items:
            item_type = getattr(item, "type", None)
            if item_type == "text":
                text = getattr(item, "text", "")
                parts.append(Text(content=str(text)))

    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        for tc in tool_calls:
            tc_id = getattr(tc, "id", None)
            tc_name = ""
            tc_args = None
            func = getattr(tc, "function", None)
            if func:
                tc_name = getattr(func, "name", "") or ""
                tc_args = getattr(func, "arguments", None)
            else:
                tc_name = getattr(tc, "name", "") or ""
                tc_args = getattr(tc, "parameters", None)
            parts.append(
                ToolCallRequest(id=tc_id, name=tc_name, arguments=tc_args)
            )

    role = getattr(message, "role", "assistant") or "assistant"
    mapped_reason = map_finish_reason(finish_reason)

    return [OutputMessage(role=str(role), parts=parts, finish_reason=mapped_reason)]
