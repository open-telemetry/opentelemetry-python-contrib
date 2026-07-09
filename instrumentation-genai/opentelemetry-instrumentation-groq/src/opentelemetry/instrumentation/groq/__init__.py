# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Groq client instrumentation supporting `groq`, it can be enabled by
using ``GroqInstrumentor``.

.. _groq: https://pypi.org/project/groq/

Usage
-----

.. code:: python

    from groq import Groq
    from opentelemetry.instrumentation.groq import GroqInstrumentor

    GroqInstrumentor().instrument()

    client = Groq()
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "user", "content": "Write a short poem on open telemetry."},
        ],
    )

Configuration
-------------

By default, the instrumentation aligns with `Semantic Conventions v1.30.0
<https://github.com/open-telemetry/semantic-conventions/tree/v1.30.0/docs/gen-ai>`_
and does not capture prompt or completion content. Behavior is controlled
via environment variables:

- ``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`` - opt into the
  latest GenAI semantic conventions. Required to access the newer attributes
  and the ``span_only`` / ``event_only`` / ``span_and_event`` content modes.
  Without this flag, the instrumentation stays on v1.30.0 conventions.
- ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` - enable capture of
  prompts, completions, tool arguments, and return values. Set to ``true``
  on the legacy path, or one of ``span_only``, ``event_only``,
  ``span_and_event`` when experimental conventions are enabled.
- ``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK=upload`` together with
  ``OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH=<fsspec-uri>`` - upload
  prompts and completions to an ``fsspec``-compatible destination
  (local filesystem, ``gs://``, ``s3://``, etc.) and record reference URIs as
  ``gen_ai.input.messages.ref`` / ``gen_ai.output.messages.ref`` attributes.
  Inline content is not captured unless
  ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` is also set.

See the `opentelemetry-util-genai README
<https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/util/opentelemetry-util-genai/README.rst>`_
for the full list of GenAI configuration variables.

A custom ``CompletionHook`` implementation can also be passed programmatically::

    GroqInstrumentor().instrument(completion_hook=my_hook)

When provided, this takes precedence over the hook resolved from
``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK``.

API
---
"""

from __future__ import annotations

from typing import Any, Collection

from wrapt import wrap_function_wrapper

from opentelemetry._logs import get_logger
from opentelemetry.instrumentation.groq.package import _instruments
from opentelemetry.instrumentation.groq.utils import is_content_enabled
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.metrics import get_meter
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer
from opentelemetry.util.genai.completion_hook import load_completion_hook
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.utils import is_experimental_mode

from .instruments import Instruments
from .patch import (
    async_chat_completions_create_v_new,
    async_chat_completions_create_v_old,
    chat_completions_create_v_new,
    chat_completions_create_v_old,
)


class GroqInstrumentor(BaseInstrumentor):
    def __init__(self) -> None:
        self._meter = None

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable Groq instrumentation."""

        latest_experimental_enabled = is_experimental_mode()
        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(
            __name__,
            "",
            tracer_provider,
            schema_url=Schemas.V1_30_0.value,  # only used on the legacy path
        )
        logger_provider = kwargs.get("logger_provider")
        logger = get_logger(
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
            "groq.resources.chat.completions",
            "Completions.create",
            (
                chat_completions_create_v_new(handler)
                if latest_experimental_enabled
                else chat_completions_create_v_old(
                    tracer, logger, instruments, is_content_enabled()
                )
            ),
        )

        wrap_function_wrapper(
            "groq.resources.chat.completions",
            "AsyncCompletions.create",
            (
                async_chat_completions_create_v_new(handler)
                if latest_experimental_enabled
                else async_chat_completions_create_v_old(
                    tracer, logger, instruments, is_content_enabled()
                )
            ),
        )

    def _uninstrument(self, **kwargs: Any) -> None:
        import groq  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        unwrap(groq.resources.chat.completions.Completions, "create")
        unwrap(groq.resources.chat.completions.AsyncCompletions, "create")
