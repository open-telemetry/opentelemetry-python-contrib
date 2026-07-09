# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Cohere client instrumentation supporting `cohere`, it can be enabled by
using ``CohereInstrumentor``.

.. _cohere: https://pypi.org/project/cohere/

Usage
-----

.. code:: python

    import cohere
    from opentelemetry.instrumentation.cohere import CohereInstrumentor

    CohereInstrumentor().instrument()

    client = cohere.ClientV2()
    response = client.chat(
        model="command-r",
        messages=[
            {"role": "user", "content": "Write a short poem on open telemetry."},
        ],
    )

Configuration
-------------

The instrumentation emits the standard OpenTelemetry GenAI semantic
conventions (``gen_ai.*``) via ``opentelemetry-util-genai``. It requires the
latest experimental GenAI conventions to be enabled:

- ``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`` - opt into the
  latest GenAI semantic conventions.
- ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` - enable capture of
  prompts, completions, tool arguments, and return values. Set to one of
  ``span_only``, ``event_only``, ``span_and_event``.

See the `opentelemetry-util-genai README
<https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/util/opentelemetry-util-genai/README.rst>`_
for the full list of GenAI configuration variables.

A custom ``CompletionHook`` implementation can also be passed programmatically::

    CohereInstrumentor().instrument(completion_hook=my_hook)

When provided, this takes precedence over the hook resolved from
``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK``.

API
---
"""

from __future__ import annotations

import logging
from typing import Any, Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.cohere.package import _instruments
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.util.genai.completion_hook import load_completion_hook
from opentelemetry.util.genai.handler import TelemetryHandler

from .patch import (
    async_chat_stream_v2,
    async_chat_v1,
    async_chat_v2,
    async_embed,
    chat_stream_v2,
    chat_v1,
    chat_v2,
    embed,
)

logger = logging.getLogger(__name__)

# (module, "Class.method", factory) tuples. Wrapped at the class that defines
# the method so both the concrete client and its subclasses are instrumented.
_V1_MODULE = "cohere.base_client"
_V2_MODULE = "cohere.v2.client"
_V1_EMBED_MODULE = "cohere.client"


class CohereInstrumentor(BaseInstrumentor):
    def __init__(self) -> None:
        self._wrapped: list[tuple[str, str]] = []

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable Cohere instrumentation."""
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

        wrap_targets = [
            # Cohere V2 clients (ClientV2 / AsyncClientV2).
            (_V2_MODULE, "V2Client.chat", chat_v2(handler)),
            (_V2_MODULE, "AsyncV2Client.chat", async_chat_v2(handler)),
            (_V2_MODULE, "V2Client.chat_stream", chat_stream_v2(handler)),
            (
                _V2_MODULE,
                "AsyncV2Client.chat_stream",
                async_chat_stream_v2(handler),
            ),
            (_V2_MODULE, "V2Client.embed", embed(handler)),
            (_V2_MODULE, "AsyncV2Client.embed", async_embed(handler)),
            # Cohere V1 clients (Client / AsyncClient).
            (_V1_MODULE, "BaseCohere.chat", chat_v1(handler)),
            (_V1_MODULE, "AsyncBaseCohere.chat", async_chat_v1(handler)),
            (_V1_EMBED_MODULE, "Client.embed", embed(handler)),
            (_V1_EMBED_MODULE, "AsyncClient.embed", async_embed(handler)),
        ]

        for module, name, wrapper in wrap_targets:
            try:
                wrap_function_wrapper(module, name, wrapper)
                self._wrapped.append((module, name))
            except (ImportError, ModuleNotFoundError, AttributeError):
                logger.debug("Failed to instrument %s.%s", module, name)

    def _uninstrument(self, **kwargs: Any) -> None:
        import importlib  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        for module, name in self._wrapped:
            class_name, method_name = name.split(".", 1)
            try:
                mod = importlib.import_module(module)
                unwrap(getattr(mod, class_name), method_name)
            except (ImportError, ModuleNotFoundError, AttributeError):
                logger.debug("Failed to uninstrument %s.%s", module, name)
        self._wrapped.clear()
