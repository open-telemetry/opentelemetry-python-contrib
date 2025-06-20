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

import unittest

from opentelemetry.util.http import redact_url


class TestRedactUrl(unittest.TestCase):
    def test_redact_both_credentials_and_query_params(self):
        """Test URL with both credentials and sensitive query parameters."""
        url = "https://user:password@api.example.com/data?AWSAccessKeyId=AKIAIOSFODNN7&color=blue"
        expected = "https://REDACTED:REDACTED@api.example.com/data?AWSAccessKeyId=REDACTED&color=blue"
        self.assertEqual(redact_url(url), expected)

    def test_multiple_sensitive_query_params(self):
        """Test URL with multiple sensitive query parameters."""
        url = "https://admin:1234@example.com/secure?Signature=abc123&X-Goog-Signature=xyz789&sig=def456"
        expected = "https://REDACTED:REDACTED@example.com/secure?Signature=REDACTED&X-Goog-Signature=REDACTED&sig=REDACTED"
        self.assertEqual(redact_url(url), expected)

    def test_url_with_special_characters(self):
        """Test URL with special characters in both credentials and query parameters."""
        url = "https://user@domain:p@ss!word@api.example.com/path?Signature=s%40me+special%20chars&normal=fine"
        expected = "https://REDACTED:REDACTED@api.example.com/path?Signature=REDACTED&normal=fine"
        self.assertEqual(redact_url(url), expected)

    def test_edge_cases(self):
        """Test unusual URL formats and corner cases."""
        # URL with fragment
        url1 = (
            "https://user:pass@api.example.com/data?Signature=secret#section"
        )
        self.assertEqual(
            redact_url(url1),
            "https://REDACTED:REDACTED@api.example.com/data?Signature=REDACTED#section",
        )

        # URL with port number
        url2 = (
            "https://user:pass@api.example.com:8443/data?AWSAccessKeyId=secret"
        )
        self.assertEqual(
            redact_url(url2),
            "https://REDACTED:REDACTED@api.example.com:8443/data?AWSAccessKeyId=REDACTED",
        )

        # URL with IP address instead of domain
        url3 = "https://user:pass@192.168.1.1/path?X-Goog-Signature=xyz"
        self.assertEqual(
            redact_url(url3),
            "https://REDACTED:REDACTED@192.168.1.1/path?X-Goog-Signature=REDACTED",
        )
