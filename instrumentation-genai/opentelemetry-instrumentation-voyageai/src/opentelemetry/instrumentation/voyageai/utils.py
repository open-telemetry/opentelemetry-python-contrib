# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import urlparse

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.invocation import EmbeddingInvocation

# There is no Voyage AI-specific ``gen_ai.provider.name`` value in semconv, so
# the provider is carried as the literal ``"voyageai"``.
_VOYAGEAI_PROVIDER = "voyageai"


def get_server_address_and_port(
    client_instance: Any,
) -> tuple[str | None, int | None]:
    """Derive ``server.address`` / ``server.port`` from the Voyage AI client.

    The Voyage AI client stores its resolved base URL in the private
    ``_params`` mapping (defaulting to ``https://api.voyageai.com/v1``).
    """
    params = getattr(client_instance, "_params", None)
    base_url = params.get("base_url") if isinstance(params, Mapping) else None
    if not base_url or not isinstance(base_url, str):
        return None, None

    parsed = urlparse(base_url)
    address = parsed.hostname
    port = parsed.port
    if port == 443:
        port = None

    return address, port


def set_span_attribute(span: Any, name: str, value: Any) -> None:
    if value is None or value == "":
        return
    span.set_attribute(name, value)


def get_embeddings_request_attributes(
    kwargs: Mapping[str, Any],
    client_instance: Any,
    latest_experimental_enabled: bool,
) -> dict[str, Any]:
    """Build the request-time span attributes for an embeddings call."""
    attributes: dict[str, Any] = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value,
    }

    model = kwargs.get("model")
    if model:
        attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] = model

    if latest_experimental_enabled:
        attributes[GenAIAttributes.GEN_AI_PROVIDER_NAME] = _VOYAGEAI_PROVIDER
    else:
        attributes[GenAIAttributes.GEN_AI_SYSTEM] = _VOYAGEAI_PROVIDER

    address, port = get_server_address_and_port(client_instance)
    if address:
        attributes[ServerAttributes.SERVER_ADDRESS] = address
    if port:
        attributes[ServerAttributes.SERVER_PORT] = port

    return {k: v for k, v in attributes.items() if v is not None}


def create_embedding_invocation(
    handler: TelemetryHandler,
    kwargs: Mapping[str, Any],
    client_instance: Any,
) -> EmbeddingInvocation:
    address, port = get_server_address_and_port(client_instance)
    invocation = handler.start_embedding(
        _VOYAGEAI_PROVIDER,
        request_model=kwargs.get("model", ""),
        server_address=address if address else None,
        server_port=port if port else None,
    )
    return invocation


def handle_span_exception(span: Any, error: BaseException) -> None:
    from opentelemetry.semconv.attributes import (  # noqa: PLC0415
        error_attributes as ErrorAttributes,
    )

    span.set_status(Status(StatusCode.ERROR, str(error)))
    if span.is_recording():
        span.set_attribute(
            ErrorAttributes.ERROR_TYPE, type(error).__qualname__
        )
    span.end()
