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

from google.genai.types import GenerateContentConfig

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

    def generate_and_get_span(self, config):
        self.generate_content(
            model="gemini-2.0-flash",
            contents="Some input prompt",
            config=config,
        )
        self.otel.assert_has_span_named("generate_content gemini-2.0-flash")
        return self.otel.get_span_named("generate_content gemini-2.0-flash")

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

    def test_option_reflected_to_span_attribute_choice_count_config_dict(self):
        self.configure_valid_response(text="Some response")
        span = self.generate_and_get_span(config={"candidate_count": 2})
        self.assertEqual(span.attributes["gen_ai.request.choice.count"], 2)

    def test_option_reflected_to_span_attribute_choice_count_config_obj(self):
        self.configure_valid_response(text="Some response")
        span = self.generate_and_get_span(
            config=GenerateContentConfig(candidate_count=2)
        )
        self.assertEqual(span.attributes["gen_ai.request.choice.count"], 2)

    def test_option_reflected_to_span_attribute_seed_config_dict(self):
        self.configure_valid_response(text="Some response")
        span = self.generate_and_get_span(config={"seed": 12345})
        self.assertEqual(span.attributes["gen_ai.request.seed"], 12345)

    def test_option_reflected_to_span_attribute_seed_config_obj(self):
        self.configure_valid_response(text="Some response")
        span = self.generate_and_get_span(
            config=GenerateContentConfig(seed=12345)
        )
        self.assertEqual(span.attributes["gen_ai.request.seed"], 12345)

    def test_option_reflected_to_span_attribute_frequency_penalty(self):
        self.configure_valid_response(text="Some response")
        span = self.generate_and_get_span(config={"frequency_penalty": 1.0})
        self.assertEqual(
            span.attributes["gen_ai.request.frequency_penalty"], 1.0
        )

    def test_option_reflected_to_span_attribute_max_tokens(self):
        self.configure_valid_response(text="Some response")
        span = self.generate_and_get_span(
            config=GenerateContentConfig(max_output_tokens=5000)
        )
        self.assertEqual(span.attributes["gen_ai.request.max_tokens"], 5000)

    def test_option_reflected_to_span_attribute_presence_penalty(self):
        self.configure_valid_response(text="Some response")
        span = self.generate_and_get_span(
            config=GenerateContentConfig(presence_penalty=0.5)
        )
        self.assertEqual(
            span.attributes["gen_ai.request.presence_penalty"], 0.5
        )

    def test_option_reflected_to_span_attribute_stop_sequences(self):
        self.configure_valid_response(text="Some response")
        span = self.generate_and_get_span(
            config={"stop_sequences": ["foo", "bar"]}
        )
        stop_sequences = span.attributes["gen_ai.request.stop_sequences"]
        self.assertEqual(len(stop_sequences), 2)
        self.assertEqual(stop_sequences[0], "foo")
        self.assertEqual(stop_sequences[1], "bar")

    def test_option_reflected_to_span_attribute_top_k(self):
        self.configure_valid_response(text="Some response")
        span = self.generate_and_get_span(
            config=GenerateContentConfig(top_k=20)
        )
        self.assertEqual(span.attributes["gen_ai.request.top_k"], 20)

    def test_option_reflected_to_span_attribute_top_p(self):
        self.configure_valid_response(text="Some response")
        span = self.generate_and_get_span(config={"top_p": 10})
        self.assertEqual(span.attributes["gen_ai.request.top_p"], 10)

    def test_option_not_reflected_to_span_attribute_system_instruction(self):
        self.configure_valid_response(text="Some response")
        span = self.generate_and_get_span(
            config={"system_instruction": "Yadda yadda yadda"}
        )
        self.assertNotIn(
            "gen_ai.gcp.request.system_instruction", span.attributes
        )
        self.assertNotIn("gen_ai.request.system_instruction", span.attributes)
        for key in span.attributes:
            value = span.attributes[key]
            if isinstance(value, str):
                self.assertNotIn("Yadda yadda yadda", value)

    def test_option_not_reflected_to_span_attribute_http_headers(self):
        self.configure_valid_response(text="Some response")
        span = self.generate_and_get_span(
            config={
                "http_options": {
                    "base_url": "my.backend.override",
                    "headers": {
                        "sensitive": 12345,
                    },
                }
            }
        )
        self.assertEqual(
            span.attributes["gen_ai.gcp.request.http_options.base_url"],
            "my.backend.override",
        )
        self.assertNotIn(
            "gen_ai.gcp.request.http_options.headers.sensitive",
            span.attributes,
        )

    def test_option_reflected_to_span_attribute_automatic_func_calling(self):
        self.configure_valid_response(text="Some response")
        span = self.generate_and_get_span(
            config={
                "automatic_function_calling": {
                    "ignore_call_history": True,
                }
            }
        )
        self.assertTrue(
            span.attributes[
                "gen_ai.gcp.request.automatic_function_calling.ignore_call_history"
            ]
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
