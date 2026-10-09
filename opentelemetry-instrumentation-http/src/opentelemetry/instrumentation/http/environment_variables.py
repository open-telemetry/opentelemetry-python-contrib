# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Environment variables read by
:meth:`~opentelemetry.instrumentation.http.client.HttpClientTelemetryOptions.from_env`.

List variables are comma-separated. Empty values are treated as unset, and
invalid values are ignored with a warning.
"""

OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_REQUEST = "OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_REQUEST"
"""Regular expressions for HTTP client request header names to capture."""

OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_RESPONSE = "OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_CLIENT_RESPONSE"
"""Regular expressions for HTTP client response header names to capture."""

OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS = "OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS"
"""Regular expressions for captured header names whose values are redacted."""

OTEL_INSTRUMENTATION_HTTP_KNOWN_METHODS = "OTEL_INSTRUMENTATION_HTTP_KNOWN_METHODS"
"""Case-sensitive HTTP methods that fully replace the default known methods.

``*`` records every HTTP method as-is instead of mapping unknown methods to
``_OTHER``.
"""

OTEL_INSTRUMENTATION_HTTP_CLIENT_OPT_IN_ATTRIBUTES = "OTEL_INSTRUMENTATION_HTTP_CLIENT_OPT_IN_ATTRIBUTES"
"""Stable opt-in attributes to record on HTTP client telemetry.

Accepts ``url.scheme``, ``network.transport`` and ``user_agent.original``, or
``*`` for all of them. When set, unlisted attributes are disabled. Unknown
entries are ignored with a warning.
"""

OTEL_PYTHON_EXCLUDED_URLS = "OTEL_PYTHON_EXCLUDED_URLS"
"""Regular expressions for request URLs to exclude from telemetry.

An instrumentation-specific ``OTEL_PYTHON_<NAME>_EXCLUDED_URLS`` variable takes
precedence when it is set, even if empty.
"""
