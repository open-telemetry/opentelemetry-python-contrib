# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, Callable

from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import Error

# ``aws.sagemaker`` has no dedicated ``GenAiProviderNameValues`` member in the
# semconv package, so a raw string literal is used for ``gen_ai.provider.name``.
_SAGEMAKER_PROVIDER = "aws.sagemaker"


def invoke_endpoint(handler: TelemetryHandler) -> Callable[..., Any]:
    """Wrap the ``sagemaker-runtime`` client's ``invoke_endpoint`` method.

    SageMaker ``invoke_endpoint`` payloads are opaque (model-specific bytes), so
    the emitted telemetry is intentionally thin: only the provider name, the
    operation name, and the endpoint name (as ``gen_ai.request.model``) are set.
    The opaque request/response ``Body`` is never parsed, and the response
    ``StreamingBody`` is never read so the caller receives it intact.
    """

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        endpoint_name = kwargs.get("EndpointName")
        invocation = handler.start_inference(
            _SAGEMAKER_PROVIDER,
            request_model=endpoint_name,
        )
        try:
            response = wrapped(*args, **kwargs)
            invocation.stop()
            return response
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


__all__ = [
    "_SAGEMAKER_PROVIDER",
    "invoke_endpoint",
]
