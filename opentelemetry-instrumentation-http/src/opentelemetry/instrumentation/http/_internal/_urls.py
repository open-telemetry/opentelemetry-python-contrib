# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
from collections.abc import Collection, Iterable
from urllib.parse import SplitResult, unquote_plus, urlunsplit

from opentelemetry.instrumentation.http._internal._semconv import URL_TEMPLATE
from opentelemetry.semconv.attributes.url_attributes import URL_FULL, URL_SCHEME

_REDACTED = "REDACTED"
_REDACTED_CREDENTIALS = "REDACTED:REDACTED"
_DEFAULT_SENSITIVE_QUERY_PARAMETERS = frozenset(
    {
        "AWSAccessKeyId",
        "Signature",
        "X-Amz-Signature",
        "X-Amz-Credential",
        "X-Amz-Security-Token",
        "sig",
        "X-Goog-Signature",
    }
)


class ExcludedUrls:
    """Matches request URLs against excluded URL patterns.

    Compiled regular expressions are searched for in the URL, strings must
    equal the URL exactly.
    """

    def __init__(self, excluded_urls: Collection[str | re.Pattern[str]] | None) -> None:
        excluded_urls = excluded_urls or ()
        self._exact = frozenset(url for url in excluded_urls if isinstance(url, str))
        self._patterns = tuple(url for url in excluded_urls if isinstance(url, re.Pattern))

    def is_excluded(self, url: str) -> bool:
        return url in self._exact or any(pattern.search(url) for pattern in self._patterns)


def _redact_query(query: str, sensitive_query_parameters: Iterable[str]) -> str:
    """Replace the values of sensitive query parameters, leaving the rest of the query as is."""
    parts = query.split("&")
    for index, part in enumerate(parts):
        key, separator, _ = part.partition("=")
        if separator and unquote_plus(key) in sensitive_query_parameters:
            parts[index] = f"{key}={_REDACTED}"
    return "&".join(parts)


class UrlAttributes:
    """Builds the ``url.*`` span attributes of an HTTP client request."""

    def __init__(
        self,
        *,
        sensitive_query_parameters: Collection[str] | None,
        capture_url_scheme: bool,
        capture_url_template: bool,
    ) -> None:
        self._sensitive_query_parameters = (
            frozenset(sensitive_query_parameters)
            if sensitive_query_parameters is not None
            else _DEFAULT_SENSITIVE_QUERY_PARAMETERS
        )
        self._capture_url_scheme = capture_url_scheme
        self._capture_url_template = capture_url_template

    def get_attributes(self, url: str, parts: SplitResult | None, url_template: str | None) -> dict[str, str]:
        """Return ``url.full`` with credentials and sensitive query values redacted and the opted-in attributes.

        ``parts`` is ``url`` split by :func:`urllib.parse.urlsplit`, or ``None`` when the URL cannot be parsed, in
        which case ``url.full`` and ``url.scheme`` are omitted.
        """
        attributes: dict[str, str] = {}
        if parts is not None:
            netloc = parts.netloc
            if "@" in netloc:
                netloc = f"{_REDACTED_CREDENTIALS}@{netloc.rpartition('@')[2]}"
            query = parts.query
            if query and self._sensitive_query_parameters:
                query = _redact_query(query, self._sensitive_query_parameters)
            if netloc != parts.netloc or query != parts.query:
                url = urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))
            attributes[URL_FULL] = url
            if self._capture_url_scheme and parts.scheme:
                attributes[URL_SCHEME] = parts.scheme
        if self._capture_url_template and url_template:
            attributes[URL_TEMPLATE] = url_template
        return attributes
