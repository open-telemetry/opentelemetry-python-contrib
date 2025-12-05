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

from unittest import mock

import httpretty
import requests

from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.semconv._incubating.attributes.user_agent_attributes import (
    USER_AGENT_ORIGINAL,
    USER_AGENT_SYNTHETIC_TYPE,
    UserAgentSyntheticTypeValues,
)
from opentelemetry.test.test_base import TestBase


class TestUserAgentSynthetic(TestBase):
    URL = "http://mock/status/200"

    def setUp(self):
        super().setUp()
        RequestsInstrumentor().instrument()
        httpretty.enable()
        httpretty.register_uri(httpretty.GET, self.URL, body="Hello!")

    def tearDown(self):
        super().tearDown()
        RequestsInstrumentor().uninstrument()
        httpretty.disable()

    def assert_span(self, num_spans=1):
        span_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(num_spans, len(span_list))
        if num_spans == 0:
            return None
        if num_spans == 1:
            return span_list[0]
        return span_list

    def test_user_agent_bot_googlebot(self):
        """Test that googlebot user agent is marked as 'bot'"""
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
        }
        requests.get(self.URL, headers=headers, timeout=5)

        span = self.assert_span()
        self.assertEqual(
            span.attributes.get(USER_AGENT_SYNTHETIC_TYPE),
            UserAgentSyntheticTypeValues.BOT.value,
        )

    def test_user_agent_bot_bingbot(self):
        """Test that bingbot user agent is marked as 'bot'"""
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)"
        }
        requests.get(self.URL, headers=headers, timeout=5)

        span = self.assert_span()
        self.assertEqual(
            span.attributes.get(USER_AGENT_SYNTHETIC_TYPE),
            UserAgentSyntheticTypeValues.BOT.value,
        )

    def test_user_agent_test_alwayson(self):
        """Test that alwayson user agent is marked as 'test'"""
        headers = {"User-Agent": "AlwaysOn-Monitor/1.0"}
        requests.get(self.URL, headers=headers, timeout=5)

        span = self.assert_span()
        self.assertEqual(
            span.attributes.get(USER_AGENT_SYNTHETIC_TYPE),
            UserAgentSyntheticTypeValues.TEST.value,
        )

    def test_user_agent_case_insensitive(self):
        """Test that detection is case insensitive"""
        headers = {"User-Agent": "GOOGLEBOT/2.1"}
        requests.get(self.URL, headers=headers, timeout=5)

        span = self.assert_span()
        self.assertEqual(
            span.attributes.get(USER_AGENT_SYNTHETIC_TYPE),
            UserAgentSyntheticTypeValues.BOT.value,
        )

        self.memory_exporter.clear()

        headers = {"User-Agent": "ALWAYSON-Monitor/1.0"}
        requests.get(self.URL, headers=headers, timeout=5)

        span = self.assert_span()
        self.assertEqual(
            span.attributes.get(USER_AGENT_SYNTHETIC_TYPE),
            UserAgentSyntheticTypeValues.TEST.value,
        )

    def test_user_agent_normal_browser(self):
        """Test that normal browser user agents don't get synthetic type"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        requests.get(self.URL, headers=headers, timeout=5)

        span = self.assert_span()
        self.assertNotIn(USER_AGENT_SYNTHETIC_TYPE, span.attributes)

    def test_no_user_agent_header(self):
        """Test that requests without user agent don't get synthetic type"""
        requests.get(self.URL, timeout=5)

        span = self.assert_span()
        self.assertNotIn(USER_AGENT_SYNTHETIC_TYPE, span.attributes)

    def test_empty_user_agent_header(self):
        """Test that empty user agent doesn't get synthetic type"""
        headers = {"User-Agent": ""}
        requests.get(self.URL, headers=headers, timeout=5)

        span = self.assert_span()
        self.assertNotIn(USER_AGENT_SYNTHETIC_TYPE, span.attributes)

    def test_user_agent_substring_match(self):
        """Test that substrings are detected correctly"""
        # Test googlebot in middle of string
        headers = {"User-Agent": "MyApp/1.0 googlebot crawler"}
        requests.get(self.URL, headers=headers, timeout=5)

        span = self.assert_span()
        self.assertEqual(
            span.attributes.get(USER_AGENT_SYNTHETIC_TYPE),
            UserAgentSyntheticTypeValues.BOT.value,
        )

        self.memory_exporter.clear()

        # Test alwayson in middle of string
        headers = {"User-Agent": "TestFramework/1.0 alwayson monitoring"}
        requests.get(self.URL, headers=headers, timeout=5)

        span = self.assert_span()
        self.assertEqual(
            span.attributes.get(USER_AGENT_SYNTHETIC_TYPE),
            UserAgentSyntheticTypeValues.TEST.value,
        )

    def test_user_agent_priority_alwayson_over_bot(self):
        """Test that alwayson takes priority if both patterns match"""
        headers = {"User-Agent": "alwayson-googlebot/1.0"}
        requests.get(self.URL, headers=headers, timeout=5)

        span = self.assert_span()
        # alwayson should be checked first and return 'test'
        self.assertEqual(
            span.attributes.get(USER_AGENT_SYNTHETIC_TYPE),
            UserAgentSyntheticTypeValues.TEST.value,
        )

    def test_user_agent_bytes_like_header(self):
        """Test that bytes-like user agent headers are handled."""

        original_prepare_headers = (
            requests.models.PreparedRequest.prepare_headers
        )

        def prepare_headers_bytes(self, headers):
            original_prepare_headers(self, headers)
            if "User-Agent" in self.headers:
                value = self.headers["User-Agent"]
                if isinstance(value, str):
                    self.headers["User-Agent"] = value.encode("utf-8")

        headers = {"User-Agent": "AlwaysOn-Monitor/1.0"}
        with mock.patch(
            "requests.models.PreparedRequest.prepare_headers",
            new=prepare_headers_bytes,
        ):
            requests.get(self.URL, headers=headers, timeout=5)

        span = self.assert_span()
        self.assertEqual(
            span.attributes.get(USER_AGENT_SYNTHETIC_TYPE),
            UserAgentSyntheticTypeValues.TEST.value,
        )
        self.assertEqual(
            span.attributes.get(USER_AGENT_ORIGINAL),
            "AlwaysOn-Monitor/1.0",
        )
