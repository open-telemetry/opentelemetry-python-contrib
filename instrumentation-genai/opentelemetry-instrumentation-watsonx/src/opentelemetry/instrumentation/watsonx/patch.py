# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, Callable

from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import Error

from .stream_wrappers import TextGenerationStreamWrapper
from .utils import (
    create_chat_invocation,
    create_text_generation_invocation,
    set_chat_response,
    set_text_generation_response,
)


def generate(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Wrap ``ModelInference.generate`` (non-streaming text completion)."""
    capture_content = handler.should_capture_content()

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_text_generation_invocation(
            handler, kwargs, args, instance, capture_content=capture_content
        )
        try:
            result = wrapped(*args, **kwargs)
            set_text_generation_response(invocation, result, capture_content)
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def chat(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Wrap ``ModelInference.chat`` (non-streaming chat completion)."""
    capture_content = handler.should_capture_content()

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_chat_invocation(
            handler, kwargs, args, instance, capture_content=capture_content
        )
        try:
            result = wrapped(*args, **kwargs)
            set_chat_response(invocation, result, capture_content)
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def generate_text_stream(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Wrap ``ModelInference.generate_text_stream`` (streaming text completion)."""
    capture_content = handler.should_capture_content()

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_text_generation_invocation(
            handler, kwargs, args, instance, capture_content=capture_content
        )
        try:
            result = wrapped(*args, **kwargs)
            return TextGenerationStreamWrapper(
                result, invocation, capture_content
            )
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


__all__ = [
    "chat",
    "generate",
    "generate_text_stream",
]
