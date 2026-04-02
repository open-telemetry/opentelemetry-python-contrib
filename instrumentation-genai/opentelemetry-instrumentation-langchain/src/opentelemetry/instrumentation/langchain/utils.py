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

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Mapping, Optional
from urllib.parse import urlparse

from opentelemetry.context import attach, detach
from opentelemetry.propagate import extract

# Provider name constants aligned with OpenTelemetry semantic conventions
_PROVIDER_AZURE_OPENAI = "azure.ai.openai"
_PROVIDER_OPENAI = "openai"
_PROVIDER_AWS_BEDROCK = "aws.bedrock"
_PROVIDER_GCP_GEN_AI = "gcp.gen_ai"
_PROVIDER_ANTHROPIC = "anthropic"
_PROVIDER_COHERE = "cohere"
_PROVIDER_OLLAMA = "ollama"

# Mapping from LangChain ls_provider values to normalized provider names
_LS_PROVIDER_MAP: Dict[str, str] = {
    "azure": _PROVIDER_AZURE_OPENAI,
    "azure_openai": _PROVIDER_AZURE_OPENAI,
    "azure-openai": _PROVIDER_AZURE_OPENAI,
    "openai": _PROVIDER_OPENAI,
    "github": _PROVIDER_AZURE_OPENAI,
    "google": _PROVIDER_GCP_GEN_AI,
    "google_genai": _PROVIDER_GCP_GEN_AI,
    "anthropic": _PROVIDER_ANTHROPIC,
    "cohere": _PROVIDER_COHERE,
    "ollama": _PROVIDER_OLLAMA,
}

# Substrings in base_url mapped to provider names (checked in order)
_URL_PROVIDER_RULES: List[tuple[str, str]] = [
    ("azure", _PROVIDER_AZURE_OPENAI),
    ("openai", _PROVIDER_OPENAI),
    ("ollama", _PROVIDER_OLLAMA),
    ("bedrock", _PROVIDER_AWS_BEDROCK),
    ("amazonaws.com", _PROVIDER_AWS_BEDROCK),
    ("anthropic", _PROVIDER_ANTHROPIC),
    ("googleapis", _PROVIDER_GCP_GEN_AI),
]

# Substrings in serialized class identifiers mapped to provider names
_CLASS_PROVIDER_RULES: List[tuple[str, str]] = [
    ("ChatOpenAI", _PROVIDER_OPENAI),
    ("ChatBedrock", _PROVIDER_AWS_BEDROCK),
    ("Bedrock", _PROVIDER_AWS_BEDROCK),
    ("ChatAnthropic", _PROVIDER_ANTHROPIC),
    ("ChatGoogleGenerativeAI", _PROVIDER_GCP_GEN_AI),
    ("ChatVertexAI", _PROVIDER_GCP_GEN_AI),
    ("Ollama", _PROVIDER_OLLAMA),
]

# Generic markers to skip when resolving agent names
_GENERIC_MARKERS = {"", "LangGraph"}


def _first_non_empty(*values: Optional[str]) -> Optional[str]:
    """Return the first non-None, non-empty string value, or None."""
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _get_class_identifier(serialized: Dict[str, Any]) -> Optional[str]:
    """Extract a class identifier string from serialized data.

    Checks ``serialized["id"]`` (a list of path components) first,
    then falls back to ``serialized["name"]``.
    """
    id_parts = serialized.get("id")
    if isinstance(id_parts, list) and id_parts:
        return str(id_parts[-1])
    name = serialized.get("name")
    if name:
        return str(name)
    return None


def _infer_from_ls_provider(
    metadata: Optional[Dict[str, Any]],
) -> Optional[str]:
    """Infer provider from LangChain's ls_provider metadata hint."""
    if metadata is None:
        return None
    ls_provider = metadata.get("ls_provider")
    if ls_provider is None:
        return None

    ls_lower = str(ls_provider).lower()

    # Direct map lookup
    mapped = _LS_PROVIDER_MAP.get(ls_lower)
    if mapped is not None:
        return mapped

    # Substring check for bedrock variants (e.g. "amazon_bedrock")
    if "bedrock" in ls_lower:
        return _PROVIDER_AWS_BEDROCK

    return None


