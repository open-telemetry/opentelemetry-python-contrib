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

from opentelemetry.semconv._incubating.attributes.user_agent_attributes import (
    UserAgentSyntheticTypeValues,
)
from opentelemetry.util.http import (
    detect_synthetic_user_agent,
    normalize_user_agent,
)


class TestDetectSyntheticUserAgent(unittest.TestCase):
    def test_detect_bot_googlebot(self):
        """Test detection of googlebot user agent."""
        user_agent = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
        result = detect_synthetic_user_agent(user_agent)
        self.assertEqual(result, UserAgentSyntheticTypeValues.BOT.value)

    def test_detect_bot_bingbot(self):
        """Test detection of bingbot user agent."""
        user_agent = "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)"
        result = detect_synthetic_user_agent(user_agent)
        self.assertEqual(result, UserAgentSyntheticTypeValues.BOT.value)

    def test_detect_test_alwayson(self):
        """Test detection of alwayson test user agent."""
        user_agent = "AlwaysOn-Monitor/1.0"
        result = detect_synthetic_user_agent(user_agent)
        self.assertEqual(result, UserAgentSyntheticTypeValues.TEST.value)

    def test_case_insensitive_detection(self):
        """Test that detection is case insensitive."""
        # Test uppercase patterns
        user_agent_bot = "GOOGLEBOT/2.1"
        result = detect_synthetic_user_agent(user_agent_bot)
        self.assertEqual(result, UserAgentSyntheticTypeValues.BOT.value)

        user_agent_test = "ALWAYSON-Monitor/1.0"
        result = detect_synthetic_user_agent(user_agent_test)
        self.assertEqual(result, UserAgentSyntheticTypeValues.TEST.value)

    def test_normal_user_agent_not_detected(self):
        """Test that normal browser user agents are not detected as synthetic."""
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        result = detect_synthetic_user_agent(user_agent)
        self.assertIsNone(result)

    def test_none_user_agent(self):
        """Test that None user agent returns None."""
        result = detect_synthetic_user_agent(None)
        self.assertIsNone(result)

    def test_empty_user_agent(self):
        """Test that empty user agent returns None."""
        result = detect_synthetic_user_agent("")
        self.assertIsNone(result)

    def test_substring_match(self):
        """Test that substrings are detected correctly."""
        # Test googlebot in middle of string
        user_agent = "MyApp/1.0 googlebot crawler"
        result = detect_synthetic_user_agent(user_agent)
        self.assertEqual(result, UserAgentSyntheticTypeValues.BOT.value)

        # Test alwayson in middle of string
        user_agent = "TestFramework/1.0 alwayson monitoring"
        result = detect_synthetic_user_agent(user_agent)
        self.assertEqual(result, UserAgentSyntheticTypeValues.TEST.value)

    def test_priority_test_over_bot(self):
        """Test that test patterns take priority over bot patterns."""
        user_agent = "alwayson-googlebot/1.0"
        result = detect_synthetic_user_agent(user_agent)
        # alwayson should be checked first and return 'test'
        self.assertEqual(result, UserAgentSyntheticTypeValues.TEST.value)

    def test_bytes_like_user_agent(self):
        """Test that bytes-like user agents are decoded and detected."""

        test_cases = [
            (b"alwayson-monitor/1.0", UserAgentSyntheticTypeValues.TEST.value),
            (
                bytearray(b"googlebot/2.1"),
                UserAgentSyntheticTypeValues.BOT.value,
            ),
            (memoryview(b"MyApp/1.0"), None),
        ]

        for user_agent_raw, expected in test_cases:
            with self.subTest(user_agent=user_agent_raw):
                normalized = normalize_user_agent(user_agent_raw)
                result = detect_synthetic_user_agent(normalized)
                self.assertEqual(result, expected)


class TestNormalizeUserAgent(unittest.TestCase):
    def test_preserves_string(self):
        self.assertEqual(normalize_user_agent("Mozilla"), "Mozilla")

    def test_decodes_bytes(self):
        self.assertEqual(
            normalize_user_agent(b"Custom-Client/1.0"), "Custom-Client/1.0"
        )

    def test_decodes_bytearray(self):
        self.assertEqual(
            normalize_user_agent(bytearray(b"Bot/2.0")), "Bot/2.0"
        )

    def test_decodes_memoryview(self):
        self.assertEqual(
            normalize_user_agent(memoryview(b"Monitor/3.0")), "Monitor/3.0"
        )

    def test_none(self):
        self.assertIsNone(normalize_user_agent(None))
