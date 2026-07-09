# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""wrapt wrappers for ollama ``chat``/``generate``/``embeddings`` methods.

Each wrapper starts a GenAI invocation through the shared ``TelemetryHandler``,
invokes the wrapped ollama method, records response telemetry, and re-raises any
error from the underlying library unmodified. Telemetry code never raises.
"""

from __future__ import annotations

from typing import Any, Callable

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.invocation import (
    EmbeddingInvocation,
    InferenceInvocation,
)

from .stream_wrapper import (
    OllamaAsyncStreamWrapper,
    OllamaSyncStreamWrapper,
)
from .utils import (
    OLLAMA_PROVIDER,
    apply_chat_request,
    apply_generate_request,
    get_server_address_and_port,
    set_chat_response,
    set_embeddings_response,
    set_generate_response,
)

# ollama's ``generate`` maps to the text_completion operation; ``chat`` to chat.
_CHAT_OPERATION = GenAI.GenAiOperationNameValues.CHAT.value
_GENERATE_OPERATION = GenAI.GenAiOperationNameValues.TEXT_COMPLETION.value


def _is_streaming(kwargs: dict[str, Any]) -> bool:
    return bool(kwargs.get("stream"))


def _request_kwargs(
    args: tuple[Any, ...], kwargs: dict[str, Any], names: tuple[str, ...]
) -> dict[str, Any]:
    """Bind positional args under their parameter names for telemetry reads.

    ollama's ``chat``/``generate``/``embed`` accept ``model`` and the content
    argument positionally, but the request helpers read from kwargs. The
    original ``args``/``kwargs`` are still forwarded to the wrapped call
    unchanged; this only builds a merged view for extraction.
    """
    if not args:
        return kwargs
    merged = dict(kwargs)
    for name, value in zip(names, args):
        merged.setdefault(name, value)
    return merged


def _start_inference(
    handler: TelemetryHandler,
    kwargs: dict[str, Any],
    instance: Any,
    operation_name: str,
) -> InferenceInvocation:
    address, port = get_server_address_and_port(instance)
    return handler.start_inference(
        OLLAMA_PROVIDER,
        request_model=kwargs.get("model") or "",
        server_address=address,
        server_port=port,
        operation_name=operation_name,
    )


def chat_wrapper(handler: TelemetryHandler) -> Callable[..., Any]:
    """Wrap ``Client.chat``."""
    capture_content = handler.should_capture_content()

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        req = _request_kwargs(args, kwargs, ("model", "messages"))
        invocation = _start_inference(handler, req, instance, _CHAT_OPERATION)
        apply_chat_request(invocation, req, capture_content=capture_content)
        try:
            result = wrapped(*args, **kwargs)
            if _is_streaming(kwargs):
                return OllamaSyncStreamWrapper(
                    result, invocation, capture_content, "chat"
                )
            set_chat_response(
                invocation, result, capture_content=capture_content
            )
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(error)
            raise

    return traced_method


def async_chat_wrapper(handler: TelemetryHandler) -> Callable[..., Any]:
    """Wrap ``AsyncClient.chat``."""
    capture_content = handler.should_capture_content()

    async def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        req = _request_kwargs(args, kwargs, ("model", "messages"))
        invocation = _start_inference(handler, req, instance, _CHAT_OPERATION)
        apply_chat_request(invocation, req, capture_content=capture_content)
        try:
            result = await wrapped(*args, **kwargs)
            if _is_streaming(kwargs):
                return OllamaAsyncStreamWrapper(
                    result, invocation, capture_content, "chat"
                )
            set_chat_response(
                invocation, result, capture_content=capture_content
            )
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(error)
            raise

    return traced_method


def generate_wrapper(handler: TelemetryHandler) -> Callable[..., Any]:
    """Wrap ``Client.generate``."""
    capture_content = handler.should_capture_content()

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        req = _request_kwargs(args, kwargs, ("model", "prompt", "suffix"))
        invocation = _start_inference(
            handler, req, instance, _GENERATE_OPERATION
        )
        apply_generate_request(
            invocation, req, capture_content=capture_content
        )
        try:
            result = wrapped(*args, **kwargs)
            if _is_streaming(kwargs):
                return OllamaSyncStreamWrapper(
                    result, invocation, capture_content, "generate"
                )
            set_generate_response(
                invocation, result, capture_content=capture_content
            )
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(error)
            raise

    return traced_method


def async_generate_wrapper(handler: TelemetryHandler) -> Callable[..., Any]:
    """Wrap ``AsyncClient.generate``."""
    capture_content = handler.should_capture_content()

    async def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        req = _request_kwargs(args, kwargs, ("model", "prompt", "suffix"))
        invocation = _start_inference(
            handler, req, instance, _GENERATE_OPERATION
        )
        apply_generate_request(
            invocation, req, capture_content=capture_content
        )
        try:
            result = await wrapped(*args, **kwargs)
            if _is_streaming(kwargs):
                return OllamaAsyncStreamWrapper(
                    result, invocation, capture_content, "generate"
                )
            set_generate_response(
                invocation, result, capture_content=capture_content
            )
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(error)
            raise

    return traced_method


def _start_embedding(
    handler: TelemetryHandler,
    kwargs: dict[str, Any],
    instance: Any,
) -> EmbeddingInvocation:
    address, port = get_server_address_and_port(instance)
    return handler.start_embedding(
        OLLAMA_PROVIDER,
        request_model=kwargs.get("model") or "",
        server_address=address,
        server_port=port,
    )


def embeddings_wrapper(handler: TelemetryHandler) -> Callable[..., Any]:
    """Wrap ``Client.embed`` / ``Client.embeddings``."""

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        req = _request_kwargs(args, kwargs, ("model",))
        invocation = _start_embedding(handler, req, instance)
        try:
            result = wrapped(*args, **kwargs)
            set_embeddings_response(invocation, result)
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(error)
            raise

    return traced_method


def async_embeddings_wrapper(handler: TelemetryHandler) -> Callable[..., Any]:
    """Wrap ``AsyncClient.embed`` / ``AsyncClient.embeddings``."""

    async def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        req = _request_kwargs(args, kwargs, ("model",))
        invocation = _start_embedding(handler, req, instance)
        try:
            result = await wrapped(*args, **kwargs)
            set_embeddings_response(invocation, result)
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(error)
            raise

    return traced_method
