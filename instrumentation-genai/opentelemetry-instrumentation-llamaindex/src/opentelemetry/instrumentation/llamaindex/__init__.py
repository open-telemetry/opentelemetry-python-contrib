# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
LlamaIndex instrumentation supporting `llama-index-core`, it can be enabled by
using ``LlamaIndexInstrumentor``.

.. _llama-index-core: https://pypi.org/project/llama-index-core/

Usage
-----

.. code:: python

    from llama_index.core.tools import FunctionTool
    from opentelemetry.instrumentation.llamaindex import LlamaIndexInstrumentor

    LlamaIndexInstrumentor().instrument()

    def multiply(a: int, b: int) -> int:
        return a * b

    tool = FunctionTool.from_defaults(fn=multiply, name="multiply")
    tool.call(3, 4)

This emits a standard GenAI ``execute_tool`` span for the tool invocation.

Scope
-----

This instrumentation focuses on tool execution. It wraps
``llama_index.core.tools.FunctionTool.call`` (sync) and
``FunctionTool.acall`` (async), emitting standard GenAI ``execute_tool`` spans.

It intentionally does not wrap LLM, retriever, or workflow classes, to avoid
double-instrumentation with dedicated provider instrumentations. Broader
LlamaIndex coverage (retrievers, query engines, workflows) is deferred as a
follow-up.

Configuration
-------------

This instrumentation emits telemetry through the shared
``opentelemetry-util-genai`` telemetry handler using the latest experimental
GenAI semantic conventions. It must therefore be enabled with:

- ``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`` - opt into the
  latest GenAI semantic conventions. Without this flag, content capture is a
  no-op.
- ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` - enable capture of
  tool arguments and return values. Set to one of ``span_only``,
  ``event_only``, ``span_and_event``.

See the `opentelemetry-util-genai README
<https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/util/opentelemetry-util-genai/README.rst>`_
for the full list of GenAI configuration variables.

A custom ``CompletionHook`` implementation can also be passed programmatically::

    LlamaIndexInstrumentor().instrument(completion_hook=my_hook)

When provided, this takes precedence over the hook resolved from
``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK``.

API
---
"""

from __future__ import annotations

from typing import Any, Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.llamaindex.package import _instruments
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.util.genai.completion_hook import load_completion_hook
from opentelemetry.util.genai.handler import TelemetryHandler

from .patch import function_tool_acall, function_tool_call


class LlamaIndexInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable LlamaIndex tool-execution instrumentation."""
        handler = TelemetryHandler(
            tracer_provider=kwargs.get("tracer_provider"),
            meter_provider=kwargs.get("meter_provider"),
            logger_provider=kwargs.get("logger_provider"),
            completion_hook=kwargs.get("completion_hook")
            or load_completion_hook(),
        )
        capture_content = handler.should_capture_content()

        wrap_function_wrapper(
            "llama_index.core.tools.function_tool",
            "FunctionTool.call",
            function_tool_call(handler, capture_content),
        )
        wrap_function_wrapper(
            "llama_index.core.tools.function_tool",
            "FunctionTool.acall",
            function_tool_acall(handler, capture_content),
        )

    def _uninstrument(self, **kwargs: Any) -> None:
        from llama_index.core.tools.function_tool import (  # pylint: disable=import-outside-toplevel  # noqa: PLC0415
            FunctionTool,
        )

        unwrap(FunctionTool, "call")
        unwrap(FunctionTool, "acall")
