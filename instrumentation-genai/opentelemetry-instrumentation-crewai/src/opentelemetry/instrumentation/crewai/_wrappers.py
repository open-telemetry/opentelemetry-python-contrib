# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Method wrappers that turn CrewAI execution into GenAI telemetry.

Each public ``wrap_*`` function here is bound with a closure to a
``TelemetryHandler`` in :mod:`opentelemetry.instrumentation.crewai` and
installed with ``wrapt.wrap_function_wrapper``. They all follow the same
shape: start an invocation via the handler, set what fields are available
before calling the wrapped method, call it, set the remaining fields from
the result, and on exception fail the invocation and re-raise unmodified.

Telemetry emission itself (spans, metrics, events, content-capture gating)
is owned entirely by ``opentelemetry-util-genai``'s ``TelemetryHandler`` --
this module never touches a ``Tracer``, ``Meter``, or ``Logger`` directly,
per the GenAI instrumentation review rules.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import TYPE_CHECKING, Any, Callable

from opentelemetry.trace import SpanContext
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.invocation import (
    AgentInvocation,
    Error,
    InferenceInvocation,
)
from opentelemetry.util.genai.types import InputMessage, OutputMessage, Text

if TYPE_CHECKING:
    from crewai import Agent, Crew, Task
    from crewai.tools import BaseTool

# ---------------------------------------------------------------------------
# crew.kickoff -> WorkflowInvocation
# ---------------------------------------------------------------------------


