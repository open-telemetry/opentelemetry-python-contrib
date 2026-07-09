# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Replicate client instrumentation supporting `replicate`, it can be enabled by
using ``ReplicateInstrumentor``.

.. _replicate: https://pypi.org/project/replicate/

Usage
-----

.. code:: python

    import replicate
    from opentelemetry.instrumentation.replicate import ReplicateInstrumentor

    ReplicateInstrumentor().instrument()

    output = replicate.run(
        "meta/meta-llama-3-8b-instruct",
        input={"prompt": "Write a short poem on open telemetry."},
    )

The emitted telemetry follows the standard OpenTelemetry GenAI semantic
conventions (``gen_ai.*``). Replicate predictions map to the
``text_completion`` operation, and the ``replicate`` value is used for
``gen_ai.provider.name``.

.. note::
    Replicate responses do not report token usage, so token-usage attributes
    (``gen_ai.usage.*``) and the token-usage metric are not emitted.

Configuration
-------------

By default the instrumentation does not capture prompt or completion content.
Behavior is controlled via environment variables:

- ``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`` - opt into the
  latest GenAI semantic conventions. This instrumentation only emits telemetry
  on the experimental path.
- ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` - enable capture of
  prompts and completions. Set to one of ``span_only``, ``event_only``,
  ``span_and_event`` when experimental conventions are enabled.

See the `opentelemetry-util-genai README
<https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/util/opentelemetry-util-genai/README.rst>`_
for the full list of GenAI configuration variables.

A custom ``CompletionHook`` implementation can also be passed programmatically::

    ReplicateInstrumentor().instrument(completion_hook=my_hook)

When provided, this takes precedence over the hook resolved from
``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK``.

API
---
"""

from __future__ import annotations

from typing import Any, Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.replicate.package import _instruments
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.util.genai.completion_hook import load_completion_hook
from opentelemetry.util.genai.handler import TelemetryHandler

from .patch import (
    async_run_v_new,
    async_stream_v_new,
    run_v_new,
    stream_v_new,
)

_CLIENT_MODULE = "replicate.client"
_CLIENT_CLASS = "Client"
# The module-level ``replicate.run`` / ``replicate.stream`` helpers are bound
# methods of the default ``Client`` instance captured at import time, so they do
# not dispatch through the patched ``Client`` class attribute. Both the class
# methods (for explicitly constructed clients) and the module-level bound methods
# must be wrapped to instrument every call site.
_METHODS = ("run", "async_run", "stream", "async_stream")


class ReplicateInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable Replicate instrumentation."""

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

        wrappers = {
            "run": run_v_new(handler),
            "async_run": async_run_v_new(handler),
            "stream": stream_v_new(handler),
            "async_stream": async_stream_v_new(handler),
        }

        for method in _METHODS:
            wrapper = wrappers[method]
            wrap_function_wrapper(
                _CLIENT_MODULE, f"{_CLIENT_CLASS}.{method}", wrapper
            )
            wrap_function_wrapper("replicate", method, wrapper)

    def _uninstrument(self, **kwargs: Any) -> None:
        import replicate  # pylint: disable=import-outside-toplevel  # noqa: PLC0415
        from replicate.client import (  # pylint: disable=import-outside-toplevel  # noqa: PLC0415
            Client,
        )

        for method in _METHODS:
            unwrap(Client, method)
            unwrap(replicate, method)
