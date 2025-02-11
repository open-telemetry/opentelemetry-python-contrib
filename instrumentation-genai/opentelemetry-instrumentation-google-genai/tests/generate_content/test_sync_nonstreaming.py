#!./run_with_env.sh

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
import logging
import os
import sys
import unittest

sys.path.append("../")

from common.base import TestCase


def create_valid_response(response_text="The model response", input_tokens=10, output_tokens=20):
    return {
        "modelVersion": "gemini-2.0-flash-test123",
        "usageMetadata": {
            "promptTokenCount": input_tokens,
            "candidatesTokenCount": output_tokens,
            "totalTokenCount": input_tokens + output_tokens,
        },
        "candidates": [{
            "content": {
                "role": "model",
                "parts": [{
                    "text": response_text,
                }],
            }
        }]
    }


class TestGenerateContentSyncNonstreaming(TestCase):

    def setUp(self):
        super().setUp()

    def configure_valid_response(self, response_text="The model_response", input_tokens=10, output_tokens=20):
        self.requests.add_response(create_valid_response(
            response_text=response_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens))

    def generate_content(self, *args, **kwargs):
        return self.client.models.generate_content(*args, **kwargs)

    def test_generates_span(self):
        self.configure_valid_response(response_text="Yep, it works!")
        response = self.generate_content(
            model="gemini-2.0-flash",
            contents="Does this work?")
        self.assertEqual(response.text, "Yep, it works!")
        self.otel.assert_has_span_named("google.genai.Models.generate_content")

    def test_generated_span_has_minimal_genai_attributes(self):
        self.configure_valid_response(response_text="Yep, it works!")
        self.generate_content(
            model="gemini-2.0-flash",
            contents="Does this work?")
        self.otel.assert_has_span_named("google.genai.Models.generate_content")
        span = self.otel.get_span_named("google.genai.Models.generate_content")
        self.assertEqual(span.attributes["gen_ai.system"], "gemini")
        self.assertEqual(span.attributes["gen_ai.operation.name"], "GenerateContent")

    def test_generated_span_counts_tokens(self):
        self.configure_valid_response(input_tokens=123, output_tokens=456)
        self.generate_content(
            model="gemini-2.0-flash",
            contents="Some input")
        self.otel.assert_has_span_named("google.genai.Models.generate_content")
        span = self.otel.get_span_named("google.genai.Models.generate_content")
        self.assertEqual(span.attributes["gen_ai.usage.input_tokens"], 123)
        self.assertEqual(span.attributes["gen_ai.usage.output_tokens"], 456)

    def test_records_system_prompt_as_log(self):
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "true"
        config = {
            "system_instruction": "foo"
        }
        self.configure_valid_response()
        self.generate_content(
            model="gemini-2.0-flash",
            contents="Some input",
            config=config)
        self.otel.assert_has_event_named("gen_ai.system.message")
        event_record = self.otel.get_event_named("gen_ai.system.message")
        self.assertEqual(event_record.attributes["gen_ai.system"], "gemini")
        self.assertEqual(event_record.body["content"], "foo")

    def test_does_not_record_system_prompt_as_log_if_disabled_by_env(self):
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "false"
        config = {
            "system_instruction": "foo"
        }
        self.configure_valid_response()
        self.generate_content(
            model="gemini-2.0-flash",
            contents="Some input",
            config=config)
        self.otel.assert_does_not_have_event_named("gen_ai.system.message")

    def test_does_not_record_system_prompt_as_log_if_no_system_prompt_present(self):
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "true"
        self.configure_valid_response()
        self.generate_content(
            model="gemini-2.0-flash",
            contents="Some input")
        self.otel.assert_does_not_have_event_named("gen_ai.system.message")

    def test_records_user_prompt_as_log(self):
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "true"
        self.configure_valid_response()
        self.generate_content(
            model="gemini-2.0-flash",
            contents="Some input")
        self.otel.assert_has_event_named("gen_ai.user.message")
        event_record = self.otel.get_event_named("gen_ai.user.message")
        self.assertEqual(event_record.attributes["gen_ai.system"], "gemini")
        self.assertEqual(event_record.body["content"], "Some input")

    def test_does_not_record_user_prompt_as_log_if_disabled_by_env(self):
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "false"
        self.configure_valid_response()
        self.generate_content(
            model="gemini-2.0-flash",
            contents="Some input")
        self.otel.assert_does_not_have_event_named("gen_ai.user.message")

    def test_records_response_as_log(self):
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "true"
        self.configure_valid_response(response_text="Some response content")
        self.generate_content(
            model="gemini-2.0-flash",
            contents="Some input")
        self.otel.assert_has_event_named("gen_ai.assistant.message")
        event_record = self.otel.get_event_named("gen_ai.assistant.message")
        self.assertEqual(event_record.attributes["gen_ai.system"], "gemini")
        self.assertIn("Some response content", json.dumps(event_record.body["content"]))

    def test_does_not_record_response_as_log_if_disabled_by_env(self):
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "false"
        self.configure_valid_response(response_text="Some response content")
        self.generate_content(
            model="gemini-2.0-flash",
            contents="Some input")
        self.otel.assert_does_not_have_event_named("gen_ai.assistant.message")

    def test_records_metrics_data(self):
        self.configure_valid_response()
        self.generate_content(
            model="gemini-2.0-flash",
            contents="Some input")
        self.otel.assert_has_metrics_data_named("gen_ai.client.token.usage")
        self.otel.assert_has_metrics_data_named("gen_ai.client.operation.duration")


def main():
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()


if __name__  == "__main__":
    main()
