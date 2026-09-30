# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import re
from unittest import TestCase
from urllib.parse import urlsplit

from opentelemetry.instrumentation.http._internal._urls import (
    ExcludedUrls,
    UrlAttributes,
)

_HEALTH = "https://example.com/health"


class TestExcludedUrls(TestCase):
    def test_is_excluded(self) -> None:
        for excluded_urls, url, expected in (
            # Unset excludes nothing.
            (None, "https://example.com", False),
            ([], "https://example.com", False),
            # Strings match exactly and are not patterns.
            ([_HEALTH], _HEALTH, True),
            ([_HEALTH], f"{_HEALTH}?full=1", False),
            ([_HEALTH], "https://example.com", False),
            ([".*"], "https://example.com", False),
            # Patterns are searched.
            ([re.compile("/health")], f"{_HEALTH}?full=1", True),
            ([re.compile("/health")], "https://example.com/users", False),
            ([re.compile("/HEALTH", re.IGNORECASE)], _HEALTH, True),
            ([re.compile("/HEALTH")], _HEALTH, False),
            # Strings and patterns.
            (["https://example.com/ready", re.compile("/health")], "https://example.com/ready", True),
            (["https://example.com/ready", re.compile("/health")], _HEALTH, True),
            (["https://example.com/ready", re.compile("/health")], "https://example.com/users", False),
        ):
            with self.subTest(excluded_urls=excluded_urls, url=url):
                self.assertIs(ExcludedUrls(excluded_urls).is_excluded(url), expected)


class TestUrlAttributes(TestCase):
    def test_url_full_unchanged(self) -> None:
        url = "https://example.com:8080/path?color=blue#top"

        attributes = UrlAttributes(
            sensitive_query_parameters=None, capture_url_scheme=False, capture_url_template=False
        ).get_attributes(url, urlsplit(url), "/path")

        self.assertEqual(attributes, {"url.full": url})
        self.assertIs(attributes["url.full"], url)

    def test_url_full_is_redacted(self) -> None:
        for url, sensitive_query_parameters, expected in (
            # Credentials.
            ("https://user:pass@example.com:8080/path", None, "https://REDACTED:REDACTED@example.com:8080/path"),
            ("https://user@example.com:8080/path", None, "https://REDACTED:REDACTED@example.com:8080/path"),
            ("https://:pass@example.com:8080/path", None, "https://REDACTED:REDACTED@example.com:8080/path"),
            # Default sensitive query parameters.
            *(
                (
                    f"https://example.com/?color=blue&{key}=secret",
                    None,
                    f"https://example.com/?color=blue&{key}=REDACTED",
                )
                for key in (
                    "AWSAccessKeyId",
                    "Signature",
                    "X-Amz-Signature",
                    "X-Amz-Credential",
                    "X-Amz-Security-Token",
                    "sig",
                    "X-Goog-Signature",
                )
            ),
            # Query keys match case-sensitively after decoding.
            ("https://example.com/?SIG=secret", None, "https://example.com/?SIG=secret"),
            (
                "https://example.com/?X%2DGoog-Signature=secret",
                None,
                "https://example.com/?X%2DGoog-Signature=REDACTED",
            ),
            # The rest of the query is preserved.
            (
                "https://example.com/?b=%20+x&sig=1&a=&sig=2&sig&c#top",
                None,
                "https://example.com/?b=%20+x&sig=REDACTED&a=&sig=REDACTED&sig&c#top",
            ),
            # Custom sensitive query parameters replace the default, and an empty list disables query redaction.
            ("https://example.com/?token=secret&sig=1", ["token"], "https://example.com/?token=REDACTED&sig=1"),
            ("https://user:pass@example.com/?sig=1", [], "https://REDACTED:REDACTED@example.com/?sig=1"),
            ("/path?sig=secret", None, "/path?sig=REDACTED"),
        ):
            with self.subTest(url=url, sensitive_query_parameters=sensitive_query_parameters):
                attributes = UrlAttributes(
                    sensitive_query_parameters=sensitive_query_parameters,
                    capture_url_scheme=False,
                    capture_url_template=False,
                ).get_attributes(url, urlsplit(url), None)

                self.assertEqual(attributes, {"url.full": expected})

    def test_opt_in_attributes(self) -> None:
        users = "https://example.com/users/1"
        for capture_url_scheme, capture_url_template, url, url_template, expected in (
            (True, False, "HTTPS://example.com", None, {"url.scheme": "https"}),
            (True, False, "/path", None, {}),
            (False, False, "https://example.com", None, {}),
            (False, True, users, "/users/{id}", {"url.template": "/users/{id}"}),
            (False, True, "https://example.com", None, {}),
            (False, False, users, "/users/{id}", {}),
        ):
            with self.subTest(
                capture_url_scheme=capture_url_scheme,
                capture_url_template=capture_url_template,
                url=url,
                url_template=url_template,
            ):
                attributes = UrlAttributes(
                    sensitive_query_parameters=None,
                    capture_url_scheme=capture_url_scheme,
                    capture_url_template=capture_url_template,
                ).get_attributes(url, urlsplit(url), url_template)

                self.assertEqual({key: value for key, value in attributes.items() if key != "url.full"}, expected)

    def test_unparsable_url(self) -> None:
        attributes = UrlAttributes(
            sensitive_query_parameters=None, capture_url_scheme=True, capture_url_template=True
        ).get_attributes("http://[::1", None, "/path")

        self.assertEqual(attributes, {"url.template": "/path"})
