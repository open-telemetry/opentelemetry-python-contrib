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

import json
import os
import unittest

from .base import TestCase


class NonStreamingTestCase(TestCase):
    # The "setUp" function is defined by "unittest.TestCase" and thus
    # this name must be used. Uncertain why pylint doesn't seem to
    # recognize that this is a unit test class for which this is inherited.
    def setUp(self):  # pylint: disable=invalid-name
        super().setUp()
        if self.__class__ == NonStreamingTestCase:
            raise unittest.SkipTest("Skipping testcase base.")

    def generate_content(self, *args, **kwargs):
        raise NotImplementedError("Must implement 'generate_content'.")

    @property
    def expected_function_name(self):
        raise NotImplementedError("Must implement 'expected_function_name'.")

    def test_instrumentation_does_not_break_core_functionality(self):
        self.configure_valid_response(text="Yep, it works!")
        response = self.generate_content(
            model="gemini-2.0-flash", contents="Does this work?"
        )
        self.assertEqual(response.text, "Yep, it works!")

    def test_generates_span(self):
        self.configure_valid_response(text="Yep, it works!")
        response = self.generate_content(
            model="gemini-2.0-flash", contents="Does this work?"
        )
        self.assertEqual(response.text, "Yep, it works!")
        self.otel.assert_has_span_named("generate_content gemini-2.0-flash")

    def test_model_reflected_into_span_name(self):
        self.configure_valid_response(text="Yep, it works!")
        response = self.generate_content(
            model="gemini-1.5-flash", contents="Does this work?"
        )
        self.assertEqual(response.text, "Yep, it works!")
        self.otel.assert_has_span_named("generate_content gemini-1.5-flash")

    def test_generated_span_has_minimal_genai_attributes(self):
        self.configure_valid_response(text="Yep, it works!")
        self.generate_content(
            model="gemini-2.0-flash", contents="Does this work?"
        )
        self.otel.assert_has_span_named("generate_content gemini-2.0-flash")
        span = self.otel.get_span_named("generate_content gemini-2.0-flash")
        self.assertEqual(span.attributes["gen_ai.system"], "gemini")
        self.assertEqual(
            span.attributes["gen_ai.operation.name"], "generate_content"
        )

    def test_generated_span_has_correct_function_name(self):
        self.configure_valid_response(text="Yep, it works!")
        self.generate_content(
            model="gemini-2.0-flash", contents="Does this work?"
        )
        self.otel.assert_has_span_named("generate_content gemini-2.0-flash")
        span = self.otel.get_span_named("generate_content gemini-2.0-flash")
        self.assertEqual(
            span.attributes["code.function.name"], self.expected_function_name
        )

    def test_generated_span_has_vertex_ai_system_when_configured(self):
        self.set_use_vertex(True)
        self.configure_valid_response(text="Yep, it works!")
        self.generate_content(
            model="gemini-2.0-flash", contents="Does this work?"
        )
        self.otel.assert_has_span_named("generate_content gemini-2.0-flash")
        span = self.otel.get_span_named("generate_content gemini-2.0-flash")
        self.assertEqual(span.attributes["gen_ai.system"], "vertex_ai")
        self.assertEqual(
            span.attributes["gen_ai.operation.name"], "generate_content"
        )

    def test_generated_span_counts_tokens(self):
        self.configure_valid_response(input_tokens=123, output_tokens=456)
        self.generate_content(model="gemini-2.0-flash", contents="Some input")
        self.otel.assert_has_span_named("generate_content gemini-2.0-flash")
        span = self.otel.get_span_named("generate_content gemini-2.0-flash")
        self.assertEqual(span.attributes["gen_ai.usage.input_tokens"], 123)
        self.assertEqual(span.attributes["gen_ai.usage.output_tokens"], 456)

    def test_records_system_prompt_as_log(self):
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = (
            "true"
        )
        config = {"system_instruction": "foo"}
        self.configure_valid_response()
        self.generate_content(
            model="gemini-2.0-flash", contents="Some input", config=config
        )
        self.otel.assert_has_event_named("gen_ai.system.message")
        event_record = self.otel.get_event_named("gen_ai.system.message")
        self.assertEqual(event_record.attributes["gen_ai.system"], "gemini")
        self.assertEqual(event_record.body["content"], "foo")

    def test_does_not_record_system_prompt_as_log_if_disabled_by_env(self):
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = (
            "false"
        )
        config = {"system_instruction": "foo"}
        self.configure_valid_response()
        self.generate_content(
            model="gemini-2.0-flash", contents="Some input", config=config
        )
        self.otel.assert_has_event_named("gen_ai.system.message")
        event_record = self.otel.get_event_named("gen_ai.system.message")
        self.assertEqual(event_record.attributes["gen_ai.system"], "gemini")
        self.assertEqual(event_record.body["content"], "<elided>")

    def test_does_not_record_system_prompt_as_log_if_no_system_prompt_present(
        self,
    ):
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = (
            "true"
        )
        self.configure_valid_response()
        self.generate_content(model="gemini-2.0-flash", contents="Some input")
        self.otel.assert_does_not_have_event_named("gen_ai.system.message")

    def test_records_user_prompt_as_log(self):
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = (
            "true"
        )
        self.configure_valid_response()
        self.generate_content(model="gemini-2.0-flash", contents="Some input")
        self.otel.assert_has_event_named("gen_ai.user.message")
        event_record = self.otel.get_event_named("gen_ai.user.message")
        self.assertEqual(event_record.attributes["gen_ai.system"], "gemini")
        self.assertEqual(event_record.body["content"], "Some input")

    def test_does_not_record_user_prompt_as_log_if_disabled_by_env(self):
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = (
            "false"
        )
        self.configure_valid_response()
        self.generate_content(model="gemini-2.0-flash", contents="Some input")
        self.otel.assert_has_event_named("gen_ai.user.message")
        event_record = self.otel.get_event_named("gen_ai.user.message")
        self.assertEqual(event_record.attributes["gen_ai.system"], "gemini")
        self.assertEqual(event_record.body["content"], "<elided>")

    def test_records_response_as_log(self):
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = (
            "true"
        )
        self.configure_valid_response(text="Some response content")
        self.generate_content(model="gemini-2.0-flash", contents="Some input")
        self.otel.assert_has_event_named("gen_ai.choice")
        event_record = self.otel.get_event_named("gen_ai.choice")
        self.assertEqual(event_record.attributes["gen_ai.system"], "gemini")
        self.assertIn(
            "Some response content", json.dumps(event_record.body["content"])
        )

    def test_does_not_record_response_as_log_if_disabled_by_env(self):
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = (
            "false"
        )
        self.configure_valid_response(text="Some response content")
        self.generate_content(model="gemini-2.0-flash", contents="Some input")
        self.otel.assert_has_event_named("gen_ai.choice")
        event_record = self.otel.get_event_named("gen_ai.choice")
        self.assertEqual(event_record.attributes["gen_ai.system"], "gemini")
        self.assertEqual(event_record.body["content"], "<elided>")

    def test_records_metrics_data(self):
        self.configure_valid_response()
        self.generate_content(model="gemini-2.0-flash", contents="Some input")
        self.otel.assert_has_metrics_data_named("gen_ai.client.token.usage")
        self.otel.assert_has_metrics_data_named(
            "gen_ai.client.operation.duration"
        )
