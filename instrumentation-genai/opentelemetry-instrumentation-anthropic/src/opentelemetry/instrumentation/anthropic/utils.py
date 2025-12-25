# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Utility functions for Anthropic instrumentation."""

from __future__ import annotations

from os import environ
from typing import Any, Optional
from urllib.parse import urlparse

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)

OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = (
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
)


def is_content_enabled() -> bool:
    """Check if content capture is enabled via environment variable."""
    capture_content = environ.get(
        OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, "false"
    )
    return capture_content.lower() == "true"


def set_server_address_and_port(
    client_instance: Any, attributes: dict[str, Any]
) -> None:
    """Extract server address and port from the Anthropic client instance."""
    base_client = getattr(client_instance, "_client", None)
    base_url = getattr(base_client, "base_url", None)
    if not base_url:
        return

    port: Optional[int] = None
    if hasattr(base_url, "host"):
        # httpx.URL object
        attributes[ServerAttributes.SERVER_ADDRESS] = base_url.host
        port = getattr(base_url, "port", None)
    elif isinstance(base_url, str):
        url = urlparse(base_url)
        attributes[ServerAttributes.SERVER_ADDRESS] = url.hostname
        port = url.port

    if port and port != 443 and port > 0:
        attributes[ServerAttributes.SERVER_PORT] = port


def get_llm_request_attributes(
    kwargs: dict[str, Any], client_instance: Any
) -> dict[str, Any]:
    """Extract LLM request attributes from kwargs."""
    attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.CHAT.value,
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.ANTHROPIC.value,  # pyright: ignore[reportDeprecated]
        GenAIAttributes.GEN_AI_REQUEST_MODEL: kwargs.get("model"),
        GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS: kwargs.get("max_tokens"),
        GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE: kwargs.get("temperature"),
        GenAIAttributes.GEN_AI_REQUEST_TOP_P: kwargs.get("top_p"),
        GenAIAttributes.GEN_AI_REQUEST_TOP_K: kwargs.get("top_k"),
        GenAIAttributes.GEN_AI_REQUEST_STOP_SEQUENCES: kwargs.get(
            "stop_sequences"
        ),
    }

    set_server_address_and_port(client_instance, attributes)

    # Filter out None values
    return {k: v for k, v in attributes.items() if v is not None}
