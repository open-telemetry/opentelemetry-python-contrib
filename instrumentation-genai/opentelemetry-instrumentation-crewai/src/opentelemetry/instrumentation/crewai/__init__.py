# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
CrewAI instrumentation supporting `crewai`, it can be enabled by using
``CrewAIInstrumentor``.

.. _crewai: https://pypi.org/project/crewai/

Usage
-----

.. code:: python

    from crewai import Agent, Crew, Task
    from opentelemetry.instrumentation.crewai import CrewAIInstrumentor

    CrewAIInstrumentor().instrument()

    crew = Crew(agents=[...], tasks=[...])
    result = crew.kickoff()

The instrumentation emits standard GenAI telemetry through the shared
``opentelemetry-util-genai`` telemetry handler:

- an ``invoke_workflow`` span for each ``Crew.kickoff`` / ``Crew.kickoff_async``,
- an ``invoke_agent`` span for each ``Agent.execute_task``,
- an ``execute_tool`` span for each tool execution (``BaseTool.run``).

The underlying LLM call (``crewai.llm.LLM.call``) is intentionally not wrapped
here to avoid double-instrumenting the underlying model provider; instrument the
provider SDK (or LiteLLM) directly for chat/inference spans.

Configuration
-------------

This instrumentation emits telemetry through the shared
``opentelemetry-util-genai`` telemetry handler using the latest experimental
GenAI semantic conventions. It must therefore be enabled with:

- ``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`` - opt into the
  latest GenAI semantic conventions. Without this flag, the instrumentation is
  a no-op (no legacy v1.30.0 path is provided yet).
- ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` - enable capture of
  prompts, completions, tool arguments, and return values. Set to one of
  ``span_only``, ``event_only``, ``span_and_event``.
- ``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK=upload`` together with
  ``OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH=<fsspec-uri>`` - upload
  prompts and completions to an ``fsspec``-compatible destination.

See the `opentelemetry-util-genai README
<https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/util/opentelemetry-util-genai/README.rst>`_
for the full list of GenAI configuration variables.

A custom ``CompletionHook`` implementation can also be passed programmatically::

    CrewAIInstrumentor().instrument(completion_hook=my_hook)

When provided, this takes precedence over the hook resolved from
``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK``.

API
---
"""

from __future__ import annotations

from typing import Any, Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.crewai.package import _instruments
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.util.genai.completion_hook import load_completion_hook
from opentelemetry.util.genai.handler import TelemetryHandler

from .patch import (
    wrap_agent_execute_task,
    wrap_kickoff,
    wrap_kickoff_async,
    wrap_tool_run,
)


class CrewAIInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable CrewAI instrumentation."""
        handler = TelemetryHandler(
            tracer_provider=kwargs.get("tracer_provider"),
            meter_provider=kwargs.get("meter_provider"),
            logger_provider=kwargs.get("logger_provider"),
            completion_hook=kwargs.get("completion_hook")
            or load_completion_hook(),
        )

        wrap_function_wrapper(
            "crewai.crew",
            "Crew.kickoff",
            wrap_kickoff(handler),
        )
        wrap_function_wrapper(
            "crewai.crew",
            "Crew.kickoff_async",
            wrap_kickoff_async(handler),
        )
        wrap_function_wrapper(
            "crewai.agent",
            "Agent.execute_task",
            wrap_agent_execute_task(handler),
        )
        wrap_function_wrapper(
            "crewai.tools.base_tool",
            "BaseTool.run",
            wrap_tool_run(handler),
        )

    def _uninstrument(self, **kwargs: Any) -> None:
        import crewai  # pylint: disable=import-outside-toplevel  # noqa: PLC0415
        from crewai.tools.base_tool import (  # pylint: disable=import-outside-toplevel  # noqa: PLC0415
            BaseTool,
        )

        unwrap(crewai.crew.Crew, "kickoff")
        unwrap(crewai.crew.Crew, "kickoff_async")
        unwrap(crewai.agent.Agent, "execute_task")
        unwrap(BaseTool, "run")
