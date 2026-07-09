# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, Callable

from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.invocation import InferenceInvocation
from opentelemetry.util.genai.types import Error

from .stream_wrappers import (
    ReplicateAsyncStreamWrapper,
    ReplicateStreamWrapper,
)
from .utils import (
    _REPLICATE_PROVIDER,
    create_inference_invocation,
    prepare_output_messages,
)


def _set_response_properties(
    invocation: InferenceInvocation, output: Any, capture_content: bool
) -> None:
    invocation.finish_reasons = ["stop"]
    if capture_content:  # optimization
        invocation.output_messages = prepare_output_messages(output)


def run_v_new(handler: TelemetryHandler) -> Callable[..., Any]:
    """Wrap the sync ``Client.run`` on the experimental semconv path."""
    capture_content = handler.should_capture_content()

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_inference_invocation(
            handler, args, kwargs, instance, capture_content=capture_content
        )
        try:
            result = wrapped(*args, **kwargs)
            _set_response_properties(invocation, result, capture_content)
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def async_run_v_new(handler: TelemetryHandler) -> Callable[..., Any]:
    """Wrap the async ``Client.async_run`` on the experimental semconv path."""
    capture_content = handler.should_capture_content()

    async def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_inference_invocation(
            handler, args, kwargs, instance, capture_content=capture_content
        )
        try:
            result = await wrapped(*args, **kwargs)
            _set_response_properties(invocation, result, capture_content)
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def stream_v_new(handler: TelemetryHandler) -> Callable[..., Any]:
    """Wrap the sync ``Client.stream`` on the experimental semconv path."""
    capture_content = handler.should_capture_content()

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_inference_invocation(
            handler, args, kwargs, instance, capture_content=capture_content
        )
        try:
            result = wrapped(*args, **kwargs)
            return ReplicateStreamWrapper(result, invocation, capture_content)
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def async_stream_v_new(handler: TelemetryHandler) -> Callable[..., Any]:
    """Wrap the async ``Client.async_stream`` on the experimental path.

    ``Client.async_stream`` is a coroutine that returns the async generator, so
    the wrapped call is awaited before the resulting stream is wrapped.
    """
    capture_content = handler.should_capture_content()

    async def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_inference_invocation(
            handler, args, kwargs, instance, capture_content=capture_content
        )
        try:
            result = await wrapped(*args, **kwargs)
            return ReplicateAsyncStreamWrapper(
                result, invocation, capture_content
            )
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


# `_REPLICATE_PROVIDER` is re-exported for symmetry with the sibling
# instrumentation packages' layout.
__all__ = [
    "_REPLICATE_PROVIDER",
    "async_run_v_new",
    "async_stream_v_new",
    "run_v_new",
    "stream_v_new",
]
