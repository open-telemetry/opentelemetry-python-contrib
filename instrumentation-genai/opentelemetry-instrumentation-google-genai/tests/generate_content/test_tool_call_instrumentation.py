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

import google.genai.types as genai_types

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

        self.assertIsNone(self.otel.get_span_named("tool_call somefunction"))
        wrapped_somefunction(somearg="someparam")
        self.otel.assert_has_span_named("tool_call somefunction")
        generated_span = self.otel.get_span_named("tool_call somefunction")
        self.assertEqual(
            generated_span.attributes["code.function.name"], "somefunction"
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

        self.assertIsNone(self.otel.get_span_named("tool_call somefunction"))
        wrapped_somefunction(somearg="someparam")
        self.otel.assert_has_span_named("tool_call somefunction")
        generated_span = self.otel.get_span_named("tool_call somefunction")
        self.assertEqual(
            generated_span.attributes["code.function.name"], "somefunction"
        )

    def test_tool_calls_record_parameter_values_on_span_if_enabled(self):
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = (
            "true"
        )
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
        self.otel.assert_has_span_named("tool_call somefunction")
        generated_span = self.otel.get_span_named("tool_call somefunction")
        self.assertEqual(
            generated_span.attributes["code.function.parameters.someparam.type"], "int"
        )
        self.assertEqual(
            generated_span.attributes["code.function.parameters.otherparam.type"],
            "str",
        )
        self.assertEqual(
            generated_span.attributes["code.function.parameters.someparam.value"], "123"
        )
        self.assertEqual(
            generated_span.attributes["code.function.parameters.otherparam.value"],
            "'abc'",
        )

    def test_tool_calls_do_not_record_parameter_values_if_not_enabled(self):
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = (
            "false"
        )
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
        self.otel.assert_has_span_named("tool_call somefunction")
        generated_span = self.otel.get_span_named("tool_call somefunction")
        self.assertEqual(
            generated_span.attributes["code.function.parameters.someparam.type"], "int"
        )
        self.assertEqual(
            generated_span.attributes["code.function.parameters.otherparam.type"],
            "str",
        )
        self.assertNotIn(
            "code.function.parameters.someparam.value", generated_span.attributes
        )
        self.assertNotIn(
            "code.function.parameters.otherparam.value", generated_span.attributes
        )

    def test_tool_calls_record_return_values_on_span_if_enabled(self):
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = (
            "true"
        )
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
        self.otel.assert_has_span_named("tool_call somefunction")
        generated_span = self.otel.get_span_named("tool_call somefunction")
        self.assertEqual(
            generated_span.attributes["code.function.return.type"], "int"
        )
        self.assertEqual(
            generated_span.attributes["code.function.return.value"], "125"
        )

    def test_tool_calls_do_not_record_return_values_if_not_enabled(self):
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = (
            "false"
        )
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
        self.otel.assert_has_span_named("tool_call somefunction")
        generated_span = self.otel.get_span_named("tool_call somefunction")
        self.assertEqual(
            generated_span.attributes["code.function.return.type"], "int"
        )
        self.assertNotIn(
            "code.function.return.value", generated_span.attributes
        )
