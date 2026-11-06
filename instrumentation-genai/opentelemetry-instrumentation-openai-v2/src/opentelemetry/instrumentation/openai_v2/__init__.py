# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
OpenAI client instrumentation supporting `openai`, it can be enabled by
using ``OpenAIInstrumentor``.

.. deprecated:: 2.5b0
    Use `opentelemetry-instrumentation-genai-openai
    <https://pypi.org/project/opentelemetry-instrumentation-genai-openai/>`_
    instead. This package only supports `Semantic Conventions v1.30.0
    <https://github.com/open-telemetry/semantic-conventions/tree/v1.30.0/docs/gen-ai>`_
    and won't receive new features.

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
and does not capture prompt or completion content.

- ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`` - capture
  prompts, completions, tool arguments, and return values on log events.
- ``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`` - opt into the
  latest GenAI semantic conventions. This package turns itself off and enables
  `opentelemetry-instrumentation-genai-openai
  <https://pypi.org/project/opentelemetry-instrumentation-genai-openai/>`_
  (installed as a dependency) instead. All ``instrument()`` arguments
  (e.g. ``completion_hook``) are forwarded to it. See its documentation for
  content capturing modes and completion hooks.

API
---
"""

from __future__ import annotations

import logging
from collections.abc import Collection
from typing import Any

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


def _get_genai_openai_instrumentor() -> BaseInstrumentor | None:
    try:
        # pylint: disable-next=import-outside-toplevel,no-name-in-module
        from opentelemetry.instrumentation.genai.openai import (  # noqa: PLC0415
            OpenAIInstrumentor as GenAIOpenAIInstrumentor,
        )
    except ImportError:
        return None
    return GenAIOpenAIInstrumentor()


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
    _delegate: BaseInstrumentor | None = None
    _blocked: BaseInstrumentor | None = None

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable OpenAI instrumentation."""

        if _is_latest_experimental_enabled():
            self._instrument_latest(**kwargs)
            return

        self._block_genai_openai()

        tracer = get_tracer(
            __name__,
            "",
            kwargs.get("tracer_provider"),
            schema_url=Schemas.V1_30_0.value,
        )
        logger = get_logger(
            __name__,
            "",
            logger_provider=kwargs.get("logger_provider"),
            schema_url=Schemas.V1_30_0.value,
        )
        meter = get_meter(
            __name__,
            "",
            kwargs.get("meter_provider"),
            schema_url=Schemas.V1_30_0.value,
        )

        instruments = Instruments(meter)
        capture_content = is_content_enabled()

        wrap_function_wrapper(
            "openai.resources.chat.completions",
            "Completions.create",
            chat_completions_create_v_old(tracer, logger, instruments, capture_content),
        )
        wrap_function_wrapper(
            "openai.resources.chat.completions",
            "AsyncCompletions.create",
            async_chat_completions_create_v_old(tracer, logger, instruments, capture_content),
        )
        wrap_function_wrapper(
            "openai.resources.embeddings",
            "Embeddings.create",
            embeddings_create(tracer, instruments),
        )
        wrap_function_wrapper(
            "openai.resources.embeddings",
            "AsyncEmbeddings.create",
            async_embeddings_create(tracer, instruments),
        )
        type(self)._legacy_instrumented = True

    def _instrument_latest(self, **kwargs: Any) -> None:
        delegate = _get_genai_openai_instrumentor()
        if delegate is None:
            _logger.warning(
                "opentelemetry-instrumentation-openai-v2 does not support "
                "gen_ai_latest_experimental and is disabled. Install "
                "opentelemetry-instrumentation-genai-openai to get the latest "
                "GenAI semantic conventions."
            )
            return

        # Auto-instrumentation may have already enabled it via its own entry point.
        if delegate.is_instrumented_by_opentelemetry:
            return

        delegate.instrument(**kwargs)
        type(self)._delegate = delegate

    def _block_genai_openai(self) -> None:
        """Keep opentelemetry-instrumentation-genai-openai off while the legacy path is active.

        Both packages register the ``openai`` entry point and auto-instrumentation loads them
        in no particular order, so undo it if it ran first and turn its ``instrument()`` into
        a no-op if it runs later. Its ``_is_instrumented_by_opentelemetry`` flag is left
        untouched so a stray ``uninstrument()`` can't unwrap our wrappers.
        """
        delegate = _get_genai_openai_instrumentor()
        if delegate is None:
            return
        if delegate.is_instrumented_by_opentelemetry:
            delegate.uninstrument()

        def _blocked_instrument(**kwargs: Any) -> None:
            _logger.warning(
                "opentelemetry-instrumentation-genai-openai is disabled because "
                "opentelemetry-instrumentation-openai-v2 is active. Set "
                "OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental or uninstall "
                "opentelemetry-instrumentation-openai-v2 to use it."
            )

        # instance attribute shadows BaseInstrumentor.instrument on the singleton
        setattr(delegate, "instrument", _blocked_instrument)
        type(self)._blocked = delegate

    def _uninstrument(self, **kwargs: Any) -> None:
        cls = type(self)
        if cls._delegate is not None:
            cls._delegate.uninstrument(**kwargs)
            cls._delegate = None

        if cls._blocked is not None:
            cls._blocked.__dict__.pop("instrument", None)
            cls._blocked = None

        if not cls._legacy_instrumented:
            return

        import openai  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        unwrap(openai.resources.chat.completions.Completions, "create")
        unwrap(openai.resources.chat.completions.AsyncCompletions, "create")
        unwrap(openai.resources.embeddings.Embeddings, "create")
        unwrap(openai.resources.embeddings.AsyncEmbeddings, "create")
        cls._legacy_instrumented = False
