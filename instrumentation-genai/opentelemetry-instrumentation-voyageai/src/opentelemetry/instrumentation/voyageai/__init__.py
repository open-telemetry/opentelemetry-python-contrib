# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Voyage AI client instrumentation supporting `voyageai`, it can be enabled by
using ``VoyageAIInstrumentor``.

.. _voyageai: https://pypi.org/project/voyageai/

Usage
-----

.. code:: python

    import voyageai
    from opentelemetry.instrumentation.voyageai import VoyageAIInstrumentor

    VoyageAIInstrumentor().instrument()

    client = voyageai.Client()
    result = client.embed(
        texts=["The capital of France is Paris."],
        model="voyage-3-lite",
        input_type="document",
    )

The instrumentation emits the standard OpenTelemetry GenAI
`embeddings <https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-spans.md>`_
telemetry (``gen_ai.*``), using the literal ``voyageai`` for
``gen_ai.provider.name`` / ``gen_ai.system``. Because embedding tokens are all
input tokens, only ``gen_ai.usage.input_tokens`` (and the corresponding
input-token metric) are recorded -- no output-token signals are emitted.

Configuration
-------------

By default, the instrumentation aligns with `Semantic Conventions v1.30.0
<https://github.com/open-telemetry/semantic-conventions/tree/v1.30.0/docs/gen-ai>`_.
Behavior is controlled via environment variables:

- ``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`` - opt into the
  latest GenAI semantic conventions, emitted via ``opentelemetry-util-genai``'s
  ``TelemetryHandler``. Without this flag, the instrumentation stays on the
  legacy v1.30.0 span-based path.

See the `opentelemetry-util-genai README
<https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/util/opentelemetry-util-genai/README.rst>`_
for the full list of GenAI configuration variables.

A custom ``CompletionHook`` implementation can also be passed programmatically::

    VoyageAIInstrumentor().instrument(completion_hook=my_hook)

When provided, this takes precedence over the hook resolved from
``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK``.

API
---
"""

from __future__ import annotations

from typing import Any, Collection

from wrapt import wrap_function_wrapper

from opentelemetry._logs import get_logger
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.instrumentation.voyageai.package import _instruments
from opentelemetry.metrics import get_meter
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer
from opentelemetry.util.genai.completion_hook import load_completion_hook
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.utils import is_experimental_mode

from .instruments import Instruments
from .patch import (
    async_embed_v_new,
    async_embed_v_old,
    embed_v_new,
    embed_v_old,
)


class VoyageAIInstrumentor(BaseInstrumentor):
    def __init__(self) -> None:
        self._meter = None

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable Voyage AI instrumentation."""

        latest_experimental_enabled = is_experimental_mode()
        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(
            __name__,
            "",
            tracer_provider,
            schema_url=Schemas.V1_30_0.value,  # only used on the legacy path
        )
        logger_provider = kwargs.get("logger_provider")
        get_logger(
            __name__,
            "",
            logger_provider=logger_provider,
            schema_url=Schemas.V1_30_0.value,  # only used on the legacy path
        )
        meter_provider = kwargs.get("meter_provider")
        self._meter = get_meter(
            __name__,
            "",
            meter_provider,
            schema_url=Schemas.V1_30_0.value,  # only used on the legacy path
        )

        instruments = Instruments(self._meter)

        handler = TelemetryHandler(
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
            logger_provider=logger_provider,
            completion_hook=kwargs.get("completion_hook")
            or load_completion_hook(),
        )

        wrap_function_wrapper(
            "voyageai.client",
            "Client.embed",
            (
                embed_v_new(handler)
                if latest_experimental_enabled
                else embed_v_old(tracer, instruments)
            ),
        )

        wrap_function_wrapper(
            "voyageai.client_async",
            "AsyncClient.embed",
            (
                async_embed_v_new(handler)
                if latest_experimental_enabled
                else async_embed_v_old(tracer, instruments)
            ),
        )

    def _uninstrument(self, **kwargs: Any) -> None:
        import voyageai  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        unwrap(voyageai.client.Client, "embed")
        unwrap(voyageai.client_async.AsyncClient, "embed")
