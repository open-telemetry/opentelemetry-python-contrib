# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, Callable

from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.invocation import InferenceInvocation
from opentelemetry.util.genai.types import Error, OutputMessage, Text

from .chat_wrappers import AsyncChatStreamWrapper, ChatStreamWrapper
from .completion_wrappers import (
    AsyncCompletionStreamWrapper,
    CompletionStreamWrapper,
)
from .utils import (
    _WRITER_PROVIDER,
    _prepare_output_messages,
    create_chat_invocation,
    create_completion_invocation,
    is_streaming,
)


def chat(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Wrap the sync ``ChatResource.chat`` method."""
    capture_content = handler.should_capture_content()

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
            if is_streaming(kwargs):
                return ChatStreamWrapper(
                    result, chat_invocation, capture_content
                )
            _set_chat_response_properties(
                chat_invocation, result, capture_content
            )
            chat_invocation.stop()
            return result
        except Exception as error:
            chat_invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def async_chat(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Wrap the async ``AsyncChatResource.chat`` method."""
    capture_content = handler.should_capture_content()

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
            if is_streaming(kwargs):
                return AsyncChatStreamWrapper(
                    result, chat_invocation, capture_content
                )
            _set_chat_response_properties(
                chat_invocation, result, capture_content
            )
            chat_invocation.stop()
            return result
        except Exception as error:
            chat_invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def completions_create(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Wrap the sync ``CompletionsResource.create`` method."""
    capture_content = handler.should_capture_content()

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_completion_invocation(
            handler, kwargs, instance, capture_content=capture_content
        )

        try:
            result = wrapped(*args, **kwargs)
            if is_streaming(kwargs):
                return CompletionStreamWrapper(
                    result, invocation, capture_content
                )
            _set_completion_response_properties(
                invocation, result, capture_content
            )
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def async_completions_create(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Wrap the async ``AsyncCompletionsResource.create`` method."""
    capture_content = handler.should_capture_content()

    async def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_completion_invocation(
            handler, kwargs, instance, capture_content=capture_content
        )

        try:
            result = await wrapped(*args, **kwargs)
            if is_streaming(kwargs):
                return AsyncCompletionStreamWrapper(
                    result, invocation, capture_content
                )
            _set_completion_response_properties(
                invocation, result, capture_content
            )
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def _set_chat_response_properties(
    chat_invocation: InferenceInvocation,
    result: Any,
    capture_content: bool,
) -> InferenceInvocation:
    if getattr(result, "model", None):
        chat_invocation.response_model_name = result.model

    choices = getattr(result, "choices", None)
    if choices:
        chat_invocation.finish_reasons = [
            getattr(choice, "finish_reason", None) or "error"
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


def _set_completion_response_properties(
    invocation: InferenceInvocation,
    result: Any,
    capture_content: bool,
) -> InferenceInvocation:
    """Record response fields for the text ``completions.create`` API.

    ``Completion`` only carries ``model`` and ``choices[].text`` -- there is no
    ``id``, ``usage``, or per-choice ``finish_reason``.
    """
    if getattr(result, "model", None):
        invocation.response_model_name = result.model

    choices = getattr(result, "choices", None)
    if choices and capture_content:  # optimization
        output_messages: list[OutputMessage] = []
        for choice in choices:
            text = getattr(choice, "text", None)
            parts = [Text(content=text)] if isinstance(text, str) else []
            output_messages.append(
                OutputMessage(
                    role="assistant",
                    finish_reason="stop",
                    parts=parts,
                )
            )
        invocation.output_messages = output_messages

    return invocation


__all__ = [
    "_WRITER_PROVIDER",
    "async_chat",
    "async_completions_create",
    "chat",
    "completions_create",
]
