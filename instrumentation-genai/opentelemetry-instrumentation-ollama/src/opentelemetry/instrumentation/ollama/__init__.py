# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Ollama client instrumentation supporting the `ollama`_ Python SDK. Enable it
using ``OllamaInstrumentor``.

.. _ollama: https://pypi.org/project/ollama/

Usage
-----

.. code:: python

    import ollama
    from opentelemetry.instrumentation.ollama import OllamaInstrumentor

    OllamaInstrumentor().instrument()

    response = ollama.chat(
        model="llama3.2",
        messages=[
            {"role": "user", "content": "Write a short poem on open telemetry."},
        ],
    )

Configuration
-------------

This instrumentation emits the standard OpenTelemetry GenAI semantic conventions
(``gen_ai.*``) through the shared ``opentelemetry-util-genai`` ``TelemetryHandler``.
It requires the latest experimental GenAI semantic conventions to be enabled:

- ``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`` - **required**. When
  this flag is not set, the instrumentation records only the operation name,
  provider, request/response model, server address/port, token usage, finish
  reasons, and the duration/token metrics -- but message content capture and the
  content-mode options below are unavailable.
- ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` - enable capture of
  prompts and completions. Set to one of ``span_only``, ``event_only``,
  ``span_and_event`` when experimental conventions are enabled.

A custom ``CompletionHook`` implementation can also be passed programmatically::

    OllamaInstrumentor().instrument(completion_hook=my_hook)

When provided, this takes precedence over the hook resolved from
``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK``.

API
---
"""

from __future__ import annotations

from typing import Any, Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.ollama.package import _instruments
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.util.genai.completion_hook import load_completion_hook
from opentelemetry.util.genai.handler import TelemetryHandler

from .patch import (
    async_chat_wrapper,
    async_embeddings_wrapper,
    async_generate_wrapper,
    chat_wrapper,
    embeddings_wrapper,
    generate_wrapper,
)

# ollama exposes module-level ``chat``/``generate``/``embed``/``embeddings``
# helpers that delegate to a shared default ``Client``. Wrapping the methods on
# ``Client``/``AsyncClient`` therefore covers both the module-level helpers and
# any explicitly constructed client instances.
_CLIENT_MODULE = "ollama._client"


class OllamaInstrumentor(BaseInstrumentor):
    """An instrumentor for the ollama client library."""

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        tracer_provider = kwargs.get("tracer_provider")
        meter_provider = kwargs.get("meter_provider")
        logger_provider = kwargs.get("logger_provider")

        handler = TelemetryHandler(
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
            logger_provider=logger_provider,
            completion_hook=kwargs.get("completion_hook")
            or load_completion_hook(),
        )

        wrap_function_wrapper(
            _CLIENT_MODULE, "Client.chat", chat_wrapper(handler)
        )
        wrap_function_wrapper(
            _CLIENT_MODULE, "AsyncClient.chat", async_chat_wrapper(handler)
        )
        wrap_function_wrapper(
            _CLIENT_MODULE, "Client.generate", generate_wrapper(handler)
        )
        wrap_function_wrapper(
            _CLIENT_MODULE,
            "AsyncClient.generate",
            async_generate_wrapper(handler),
        )
        wrap_function_wrapper(
            _CLIENT_MODULE, "Client.embed", embeddings_wrapper(handler)
        )
        wrap_function_wrapper(
            _CLIENT_MODULE,
            "AsyncClient.embed",
            async_embeddings_wrapper(handler),
        )
        wrap_function_wrapper(
            _CLIENT_MODULE, "Client.embeddings", embeddings_wrapper(handler)
        )
        wrap_function_wrapper(
            _CLIENT_MODULE,
            "AsyncClient.embeddings",
            async_embeddings_wrapper(handler),
        )

    def _uninstrument(self, **kwargs: Any) -> None:
        from ollama._client import (  # noqa: PLC0415  # pylint: disable=import-outside-toplevel
            AsyncClient,
            Client,
        )

        for method in ("chat", "generate", "embed", "embeddings"):
            unwrap(Client, method)
            unwrap(AsyncClient, method)
