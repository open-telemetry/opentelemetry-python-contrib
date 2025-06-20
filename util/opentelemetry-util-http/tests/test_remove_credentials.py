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

from opentelemetry.util.http import remove_url_credentials


class TestRemoveUrlCredentials(unittest.TestCase):
    def test_remove_no_credentials(self):
        url = "http://opentelemetry.io:8080/test/path?query=value"
        cleaned_url = remove_url_credentials(url)
        self.assertEqual(cleaned_url, url)

    def test_remove_credentials(self):
        url = "http://someuser:somepass@opentelemetry.io:8080/test/path?sig=value"
        cleaned_url = remove_url_credentials(url)
        self.assertEqual(
            cleaned_url,
            "http://REDACTED:REDACTED@opentelemetry.io:8080/test/path?sig=value",
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