def _infer_from_url(
    invocation_params: Optional[Dict[str, Any]],
) -> Optional[str]:
    """Infer provider from a base URL in invocation params."""
    if invocation_params is None:
        return None
    base_url = invocation_params.get("base_url") or invocation_params.get(
        "openai_api_base"
    )
    if not base_url:
        return None

    url_lower = str(base_url).lower()
    for substring, provider in _URL_PROVIDER_RULES:
        if substring in url_lower:
            return provider
    return None


def _infer_from_class(
    serialized: Optional[Dict[str, Any]],
) -> Optional[str]:
    """Infer provider from the serialized class name or id."""
    if serialized is None:
        return None
    class_id = _get_class_identifier(serialized)
    if class_id is None:
        return None

    for substring, provider in _CLASS_PROVIDER_RULES:
        if substring in class_id:
            return provider
    return None


def _infer_from_kwargs(
    serialized: Optional[Dict[str, Any]],
) -> Optional[str]:
    """Infer provider from serialized kwargs (endpoint fields)."""
    if serialized is None:
        return None
    ser_kwargs = serialized.get("kwargs")
    if not isinstance(ser_kwargs, dict):
        return None

    if ser_kwargs.get("azure_endpoint"):
        return _PROVIDER_AZURE_OPENAI

    openai_api_base = ser_kwargs.get("openai_api_base")
    if isinstance(openai_api_base, str) and openai_api_base.endswith(
        ".azure.com"
    ):
        return _PROVIDER_AZURE_OPENAI

    return None


def infer_provider_name(
    serialized: Optional[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]],
    invocation_params: Optional[Dict[str, Any]],
) -> Optional[str]:
    """Infer the GenAI provider name from available LangChain callback data.

    Sources are checked in decreasing order of specificity:
    1. ``metadata["ls_provider"]`` — LangChain's own provider hint
    2. ``invocation_params["base_url"]`` — URL-based inference
    3. ``serialized["id"]`` / ``serialized["name"]`` — class name based
    4. ``serialized["kwargs"]`` — endpoint-based

    Returns ``None`` if the provider cannot be determined.
    """
    return (
        _infer_from_ls_provider(metadata)
        or _infer_from_url(invocation_params)
        or _infer_from_class(serialized)
        or _infer_from_kwargs(serialized)
    )


def _extract_url(
    serialized: Optional[Dict[str, Any]],
    invocation_params: Optional[Dict[str, Any]],
) -> Optional[str]:
    """Find the first available URL from invocation params or serialized kwargs."""
    if invocation_params:
        url = invocation_params.get("base_url") or invocation_params.get(
            "openai_api_base"
        )
        if url:
            return str(url)

    if serialized:
        ser_kwargs = serialized.get("kwargs")
        if isinstance(ser_kwargs, dict):
            url = ser_kwargs.get("openai_api_base") or ser_kwargs.get(
                "azure_endpoint"
            )
            if url:
                return str(url)

    return None


def infer_server_address(
    serialized: Optional[Dict[str, Any]],
    invocation_params: Optional[Dict[str, Any]],
) -> Optional[str]:
    """Extract the server hostname from available URL sources.

    Checks ``invocation_params["base_url"]``,
    ``invocation_params["openai_api_base"]``,
    ``serialized["kwargs"]["openai_api_base"]``, and
    ``serialized["kwargs"]["azure_endpoint"]``.
    """
    url = _extract_url(serialized, invocation_params)
    if url is None:
        return None

    parsed = urlparse(url)
    return parsed.hostname or None


def infer_server_port(
    serialized: Optional[Dict[str, Any]],
    invocation_params: Optional[Dict[str, Any]],
) -> Optional[int]:
    """Extract the server port from available URL sources.

    Only returns a value when the port is explicitly specified in the URL
    (not inferred default ports).
    """
    url = _extract_url(serialized, invocation_params)
    if url is None:
        return None

    parsed = urlparse(url)
    return parsed.port  # None when port is not explicitly set


