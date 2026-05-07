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

# Includes work from:
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest import TestCase

# pylint: disable=no-name-in-module
from opentelemetry.sdk.extension.aws.trace.sampler._matcher import _Matcher
from opentelemetry.util.types import Attributes


class TestMatcher(TestCase):
    def test_wild_card_match(self):
        test_cases = [
            [None, "*"],
            ["", "*"],
            ["HelloWorld", "*"],
            ["HelloWorld", "HelloWorld"],
            ["HelloWorld", "Hello*"],
            ["HelloWorld", "*World"],
            ["HelloWorld", "?ello*"],
            ["HelloWorld", "Hell?W*d"],
            ["Hello.World", "*.World"],
            ["Bye.World", "*.World"],
        ]
        for test_case in test_cases:
            self.assertTrue(
                _Matcher.wild_card_match(
                    text=test_case[0], pattern=test_case[1]
                )
            )

    def test_wild_card_not_match(self):
        test_cases = [[None, "Hello*"], ["HelloWorld", None]]
        for test_case in test_cases:
            self.assertFalse(
                _Matcher.wild_card_match(
                    text=test_case[0], pattern=test_case[1]
                )
            )

    def test_attribute_matching(self):
        attributes: Attributes = {
            "dog": "bark",
            "cat": "meow",
            "cow": "mooo",
        }
        rule_attributes = {
            "dog": "bar?",
            "cow": "mooo",
        }

        self.assertTrue(_Matcher.attribute_match(attributes, rule_attributes))

    def test_attribute_matching_without_rule_attributes(self):
        attributes = {
            "dog": "bark",
            "cat": "meow",
            "cow": "mooo",
        }
        rule_attributes = {}
        print("LENGTH %s", len(rule_attributes))

        self.assertTrue(_Matcher.attribute_match(attributes, rule_attributes))

    def test_attribute_matching_without_span_attributes(self):
        attributes = {}
        rule_attributes = {
            "dog": "bar?",
            "cow": "mooo",
        }

        self.assertFalse(_Matcher.attribute_match(attributes, rule_attributes))
