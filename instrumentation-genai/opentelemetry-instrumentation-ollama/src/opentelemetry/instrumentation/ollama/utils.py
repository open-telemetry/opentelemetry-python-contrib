# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Helpers for parsing ollama SDK requests and responses into GenAI invocations.

The ollama SDK exposes ``chat``, ``generate``, ``embed`` and ``embeddings``
methods on ``ollama.Client`` and ``ollama.AsyncClient``. Requests are passed as
keyword arguments; responses are pydantic models (``ChatResponse``,
``GenerateResponse``, ``EmbedResponse``, ``EmbeddingsResponse``) that also behave
like mappings. This module maps those shapes onto the shared
``opentelemetry-util-genai`` invocation objects using only standard
``opentelemetry.semconv`` attributes.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from opentelemetry.util.genai.invocation import (
    EmbeddingInvocation,
    InferenceInvocation,
)
from opentelemetry.util.genai.types import (
    InputMessage,
    OutputMessage,
    Text,
    ToolCallRequest,
    ToolCallResponse,
)

# The GenAI provider name. ``ollama`` has no dedicated value in
# ``GenAiProviderNameValues`` in the current semconv release, so use the literal
# string. Switch to the enum value once semconv defines one.
OLLAMA_PROVIDER = "ollama"

_DEFAULT_OLLAMA_PORT = 11434


def _get(obj: Any, name: str) -> Any:
    """Read ``name`` from a mapping or an object attribute."""
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


def get_server_address_and_port(
    client_instance: Any,
) -> tuple[str | None, int | None]:
    """Extract the ollama server address and port from the client instance.

    ollama's ``Client`` keeps the httpx client at ``_client`` with a ``base_url``.
    """
    base_client = getattr(client_instance, "_client", None)
    base_url = getattr(base_client, "base_url", None)
    if not base_url:
        return None, None

    host = getattr(base_url, "host", None)
    port = getattr(base_url, "port", None)
    if host is None:
        # base_url may be a plain string on some versions.
        parsed = urlparse(str(base_url))
        host = parsed.hostname
        port = parsed.port

    if port == _DEFAULT_OLLAMA_PORT:
        # Default port carries no information; drop it to reduce cardinality.
        port = None

    return host, port


def _messages_from_kwargs(kwargs: Mapping[str, Any]) -> Sequence[Any]:
    messages = kwargs.get("messages")
    return messages or []


def _text_content(content: Any) -> str | None:
    if content is None:
        return None
    if isinstance(content, str):
        return content
    return None


def _extract_tool_calls(tool_calls: Any) -> list[ToolCallRequest]:
    parts: list[ToolCallRequest] = []
    for tool_call in tool_calls or []:
        func = _get(tool_call, "function")
        name = _get(func, "name") if func is not None else None
        arguments = _get(func, "arguments") if func is not None else None
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                pass
        parts.append(
            ToolCallRequest(
                id=_get(tool_call, "id"),
                name=str(name) if name is not None else "",
                arguments=arguments,
            )
        )
    return parts


def _prepare_chat_input_messages(
    messages: Sequence[Any],
) -> list[InputMessage]:
    input_messages: list[InputMessage] = []
    for message in messages:
        role = _get(message, "role")
        chat_message = InputMessage(role=str(role) if role else "", parts=[])
        content = _get(message, "content")
        tool_calls = _get(message, "tool_calls")

        if role == "tool":
            chat_message.parts.append(
                ToolCallResponse(
                    id=_get(message, "tool_name") or _get(message, "tool_call_id"),
                    response=content,
                )
            )
        else:
            if tool_calls:
                chat_message.parts.extend(_extract_tool_calls(tool_calls))
            text = _text_content(content)
            if text:
                chat_message.parts.append(Text(content=text))
        input_messages.append(chat_message)
    return input_messages


def apply_chat_request(
    invocation: InferenceInvocation,
    kwargs: Mapping[str, Any],
    *,
    capture_content: bool,
) -> None:
    """Populate an inference invocation from ollama ``chat`` request kwargs."""
    _apply_request_options(invocation, kwargs)
    if capture_content:
        invocation.input_messages = _prepare_chat_input_messages(
            _messages_from_kwargs(kwargs)
        )


