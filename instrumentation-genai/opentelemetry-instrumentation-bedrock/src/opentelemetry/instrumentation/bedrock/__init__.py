# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
AWS Bedrock client instrumentation supporting ``boto3`` / ``botocore``, it can
be enabled by using ``BedrockInstrumentor``.

.. _boto3: https://pypi.org/project/boto3/

Usage
-----

.. code:: python

    import boto3
    from opentelemetry.instrumentation.bedrock import BedrockInstrumentor

    BedrockInstrumentor().instrument()

    client = boto3.client("bedrock-runtime", region_name="us-east-1")
    response = client.converse(
        modelId="anthropic.claude-3-haiku-20240307-v1:0",
        messages=[
            {"role": "user", "content": [{"text": "Write a short poem."}]},
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
  prompts and completions. Set to one of ``span_only``, ``event_only``,
  ``span_and_event``.
- ``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK=upload`` together with
  ``OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH=<fsspec-uri>`` - upload
  prompts and completions to an ``fsspec``-compatible destination.

See the `opentelemetry-util-genai README
<https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/util/opentelemetry-util-genai/README.rst>`_
for the full list of GenAI configuration variables.

A custom ``CompletionHook`` implementation can also be passed programmatically::

    BedrockInstrumentor().instrument(completion_hook=my_hook)

When provided, this takes precedence over the hook resolved from
``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK``.

API
---
"""

from __future__ import annotations

from typing import Any, Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.bedrock.package import _instruments
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.util.genai.completion_hook import load_completion_hook
from opentelemetry.util.genai.handler import TelemetryHandler

from .patch import converse_wrapper, invoke_model_wrapper

# The bedrock-runtime service exposes the GenAI inference APIs. Other Bedrock
# services (``bedrock``, ``bedrock-agent``, ...) are control-plane only and are
# not instrumented here.
_BEDROCK_RUNTIME_SERVICE = "bedrock-runtime"

# bedrock-runtime client methods that map cleanly onto the standard GenAI
# semantic conventions.
_WRAPPED_CLIENT_METHODS = ("converse", "invoke_model")


class BedrockInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable AWS Bedrock instrumentation."""
        handler = TelemetryHandler(
            tracer_provider=kwargs.get("tracer_provider"),
            meter_provider=kwargs.get("meter_provider"),
            logger_provider=kwargs.get("logger_provider"),
            completion_hook=kwargs.get("completion_hook")
            or load_completion_hook(),
        )

        wrap_function_wrapper(
            "botocore.client",
            "ClientCreator.create_client",
            _client_creator_wrapper(handler),
        )

    def _uninstrument(self, **kwargs: Any) -> None:
        from botocore.client import (  # noqa: PLC0415  # pylint: disable=import-outside-toplevel
            ClientCreator,
        )

        # Only the ``create_client`` factory is unwrapped. bedrock-runtime
        # clients created while instrumentation was enabled keep their wrapped
        # methods until they are garbage collected; this is expected because the
        # method wrappers are bound to each client instance.
        unwrap(ClientCreator, "create_client")


def _client_creator_wrapper(
    handler: TelemetryHandler,
) -> Any:
    """Return a wrapt wrapper for ``ClientCreator.create_client``.

    When the created client's service is ``bedrock-runtime``, the relevant
    inference methods are wrapped on the returned client instance.
    """

    def wrapper(
        wrapped: Any,
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        client = wrapped(*args, **kwargs)

        service_name = kwargs.get("service_name")
        if service_name is None and args:
            service_name = args[0]

        if service_name != _BEDROCK_RUNTIME_SERVICE:
            return client

        wrap_function_wrapper(client, "converse", converse_wrapper(handler))
        wrap_function_wrapper(
            client, "invoke_model", invoke_model_wrapper(handler)
        )
        return client

    return wrapper
