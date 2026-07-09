# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Wrappers bridging LlamaIndex tool execution to ``opentelemetry-util-genai``.

The wrappers here translate calls to :class:`llama_index.core.tools.FunctionTool`
into standard GenAI ``execute_tool`` spans via the shared
:class:`~opentelemetry.util.genai.handler.TelemetryHandler`.
"""

from __future__ import annotations

from typing import Any, Callable

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.invocation import ToolInvocation
from opentelemetry.util.genai.types import Error
from opentelemetry.util.genai.utils import gen_ai_json_dumps

# Type classification per the GenAI semantic conventions for a locally executed
# function tool.
_TOOL_TYPE_FUNCTION = "function"


def _tool_name(instance: Any) -> str | None:
    """Return the tool name from a ``FunctionTool`` instance, if available."""
    metadata = getattr(instance, "metadata", None)
    if metadata is None:
        return None
    return getattr(metadata, "name", None)


def _tool_description(instance: Any) -> str | None:
    """Return the tool description from a ``FunctionTool`` instance, if available."""
    metadata = getattr(instance, "metadata", None)
    if metadata is None:
        return None
    return getattr(metadata, "description", None)


def _arguments(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """Serialize the positional and keyword call arguments into a JSON string.

    The shared ``ToolInvocation`` records ``gen_ai.tool.call.arguments`` verbatim,
    and span attributes must be primitive values, so serialization happens here.
    """
    payload: dict[str, Any] = dict(kwargs)
    if args:
        payload["args"] = list(args)
    try:
        return gen_ai_json_dumps(payload)
    except (TypeError, ValueError):
        # Never raise from telemetry code if an argument isn't serializable.
        return str(payload)


def _result_value(result: Any) -> Any:
    """Extract the underlying value from a LlamaIndex ``ToolOutput``."""
    raw_output = getattr(result, "raw_output", None)
    if raw_output is not None:
        return raw_output
    return str(result)


def _start_tool(
    handler: TelemetryHandler,
    instance: Any,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    capture_content: bool,
) -> ToolInvocation:
    name = _tool_name(instance)
    invocation = handler.start_tool(
        name=name if name is not None else "",
        arguments=_arguments(args, kwargs) if capture_content else None,
        tool_type=_TOOL_TYPE_FUNCTION,
        tool_description=_tool_description(instance),
    )
    return invocation


def _finish_tool(
    invocation: ToolInvocation,
    result: Any,
    capture_content: bool,
) -> None:
    value = _result_value(result)
    invocation.tool_result = value
    if capture_content:
        invocation.attributes[GenAI.GEN_AI_TOOL_CALL_RESULT] = str(value)
    invocation.stop()


def function_tool_call(
    handler: TelemetryHandler, capture_content: bool
) -> Callable[..., Any]:
    """Build a sync wrapper for ``FunctionTool.call``."""

    def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = _start_tool(
            handler, instance, args, kwargs, capture_content
        )
        try:
            result = wrapped(*args, **kwargs)
        except Exception as error:  # pylint: disable=broad-except
            invocation.fail(Error(type=type(error), message=str(error)))
            raise
        _finish_tool(invocation, result, capture_content)
        return result

    return wrapper


def function_tool_acall(
    handler: TelemetryHandler, capture_content: bool
) -> Callable[..., Any]:
    """Build an async wrapper for ``FunctionTool.acall``."""

    async def wrapper(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = _start_tool(
            handler, instance, args, kwargs, capture_content
        )
        try:
            result = await wrapped(*args, **kwargs)
        except Exception as error:  # pylint: disable=broad-except
            invocation.fail(Error(type=type(error), message=str(error)))
            raise
        _finish_tool(invocation, result, capture_content)
        return result

    return wrapper
