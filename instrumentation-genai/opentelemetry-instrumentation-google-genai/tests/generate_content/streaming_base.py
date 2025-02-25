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

import os
import unittest

from ..common.base import TestCase
from .util import create_valid_response


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

    def configure_valid_response(
        self,
        *args,
        **kwargs
    ):
        self.requests.add_response(
            create_valid_response(*args, **kwargs))

    def test_instrumentation_does_not_break_core_functionality(self):
        self.configure_valid_response(response_text="Yep, it works!")
        responses = self.generate_content(
            model="gemini-2.0-flash", contents="Does this work?"
        )
        self.assertEqual(len(responses), 1)
        response = responses[0]
        self.assertEqual(response.text, "Yep, it works!")

    def test_handles_multiple_ressponses(self):
        self.configure_valid_response(response_text="First response")
        self.configure_valid_response(response_text="Second response")
        responses = self.generate_content(
            model="gemini-2.0-flash", contents="Does this work?"
        )
        self.assertEqual(len(responses), 2)
        self.assertEqual(responses[0].text, "First response")
        self.assertEqual(responses[1].text, "Second response")
        choice_events = self.otel.get_events_named("gen_ai.choice")
        self.assertEqual(len(choice_events), 2)
