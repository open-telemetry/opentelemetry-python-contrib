# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Model Context Protocol (MCP) client instrumentation supporting `mcp`, it can be
enabled by using ``McpInstrumentor``.

.. _mcp: https://pypi.org/project/mcp/

Usage
-----

.. code:: python

    from mcp.client.session import ClientSession
    from opentelemetry.instrumentation.mcp import McpInstrumentor

    McpInstrumentor().instrument()

    # ... open an MCP client session over a transport ...
    async with ClientSession(read_stream, write_stream) as session:
        await session.initialize()
        result = await session.call_tool("get_weather", {"city": "London"})

Each client-side ``ClientSession.call_tool`` invocation emits an
``execute_tool`` GenAI span.

Scope
-----

This instrumentation only wraps the client-side ``ClientSession.call_tool``
method and emits standard GenAI ``execute_tool`` (tool-execution) spans. It does
**not** wrap the MCP transport layer, so cross-process trace context propagation
between the MCP client and server is not yet performed. ``list_tools`` and the
server-side ``ServerSession`` are also out of scope. These are planned as
follow-up work.

Configuration
-------------

This instrumentation emits telemetry through the shared
``opentelemetry-util-genai`` telemetry handler using the latest experimental
GenAI semantic conventions. It must therefore be enabled with:

- ``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`` - opt into the
  latest GenAI semantic conventions. Without this flag, the instrumentation is
  a no-op (no legacy v1.30.0 path is provided yet).
- ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` - enable capture of
  tool arguments and results. Set to one of ``span_only``, ``event_only``,
  ``span_and_event``.
- ``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK=upload`` together with
  ``OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH=<fsspec-uri>`` - upload tool
  arguments and results to an ``fsspec``-compatible destination.

See the `opentelemetry-util-genai README
<https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/util/opentelemetry-util-genai/README.rst>`_
for the full list of GenAI configuration variables.

A custom ``CompletionHook`` implementation can also be passed programmatically::

    McpInstrumentor().instrument(completion_hook=my_hook)

When provided, this takes precedence over the hook resolved from
``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK``.

API
---
"""

from __future__ import annotations

from typing import Any, Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.mcp.package import _instruments
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.util.genai.completion_hook import load_completion_hook
from opentelemetry.util.genai.handler import TelemetryHandler

from .patch import call_tool


class McpInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable MCP client instrumentation."""
        handler = TelemetryHandler(
            tracer_provider=kwargs.get("tracer_provider"),
            meter_provider=kwargs.get("meter_provider"),
            logger_provider=kwargs.get("logger_provider"),
            completion_hook=kwargs.get("completion_hook")
            or load_completion_hook(),
        )

        wrap_function_wrapper(
            "mcp.client.session",
            "ClientSession.call_tool",
            call_tool(handler),
        )

    def _uninstrument(self, **kwargs: Any) -> None:
        import mcp.client.session  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        unwrap(mcp.client.session.ClientSession, "call_tool")
