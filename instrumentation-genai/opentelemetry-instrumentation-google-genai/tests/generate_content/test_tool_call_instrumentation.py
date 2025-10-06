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

from unittest.mock import patch

import google.genai.types as genai_types

from opentelemetry.instrumentation._semconv import (
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _StabilityMode,
)
from opentelemetry.util.genai.types import ContentCapturingMode

from .base import TestCase


class ToolCallInstrumentationTestCase(TestCase):
    def test_tool_calls_with_config_dict_outputs_spans(self):
        calls = []

        def handle(*args, **kwargs):
            calls.append((args, kwargs))
            return "some result"

        def somefunction(somearg):
            print("somearg=%s", somearg)

        self.mock_generate_content.side_effect = handle
        self.client.models.generate_content(
            model="some-model-name",
            contents="Some content",
            config={
                "tools": [somefunction],
            },
        )
        self.assertEqual(len(calls), 1)
        config = calls[0][1]["config"]
        tools = config.tools
        wrapped_somefunction = tools[0]

        self.assertIsNone(
            self.otel.get_span_named("execute_tool somefunction")
        )
        wrapped_somefunction("someparam")
        self.otel.assert_has_span_named("execute_tool somefunction")
        generated_span = self.otel.get_span_named("execute_tool somefunction")
        self.assertIn("gen_ai.system", generated_span.attributes)
        self.assertEqual(
            generated_span.attributes["gen_ai.tool.name"], "somefunction"
        )
        self.assertEqual(
            generated_span.attributes["code.args.positional.count"], 1
        )
        self.assertEqual(
            generated_span.attributes["code.args.keyword.count"], 0
        )

    def test_tool_calls_with_config_object_outputs_spans(self):
        calls = []

        def handle(*args, **kwargs):
            calls.append((args, kwargs))
            return "some result"

        def somefunction(somearg):
            print("somearg=%s", somearg)

        self.mock_generate_content.side_effect = handle
        self.client.models.generate_content(
            model="some-model-name",
            contents="Some content",
            config=genai_types.GenerateContentConfig(
                tools=[somefunction],
            ),
        )
        self.assertEqual(len(calls), 1)
        config = calls[0][1]["config"]
        tools = config.tools
        wrapped_somefunction = tools[0]

        self.assertIsNone(
            self.otel.get_span_named("execute_tool somefunction")
        )
        wrapped_somefunction("someparam")
        self.otel.assert_has_span_named("execute_tool somefunction")
        generated_span = self.otel.get_span_named("execute_tool somefunction")
        self.assertIn("gen_ai.system", generated_span.attributes)
        self.assertEqual(
            generated_span.attributes["gen_ai.tool.name"], "somefunction"
        )
        self.assertEqual(
            generated_span.attributes["code.args.positional.count"], 1
        )
        self.assertEqual(
            generated_span.attributes["code.args.keyword.count"], 0
        )

    @patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true"},
    )
    def test_tool_calls_record_parameter_values_on_span_if_enabled(self):
        calls = []

        def handle(*args, **kwargs):
            calls.append((args, kwargs))
            return "some result"

        def somefunction(someparam, otherparam=2):
            print("someparam=%s, otherparam=%s", someparam, otherparam)

        self.mock_generate_content.side_effect = handle
        self.client.models.generate_content(
            model="some-model-name",
            contents="Some content",
            config={
                "tools": [somefunction],
            },
        )
        self.assertEqual(len(calls), 1)
        config = calls[0][1]["config"]
        tools = config.tools
        wrapped_somefunction = tools[0]
        wrapped_somefunction(123, otherparam="abc")
        self.otel.assert_has_span_named("execute_tool somefunction")
        generated_span = self.otel.get_span_named("execute_tool somefunction")
        self.assertEqual(
            generated_span.attributes[
                "code.function.parameters.someparam.type"
            ],
            "int",
        )
        self.assertEqual(
            generated_span.attributes[
                "code.function.parameters.otherparam.type"
            ],
            "str",
        )
        self.assertEqual(
            generated_span.attributes[
                "code.function.parameters.someparam.value"
            ],
            123,
        )
        self.assertEqual(
            generated_span.attributes[
                "code.function.parameters.otherparam.value"
            ],
            "abc",
        )

    @patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false"},
    )
    def test_tool_calls_do_not_record_parameter_values_if_not_enabled(self):
        calls = []

        def handle(*args, **kwargs):
            calls.append((args, kwargs))
            return "some result"

        def somefunction(someparam, otherparam=2):
            print("someparam=%s, otherparam=%s", someparam, otherparam)

        self.mock_generate_content.side_effect = handle
        self.client.models.generate_content(
            model="some-model-name",
            contents="Some content",
            config={
                "tools": [somefunction],
            },
        )
        self.assertEqual(len(calls), 1)
        config = calls[0][1]["config"]
        tools = config.tools
        wrapped_somefunction = tools[0]
        wrapped_somefunction(123, otherparam="abc")
        self.otel.assert_has_span_named("execute_tool somefunction")
        generated_span = self.otel.get_span_named("execute_tool somefunction")
        self.assertEqual(
            generated_span.attributes[
                "code.function.parameters.someparam.type"
            ],
            "int",
        )
        self.assertEqual(
            generated_span.attributes[
                "code.function.parameters.otherparam.type"
            ],
            "str",
        )
        self.assertNotIn(
            "code.function.parameters.someparam.value",
            generated_span.attributes,
        )
        self.assertNotIn(
            "code.function.parameters.otherparam.value",
            generated_span.attributes,
        )

    @patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true"},
    )
    def test_tool_calls_record_return_values_on_span_if_enabled(self):
        calls = []

        def handle(*args, **kwargs):
            calls.append((args, kwargs))
            return "some result"

        def somefunction(x, y=2):
            return x + y

        self.mock_generate_content.side_effect = handle
        self.client.models.generate_content(
            model="some-model-name",
            contents="Some content",
            config={
                "tools": [somefunction],
            },
        )
        self.assertEqual(len(calls), 1)
        config = calls[0][1]["config"]
        tools = config.tools
        wrapped_somefunction = tools[0]
        wrapped_somefunction(123)
        self.otel.assert_has_span_named("execute_tool somefunction")
        generated_span = self.otel.get_span_named("execute_tool somefunction")
        self.assertEqual(
            generated_span.attributes["code.function.return.type"], "int"
        )
        self.assertEqual(
            generated_span.attributes["code.function.return.value"], 125
        )

    @patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false"},
    )
    def test_tool_calls_do_not_record_return_values_if_not_enabled(self):
        calls = []

        def handle(*args, **kwargs):
            calls.append((args, kwargs))
            return "some result"

        def somefunction(x, y=2):
            return x + y

        self.mock_generate_content.side_effect = handle
        self.client.models.generate_content(
            model="some-model-name",
            contents="Some content",
            config={
                "tools": [somefunction],
            },
        )
        self.assertEqual(len(calls), 1)
        config = calls[0][1]["config"]
        tools = config.tools
        wrapped_somefunction = tools[0]
        wrapped_somefunction(123)
        self.otel.assert_has_span_named("execute_tool somefunction")
        generated_span = self.otel.get_span_named("execute_tool somefunction")
        self.assertEqual(
            generated_span.attributes["code.function.return.type"], "int"
        )
        self.assertNotIn(
            "code.function.return.value", generated_span.attributes
        )

    def test_new_semconv_tool_calls_record_parameter_values(self):
        for mode in ContentCapturingMode:
            calls = []
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

                    def handle(*args, **kwargs):
                        calls.append((args, kwargs))
                        return "some result"

                    def somefunction(someparam, otherparam=2):
                        print(
                            "someparam=%s, otherparam=%s",
                            someparam,
                            otherparam,
                        )

                    self.mock_generate_content.side_effect = handle
                    self.client.models.generate_content(
                        model="some-model-name",
                        contents="Some content",
                        config={
                            "tools": [somefunction],
                        },
                    )
                    self.assertEqual(len(calls), 1)
                    config = calls[0][1]["config"]
                    tools = config.tools
                    wrapped_somefunction = tools[0]
                    wrapped_somefunction(123, otherparam="abc")
                    self.otel.assert_has_span_named(
                        "execute_tool somefunction"
                    )
                    generated_span = self.otel.get_span_named(
                        "execute_tool somefunction"
                    )
                    self.assertEqual(
                        generated_span.attributes[
                            "code.function.parameters.someparam.type"
                        ],
                        "int",
                    )
                    self.assertEqual(
                        generated_span.attributes[
                            "code.function.parameters.otherparam.type"
                        ],
                        "str",
                    )
                    if mode in [
                        ContentCapturingMode.SPAN_ONLY,
                        ContentCapturingMode.SPAN_AND_EVENT,
                    ]:
                        self.assertEqual(
                            generated_span.attributes[
                                "code.function.parameters.someparam.value"
                            ],
                            123,
                        )
                        self.assertEqual(
                            generated_span.attributes[
                                "code.function.parameters.otherparam.value"
                            ],
                            "abc",
                        )
                    else:
                        self.assertNotIn(
                            "code.function.parameters.someparam.value",
                            generated_span.attributes,
                        )
                        self.assertNotIn(
                            "code.function.parameters.otherparam.value",
                            generated_span.attributes,
                        )
                self.tearDown()

    def test_new_semconv_tool_calls_record_return_values(self):
        for mode in ContentCapturingMode:
            calls = []
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

                    def handle(*args, **kwargs):
                        calls.append((args, kwargs))
                        return "some result"

                    def somefunction(x, y=2):
                        return x + y

                    self.mock_generate_content.side_effect = handle
                    self.client.models.generate_content(
                        model="some-model-name",
                        contents="Some content",
                        config={
                            "tools": [somefunction],
                        },
                    )
                    self.assertEqual(len(calls), 1)
                    config = calls[0][1]["config"]
                    tools = config.tools
                    wrapped_somefunction = tools[0]
                    wrapped_somefunction(123)
                    self.otel.assert_has_span_named(
                        "execute_tool somefunction"
                    )
                    generated_span = self.otel.get_span_named(
                        "execute_tool somefunction"
                    )
                    self.assertEqual(
                        generated_span.attributes["code.function.return.type"],
                        "int",
                    )
                    if mode in [
                        ContentCapturingMode.SPAN_ONLY,
                        ContentCapturingMode.SPAN_AND_EVENT,
                    ]:
                        self.assertIn(
                            "code.function.return.value",
                            generated_span.attributes,
                        )
                    else:
                        self.assertNotIn(
                            "code.function.return.value",
                            generated_span.attributes,
                        )
                self.tearDown()
