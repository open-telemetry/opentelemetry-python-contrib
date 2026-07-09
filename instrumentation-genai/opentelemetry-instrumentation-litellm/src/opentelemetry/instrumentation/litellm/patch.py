# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, Callable

from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import Error

from .chat_wrappers import AsyncChatStreamWrapper, ChatStreamWrapper
from .utils import (
    create_chat_invocation,
    create_embedding_invocation,
    is_streaming,
    set_chat_response,
    set_embedding_response,
)


def completion_wrapper(handler: TelemetryHandler) -> Callable[..., Any]:
    """Wrap the sync ``litellm.completion`` on the experimental semconv path."""
    capture_content = handler.should_capture_content()

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_chat_invocation(
            handler, args, kwargs, capture_content=capture_content
        )
        try:
            result = wrapped(*args, **kwargs)
            if is_streaming(kwargs) and result is not None:
                return ChatStreamWrapper(result, invocation, capture_content)

            set_chat_response(invocation, result, capture_content)
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def acompletion_wrapper(handler: TelemetryHandler) -> Callable[..., Any]:
    """Wrap the async ``litellm.acompletion`` on the experimental path."""
    capture_content = handler.should_capture_content()

    async def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_chat_invocation(
            handler, args, kwargs, capture_content=capture_content
        )
        try:
            result = await wrapped(*args, **kwargs)
            if is_streaming(kwargs) and result is not None:
                return AsyncChatStreamWrapper(
                    result, invocation, capture_content
                )

            set_chat_response(invocation, result, capture_content)
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def embedding_wrapper(handler: TelemetryHandler) -> Callable[..., Any]:
    """Wrap the sync ``litellm.embedding`` on the experimental path."""

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_embedding_invocation(handler, args, kwargs)
        try:
            result = wrapped(*args, **kwargs)
            set_embedding_response(invocation, result)
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def aembedding_wrapper(handler: TelemetryHandler) -> Callable[..., Any]:
    """Wrap the async ``litellm.aembedding`` on the experimental path."""

    async def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_embedding_invocation(handler, args, kwargs)
        try:
            result = await wrapped(*args, **kwargs)
            set_embedding_response(invocation, result)
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


__all__ = [
    "acompletion_wrapper",
    "aembedding_wrapper",
    "completion_wrapper",
    "embedding_wrapper",
]
