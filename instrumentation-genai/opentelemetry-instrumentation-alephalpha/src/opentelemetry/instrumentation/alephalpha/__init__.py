# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Aleph Alpha client instrumentation supporting `aleph_alpha_client`, it can be
enabled by using ``AlephAlphaInstrumentor``.

.. _aleph_alpha_client: https://pypi.org/project/aleph-alpha-client/

Usage
-----

.. code:: python

    from aleph_alpha_client import Client, CompletionRequest, Prompt
    from opentelemetry.instrumentation.alephalpha import AlephAlphaInstrumentor

    AlephAlphaInstrumentor().instrument()

    client = Client(token="...")
    request = CompletionRequest(
        prompt=Prompt.from_text("An apple a day"),
        maximum_tokens=32,
    )
    response = client.complete(request, model="luminous-base")

Configuration
-------------

This instrumentation emits telemetry through the shared
``opentelemetry-util-genai`` telemetry handler using the latest experimental
GenAI semantic conventions. It must therefore be enabled with:

- ``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`` - opt into the
  latest GenAI semantic conventions. Without this flag, the instrumentation is
  a no-op (no legacy v1.30.0 path is provided yet).
- ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` - enable capture of
  prompts and completions. Set to one of ``span_only``, ``event_only``,
  ``span_and_event``.
- ``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK=upload`` together with
  ``OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH=<fsspec-uri>`` - upload
  prompts and completions to an ``fsspec``-compatible destination.

See the `opentelemetry-util-genai README
<https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/util/opentelemetry-util-genai/README.rst>`_
for the full list of GenAI configuration variables.

A custom ``CompletionHook`` implementation can also be passed programmatically::

    AlephAlphaInstrumentor().instrument(completion_hook=my_hook)

When provided, this takes precedence over the hook resolved from
``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK``.

API
---
"""

from __future__ import annotations

from typing import Any, Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.alephalpha.package import _instruments
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.util.genai.completion_hook import load_completion_hook
from opentelemetry.util.genai.handler import TelemetryHandler

from .patch import async_complete, complete


class AlephAlphaInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable Aleph Alpha instrumentation."""
        handler = TelemetryHandler(
            tracer_provider=kwargs.get("tracer_provider"),
            meter_provider=kwargs.get("meter_provider"),
            logger_provider=kwargs.get("logger_provider"),
            completion_hook=kwargs.get("completion_hook")
            or load_completion_hook(),
        )

        wrap_function_wrapper(
            "aleph_alpha_client",
            "Client.complete",
            complete(handler),
        )
        wrap_function_wrapper(
            "aleph_alpha_client",
            "AsyncClient.complete",
            async_complete(handler),
        )

    def _uninstrument(self, **kwargs: Any) -> None:
        import aleph_alpha_client  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        unwrap(aleph_alpha_client.Client, "complete")
        unwrap(aleph_alpha_client.AsyncClient, "complete")
