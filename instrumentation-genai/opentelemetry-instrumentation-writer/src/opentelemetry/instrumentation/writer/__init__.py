# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Writer AI client instrumentation supporting `writerai`, it can be enabled by
using ``WriterInstrumentor``.

.. _writerai: https://pypi.org/project/writerai/

Usage
-----

.. code:: python

    from writerai import Writer
    from opentelemetry.instrumentation.writer import WriterInstrumentor

    WriterInstrumentor().instrument()

    client = Writer(api_key="...")
    response = client.chat.chat(
        model="palmyra-x-004",
        messages=[
            {"role": "user", "content": "Write a short poem on open telemetry."},
        ],
    )

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

    WriterInstrumentor().instrument(completion_hook=my_hook)

When provided, this takes precedence over the hook resolved from
``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK``.

API
---
"""

from __future__ import annotations

from typing import Any, Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.instrumentation.writer.package import _instruments
from opentelemetry.util.genai.completion_hook import load_completion_hook
from opentelemetry.util.genai.handler import TelemetryHandler

from .patch import (
    async_chat,
    async_completions_create,
    chat,
    completions_create,
)


class WriterInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable Writer AI instrumentation."""
        handler = TelemetryHandler(
            tracer_provider=kwargs.get("tracer_provider"),
            meter_provider=kwargs.get("meter_provider"),
            logger_provider=kwargs.get("logger_provider"),
            completion_hook=kwargs.get("completion_hook")
            or load_completion_hook(),
        )

        wrap_function_wrapper(
            "writerai.resources.chat",
            "ChatResource.chat",
            chat(handler),
        )
        wrap_function_wrapper(
            "writerai.resources.chat",
            "AsyncChatResource.chat",
            async_chat(handler),
        )
        wrap_function_wrapper(
            "writerai.resources.completions",
            "CompletionsResource.create",
            completions_create(handler),
        )
        wrap_function_wrapper(
            "writerai.resources.completions",
            "AsyncCompletionsResource.create",
            async_completions_create(handler),
        )

    def _uninstrument(self, **kwargs: Any) -> None:
        import writerai  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        unwrap(writerai.resources.chat.ChatResource, "chat")
        unwrap(writerai.resources.chat.AsyncChatResource, "chat")
        unwrap(writerai.resources.completions.CompletionsResource, "create")
        unwrap(
            writerai.resources.completions.AsyncCompletionsResource, "create"
        )
