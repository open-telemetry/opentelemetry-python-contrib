# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import unittest

from opentelemetry.util.http import _parse_url_query


class TestParseUrlQuery(unittest.TestCase):
    def test_absolute_url(self):
        self.assertEqual(
            _parse_url_query("https://example.com/path?color=blue"),
            ("/path", "color=blue"),
        )

    def test_request_target(self):
        self.assertEqual(_parse_url_query("/path?color=blue"), ("/path", "color=blue"))

    def test_no_query(self):
        self.assertEqual(_parse_url_query("/path"), ("/path", ""))

    def test_empty_url(self):
        self.assertEqual(_parse_url_query(""), ("", ""))

    def test_unparsable_url_returns_empty_components(self):
        # urlparse raises "Invalid IPv6 URL" on an unbalanced bracket in what
        # it takes to be the netloc. Request targets are attacker controlled,
        # so this must not propagate out of instrumentation.
        self.assertEqual(_parse_url_query("//exa[mple"), ("", ""))

    def test_unparsable_url_with_query_returns_empty_components(self):
        self.assertEqual(_parse_url_query("//exa[mple?color=blue"), ("", ""))

    def test_unparsable_absolute_url_returns_empty_components(self):
        self.assertEqual(_parse_url_query("http://example.com[invalid"), ("", ""))
