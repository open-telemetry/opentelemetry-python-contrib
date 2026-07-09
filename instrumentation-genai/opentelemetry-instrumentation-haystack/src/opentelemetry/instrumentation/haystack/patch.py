# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, Awaitable, Callable

from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import Error


def pipeline_run(
    handler: TelemetryHandler,
    workflow_name: str,
) -> Callable[..., Any]:
    """Build a synchronous ``Pipeline.run`` wrapper emitting a workflow span."""

    def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = handler.start_workflow(name=workflow_name)
        try:
            result = wrapped(*args, **kwargs)
        except Exception as error:  # pylint: disable=broad-except
            invocation.fail(Error(message=str(error), type=type(error)))
            raise
        invocation.stop()
        return result

    return wrapper


def pipeline_run_async(
    handler: TelemetryHandler,
    workflow_name: str,
) -> Callable[..., Awaitable[Any]]:
    """Build an asynchronous ``AsyncPipeline.run_async`` wrapper emitting a workflow span."""

    async def wrapper(
        wrapped: Callable[..., Awaitable[Any]],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = handler.start_workflow(name=workflow_name)
        try:
            result = await wrapped(*args, **kwargs)
        except Exception as error:  # pylint: disable=broad-except
            invocation.fail(Error(message=str(error), type=type(error)))
            raise
        invocation.stop()
        return result

    return wrapper
