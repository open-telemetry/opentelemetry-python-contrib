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

from .chat_wrappers import AsyncV2ChatStreamWrapper, V2ChatStreamWrapper
from .utils import (
    _COHERE_PROVIDER,
    create_chat_invocation,
    create_embedding_invocation,
    get_property_value,
    prepare_output_messages_v1,
    prepare_output_messages_v2,
)

__all__ = [
    "_COHERE_PROVIDER",
    "async_chat_v1",
    "async_chat_v2",
    "async_chat_stream_v2",
    "async_embed",
    "chat_v1",
    "chat_v2",
    "chat_stream_v2",
    "embed",
]


def _set_chat_v2_response(
    invocation: InferenceInvocation, response: Any, capture_content: bool
) -> None:
    response_id = get_property_value(response, "id")
    if response_id:
        invocation.response_id = response_id

    finish_reason = get_property_value(response, "finish_reason")
    if finish_reason:
        invocation.finish_reasons = [str(finish_reason)]

    usage = get_property_value(response, "usage")
    input_tokens, output_tokens = _billed_tokens(usage)
    if input_tokens is not None:
        invocation.input_tokens = input_tokens
    if output_tokens is not None:
        invocation.output_tokens = output_tokens

    if capture_content:  # optimization
        invocation.output_messages = prepare_output_messages_v2(response)


def _set_chat_v1_response(
    invocation: InferenceInvocation, response: Any, capture_content: bool
) -> None:
    response_id = get_property_value(response, "response_id")
    if response_id:
        invocation.response_id = response_id

    finish_reason = get_property_value(response, "finish_reason")
    if finish_reason:
        invocation.finish_reasons = [str(finish_reason)]

    meta = get_property_value(response, "meta")
    input_tokens, output_tokens = _billed_tokens(meta)
    if input_tokens is not None:
        invocation.input_tokens = input_tokens
    if output_tokens is not None:
        invocation.output_tokens = output_tokens

    if capture_content:  # optimization
        invocation.output_messages = prepare_output_messages_v1(response)


def _set_embedding_response(
    invocation: EmbeddingInvocation, response: Any
) -> None:
    meta = get_property_value(response, "meta")
    billed_units = get_property_value(meta, "billed_units")
    input_tokens = get_property_value(billed_units, "input_tokens")
    if input_tokens is not None:
        invocation.input_tokens = int(input_tokens)

    embeddings = get_property_value(response, "embeddings")
    # V2 returns an object with a ``float_`` attribute; V1 returns the vectors
    # as a plain list, so fall back to the list-shaped response.
    vectors = get_property_value(embeddings, "float_")
    if vectors is None and isinstance(embeddings, (list, tuple)):
        vectors = embeddings
    if vectors and isinstance(vectors[0], (list, tuple)):
        invocation.dimension_count = len(vectors[0])


def _billed_tokens(usage: Any) -> tuple[int | None, int | None]:
    billed_units = get_property_value(usage, "billed_units")
    if billed_units is None:
        return None, None
    input_tokens = get_property_value(billed_units, "input_tokens")
    output_tokens = get_property_value(billed_units, "output_tokens")
    return (
        int(input_tokens) if input_tokens is not None else None,
        int(output_tokens) if output_tokens is not None else None,
    )


# --- Chat (non-streaming) ---------------------------------------------------


def chat_v2(handler: TelemetryHandler) -> Callable[..., Any]:
    capture_content = handler.should_capture_content()

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_chat_invocation(
            handler, kwargs, instance, capture_content=capture_content
        )
        try:
            response = wrapped(*args, **kwargs)
            _set_chat_v2_response(invocation, response, capture_content)
            invocation.stop()
            return response
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def async_chat_v2(handler: TelemetryHandler) -> Callable[..., Any]:
    capture_content = handler.should_capture_content()

    async def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_chat_invocation(
            handler, kwargs, instance, capture_content=capture_content
        )
        try:
            response = await wrapped(*args, **kwargs)
            _set_chat_v2_response(invocation, response, capture_content)
            invocation.stop()
            return response
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def chat_v1(handler: TelemetryHandler) -> Callable[..., Any]:
    capture_content = handler.should_capture_content()

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_chat_invocation(
            handler, kwargs, instance, capture_content=capture_content
        )
        try:
            response = wrapped(*args, **kwargs)
            _set_chat_v1_response(invocation, response, capture_content)
            invocation.stop()
            return response
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def async_chat_v1(handler: TelemetryHandler) -> Callable[..., Any]:
    capture_content = handler.should_capture_content()

    async def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_chat_invocation(
            handler, kwargs, instance, capture_content=capture_content
        )
        try:
            response = await wrapped(*args, **kwargs)
            _set_chat_v1_response(invocation, response, capture_content)
            invocation.stop()
            return response
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


# --- Chat (streaming, V2 only) ----------------------------------------------


def chat_stream_v2(handler: TelemetryHandler) -> Callable[..., Any]:
    capture_content = handler.should_capture_content()

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_chat_invocation(
            handler, kwargs, instance, capture_content=capture_content
        )
        try:
            stream = wrapped(*args, **kwargs)
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise
        return V2ChatStreamWrapper(stream, invocation, capture_content)

    return traced_method


def async_chat_stream_v2(handler: TelemetryHandler) -> Callable[..., Any]:
    capture_content = handler.should_capture_content()

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        # Cohere's async ``chat_stream`` returns an async generator directly
        # (it is not a coroutine), so it is wrapped without awaiting.
        invocation = create_chat_invocation(
            handler, kwargs, instance, capture_content=capture_content
        )
        try:
            stream = wrapped(*args, **kwargs)
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise
        return AsyncV2ChatStreamWrapper(stream, invocation, capture_content)

    return traced_method


# --- Embeddings -------------------------------------------------------------


def embed(handler: TelemetryHandler) -> Callable[..., Any]:
    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_embedding_invocation(handler, kwargs, instance)
        try:
            response = wrapped(*args, **kwargs)
            _set_embedding_response(invocation, response)
            invocation.response_model_name = get_property_value(
                response, "model"
            )
            invocation.stop()
            return response
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def async_embed(handler: TelemetryHandler) -> Callable[..., Any]:
    async def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_embedding_invocation(handler, kwargs, instance)
        try:
            response = await wrapped(*args, **kwargs)
            _set_embedding_response(invocation, response)
            invocation.response_model_name = get_property_value(
                response, "model"
            )
            invocation.stop()
            return response
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method
