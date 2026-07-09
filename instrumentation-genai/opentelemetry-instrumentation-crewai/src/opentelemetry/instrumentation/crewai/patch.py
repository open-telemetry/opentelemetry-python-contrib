# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, Callable

from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import Error

# CrewAI is not (yet) a member of ``GenAiProviderNameValues`` in the semantic
# conventions, so the provider value is a plain literal until it is added.
_CREWAI_PROVIDER = "crewai"


def _agent_request_model(instance: Any) -> str | None:
    """Read the LLM model configured on a CrewAI ``Agent`` defensively.

    CrewAI agents expose an ``llm`` object (a ``crewai.llm.LLM`` or a
    LiteLLM-backed wrapper) whose ``model`` attribute holds the model name.
    Both ``llm`` and ``model`` may be missing, so introspect defensively and
    return ``None`` when the model cannot be determined.
    """
    model = getattr(getattr(instance, "llm", None), "model", None)
    if model is None:
        return None
    return str(model)


def wrap_kickoff(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Wrap the sync ``crewai.crew.Crew.kickoff`` method as a workflow span."""

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = handler.start_workflow(
            name=getattr(instance, "name", None) or "crew"
        )
        try:
            result = wrapped(*args, **kwargs)
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def wrap_kickoff_async(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Wrap the async ``crewai.crew.Crew.kickoff_async`` method as a workflow span."""

    async def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = handler.start_workflow(
            name=getattr(instance, "name", None) or "crew"
        )
        try:
            result = await wrapped(*args, **kwargs)
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def wrap_agent_execute_task(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Wrap ``crewai.agent.Agent.execute_task`` as an invoke_agent span."""

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = handler.start_invoke_local_agent(
            provider=_CREWAI_PROVIDER,
            agent_name=getattr(instance, "role", None),
            request_model=_agent_request_model(instance),
        )
        try:
            result = wrapped(*args, **kwargs)
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def wrap_tool_run(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Wrap ``crewai.tools.base_tool.BaseTool.run`` as an execute_tool span.

    ``BaseTool.run`` is the shared, public tool-execution entry point that all
    CrewAI tools inherit; it calls the tool's ``_run`` implementation.
    """

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = handler.start_tool(
            name=getattr(instance, "name", None) or "tool",
        )
        try:
            result = wrapped(*args, **kwargs)
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


__all__ = [
    "wrap_agent_execute_task",
    "wrap_kickoff",
    "wrap_kickoff_async",
    "wrap_tool_run",
]
