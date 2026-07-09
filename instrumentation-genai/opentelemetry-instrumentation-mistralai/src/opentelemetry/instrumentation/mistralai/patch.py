# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, Callable

from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.invocation import (
    EmbeddingInvocation,
    InferenceInvocation,
)
from opentelemetry.util.genai.types import Error

from .chat_wrappers import AsyncChatStreamWrapper, ChatStreamWrapper
from .utils import (
    _MISTRAL_AI_PROVIDER,
    _prepare_output_messages,
    create_chat_invocation,
    create_embedding_invocation,
    get_property_value,
    is_streaming,
)


def chat_complete(
    handler: TelemetryHandler,
    method_name: str,
) -> Callable[..., Any]:
    """Wrap the sync ``Chat.complete`` / ``Chat.stream`` methods."""
    capture_content = handler.should_capture_content()
    streaming = is_streaming(method_name)

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        chat_invocation = create_chat_invocation(
            handler, kwargs, instance, capture_content=capture_content
        )

        try:
            result = wrapped(*args, **kwargs)
            if streaming:
                return ChatStreamWrapper(
                    result, chat_invocation, capture_content
                )
            _set_response_properties(
                chat_invocation, result, capture_content
            )
            chat_invocation.stop()
            return result
        except Exception as error:
            chat_invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def async_chat_complete(
    handler: TelemetryHandler,
    method_name: str,
) -> Callable[..., Any]:
    """Wrap the async ``Chat.complete_async`` / ``Chat.stream_async`` methods."""
    capture_content = handler.should_capture_content()
    streaming = is_streaming(method_name)

    async def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        chat_invocation = create_chat_invocation(
            handler, kwargs, instance, capture_content=capture_content
        )

        try:
            result = await wrapped(*args, **kwargs)
            if streaming:
                return AsyncChatStreamWrapper(
                    result, chat_invocation, capture_content
                )
            _set_response_properties(
                chat_invocation, result, capture_content
            )
            chat_invocation.stop()
            return result
        except Exception as error:
            chat_invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def embeddings_create(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Wrap the sync ``Embeddings.create`` method."""

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_embedding_invocation(handler, kwargs, instance)
        try:
            result = wrapped(*args, **kwargs)
            _set_embedding_response_properties(invocation, result)
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def async_embeddings_create(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Wrap the async ``Embeddings.create_async`` method."""

    async def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_embedding_invocation(handler, kwargs, instance)
        try:
            result = await wrapped(*args, **kwargs)
            _set_embedding_response_properties(invocation, result)
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def _set_response_properties(
    chat_invocation: InferenceInvocation,
    result: Any,
    capture_content: bool,
) -> InferenceInvocation:
    if getattr(result, "model", None):
        chat_invocation.response_model_name = result.model

    choices = getattr(result, "choices", None)
    if choices:
        chat_invocation.finish_reasons = [
            get_property_value(choice, "finish_reason") or "error"
            for choice in choices
        ]
        if capture_content:  # optimization
            chat_invocation.output_messages = _prepare_output_messages(choices)

    if getattr(result, "id", None):
        chat_invocation.response_id = result.id

    usage = getattr(result, "usage", None)
    if usage is not None:
        chat_invocation.input_tokens = usage.prompt_tokens
        chat_invocation.output_tokens = usage.completion_tokens

    return chat_invocation


def _set_embedding_response_properties(
    invocation: EmbeddingInvocation,
    result: Any,
) -> EmbeddingInvocation:
    if getattr(result, "model", None):
        invocation.response_model_name = result.model

    usage = getattr(result, "usage", None)
    if usage is not None:
        invocation.input_tokens = usage.prompt_tokens

    data = getattr(result, "data", None)
    if data:
        first = data[0]
        embedding = getattr(first, "embedding", None)
        if embedding is not None:
            invocation.dimension_count = len(embedding)

    return invocation


__all__ = [
    "_MISTRAL_AI_PROVIDER",
    "async_chat_complete",
    "async_embeddings_create",
    "chat_complete",
    "embeddings_create",
]
