# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
AWS SageMaker runtime instrumentation supporting ``boto3``/``botocore``, it can
be enabled by using ``SageMakerInstrumentor``.

This instrumentation traces calls to the ``sagemaker-runtime`` client's
``invoke_endpoint`` method.

.. _boto3: https://pypi.org/project/boto3/

Usage
-----

.. code:: python

    import boto3
    from opentelemetry.instrumentation.sagemaker import SageMakerInstrumentor

    SageMakerInstrumentor().instrument()

    client = boto3.client("sagemaker-runtime")
    response = client.invoke_endpoint(
        EndpointName="my-endpoint",
        Body=b"...",
        ContentType="application/json",
    )

Thin telemetry (opaque payloads)
--------------------------------

SageMaker ``invoke_endpoint`` payloads are **opaque, model-specific bytes**: the
request ``Body`` and the response ``Body`` are arbitrary content whose schema
depends entirely on the container deployed behind the endpoint. There is no
standardized foundation-model id, prompt/completion structure, or token-usage
information exposed by the SageMaker runtime API.

As a result, the standard-semconv telemetry emitted here is intentionally
**thin**. Only the attributes that can be mapped reliably are set:

- ``gen_ai.provider.name`` = ``"aws.sagemaker"``
- ``gen_ai.operation.name``
- ``gen_ai.request.model`` = the SageMaker ``EndpointName``

.. note::

    ``gen_ai.request.model`` carries the SageMaker **endpoint name**, which is
    the only stable identifier available. It is *not* a foundation-model id.

This instrumentation does **not**:

- parse the opaque request or response ``Body``,
- read or consume the response ``StreamingBody`` (doing so would break the
  caller by exhausting the stream),
- emit token usage, finish reasons, or output messages.

Configuration
-------------

This instrumentation emits telemetry through the shared
``opentelemetry-util-genai`` telemetry handler using the latest experimental
GenAI semantic conventions. It must therefore be enabled with:

- ``OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`` - opt into the
  latest GenAI semantic conventions. Without this flag, the instrumentation is
  a no-op (no legacy v1.30.0 path is provided).

See the `opentelemetry-util-genai README
<https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/util/opentelemetry-util-genai/README.rst>`_
for the full list of GenAI configuration variables.

API
---
"""

from __future__ import annotations

from typing import Any, Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.sagemaker.package import _instruments
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.util.genai.completion_hook import load_completion_hook
from opentelemetry.util.genai.handler import TelemetryHandler

from .patch import invoke_endpoint


class SageMakerInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable AWS SageMaker instrumentation."""
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
        from botocore.client import (  # pylint: disable=import-outside-toplevel  # noqa: PLC0415
            ClientCreator,
        )

        unwrap(ClientCreator, "create_client")


def _client_creator_wrapper(handler: TelemetryHandler) -> Any:
    """Wrap ``ClientCreator.create_client`` to instrument SageMaker runtime.

    ``boto3``/``botocore`` build service clients dynamically, so the individual
    client methods (such as ``invoke_endpoint``) only exist on the returned
    client instance. We therefore wrap ``invoke_endpoint`` on the client that is
    created for the ``sagemaker-runtime`` service.
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
        if service_name == "sagemaker-runtime" and hasattr(
            client, "invoke_endpoint"
        ):
            wrap_function_wrapper(
                client, "invoke_endpoint", invoke_endpoint(handler)
            )
        return client

    return wrapper
