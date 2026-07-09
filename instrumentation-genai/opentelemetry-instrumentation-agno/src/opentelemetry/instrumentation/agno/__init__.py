# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Agno agent framework instrumentation supporting `agno`, it can be enabled by
using ``AgnoInstrumentor``.

.. _agno: https://pypi.org/project/agno/

Usage
-----

.. code:: python

    from agno.agent import Agent
    from opentelemetry.instrumentation.agno import AgnoInstrumentor

    AgnoInstrumentor().instrument()

    agent = Agent(name="my-agent", model=...)
    response = agent.run("What is the weather in Paris?")

Configuration
-------------

This instrumentation emits telemetry through the shared
``opentelemetry-util-genai`` telemetry handler using the latest experimental
GenAI semantic conventions. It must therefore be enabled with:

- ``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`` - opt into the
  latest GenAI semantic conventions. Without this flag, the instrumentation is
  a no-op (no legacy v1.30.0 path is provided yet).
- ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` - enable capture of
  tool arguments and return values. Set to one of ``span_only``,
  ``event_only``, ``span_and_event``.
- ``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK=upload`` together with
  ``OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH=<fsspec-uri>`` - upload
  prompts and completions to an ``fsspec``-compatible destination.

See the `opentelemetry-util-genai README
<https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/util/opentelemetry-util-genai/README.rst>`_
for the full list of GenAI configuration variables.

A custom ``CompletionHook`` implementation can also be passed programmatically::

    AgnoInstrumentor().instrument(completion_hook=my_hook)

When provided, this takes precedence over the hook resolved from
``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK``.

API
---
"""

from __future__ import annotations

from typing import Any, Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.agno.package import _instruments
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.util.genai.completion_hook import load_completion_hook
from opentelemetry.util.genai.handler import TelemetryHandler

from .patch import agent_arun, agent_run, function_call_execute


class AgnoInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable Agno instrumentation."""
        handler = TelemetryHandler(
            tracer_provider=kwargs.get("tracer_provider"),
            meter_provider=kwargs.get("meter_provider"),
            logger_provider=kwargs.get("logger_provider"),
            completion_hook=kwargs.get("completion_hook")
            or load_completion_hook(),
        )

        wrap_function_wrapper(
            "agno.agent",
            "Agent.run",
            agent_run(handler),
        )
        wrap_function_wrapper(
            "agno.agent",
            "Agent.arun",
            agent_arun(handler),
        )
        wrap_function_wrapper(
            "agno.tools",
            "FunctionCall.execute",
            function_call_execute(handler),
        )

    def _uninstrument(self, **kwargs: Any) -> None:
        import agno.agent  # pylint: disable=import-outside-toplevel  # noqa: PLC0415
        import agno.tools  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        unwrap(agno.agent.Agent, "run")
        unwrap(agno.agent.Agent, "arun")
        unwrap(agno.tools.FunctionCall, "execute")
