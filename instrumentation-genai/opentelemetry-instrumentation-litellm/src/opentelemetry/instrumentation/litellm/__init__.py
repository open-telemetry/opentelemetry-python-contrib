# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
LiteLLM instrumentation supporting `litellm`, it can be enabled by
using ``LiteLLMInstrumentor``.

.. _litellm: https://pypi.org/project/litellm/

Usage
-----

.. code:: python

    import litellm
    from opentelemetry.instrumentation.litellm import LiteLLMInstrumentor

    LiteLLMInstrumentor().instrument()

    response = litellm.completion(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "user", "content": "Write a short poem on open telemetry."},
        ],
    )

LiteLLM is a router that normalizes many providers to the OpenAI response
shape. This instrumentation wraps the module-level ``litellm.completion`` /
``litellm.acompletion`` (chat) and ``litellm.embedding`` /
``litellm.aembedding`` (embeddings) functions so a single set of wrappers
produces consistent ``gen_ai.*`` telemetry across all back-ends.

The provider recorded as ``gen_ai.provider.name`` is derived per call from the
provider litellm actually dispatched to: from the response's
``_hidden_params["custom_llm_provider"]`` when available, else from an explicit
``custom_llm_provider`` kwarg or the ``provider/model`` prefix on the model
string. LiteLLM prefixes that differ from the OTel well-known values (e.g.
``bedrock`` -> ``aws.bedrock``) are normalized to the matching
``GenAiProviderNameValues`` member; unknown providers pass through as literal
strings. When the provider cannot be determined (a bare model whose provider is
only known after the response), it falls back to the literal ``"litellm"``.

Configuration
-------------

By default the instrumentation does not capture prompt or completion content.
Behavior is controlled via environment variables:

- ``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`` - opt into the
  latest GenAI semantic conventions. Required for this instrumentation to emit
  telemetry via the shared ``opentelemetry-util-genai`` ``TelemetryHandler``.
- ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` - enable capture of
  prompts, completions, tool arguments, and return values. Set to one of
  ``span_only``, ``event_only``, ``span_and_event``.

See the `opentelemetry-util-genai README
<https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/util/opentelemetry-util-genai/README.rst>`_
for the full list of GenAI configuration variables.

A custom ``CompletionHook`` implementation can also be passed programmatically::

    LiteLLMInstrumentor().instrument(completion_hook=my_hook)

When provided, this takes precedence over the hook resolved from
``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK``.

API
---
"""

from __future__ import annotations

import logging
from typing import Any, Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.util.genai.completion_hook import load_completion_hook
from opentelemetry.util.genai.handler import TelemetryHandler

from .package import _instruments
from .patch import (
    acompletion_wrapper,
    aembedding_wrapper,
    completion_wrapper,
    embedding_wrapper,
)

_logger = logging.getLogger(__name__)

_WRAPPED_METHODS = (
    ("completion", completion_wrapper),
    ("acompletion", acompletion_wrapper),
    ("embedding", embedding_wrapper),
    ("aembedding", aembedding_wrapper),
)


class LiteLLMInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable LiteLLM instrumentation."""
        handler = TelemetryHandler(
            tracer_provider=kwargs.get("tracer_provider"),
            meter_provider=kwargs.get("meter_provider"),
            logger_provider=kwargs.get("logger_provider"),
            completion_hook=kwargs.get("completion_hook")
            or load_completion_hook(),
        )

        for method, factory in _WRAPPED_METHODS:
            try:
                wrap_function_wrapper("litellm", method, factory(handler))
            except (AttributeError, ModuleNotFoundError):
                _logger.debug("litellm.%s not found, skipping", method)

    def _uninstrument(self, **kwargs: Any) -> None:
        import litellm  # pylint: disable=import-outside-toplevel  # noqa: PLC0415

        for method, _ in _WRAPPED_METHODS:
            try:
                unwrap(litellm, method)
            except (AttributeError, ModuleNotFoundError):
                pass
