# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
import re
from collections.abc import Collection
from dataclasses import dataclass, fields
from typing import Any

from opentelemetry.instrumentation.http._internal._env import (
    parse_list_env_var,
    parse_patterns_env_var,
)
from opentelemetry.instrumentation.http.environment_variables import (
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_REQUEST,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_RESPONSE,
    OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS,
    OTEL_INSTRUMENTATION_HTTP_CLIENT_OPT_IN_ATTRIBUTES,
    OTEL_INSTRUMENTATION_HTTP_KNOWN_METHODS,
    OTEL_PYTHON_EXCLUDED_URLS,
)
from opentelemetry.semconv.attributes.network_attributes import NETWORK_TRANSPORT
from opentelemetry.semconv.attributes.url_attributes import URL_SCHEME
from opentelemetry.semconv.attributes.user_agent_attributes import USER_AGENT_ORIGINAL

_logger = logging.getLogger(__name__)

_OPT_IN_ATTRIBUTE_FIELDS = {
    URL_SCHEME: "capture_url_scheme",
    NETWORK_TRANSPORT: "capture_network_transport",
    USER_AGENT_ORIGINAL: "capture_user_agent_original",
}


def _get_opt_in_attributes_from_env() -> dict[str, bool | None]:
    entries = parse_list_env_var(OTEL_INSTRUMENTATION_HTTP_CLIENT_OPT_IN_ATTRIBUTES)
    if entries is None:
        return dict.fromkeys(_OPT_IN_ATTRIBUTE_FIELDS.values(), None)
    if "*" in entries:
        return dict.fromkeys(_OPT_IN_ATTRIBUTE_FIELDS.values(), True)
    enabled: dict[str, bool | None] = dict.fromkeys(_OPT_IN_ATTRIBUTE_FIELDS.values(), False)
    for entry in entries:
        field_name = _OPT_IN_ATTRIBUTE_FIELDS.get(entry)
        if field_name is None:
            _logger.warning(
                "Ignoring unknown attribute %r in %s", entry, OTEL_INSTRUMENTATION_HTTP_CLIENT_OPT_IN_ATTRIBUTES
            )
            continue
        enabled[field_name] = True
    return enabled


@dataclass(frozen=True, kw_only=True, slots=True)
class HttpClientTelemetryOptions:
    """Stable options for :class:`HttpClientTelemetry`.

    Options in this struct follow semantic versioning. Every option defaults
    to ``None``, meaning unset; unset options use the behavior described
    below. Collection options are read once, when the telemetry is created.

    Header patterns are either compiled regular expressions, which must fully
    match the lowercased header name, or strings, which must equal the header
    name case-insensitively.

    Attributes:
        captured_request_headers: Header patterns for request headers recorded
            as ``http.request.header.<key>`` span attributes. Unset captures
            no headers.
        captured_response_headers: Header patterns for response headers
            recorded as ``http.response.header.<key>`` span attributes. Unset
            captures no headers.
        sanitized_headers: Header patterns for captured headers whose values
            are recorded as ``[REDACTED]``. Unset redacts nothing.
        capture_network_transport: Record ``network.transport`` on spans.
            Unset means ``False``.
        capture_url_scheme: Record ``url.scheme`` on spans and on all enabled
            HTTP client metrics. Unset means ``False``.
        capture_user_agent_original: Record ``user_agent.original`` on spans.
            Unset means ``False``.
        known_methods: Case-sensitive HTTP methods known to the
            instrumentation, fully replacing the default list (the RFC9110
            methods, ``PATCH`` and ``QUERY``). Other methods are recorded as ``_OTHER``
            in ``http.request.method``. Unset uses the default list.
        capture_all_methods: Record every HTTP method as-is instead of
            mapping unknown methods to ``_OTHER``. Takes precedence over
            ``known_methods``. Unset means ``False``.
        excluded_urls: URL patterns for requests that get no telemetry.
            Compiled regular expressions are searched for in the request URL;
            strings must equal the URL exactly. Unset excludes nothing.
    """

    captured_request_headers: Collection[str | re.Pattern[str]] | None = None
    captured_response_headers: Collection[str | re.Pattern[str]] | None = None
    sanitized_headers: Collection[str | re.Pattern[str]] | None = None
    capture_network_transport: bool | None = None
    capture_url_scheme: bool | None = None
    capture_user_agent_original: bool | None = None
    known_methods: Collection[str] | None = None
    capture_all_methods: bool | None = None
    excluded_urls: Collection[str | re.Pattern[str]] | None = None

    @classmethod
    def from_env(cls, instrumentation_name: str | None = None) -> HttpClientTelemetryOptions:
        """Create options from environment variables.

        See :mod:`opentelemetry.instrumentation.http.environment_variables`.
        Unset, empty or invalid variables leave their options unset.
        ``OTEL_INSTRUMENTATION_HTTP_KNOWN_METHODS=*`` sets
        ``capture_all_methods``.

        Args:
            instrumentation_name: Name used to read the instrumentation-specific
                ``OTEL_PYTHON_<NAME>_EXCLUDED_URLS`` variable, e.g.
                ``"REQUESTS"``. When that variable is unset, empty or invalid,
                ``OTEL_PYTHON_EXCLUDED_URLS`` is used instead.
        """
        excluded_urls = None
        if instrumentation_name is not None:
            excluded_urls = parse_patterns_env_var(f"OTEL_PYTHON_{instrumentation_name.upper()}_EXCLUDED_URLS")
        if excluded_urls is None:
            excluded_urls = parse_patterns_env_var(OTEL_PYTHON_EXCLUDED_URLS)

        known_methods = parse_list_env_var(OTEL_INSTRUMENTATION_HTTP_KNOWN_METHODS)
        capture_all_methods = None
        if known_methods is not None and "*" in known_methods:
            known_methods = None
            capture_all_methods = True

        return cls(
            **_get_opt_in_attributes_from_env(),
            captured_request_headers=parse_patterns_env_var(
                OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_REQUEST, re.IGNORECASE
            ),
            captured_response_headers=parse_patterns_env_var(
                OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_RESPONSE, re.IGNORECASE
            ),
            sanitized_headers=parse_patterns_env_var(
                OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS, re.IGNORECASE
            ),
            known_methods=known_methods,
            capture_all_methods=capture_all_methods,
            excluded_urls=excluded_urls,
        )

    def merge(self, other: HttpClientTelemetryOptions) -> HttpClientTelemetryOptions:
        """Return new options where every option set in ``other`` overrides this one."""
        values: dict[str, Any] = {}
        for field in fields(self):
            value = getattr(other, field.name)
            values[field.name] = value if value is not None else getattr(self, field.name)
        return HttpClientTelemetryOptions(**values)
