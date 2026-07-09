# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Wrapper factories bridging Agno callables to the shared GenAI telemetry handler."""

from __future__ import annotations

import inspect
from typing import Any, Callable

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import Error

# ``agno`` is the provider name for agent spans. There is no matching
# ``GenAiProviderNameValues`` member, so the literal string is used directly.
_PROVIDER = "agno"


def _fail(invocation: Any, exc: BaseException) -> None:
    invocation.fail(Error(type=type(exc), message=str(exc)))


def _finalize_sync_stream(stream: Any, invocation: Any) -> Any:
    """Passthrough a streaming ``run`` result, ending the span when it finishes.

    ``Agent.run(stream=True)`` returns an iterator; the span must stay open
    until iteration completes, errors, or the caller closes it early.
    """
    failed = False
    try:
        yield from stream
    except Exception as exc:  # pylint: disable=broad-except
        failed = True
        _fail(invocation, exc)
        raise
    finally:
        if not failed:
            invocation.stop()


async def _finalize_async_stream(stream: Any, invocation: Any) -> Any:
    """Passthrough a streaming ``arun`` result (an async generator)."""
    failed = False
    try:
        async for item in stream:
            yield item
    except Exception as exc:  # pylint: disable=broad-except
        failed = True
        _fail(invocation, exc)
        raise
    finally:
        if not failed:
            invocation.stop()


async def _finalize_coro(awaitable: Any, invocation: Any) -> Any:
    """Await a non-streaming ``arun`` coroutine and end its span."""
    try:
        result = await awaitable
    except Exception as exc:  # pylint: disable=broad-except
        _fail(invocation, exc)
        raise
    invocation.stop()
    return result


def _agent_model_id(instance: Any) -> str | None:
    """Read the agent's model id defensively (``instance.model.id``)."""
    return getattr(getattr(instance, "model", None), "id", None)


def _agent_name(instance: Any) -> str | None:
    """Read the agent's name defensively (``instance.name``)."""
    return getattr(instance, "name", None)


def _tool_name(instance: Any) -> str:
    """Read the tool name defensively (``instance.function.name``)."""
    name = getattr(getattr(instance, "function", None), "name", None)
    return name if isinstance(name, str) and name else "unknown"


def agent_run(
    handler: TelemetryHandler,
) -> Callable[[Callable[..., Any], Any, tuple[Any, ...], dict[str, Any]], Any]:
    """Build a wrapt wrapper for the synchronous ``Agent.run`` method."""

    def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = handler.start_invoke_local_agent(
            provider=_PROVIDER,
            request_model=_agent_model_id(instance),
            agent_name=_agent_name(instance),
        )
        try:
            result = wrapped(*args, **kwargs)
        except Exception as exc:  # pylint: disable=broad-except
            _fail(invocation, exc)
            raise
        if inspect.isgenerator(result):
            # Streaming run returns a generator (agno enables streaming from
            # the stream kwarg or the agent-level ``stream`` default); keep the
            # span open until it is consumed instead of stopping before any
            # work happens.
            return _finalize_sync_stream(result, invocation)
        invocation.stop()
        return result

    return wrapper


def agent_arun(
    handler: TelemetryHandler,
) -> Callable[[Callable[..., Any], Any, tuple[Any, ...], dict[str, Any]], Any]:
    """Build a wrapt wrapper for the asynchronous ``Agent.arun`` method.

    ``Agent.arun`` is a plain function that returns a coroutine when
    ``stream=False`` and an async generator when ``stream=True``. The wrapper
    mirrors that: it is a sync function so the streaming call still returns an
    async iterator (awaiting an async generator raises ``TypeError``).
    """

    def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = handler.start_invoke_local_agent(
            provider=_PROVIDER,
            request_model=_agent_model_id(instance),
            agent_name=_agent_name(instance),
        )
        try:
            result = wrapped(*args, **kwargs)
        except Exception as exc:  # pylint: disable=broad-except
            _fail(invocation, exc)
            raise
        if inspect.isasyncgen(result):
            # Streaming arun returns an async generator (agno enables streaming
            # from the stream kwarg or the agent-level ``stream`` default);
            # awaiting it would raise TypeError.
            return _finalize_async_stream(result, invocation)
        return _finalize_coro(result, invocation)

    return wrapper


def function_call_execute(
    handler: TelemetryHandler,
) -> Callable[[Callable[..., Any], Any, tuple[Any, ...], dict[str, Any]], Any]:
    """Build a wrapt wrapper for the synchronous ``FunctionCall.execute`` method."""
    capture_content = handler.should_capture_content()

    def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = handler.start_tool(name=_tool_name(instance))
        try:
            result = wrapped(*args, **kwargs)
            if capture_content:
                invocation.tool_result = result
                invocation.attributes[GenAI.GEN_AI_TOOL_CALL_RESULT] = str(
                    result
                )
            invocation.stop()
            return result
        except Exception as exc:  # pylint: disable=broad-except
            invocation.fail(Error(type=type(exc), message=str(exc)))
            raise

    return wrapper
