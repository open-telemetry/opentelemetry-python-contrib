# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, Callable

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import Error
from opentelemetry.util.genai.utils import gen_ai_json_dumps


def _get_tool_name(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """Extract the tool ``name`` argument from ``ClientSession.call_tool``.

    ``call_tool(self, name, arguments=None, ...)`` is wrapped by ``wrapt``, so
    ``self`` is passed separately as ``instance`` and ``name`` is the first
    positional argument.
    """
    if args:
        return str(args[0])
    return str(kwargs.get("name", ""))


def _get_tool_arguments(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    """Extract the ``arguments`` argument from ``ClientSession.call_tool``."""
    if len(args) > 1:
        return args[1]
    return kwargs.get("arguments")


def _serialize(value: Any) -> str:
    """Serialize a value to a span-compatible string attribute.

    Falls back to ``str`` for values the GenAI JSON encoder cannot handle,
    never raising from telemetry code.
    """
    try:
        return gen_ai_json_dumps(value)
    except (TypeError, ValueError):
        return str(value)


def call_tool(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Build a ``wrapt`` wrapper for the async ``ClientSession.call_tool``.

    Emits an ``execute_tool`` GenAI span per client-side MCP tool call via the
    shared ``opentelemetry-util-genai`` telemetry handler.
    """
    capture_content = handler.should_capture_content()

    async def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        name = _get_tool_name(args, kwargs)
        arguments = (
            _get_tool_arguments(args, kwargs) if capture_content else None
        )
        invocation = handler.start_tool(
            name=name,
            arguments=_serialize(arguments) if arguments is not None else None,
        )
        try:
            result = await wrapped(*args, **kwargs)
            if capture_content:
                invocation.attributes[GenAI.GEN_AI_TOOL_CALL_RESULT] = (
                    _serialize(result)
                )
            invocation.stop()
            return result
        except Exception as error:  # pylint: disable=broad-except
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


__all__ = ["call_tool"]
