# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Mistral AI client instrumentation supporting `mistralai`, it can be enabled by
using ``MistralAiInstrumentor``.

.. _mistralai: https://pypi.org/project/mistralai/

Usage
-----

.. code:: python

    from mistralai import Mistral
    from opentelemetry.instrumentation.mistralai import MistralAiInstrumentor

    MistralAiInstrumentor().instrument()

    client = Mistral(api_key="...")
    response = client.chat.complete(
        model="mistral-small-latest",
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

    MistralAiInstrumentor().instrument(completion_hook=my_hook)

When provided, this takes precedence over the hook resolved from
``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK``.

API
---
"""

from __future__ import annotations

from typing import Any, Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.mistralai.package import _instruments
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.util.genai.completion_hook import load_completion_hook
from opentelemetry.util.genai.handler import TelemetryHandler

from .patch import (
    async_chat_complete,
    async_embeddings_create,
    chat_complete,
    embeddings_create,
)


class MistralAiInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable Mistral AI instrumentation."""
        handler = TelemetryHandler(
            tracer_provider=kwargs.get("tracer_provider"),
            meter_provider=kwargs.get("meter_provider"),
            logger_provider=kwargs.get("logger_provider"),
            completion_hook=kwargs.get("completion_hook")
            or load_completion_hook(),
        )

        wrap_function_wrapper(
            "mistralai.chat",
            "Chat.complete",
            chat_complete(handler, "complete"),
        )
        wrap_function_wrapper(
            "mistralai.chat",
            "Chat.complete_async",
            async_chat_complete(handler, "complete_async"),
        )
        wrap_function_wrapper(
            "mistralai.chat",
            "Chat.stream",
            chat_complete(handler, "stream"),
        )
        wrap_function_wrapper(
            "mistralai.chat",
            "Chat.stream_async",
            async_chat_complete(handler, "stream_async"),
        )
        wrap_function_wrapper(
            "mistralai.embeddings",
            "Embeddings.create",
            embeddings_create(handler),
        )
        wrap_function_wrapper(
            "mistralai.embeddings",
            "Embeddings.create_async",
            async_embeddings_create(handler),
        )

    def _uninstrument(self, **kwargs: Any) -> None:
        import mistralai  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        unwrap(mistralai.chat.Chat, "complete")
        unwrap(mistralai.chat.Chat, "complete_async")
        unwrap(mistralai.chat.Chat, "stream")
        unwrap(mistralai.chat.Chat, "stream_async")
        unwrap(mistralai.embeddings.Embeddings, "create")
        unwrap(mistralai.embeddings.Embeddings, "create_async")
