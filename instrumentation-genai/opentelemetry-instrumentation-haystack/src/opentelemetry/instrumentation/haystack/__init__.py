# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Haystack instrumentation supporting `haystack-ai`, it can be enabled by using
``HaystackInstrumentor``.

.. _haystack-ai: https://pypi.org/project/haystack-ai/

Usage
-----

.. code:: python

    from haystack import Pipeline
    from opentelemetry.instrumentation.haystack import HaystackInstrumentor

    HaystackInstrumentor().instrument()

    pipeline = Pipeline()
    # ... add and connect components ...
    result = pipeline.run({"component": {"input": "value"}})

Scope
-----

This instrumentation wraps the Haystack pipeline entry points
``Pipeline.run`` (synchronous) and ``AsyncPipeline.run_async`` (asynchronous)
and maps each pipeline run to a single GenAI *workflow* span
(``invoke_workflow``) emitted through the shared ``opentelemetry-util-genai``
telemetry handler.

It deliberately does **not** wrap the individual generator/embedder components
inside a pipeline. Those components typically delegate to provider SDKs (for
example the ``openai`` package), which are instrumented by their own dedicated
OpenTelemetry instrumentations. Wrapping them here as well would double
-instrument those calls, so component-level telemetry is left to the respective
provider instrumentations.

Configuration
-------------

This instrumentation emits telemetry through the shared
``opentelemetry-util-genai`` telemetry handler using the latest experimental
GenAI semantic conventions:

- ``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`` - opt into the
  latest GenAI semantic conventions. This gates the experimental,
  content-carrying attributes; the workflow span itself is emitted regardless.
- ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` - enable capture of
  message content. Set to one of ``span_only``, ``event_only``,
  ``span_and_event``.

See the `opentelemetry-util-genai README
<https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/util/opentelemetry-util-genai/README.rst>`_
for the full list of GenAI configuration variables.

A custom ``CompletionHook`` implementation can also be passed programmatically::

    HaystackInstrumentor().instrument(completion_hook=my_hook)

When provided, this takes precedence over the hook resolved from
``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK``.

API
---
"""

from __future__ import annotations

from typing import Any, Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.haystack.package import _instruments
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.util.genai.completion_hook import load_completion_hook
from opentelemetry.util.genai.handler import TelemetryHandler

from .patch import pipeline_run, pipeline_run_async

_WORKFLOW_NAME = "haystack.pipeline"


class HaystackInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable Haystack instrumentation."""
        handler = TelemetryHandler(
            tracer_provider=kwargs.get("tracer_provider"),
            meter_provider=kwargs.get("meter_provider"),
            logger_provider=kwargs.get("logger_provider"),
            completion_hook=kwargs.get("completion_hook")
            or load_completion_hook(),
        )

        wrap_function_wrapper(
            "haystack.core.pipeline.pipeline",
            "Pipeline.run",
            pipeline_run(handler, _WORKFLOW_NAME),
        )
        wrap_function_wrapper(
            "haystack.core.pipeline.async_pipeline",
            "AsyncPipeline.run_async",
            pipeline_run_async(handler, _WORKFLOW_NAME),
        )

    def _uninstrument(self, **kwargs: Any) -> None:
        from haystack.core.pipeline.async_pipeline import (  # pylint: disable=import-outside-toplevel  # noqa: PLC0415
            AsyncPipeline,
        )
        from haystack.core.pipeline.pipeline import (  # pylint: disable=import-outside-toplevel  # noqa: PLC0415
            Pipeline,
        )

        unwrap(Pipeline, "run")
        unwrap(AsyncPipeline, "run_async")
