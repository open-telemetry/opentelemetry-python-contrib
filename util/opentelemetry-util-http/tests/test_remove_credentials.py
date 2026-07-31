# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import unittest

from opentelemetry.util.http import remove_url_credentials


class TestRemoveUrlCredentials(unittest.TestCase):
    def test_remove_no_credentials(self):
        url = "http://mock/status/200/test/path?query=value"
        cleaned_url = remove_url_credentials(url)
        self.assertEqual(cleaned_url, url)

    def test_remove_credentials(self):
        url = "http://someuser:somepass@mock/status/200/test/path?sig=value"
        cleaned_url = remove_url_credentials(url)
        self.assertEqual(
            cleaned_url,
            "http://REDACTED:REDACTED@mock/status/200/test/path?sig=value",
        )

    def test_remove_credentials_ipv4_literal(self):
        url = "http://someuser:somepass@127.0.0.1:8080/test/path?query=value"
        cleaned_url = remove_url_credentials(url)
        self.assertEqual(
            cleaned_url,
            "http://REDACTED:REDACTED@127.0.0.1:8080/test/path?query=value",
        )

    def test_remove_credentials_ipv6_literal(self):
        url = "http://someuser:somepass@[::1]:8080/test/path?query=value"
        cleaned_url = remove_url_credentials(url)
        self.assertEqual(
            cleaned_url,
            "http://REDACTED:REDACTED@[::1]:8080/test/path?query=value",
        )
