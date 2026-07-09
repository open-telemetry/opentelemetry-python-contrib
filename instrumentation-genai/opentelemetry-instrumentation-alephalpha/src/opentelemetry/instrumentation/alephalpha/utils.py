# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, List, Mapping
from urllib.parse import urlparse

from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.invocation import InferenceInvocation
from opentelemetry.util.genai.types import (
    InputMessage,
    OutputMessage,
    Text,
)

# There is no ``aleph_alpha`` member in ``GenAiProviderNameValues`` /
# ``GenAiSystemValues`` in the semconv package, so the raw string literal is
# used for ``gen_ai.provider.name``. Switch to the generated enum member if one
# is added upstream.
_ALEPH_ALPHA_PROVIDER = "aleph_alpha"


def get_request_model(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> str:
    """Resolve the request model name from the ``complete(request, model)`` call.

    ``model`` may be passed positionally (``complete(request, "luminous-base")``)
    or as a keyword (``complete(request, model="luminous-base")``). Fall back to
    ``request.model`` if the SDK ever exposes it on the request object.
    """
    model = kwargs.get("model")
    if model is None and len(args) >= 2:
        model = args[1]
    if model is None:
        request = kwargs.get("request")
        if request is None and args:
            request = args[0]
        model = getattr(request, "model", None)
    return str(model) if model is not None else ""


def get_completion_request(
    args: tuple[Any, ...], kwargs: Mapping[str, Any]
) -> Any:
    request = kwargs.get("request")
    if request is None and args:
        request = args[0]
    return request


def get_server_address_and_port(
    client_instance: Any,
) -> tuple[str | None, int | None]:
    """Extract the server host/port from an ``aleph_alpha_client`` client.

    Both ``Client`` and ``AsyncClient`` store the base URL on the ``host``
    attribute.
    """
    base_url = getattr(client_instance, "host", None)
    if not base_url:
        return None, None

    parsed = urlparse(base_url)
    address = parsed.hostname
    port = parsed.port
    if port == 443:
        port = None
    return address, port


def _prompt_text(request: Any) -> str | None:
    """Return the textual prompt of a ``CompletionRequest`` when available.

    A ``Prompt`` wraps a list of items; text items expose their content on
    ``text``. Non-text items (e.g. images) are skipped.
    """
    prompt = getattr(request, "prompt", None)
    if prompt is None:
        return None
    if isinstance(prompt, str):
        return prompt

    items = getattr(prompt, "items", None)
    if items is None:
        return None

    texts: list[str] = []
    for item in items:
        text = getattr(item, "text", None)
        if isinstance(text, str):
            texts.append(text)
    if texts:
        return "".join(texts)
    return None


def _prepare_input_messages(request: Any) -> List[InputMessage]:
    text = _prompt_text(request)
    if text is None:
        return []
    return [InputMessage(role="user", parts=[Text(content=text)])]


def _prepare_output_messages(result: Any) -> List[OutputMessage]:
    completions = getattr(result, "completions", None) or []
    output_messages: list[OutputMessage] = []
    for completion in completions:
        text = getattr(completion, "completion", None)
        parts: list[Any] = []
        if isinstance(text, str):
            parts.append(Text(content=text))
        # Aleph Alpha finish reasons (e.g. ``maximum_tokens``, ``end_of_text``)
        # are not part of the semconv finish-reason value set, so an empty
        # finish reason is used and consequently omitted from telemetry.
        output_messages.append(
            OutputMessage(role="assistant", parts=parts, finish_reason="")
        )
    return output_messages


def create_chat_invocation(
    handler: TelemetryHandler,
    args: tuple[Any, ...],
    kwargs: Mapping[str, Any],
    client_instance: Any,
    capture_content: bool,
) -> InferenceInvocation:
    address, port = get_server_address_and_port(client_instance)
    invocation = handler.start_inference(
        _ALEPH_ALPHA_PROVIDER,
        request_model=get_request_model(args, kwargs),
        server_address=address if address else None,
        server_port=port if port else None,
    )

    request = get_completion_request(args, kwargs)
    if request is not None:
        invocation.temperature = getattr(request, "temperature", None)
        invocation.top_p = getattr(request, "top_p", None)
        invocation.max_tokens = getattr(request, "maximum_tokens", None)
        invocation.presence_penalty = getattr(
            request, "presence_penalty", None
        )
        invocation.frequency_penalty = getattr(
            request, "frequency_penalty", None
        )
        stop_sequences = getattr(request, "stop_sequences", None)
        if stop_sequences:
            invocation.stop_sequences = list(stop_sequences)

    if capture_content and request is not None:
        invocation.input_messages = _prepare_input_messages(request)

    return invocation


def set_response_properties(
    invocation: InferenceInvocation,
    result: Any,
    capture_content: bool,
) -> InferenceInvocation:
    model_version = getattr(result, "model_version", None)
    if model_version:
        invocation.response_model_name = str(model_version)

    input_tokens = getattr(result, "num_tokens_prompt_total", None)
    if isinstance(input_tokens, int):
        invocation.input_tokens = input_tokens

    output_tokens = getattr(result, "num_tokens_generated", None)
    if isinstance(output_tokens, int):
        invocation.output_tokens = output_tokens

    if capture_content:
        invocation.output_messages = _prepare_output_messages(result)

    return invocation


__all__ = [
    "_ALEPH_ALPHA_PROVIDER",
    "create_chat_invocation",
    "get_request_model",
    "get_server_address_and_port",
    "set_response_properties",
]
