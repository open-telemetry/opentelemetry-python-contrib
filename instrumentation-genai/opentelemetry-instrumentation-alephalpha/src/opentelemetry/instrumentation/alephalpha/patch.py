# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, Callable

from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import Error

from .utils import (
    _ALEPH_ALPHA_PROVIDER,
    create_chat_invocation,
    set_response_properties,
)


def complete(handler: TelemetryHandler) -> Callable[..., Any]:
    """Wrap the sync ``Client.complete`` method."""
    capture_content = handler.should_capture_content()

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_chat_invocation(
            handler, args, kwargs, instance, capture_content=capture_content
        )
        try:
            result = wrapped(*args, **kwargs)
            set_response_properties(invocation, result, capture_content)
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def async_complete(handler: TelemetryHandler) -> Callable[..., Any]:
    """Wrap the async ``AsyncClient.complete`` method."""
    capture_content = handler.should_capture_content()

    async def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_chat_invocation(
            handler, args, kwargs, instance, capture_content=capture_content
        )
        try:
            result = await wrapped(*args, **kwargs)
            set_response_properties(invocation, result, capture_content)
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


__all__ = [
    "_ALEPH_ALPHA_PROVIDER",
    "async_complete",
    "complete",
]
