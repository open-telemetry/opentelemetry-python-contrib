# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
HuggingFace ``transformers`` local pipeline instrumentation. It can be enabled
by using ``TransformersInstrumentor``.

.. _transformers: https://pypi.org/project/transformers/

Usage
-----

.. code:: python

    from transformers import pipeline
    from opentelemetry.instrumentation.transformers import (
        TransformersInstrumentor,
    )

    TransformersInstrumentor().instrument()

    generator = pipeline("text-generation", model="gpt2")
    result = generator("Say hi")

This instruments *local* inference: the model runs in-process, so there is no
network call and no hosted provider. Because there is no
``GenAiProviderNameValues`` member for HuggingFace/local inference, the
``gen_ai.provider.name`` attribute is set to the ``huggingface`` literal.

A local pipeline exposes no token usage and no finish reason, so
``gen_ai.usage.*`` and ``gen_ai.response.finish_reasons`` are not emitted.

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

    TransformersInstrumentor().instrument(completion_hook=my_hook)

When provided, this takes precedence over the hook resolved from
``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK``.

API
---
"""

from __future__ import annotations

from typing import Any, Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.transformers.package import _instruments
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.util.genai.completion_hook import load_completion_hook
from opentelemetry.util.genai.handler import TelemetryHandler

from .patch import text_generation


class TransformersInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable HuggingFace transformers instrumentation."""
        handler = TelemetryHandler(
            tracer_provider=kwargs.get("tracer_provider"),
            meter_provider=kwargs.get("meter_provider"),
            logger_provider=kwargs.get("logger_provider"),
            completion_hook=kwargs.get("completion_hook")
            or load_completion_hook(),
        )

        wrap_function_wrapper(
            "transformers",
            "TextGenerationPipeline.__call__",
            text_generation(handler),
        )

    def _uninstrument(self, **kwargs: Any) -> None:
        from transformers import (  # pylint: disable=import-outside-toplevel  # noqa: PLC0415
            TextGenerationPipeline,
        )

        unwrap(TextGenerationPipeline, "__call__")
