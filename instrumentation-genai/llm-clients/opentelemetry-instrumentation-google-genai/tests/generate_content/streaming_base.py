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

from .base import TestCase


class StreamingTestCase(TestCase):
    # The "setUp" function is defined by "unittest.TestCase" and thus
    # this name must be used. Uncertain why pylint doesn't seem to
    # recognize that this is a unit test class for which this is inherited.
    def setUp(self):  # pylint: disable=invalid-name
        super().setUp()
        if self.__class__ == StreamingTestCase:
            raise unittest.SkipTest("Skipping testcase base.")

    def generate_content(self, *args, **kwargs):
        raise NotImplementedError("Must implement 'generate_content'.")

    @property
    def expected_function_name(self):
        raise NotImplementedError("Must implement 'expected_function_name'.")

    def test_instrumentation_does_not_break_core_functionality(self):
        self.configure_valid_response(text="Yep, it works!")
        responses = self.generate_content(
            model="gemini-2.0-flash", contents="Does this work?"
        )
        self.assertEqual(len(responses), 1)
        response = responses[0]
        self.assertEqual(response.text, "Yep, it works!")

    def test_handles_multiple_ressponses(self):
        self.configure_valid_response(text="First response")
        self.configure_valid_response(text="Second response")
        responses = self.generate_content(
            model="gemini-2.0-flash", contents="Does this work?"
        )
        self.assertEqual(len(responses), 2)
        self.assertEqual(responses[0].text, "First response")
        self.assertEqual(responses[1].text, "Second response")
        choice_events = self.otel.get_events_named("gen_ai.choice")
        self.assertEqual(len(choice_events), 2)

    def test_includes_token_counts_in_span_aggregated_from_responses(self):
        # Configure multiple responses whose input/output tokens should be
        # accumulated together when summarizing the end-to-end request.
        #
        #   Input: 1 + 3 + 5 => 4 + 5 => 9
        #   Output: 2 + 4 + 6 => 6 + 6 => 12
        self.configure_valid_response(input_tokens=1, output_tokens=2)
        self.configure_valid_response(input_tokens=3, output_tokens=4)
        self.configure_valid_response(input_tokens=5, output_tokens=6)

        self.generate_content(model="gemini-2.0-flash", contents="Some input")

        self.otel.assert_has_span_named("generate_content gemini-2.0-flash")
        span = self.otel.get_span_named("generate_content gemini-2.0-flash")
        self.assertEqual(span.attributes["gen_ai.usage.input_tokens"], 9)
        self.assertEqual(span.attributes["gen_ai.usage.output_tokens"], 12)