def resolve_agent_name(
    serialized: Optional[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]],
    kwargs: Optional[Dict[str, Any]],
    default: str,
) -> str:
    """Resolve the most specific agent name from available sources.

    Sources are checked in order:
    1. ``kwargs["name"]`` — explicit callback name
    2. ``metadata["langgraph_node"]`` — per-node name
    3. ``metadata["agent_name"]`` — explicit agent name metadata
    4. ``metadata["agent_type"]`` — agent type fallback
    5. ``metadata["langgraph_path"][-1]`` — path-based fallback
    6. ``serialized["id"]`` / ``serialized["name"]`` — serialized ID
    7. ``default`` — final fallback
    """
    skip = _GENERIC_MARKERS | {default}

    # 1. Explicit callback name
    if kwargs:
        name = kwargs.get("name")
        if isinstance(name, str) and name not in skip:
            return name

    if metadata:
        # 2. LangGraph node name
        node = metadata.get("langgraph_node")
        if isinstance(node, str) and node not in skip:
            return node

        # 3. Explicit agent name metadata
        agent_name = metadata.get("agent_name")
        if isinstance(agent_name, str) and agent_name not in skip:
            return agent_name

        # 4. Agent type fallback
        agent_type = metadata.get("agent_type")
        if isinstance(agent_type, str) and agent_type not in skip:
            return agent_type

        # 5. Path-based fallback
        path = metadata.get("langgraph_path")
        if isinstance(path, list) and path:
            last = path[-1]
            if isinstance(last, str) and last not in skip:
                return last

    # 6. Serialized class identifier
    if serialized:
        class_id = _get_class_identifier(serialized)
        if class_id is not None and class_id not in skip:
            return class_id

    return default


_logger = logging.getLogger(__name__)

# Header keys recognised by the W3C Trace Context specification.
_TRACE_HEADER_KEYS = ("traceparent", "tracestate")

# Common nested attribute names where HTTP / trace headers may reside.
_NESTED_HEADER_KEYS = (
    "headers",
    "header",
    "http_headers",
    "request_headers",
    "metadata",
    "request",
)


def extract_trace_headers(container: Any) -> Optional[Dict[str, str]]:
    """Extract W3C trace context headers from a container.

    Looks for traceparent/tracestate at the top level and in common
    nested locations (headers, metadata, request, etc.).
    """
    if not isinstance(container, dict):
        return None

    # 1. Check top-level keys
    found: Dict[str, str] = {}
    for key in _TRACE_HEADER_KEYS:
        value = container.get(key)
        if isinstance(value, str) and value:
            found[key] = value

    if found:
        return found

    # 2. Check nested containers
    for nested_key in _NESTED_HEADER_KEYS:
        nested = container.get(nested_key)
        if isinstance(nested, dict):
            for key in _TRACE_HEADER_KEYS:
                value = nested.get(key)
                if isinstance(value, str) and value:
                    found[key] = value
            if found:
                return found

    return None


@contextmanager
def propagated_context(
    headers: Optional[Mapping[str, str]],
) -> Iterator[None]:
    """Temporarily adopt an upstream trace context extracted from W3C headers.

    Uses OpenTelemetry's extract() to deserialize W3C trace context,
    then attaches it for the duration of the context manager.
    """
    if not headers:
        yield
        return

    token = None
    try:
        ctx = extract(headers)
        token = attach(ctx)
    except Exception:  # noqa: BLE001
        _logger.debug(
            "Failed to extract/attach propagation context", exc_info=True
        )

    try:
        yield
    finally:
        if token is not None:
            try:
                detach(token)
            except Exception:  # noqa: BLE001
                _logger.debug(
                    "Failed to detach propagation context", exc_info=True
                )


def extract_propagation_context(
    metadata: Optional[Dict[str, Any]],
    inputs: Any,
    kwargs: Dict[str, Any],
) -> Optional[Dict[str, str]]:
    """Try to extract W3C trace headers from callback arguments.

    Checks metadata, inputs, and kwargs in order.
    """
    for source in (metadata, inputs, kwargs):
        if source is not None:
            headers = extract_trace_headers(source)
            if headers:
                return headers
    return None
