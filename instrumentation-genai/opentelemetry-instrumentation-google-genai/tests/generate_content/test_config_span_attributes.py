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

from google.genai.types import GenerateContentConfig

from .base import TestCase


class ConfigSpanAttributesTestCase(TestCase):

    def setUp(self):
        super().setUp()
        self.configure_valid_response(text="Some response")

    def generate_content(self, *args, **kwargs):
        return self.client.models.generate_content(*args, **kwargs)

    def generate_and_get_span(self, config):
        self.client.models.generate_content(
            model="gemini-2.0-flash",
            contents="Some input prompt",
            config=config,
        )
        self.otel.assert_has_span_named("generate_content gemini-2.0-flash")
        return self.otel.get_span_named("generate_content gemini-2.0-flash")

    def test_option_reflected_to_span_attribute_choice_count_config_dict(self):
        span = self.generate_and_get_span(config={"candidate_count": 2})
        self.assertEqual(span.attributes["gen_ai.request.choice.count"], 2)

    def test_option_reflected_to_span_attribute_choice_count_config_obj(self):
        span = self.generate_and_get_span(
            config=GenerateContentConfig(candidate_count=2)
        )
        self.assertEqual(span.attributes["gen_ai.request.choice.count"], 2)

    def test_option_reflected_to_span_attribute_seed_config_dict(self):
        span = self.generate_and_get_span(config={"seed": 12345})
        self.assertEqual(span.attributes["gen_ai.request.seed"], 12345)

    def test_option_reflected_to_span_attribute_seed_config_obj(self):
        span = self.generate_and_get_span(
            config=GenerateContentConfig(seed=12345)
        )
        self.assertEqual(span.attributes["gen_ai.request.seed"], 12345)

    def test_option_reflected_to_span_attribute_frequency_penalty(self):
        span = self.generate_and_get_span(config={"frequency_penalty": 1.0})
        self.assertEqual(
            span.attributes["gen_ai.request.frequency_penalty"], 1.0
        )

    def test_option_reflected_to_span_attribute_max_tokens(self):
        span = self.generate_and_get_span(
            config=GenerateContentConfig(max_output_tokens=5000)
        )
        self.assertEqual(span.attributes["gen_ai.request.max_tokens"], 5000)

    def test_option_reflected_to_span_attribute_presence_penalty(self):
        span = self.generate_and_get_span(
            config=GenerateContentConfig(presence_penalty=0.5)
        )
        self.assertEqual(
            span.attributes["gen_ai.request.presence_penalty"], 0.5
        )

    def test_option_reflected_to_span_attribute_stop_sequences(self):
        span = self.generate_and_get_span(
            config={"stop_sequences": ["foo", "bar"]}
        )
        stop_sequences = span.attributes["gen_ai.request.stop_sequences"]
        self.assertEqual(len(stop_sequences), 2)
        self.assertEqual(stop_sequences[0], "foo")
        self.assertEqual(stop_sequences[1], "bar")

    def test_option_reflected_to_span_attribute_top_k(self):
        span = self.generate_and_get_span(
            config=GenerateContentConfig(top_k=20)
        )
        self.assertEqual(span.attributes["gen_ai.request.top_k"], 20)

    def test_option_reflected_to_span_attribute_top_p(self):
        span = self.generate_and_get_span(config={"top_p": 10})
        self.assertEqual(span.attributes["gen_ai.request.top_p"], 10)

    def test_option_not_reflected_to_span_attribute_system_instruction(self):
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