def apply_generate_request(
    invocation: InferenceInvocation,
    kwargs: Mapping[str, Any],
    *,
    capture_content: bool,
) -> None:
    """Populate an inference invocation from ollama ``generate`` request kwargs."""
    _apply_request_options(invocation, kwargs)
    if capture_content:
        prompt = kwargs.get("prompt")
        if isinstance(prompt, str) and prompt:
            invocation.input_messages = [
                InputMessage(role="user", parts=[Text(content=prompt)])
            ]
        system = kwargs.get("system")
        if isinstance(system, str) and system:
            invocation.system_instruction = [Text(content=system)]


def _apply_request_options(
    invocation: InferenceInvocation, kwargs: Mapping[str, Any]
) -> None:
    """Map ollama request ``options`` onto the standard request attributes.

    ollama accepts sampling parameters inside an ``options`` mapping (or
    ``Options`` object). Only well-known semconv request parameters are mapped.
    """
    options = kwargs.get("options")
    if options is None:
        return
    invocation.temperature = _as_float(_get(options, "temperature"))
    invocation.top_p = _as_float(_get(options, "top_p"))
    invocation.frequency_penalty = _as_float(
        _get(options, "frequency_penalty")
    )
    invocation.presence_penalty = _as_float(_get(options, "presence_penalty"))
    invocation.max_tokens = _as_int(_get(options, "num_predict"))
    invocation.seed = _as_int(_get(options, "seed"))
    stop = _get(options, "stop")
    if isinstance(stop, str):
        invocation.stop_sequences = [stop]
    elif isinstance(stop, (list, tuple)):
        invocation.stop_sequences = [str(item) for item in stop]


def _as_float(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def set_chat_response(
    invocation: InferenceInvocation,
    response: Any,
    *,
    capture_content: bool,
) -> None:
    """Populate an inference invocation from an ollama ``ChatResponse``."""
    _set_common_response(invocation, response)
    if not capture_content:
        return
    message = _get(response, "message")
    if message is None:
        return
    parts: list[Any] = []
    tool_calls = _get(message, "tool_calls")
    if tool_calls:
        parts.extend(_extract_tool_calls(tool_calls))
    text = _text_content(_get(message, "content"))
    if text:
        parts.append(Text(content=text))
    role = _get(message, "role") or "assistant"
    invocation.output_messages = [
        OutputMessage(
            role=str(role),
            parts=parts,
            finish_reason=_finish_reason(response),
        )
    ]


def set_generate_response(
    invocation: InferenceInvocation,
    response: Any,
    *,
    capture_content: bool,
) -> None:
    """Populate an inference invocation from an ollama ``GenerateResponse``."""
    _set_common_response(invocation, response)
    if not capture_content:
        return
    text = _text_content(_get(response, "response"))
    if text:
        invocation.output_messages = [
            OutputMessage(
                role="assistant",
                parts=[Text(content=text)],
                finish_reason=_finish_reason(response),
            )
        ]


def _finish_reason(response: Any) -> str:
    reason = _get(response, "done_reason")
    return str(reason) if reason else "stop"


def _set_common_response(
    invocation: InferenceInvocation, response: Any
) -> None:
    model = _get(response, "model")
    if model:
        invocation.response_model_name = str(model)

    done_reason = _get(response, "done_reason")
    if done_reason:
        invocation.finish_reasons = [str(done_reason)]

    input_tokens = _as_int(_get(response, "prompt_eval_count"))
    if input_tokens is not None:
        invocation.input_tokens = input_tokens

    output_tokens = _as_int(_get(response, "eval_count"))
    if output_tokens is not None:
        invocation.output_tokens = output_tokens


def set_embeddings_response(
    invocation: EmbeddingInvocation, response: Any
) -> None:
    """Populate an embedding invocation from an ollama ``EmbedResponse``."""
    model = _get(response, "model")
    if model:
        invocation.response_model_name = str(model)

    input_tokens = _as_int(_get(response, "prompt_eval_count"))
    if input_tokens is not None:
        invocation.input_tokens = input_tokens

    # ``embed`` returns an ``EmbedResponse`` with a plural ``embeddings`` list;
    # the legacy ``embeddings`` method returns an ``EmbeddingsResponse`` whose
    # only field is a singular ``embedding`` vector.
    embeddings = _get(response, "embeddings")
    first = embeddings[0] if embeddings else _get(response, "embedding")
    if first is not None:
        try:
            invocation.dimension_count = len(first)
        except TypeError:
            pass