def wrap_crew_kickoff(
    handler: TelemetryHandler,
) -> Callable[
    [Callable[..., Any], Crew, tuple[Any, ...], dict[str, Any]], Any
]:
    """Build the wrapper for ``Crew.kickoff``.

    Only the synchronous ``kickoff`` is patched. ``Crew.kickoff_async``
    delegates to ``self.kickoff`` via ``asyncio.to_thread`` (which copies the
    current ``contextvars.Context`` into the worker thread), so patching
    both would double-count every async run as two nested workflow spans.
    Patching only the sync method covers both entry points correctly.
    """

    def _wrap_crew_kickoff(
        wrapped: Callable[..., Any],
        instance: Crew,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        agents: list[Any] = getattr(instance, "agents", None) or []
        tasks: list[Any] = getattr(instance, "tasks", None) or []
        process = getattr(instance, "process", None)

        invocation = handler.start_workflow(name="crew.kickoff")
        invocation.attributes["crewai.crew.id"] = str(
            getattr(instance, "id", "")
        )
        invocation.attributes["crewai.crew.process"] = (
            getattr(process, "value", str(process)) if process else ""
        )
        invocation.attributes["crewai.crew.agent_count"] = len(agents)
        invocation.attributes["crewai.crew.task_count"] = len(tasks)

        _reset_handoff_state(instance)
        try:
            result = wrapped(*args, **kwargs)
        except Exception as exc:
            invocation.fail(Error(type=type(exc), message=str(exc)))
            raise
        finally:
            _clear_handoff_state(instance)

        invocation.stop()
        return result

    return _wrap_crew_kickoff


# ---------------------------------------------------------------------------
# agent.execute_task -> AgentInvocation (local, INTERNAL span kind)
# + opt-in prompt capture, + handoff links
# ---------------------------------------------------------------------------

# Per-crew-run handoff tracking: id(crew) -> {id(task): SpanContext of the
# agent invocation that produced that task's output}. Kept on the
# instrumentation module rather than on the crewai objects themselves,
# because Crew/Task/Agent are pydantic models that reject arbitrary
# attribute assignment.
_handoff_spans: dict[int, dict[int, SpanContext]] = {}
_handoff_lock = threading.Lock()


def _reset_handoff_state(crew: Crew) -> None:
    with _handoff_lock:
        _handoff_spans[id(crew)] = {}


def _clear_handoff_state(crew: Crew) -> None:
    with _handoff_lock:
        _handoff_spans.pop(id(crew), None)


def _record_handoff_span(
    crew: Crew | None, task: Task, span_context: SpanContext
) -> None:
    if crew is None or isinstance(crew, str):
        return
    with _handoff_lock:
        crew_spans = _handoff_spans.get(id(crew))
        if crew_spans is not None:
            crew_spans[id(task)] = span_context


def _resolve_handoff_span_contexts(
    crew: Crew | None, task: Task
) -> list[SpanContext]:
    """Resolve the span contexts representing a handoff into ``task``.

    Mirrors ``Crew._get_context``: an explicit ``task.context`` list links
    only to those specific prior tasks; the default "not specified" sentinel
    links to every task executed so far in this crew run (matching CrewAI's
    own default of aggregating every prior task output); an explicit
    ``None``/empty list means no handoff at all.
    """
    if crew is None or isinstance(crew, str):
        return []
    with _handoff_lock:
        crew_spans = _handoff_spans.get(id(crew))
        if not crew_spans:
            return []

        task_context = getattr(task, "context", None)
        if not task_context:
            return []

        try:
            from crewai.utilities.constants import (  # noqa: PLC0415
                NOT_SPECIFIED,
            )

            context_is_not_specified = task_context is NOT_SPECIFIED
        except ImportError:
            context_is_not_specified = False  # pragma: no cover - defensive

        if context_is_not_specified:
            source_task_ids = list(crew_spans.keys())
        else:
            source_task_ids = [id(t) for t in task_context]

        return [
            crew_spans[task_id]
            for task_id in source_task_ids
            if task_id in crew_spans
        ]


def wrap_agent_execute_task(
    handler: TelemetryHandler,
) -> Callable[
    [Callable[..., Any], Agent, tuple[Any, ...], dict[str, Any]], Any
]:
    """Build the wrapper for ``Agent.execute_task``."""
    capture_content = handler.should_capture_content()

    def _wrap_agent_execute_task(
        wrapped: Callable[..., Any],
        instance: Agent,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        task: Task | None = args[0] if args else kwargs.get("task")
        crew = getattr(instance, "crew", None)
        role = getattr(instance, "role", "") or ""

        invocation: AgentInvocation = handler.start_invoke_local_agent(
            "crewai", agent_name=role or None
        )
        invocation.attributes["crewai.agent.role"] = role
        if task is not None:
            invocation.attributes["crewai.task.description"] = str(
                getattr(task, "description", "")
            )
            for link_context in _resolve_handoff_span_contexts(crew, task):
                invocation.span.add_link(link_context)

            if capture_content:
                task_context = (
                    args[1] if len(args) > 1 else kwargs.get("context")
                )
                if task_context:
                    invocation.input_messages = [
                        InputMessage(
                            role="user",
                            parts=[Text(content=str(task_context))],
                        )
                    ]

        try:
            result = wrapped(*args, **kwargs)
        except Exception as exc:
            invocation.fail(Error(type=type(exc), message=str(exc)))
            raise

        if capture_content:
            invocation.output_messages = [
                OutputMessage(
                    role="assistant",
                    parts=[Text(content=str(result))],
                    finish_reason="stop",
                )
            ]

        invocation.stop()

        if task is not None:
            _record_handoff_span(
                crew, task, invocation.span.get_span_context()
            )
        return result

    return _wrap_agent_execute_task


# ---------------------------------------------------------------------------
# llm.call -> InferenceInvocation
# ---------------------------------------------------------------------------

# LLM.call() only returns text (or a tool result) -- usage, finish_reason,
# and the resolved model aren't in that return value, they're only on the
# LLMCallCompletedEvent CrewAI emits from inside the call. That emit() is
# fire-and-forget (crewai_event_bus dispatches sync handlers on a
# ThreadPoolExecutor and does not wait for them -- see
# CrewAIEventsBus.emit()), so there is no guarantee the event has already
# been handled by the time the wrapped call() returns. We correlate by
# id(instance) (the handler's ``source`` argument is the same LLM instance
# our wrapper is closed over) and wait briefly with a threading.Event,
# rather than relying on contextvars, which would not propagate a value set
# inside a different worker thread back to the caller's context.
#
# Each instance maps to a FIFO queue of waiters, not a single slot: CrewAI
# gives each agent its own LLM instance by default, so in the common case
# there's one waiter per instance and the queue never holds more than one
# entry. But if a user shares one LLM object across agents/tasks that run
# concurrently, two calls on the *same* instance can be in flight at once;
# a single overwritable slot would let the second call's registration clobber
# the first's, delivering the wrong usage data to the wrong span. A queue
# means overlapping calls each get their own waiter instead of colliding.
# This still assumes completion events arrive in the same order calls were
# dispatched, which holds unless two concurrent calls on one shared instance
# finish out of order -- a narrow edge case that's a documented limitation,
# not a crash: attributes just end up on the wrong (but still valid)
# invocation.
_pending_llm_calls: dict[int, deque[tuple[threading.Event, list[Any]]]] = {}
_pending_lock = threading.Lock()
_LLM_EVENT_WAIT_SECONDS = 2.0


def on_llm_call_completed(source: Any, event: Any) -> None:
    """crewai_event_bus listener: hand a completed call's usage/finish data
    to the oldest still-waiting ``wrap_llm_call`` invocation for this
    instance."""
    with _pending_lock:
        queue = _pending_llm_calls.get(id(source))
        entry = queue.popleft() if queue else None
    if entry is not None:
        wait_event, holder = entry
        holder.append(event)
        wait_event.set()


def wrap_llm_call(
    handler: TelemetryHandler,
) -> Callable[[Callable[..., Any], Any, tuple[Any, ...], dict[str, Any]], Any]:
    """Build the wrapper for ``LLM.call``."""
    capture_content = handler.should_capture_content()

    def _wrap_llm_call(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        messages = args[0] if args else kwargs.get("messages")
        provider = str(
            getattr(instance, "provider", None)
            or getattr(instance, "model", "")
        )
        request_model = str(getattr(instance, "model", ""))

        invocation: InferenceInvocation = handler.start_inference(
            provider, request_model=request_model
        )
        if capture_content and messages is not None:
            invocation.input_messages = [
                InputMessage(role="user", parts=[Text(content=str(messages))])
            ]

        wait_event = threading.Event()
        holder: list[Any] = []
        entry = (wait_event, holder)
        with _pending_lock:
            _pending_llm_calls.setdefault(id(instance), deque()).append(entry)
        try:
            result = wrapped(*args, **kwargs)
        except Exception as exc:
            with _pending_lock:
                _discard_pending_entry(id(instance), entry)
            invocation.fail(Error(type=type(exc), message=str(exc)))
            raise

        # Success path only: emit() dispatches the completion event to a
        # thread pool asynchronously, so it may not have arrived yet even
        # though call() itself has already returned. Wait briefly, then
        # stop listening for it either way.
        wait_event.wait(timeout=_LLM_EVENT_WAIT_SECONDS)
        with _pending_lock:
            _discard_pending_entry(id(instance), entry)
        completed_event = holder[0] if holder else None
        _apply_llm_response(invocation, completed_event)

        if capture_content:
            finish_reason = (
                invocation.finish_reasons[0]
                if invocation.finish_reasons
                else "stop"
            )
            invocation.output_messages = [
                OutputMessage(
                    role="assistant",
                    parts=[Text(content=str(result))],
                    finish_reason=finish_reason,
                )
            ]

        invocation.stop()
        return result

    return _wrap_llm_call


def _discard_pending_entry(
    instance_id: int, entry: tuple[threading.Event, list[Any]]
) -> None:
    """Remove ``entry`` from its instance's waiter queue if it's still there
    (already-serviced entries are gone) and drop the queue once it's empty,
    so ``_pending_llm_calls`` never accumulates stale keys."""
    queue = _pending_llm_calls.get(instance_id)
    if queue is None:
        return
    try:
        queue.remove(entry)
    except ValueError:
        pass  # already popped by on_llm_call_completed
    if not queue:
        del _pending_llm_calls[instance_id]


def _apply_llm_response(invocation: InferenceInvocation, event: Any) -> None:
    if event is None:
        return
    usage: dict[str, Any] = getattr(event, "usage", None) or {}
    input_tokens: int | None = usage.get("prompt_tokens")
    output_tokens: int | None = usage.get("completion_tokens")
    if input_tokens is not None:
        invocation.input_tokens = input_tokens
    if output_tokens is not None:
        invocation.output_tokens = output_tokens
    finish_reason = getattr(event, "finish_reason", None)
    if finish_reason:
        invocation.finish_reasons = [str(finish_reason)]


# ---------------------------------------------------------------------------
# tool.call -> ToolInvocation
# ---------------------------------------------------------------------------


def wrap_tool_run(
    handler: TelemetryHandler,
) -> Callable[
    [Callable[..., Any], BaseTool, tuple[Any, ...], dict[str, Any]], Any
]:
    """Build the wrapper for ``BaseTool.run``.

    ``run`` (not ``_run``) is the stable public entry point: every tool
    subclass implements ``_run`` differently, but ``run`` is the single
    common method every tool call passes through.
    """
    capture_content = handler.should_capture_content()

    def _wrap_tool_run(
        wrapped: Callable[..., Any],
        instance: BaseTool,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = handler.start_tool(
            getattr(instance, "name", "") or "",
            arguments={"args": args, "kwargs": kwargs}
            if capture_content
            else None,
        )
        try:
            result = wrapped(*args, **kwargs)
        except Exception as exc:
            invocation.fail(Error(type=type(exc), message=str(exc)))
            raise

        if capture_content:
            invocation.tool_result = result

        invocation.stop()
        return result

    return _wrap_tool_run
