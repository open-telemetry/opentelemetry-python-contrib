# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Collection

from opentelemetry.semconv.attributes.http_attributes import (
    HTTP_REQUEST_METHOD,
    HTTP_REQUEST_METHOD_ORIGINAL,
    HttpRequestMethodValues,
)

_OTHER_METHOD = HttpRequestMethodValues.OTHER.value
# The RFC9110 methods, PATCH and QUERY.
_DEFAULT_KNOWN_METHODS = frozenset(
    {method.value for method in HttpRequestMethodValues if method is not HttpRequestMethodValues.OTHER} | {"QUERY"}
)
_UNKNOWN_METHOD_SPAN_NAME = "HTTP"


def get_known_methods(known_methods: Collection[str] | None) -> frozenset[str]:
    """Return the known HTTP methods; ``known_methods`` fully replaces the default list."""
    if known_methods is not None:
        return frozenset(known_methods)
    return _DEFAULT_KNOWN_METHODS


def get_method_attributes(method: str, known_methods: frozenset[str] | None) -> dict[str, str]:
    """Return ``http.request.method`` and, for unknown methods ``http.request.method_original``.

    Methods are matched case-sensitively. ``known_methods`` of ``None`` treats
    every method as known. Unknown methods are recorded as ``_OTHER``.
    """
    if known_methods is None or method in known_methods:
        return {HTTP_REQUEST_METHOD: method}
    attributes = {HTTP_REQUEST_METHOD: _OTHER_METHOD}
    if method != _OTHER_METHOD:
        attributes[HTTP_REQUEST_METHOD_ORIGINAL] = method
    return attributes


def get_span_name(method: str, known_methods: frozenset[str] | None, target: str | None = None) -> str:
    """Return the HTTP span name ``{method} {target}``.

    ``known_methods`` of ``None`` treats every method as known. Unknown
    methods are named ``HTTP``.
    """
    if known_methods is not None and method not in known_methods:
        method = _UNKNOWN_METHOD_SPAN_NAME
    if target:
        return f"{method} {target}"
    return method
