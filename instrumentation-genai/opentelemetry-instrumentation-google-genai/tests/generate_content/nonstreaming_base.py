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
import unittest
from unittest.mock import patch

import pytest
from google.genai.types import GenerateContentConfig, Part
from pydantic import BaseModel, Field

from opentelemetry import context as context_api
from opentelemetry.instrumentation._semconv import (
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _StabilityMode,
)
from opentelemetry.instrumentation.google_genai import (
    GENERATE_CONTENT_EXTRA_ATTRIBUTES_CONTEXT_KEY,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes,
)
from opentelemetry.util.genai.types import ContentCapturingMode

from .base import TestCase

# pylint: disable=too-many-public-methods


class ExampleResponseSchema(BaseModel):
    name: str = Field(description="A Destination's Name")


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

    def _generate_and_get_span(self, config):
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

    def test_generated_span_has_extra_genai_attributes(self):
        self.configure_valid_response(text="Yep, it works!")
        tok = context_api.attach(
            context_api.set_value(
                GENERATE_CONTENT_EXTRA_ATTRIBUTES_CONTEXT_KEY,
                {"extra_attribute_key": "extra_attribute_value"},
            )
        )
        try:
            self.generate_content(
                model="gemini-2.0-flash", contents="Does this work?"
            )
            self.otel.assert_has_span_named(
                "generate_content gemini-2.0-flash"
            )
            span = self.otel.get_span_named(
                "generate_content gemini-2.0-flash"
            )
            self.assertEqual(
                span.attributes["extra_attribute_key"], "extra_attribute_value"
            )
        finally:
            context_api.detach(tok)

    def test_span_and_event_still_written_when_response_is_exception(self):
        self.configure_exception(ValueError("Uh oh!"))
        patched_environ = patch.dict(
            "os.environ",
            {
                "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "SPAN_AND_EVENT",
                "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
            },
        )
        with patched_environ:
            _OpenTelemetrySemanticConventionStability._initialized = False
            _OpenTelemetrySemanticConventionStability._initialize()
            with pytest.raises(ValueError):
                self.generate_content(
                    model="gemini-2.0-flash", contents="Does this work?"
                )
            self.otel.assert_has_span_named(
                "generate_content gemini-2.0-flash"
            )
            span = self.otel.get_span_named(
                "generate_content gemini-2.0-flash"
            )
            self.otel.assert_has_event_named(
                "gen_ai.client.inference.operation.details"
            )
            event = self.otel.get_event_named(
                "gen_ai.client.inference.operation.details"
            )
            assert (
                span.attributes["error.type"]
                == event.attributes["error.type"]
                == "ValueError"
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

    @patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true"},
    )
    def test_records_system_prompt_as_log(self):
        config = {"system_instruction": "foo"}
        self.configure_valid_response()
        self.generate_content(
            model="gemini-2.0-flash", contents="Some input", config=config
        )
        self.otel.assert_has_event_named("gen_ai.system.message")
        event_record = self.otel.get_event_named("gen_ai.system.message")
        self.assertEqual(event_record.attributes["gen_ai.system"], "gemini")
        self.assertEqual(event_record.body["content"], "foo")

    @patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true"},
    )
    def test_system_prompt_passed_as_list_of_text(self):
        config = GenerateContentConfig(
            system_instruction=["help", "me please."]
        )
        self.configure_valid_response()
        self.generate_content(
            model="gemini-2.0-flash", contents="Some input", config=config
        )
        self.otel.assert_has_event_named("gen_ai.system.message")
        event_record = self.otel.get_event_named("gen_ai.system.message")
        self.assertEqual(event_record.body["content"], "help me please.")

    @patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true"},
    )
    def test_system_prompt_passed_as_list_of_text_parts(self):
        config = GenerateContentConfig(
            system_instruction=[
                Part.from_text(text="help"),
                Part.from_text(text="me please."),
            ]
        )
        self.configure_valid_response()
        self.generate_content(
            model="gemini-2.0-flash", contents="Some input", config=config
        )
        self.otel.assert_has_event_named("gen_ai.system.message")
        event_record = self.otel.get_event_named("gen_ai.system.message")
        self.assertEqual(event_record.body["content"], "help me please.")

    @patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true"},
    )
    def test_system_prompt_passed_is_invalid(self):
        config = GenerateContentConfig(
            system_instruction=[
                Part.from_uri(file_uri="test.jpg"),
            ]
        )
        self.configure_valid_response()
        self.generate_content(
            model="gemini-2.0-flash", contents="Some input", config=config
        )
        self.otel.assert_does_not_have_event_named("gen_ai.system.message")

    @patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false"},
    )
    def test_does_not_record_system_prompt_as_log_if_disabled_by_env(self):
        config = {"system_instruction": "foo"}
        self.configure_valid_response()
        self.generate_content(
            model="gemini-2.0-flash", contents="Some input", config=config
        )
        self.otel.assert_has_event_named("gen_ai.system.message")
        event_record = self.otel.get_event_named("gen_ai.system.message")
        self.assertEqual(event_record.attributes["gen_ai.system"], "gemini")
        self.assertEqual(event_record.body["content"], "<elided>")

    @patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true"},
    )
    def test_does_not_record_system_prompt_as_log_if_no_system_prompt_present(
        self,
    ):
        self.configure_valid_response()
        self.generate_content(model="gemini-2.0-flash", contents="Some input")
        self.otel.assert_does_not_have_event_named("gen_ai.system.message")

    @patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true"},
    )
    def test_records_user_prompt_as_log(self):
        self.configure_valid_response()
        self.generate_content(model="gemini-2.0-flash", contents="Some input")
        self.otel.assert_has_event_named("gen_ai.user.message")
        event_record = self.otel.get_event_named("gen_ai.user.message")
        self.assertEqual(event_record.attributes["gen_ai.system"], "gemini")
        self.assertEqual(event_record.body["content"], "Some input")

    @patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false"},
    )
    def test_does_not_record_user_prompt_as_log_if_disabled_by_env(self):
        self.configure_valid_response()
        self.generate_content(model="gemini-2.0-flash", contents="Some input")
        self.otel.assert_has_event_named("gen_ai.user.message")
        event_record = self.otel.get_event_named("gen_ai.user.message")
        self.assertEqual(event_record.attributes["gen_ai.system"], "gemini")
        self.assertEqual(event_record.body["content"], "<elided>")

    @patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true"},
    )
    def test_records_response_as_log(self):
        self.configure_valid_response(text="Some response content")
        self.generate_content(model="gemini-2.0-flash", contents="Some input")
        self.otel.assert_has_event_named("gen_ai.choice")
        event_record = self.otel.get_event_named("gen_ai.choice")
        self.assertEqual(event_record.attributes["gen_ai.system"], "gemini")
        self.assertIn(
            "Some response content", json.dumps(event_record.body["content"])
        )

    @patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false"},
    )
    def test_does_not_record_response_as_log_if_disabled_by_env(self):
        self.configure_valid_response(text="Some response content")
        self.generate_content(model="gemini-2.0-flash", contents="Some input")
        self.otel.assert_has_event_named("gen_ai.choice")
        event_record = self.otel.get_event_named("gen_ai.choice")
        self.assertEqual(event_record.attributes["gen_ai.system"], "gemini")
        self.assertEqual(event_record.body["content"], "<elided>")

    @patch.dict(
        "os.environ",
        {
            "OTEL_GOOGLE_GENAI_GENERATE_CONTENT_CONFIG_INCLUDES": "gcp.gen_ai.operation.config.response_schema"
        },
    )
    def test_new_semconv_record_completion_as_log(self):
        for mode in ContentCapturingMode:
            patched_environ = patch.dict(
                "os.environ",
                {
                    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": mode.name,
                    "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
                },
            )
            patched_otel_mapping = patch.dict(
                _OpenTelemetrySemanticConventionStability._OTEL_SEMCONV_STABILITY_SIGNAL_MAPPING,
                {
                    _OpenTelemetryStabilitySignalType.GEN_AI: _StabilityMode.GEN_AI_LATEST_EXPERIMENTAL
                },
            )
            content = "Some input"
            output = "Some response content"
            sys_instr = "System instruction"
            with self.subTest(
                f"mode: {mode}", patched_environ=patched_environ
            ):
                self.setUp()
                with patched_environ, patched_otel_mapping:
                    self.configure_valid_response(text=output)
                    self.generate_content(
                        model="gemini-2.0-flash",
                        contents=content,
                        config=GenerateContentConfig(
                            system_instruction=sys_instr,
                            response_schema=ExampleResponseSchema,
                        ),
                    )
                    self.otel.assert_has_event_named(
                        "gen_ai.client.inference.operation.details"
                    )
                    event = self.otel.get_event_named(
                        "gen_ai.client.inference.operation.details"
                    )
                    assert (
                        event.attributes[
                            "gcp.gen_ai.operation.config.response_schema"
                        ]
                        == "<class 'tests.generate_content.nonstreaming_base.ExampleResponseSchema'>"
                    )
                    if mode in [
                        ContentCapturingMode.NO_CONTENT,
                        ContentCapturingMode.SPAN_ONLY,
                    ]:
                        self.assertNotIn(
                            gen_ai_attributes.GEN_AI_INPUT_MESSAGES,
                            event.attributes,
                        )
                        self.assertNotIn(
                            gen_ai_attributes.GEN_AI_OUTPUT_MESSAGES,
                            event.attributes,
                        )
                        self.assertNotIn(
                            gen_ai_attributes.GEN_AI_SYSTEM_INSTRUCTIONS,
                            event.attributes,
                        )
                    else:
                        expected_event_attributes = {
                            gen_ai_attributes.GEN_AI_INPUT_MESSAGES: (
                                {
                                    "role": "user",
                                    "parts": (
                                        {"content": content, "type": "text"},
                                    ),
                                },
                            ),
                            gen_ai_attributes.GEN_AI_OUTPUT_MESSAGES: (
                                {
                                    "role": "assistant",
                                    "parts": (
                                        {"content": output, "type": "text"},
                                    ),
                                    "finish_reason": "",
                                },
                            ),
                            gen_ai_attributes.GEN_AI_SYSTEM_INSTRUCTIONS: (
                                {"content": sys_instr, "type": "text"},
                            ),
                        }
                        self.assertEqual(
                            event.attributes[
                                gen_ai_attributes.GEN_AI_INPUT_MESSAGES
                            ],
                            expected_event_attributes[
                                gen_ai_attributes.GEN_AI_INPUT_MESSAGES
                            ],
                        )
                        self.assertEqual(
                            event.attributes[
                                gen_ai_attributes.GEN_AI_OUTPUT_MESSAGES
                            ],
                            expected_event_attributes[
                                gen_ai_attributes.GEN_AI_OUTPUT_MESSAGES
                            ],
                        )
                        self.assertEqual(
                            event.attributes[
                                gen_ai_attributes.GEN_AI_SYSTEM_INSTRUCTIONS
                            ],
                            expected_event_attributes[
                                gen_ai_attributes.GEN_AI_SYSTEM_INSTRUCTIONS
                            ],
                        )
                self.tearDown()

    def test_new_semconv_record_completion_in_span(self):
        for mode in ContentCapturingMode:
            patched_environ = patch.dict(
                "os.environ",
                {
                    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": mode.name,
                    "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
                },
            )
            patched_otel_mapping = patch.dict(
                _OpenTelemetrySemanticConventionStability._OTEL_SEMCONV_STABILITY_SIGNAL_MAPPING,
                {
                    _OpenTelemetryStabilitySignalType.GEN_AI: _StabilityMode.GEN_AI_LATEST_EXPERIMENTAL
                },
            )
            with self.subTest(
                f"mode: {mode}", patched_environ=patched_environ
            ):
                self.setUp()
                with patched_environ, patched_otel_mapping:
                    self.configure_valid_response(text="Some response content")
                    self.generate_content(
                        model="gemini-2.0-flash",
                        contents="Some input",
                        config=GenerateContentConfig(
                            system_instruction="System instruction",
                            response_schema=ExampleResponseSchema,
                        ),
                    )
                    span = self.otel.get_span_named(
                        "generate_content gemini-2.0-flash"
                    )
                    if mode in [
                        ContentCapturingMode.SPAN_ONLY,
                        ContentCapturingMode.SPAN_AND_EVENT,
                    ]:
                        self.assertEqual(
                            span.attributes[
                                gen_ai_attributes.GEN_AI_INPUT_MESSAGES
                            ],
                            '[{"role":"user","parts":[{"content":"Some input","type":"text"}]}]',
                        )
                        self.assertEqual(
                            span.attributes[
                                gen_ai_attributes.GEN_AI_OUTPUT_MESSAGES
                            ],
                            '[{"role":"assistant","parts":[{"content":"Some response content","type":"text"}],"finish_reason":""}]',
                        )
                        self.assertEqual(
                            span.attributes[
                                gen_ai_attributes.GEN_AI_SYSTEM_INSTRUCTIONS
                            ],
                            '[{"content":"System instruction","type":"text"}]',
                        )
                    else:
                        self.assertNotIn(
                            gen_ai_attributes.GEN_AI_INPUT_MESSAGES,
                            span.attributes,
                        )
                        self.assertNotIn(
                            gen_ai_attributes.GEN_AI_OUTPUT_MESSAGES,
                            span.attributes,
                        )
                        self.assertNotIn(
                            gen_ai_attributes.GEN_AI_SYSTEM_INSTRUCTIONS,
                            span.attributes,
                        )

                self.tearDown()

    def test_records_metrics_data(self):
        self.configure_valid_response()
        self.generate_content(model="gemini-2.0-flash", contents="Some input")
        self.otel.assert_has_metrics_data_named("gen_ai.client.token.usage")
        self.otel.assert_has_metrics_data_named(
            "gen_ai.client.operation.duration"
        )
