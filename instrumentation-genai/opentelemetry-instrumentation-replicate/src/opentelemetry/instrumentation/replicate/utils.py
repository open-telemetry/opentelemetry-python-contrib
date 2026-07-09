# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, List, Mapping

from httpx import URL

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.invocation import InferenceInvocation
from opentelemetry.util.genai.types import (
    InputMessage,
    OutputMessage,
    Text,
)

# Replicate is not (yet) a well-known value in ``GenAiProviderNameValues`` /
# ``GenAiSystemValues``, so the ``replicate`` provider name is used as a literal
# string here. Replace with the semconv enum value once one is published.
_REPLICATE_PROVIDER = "replicate"

# Replicate predictions are text/model generation, so they map to the
# ``text_completion`` GenAI operation.
_REPLICATE_OPERATION = (
    GenAIAttributes.GenAiOperationNameValues.TEXT_COMPLETION.value
)


def get_server_address_and_port(
    client_instance: Any,
) -> tuple[str | None, int | None]:
    base_client = getattr(client_instance, "_client", None)
    base_url = getattr(base_client, "base_url", None)
    if not base_url:
        return None, None
    address: str | None = None
    port: int | None = None
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


def _resolve_model_ref(
    args: tuple[Any, ...], kwargs: Mapping[str, Any]
) -> str:
    """The Replicate model reference is the first positional/keyword argument.

    Replicate accepts a ``str`` (``owner/name`` or ``owner/name:version``), a
    ``Model``, or a ``Version``. We record the ``str()`` form as
    ``gen_ai.request.model``.
    """
    ref: Any = None
    if args:
        ref = args[0]
    elif "ref" in kwargs:
        ref = kwargs["ref"]
    if ref is None:
        return ""
    return str(ref)


def _get_model_input(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> Any:
    """Return the ``input`` mapping passed to run/stream.

    ``run``/``async_run`` accept ``input`` positionally (second arg) or as a
    keyword; ``stream`` accepts it as a keyword only.
    """
    if "input" in kwargs:
        return kwargs["input"]
    if len(args) > 1:
        return args[1]
    return None


def create_inference_invocation(
    handler: TelemetryHandler,
    args: tuple[Any, ...],
    kwargs: Mapping[str, Any],
    client_instance: Any,
    capture_content: bool,
) -> InferenceInvocation:
    address, port = get_server_address_and_port(client_instance)
    model_ref = _resolve_model_ref(args, kwargs)
    invocation = handler.start_inference(
        _REPLICATE_PROVIDER,
        request_model=model_ref,
        server_address=address if address else None,
        server_port=port if port else None,
        operation_name=_REPLICATE_OPERATION,
    )

    model_input = _get_model_input(args, kwargs)
    if isinstance(model_input, Mapping):
        temperature = model_input.get("temperature")
        if temperature is not None:
            invocation.temperature = temperature
        top_p = model_input.get("top_p")
        if top_p is not None:
            invocation.top_p = top_p
        max_tokens = model_input.get("max_new_tokens") or model_input.get(
            "max_tokens"
        )
        if max_tokens is not None:
            invocation.max_tokens = max_tokens

    if capture_content:  # optimization
        invocation.input_messages = _prepare_input_messages(model_input)

    return invocation


def _prepare_input_messages(model_input: Any) -> List[InputMessage]:
    if not isinstance(model_input, Mapping):
        return []
    prompt = model_input.get("prompt")
    if prompt is None:
        return []
    return [
        InputMessage(role="user", parts=[Text(content=str(prompt))]),
    ]


def prepare_output_messages(output: Any) -> List[OutputMessage]:
    """Build a single assistant ``OutputMessage`` from a Replicate output.

    Replicate outputs are commonly a list of string chunks (which the caller
    concatenates) or a single string. Non-text outputs (e.g. file references)
    are stringified.
    """
    text = _output_to_text(output)
    if text is None:
        return []
    return [
        OutputMessage(
            role="assistant",
            parts=[Text(content=text)],
            finish_reason="stop",
        )
    ]


def _output_to_text(output: Any) -> str | None:
    if output is None:
        return None
    if isinstance(output, str):
        return output
    if isinstance(output, (list, tuple)):
        return "".join(str(item) for item in output)
    return str(output)
