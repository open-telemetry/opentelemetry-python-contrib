# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
OpenAI client instrumentation supporting `openai`, it can be enabled by
using ``OpenAIInstrumentor``.

.. deprecated:: 2.5b0
    Use `opentelemetry-instrumentation-genai-openai
    <https://pypi.org/project/opentelemetry-instrumentation-genai-openai/>`_
    instead. This package won't receive new features for `Semantic Conventions v1.30.0
    <https://github.com/open-telemetry/semantic-conventions/tree/v1.30.0/docs/gen-ai>`_.

.. _openai: https://pypi.org/project/openai/

Usage
-----

.. code:: python

    from openai import OpenAI
    from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

    OpenAIInstrumentor().instrument()

    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
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

    OpenAIInstrumentor().instrument(completion_hook=my_hook)

When provided, this takes precedence over the hook resolved from
``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK``.

API
---
"""

import logging
from collections.abc import Collection

from typing_extensions import deprecated
from wrapt import wrap_function_wrapper

from opentelemetry._logs import get_logger
from opentelemetry.instrumentation._semconv import (
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _StabilityMode,
)
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.openai_v2.package import _instruments
from opentelemetry.instrumentation.openai_v2.utils import is_content_enabled
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.metrics import get_meter
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer

from .instruments import Instruments
from .patch import (
    async_chat_completions_create_v_old,
    async_embeddings_create,
    chat_completions_create_v_old,
    embeddings_create,
)

_logger = logging.getLogger(__name__)


def _is_latest_experimental_enabled() -> bool:
    _OpenTelemetrySemanticConventionStability._initialize()
    return (
        _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
            _OpenTelemetryStabilitySignalType.GEN_AI
        )
        is _StabilityMode.GEN_AI_LATEST_EXPERIMENTAL
    )


@deprecated(
    "opentelemetry-instrumentation-openai-v2 is deprecated. Use the "
    "opentelemetry-instrumentation-genai-openai package instead. This package "
    "only receives security patches."
)
class OpenAIInstrumentor(BaseInstrumentor):
    """OpenTelemetry instrumentation for the OpenAI Python client.

    .. deprecated:: 2.5b0
        Use the ``opentelemetry-instrumentation-genai-openai`` package instead.
        This package only receives security patches.
    """

    # BaseInstrumentor is a singleton and __init__ re-runs on every
    # OpenAIInstrumentor() call, so state lives on the class.
    _legacy_instrumented: bool = False

    def __init__(self):
        self._meter = None

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        """Enable OpenAI instrumentation."""

        if _is_latest_experimental_enabled():
            _logger.warning(
                "opentelemetry-instrumentation-openai-v2 does not support "
                "gen_ai_latest_experimental and is disabled. Use "
                "opentelemetry-instrumentation-genai-openai to get the latest "
                "GenAI semantic conventions."
            )
            return

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

        wrap_function_wrapper(
            "openai.resources.chat.completions",
            "Completions.create",
            chat_completions_create_v_old(tracer, logger, instruments, is_content_enabled()),
        )

        wrap_function_wrapper(
            "openai.resources.chat.completions",
            "AsyncCompletions.create",
            async_chat_completions_create_v_old(tracer, logger, instruments, is_content_enabled()),
        )

        # Add instrumentation for the embeddings API
        wrap_function_wrapper(
            "openai.resources.embeddings",
            "Embeddings.create",
            embeddings_create(tracer, instruments, False),
        )

        wrap_function_wrapper(
            "openai.resources.embeddings",
            "AsyncEmbeddings.create",
            async_embeddings_create(tracer, instruments, False),
        )

        type(self)._legacy_instrumented = True

    def _uninstrument(self, **kwargs):
        if not type(self)._legacy_instrumented:
            return

        import openai  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        unwrap(openai.resources.chat.completions.Completions, "create")
        unwrap(openai.resources.chat.completions.AsyncCompletions, "create")
        unwrap(openai.resources.embeddings.Embeddings, "create")
        unwrap(openai.resources.embeddings.AsyncEmbeddings, "create")
        type(self)._legacy_instrumented = False
