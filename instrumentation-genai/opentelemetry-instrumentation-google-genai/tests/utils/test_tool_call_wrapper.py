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

import asyncio
import unittest
from unittest.mock import patch

from google.genai import types as genai_types
from opentelemetry._events import get_event_logger_provider
from opentelemetry.instrumentation._semconv import (
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _StabilityMode,
)
from opentelemetry.instrumentation.google_genai import otel_wrapper, tool_call_wrapper
from opentelemetry.metrics import get_meter_provider
from opentelemetry.trace import get_tracer_provider
from opentelemetry.util.genai.types import ContentCapturingMode

from ..common import otel_mocker


class TestCase(unittest.TestCase):
    def setUp(self):
        self._otel = otel_mocker.OTelMocker()
        self._otel.install()
        self._otel_wrapper = otel_wrapper.OTelWrapper.from_providers(
            get_tracer_provider(),
            get_event_logger_provider(),
            get_meter_provider(),
        )

    @property
    def otel(self):
        return self._otel

    @property
    def otel_wrapper(self):
        return self._otel_wrapper

    def wrap(self, tool_or_tools, **kwargs):
        return tool_call_wrapper.wrapped(
            tool_or_tools, self.otel_wrapper, **kwargs
        )

    def test_wraps_none(self):
        result = self.wrap(None)
        self.assertIsNone(result)

    def test_wraps_single_tool_function(self):
        def somefunction():
            pass

        wrapped_somefunction = self.wrap(somefunction)
        self.otel.assert_does_not_have_span_named("execute_tool somefunction")
        somefunction()
        self.otel.assert_does_not_have_span_named("execute_tool somefunction")
        wrapped_somefunction()
        self.otel.assert_has_span_named("execute_tool somefunction")
        span = self.otel.get_span_named("execute_tool somefunction")
        self.assertEqual(
            span.attributes["gen_ai.operation.name"], "execute_tool"
        )
        self.assertEqual(span.attributes["gen_ai.tool.name"], "somefunction")

    def test_wraps_multiple_tool_functions_as_list(self):
        def somefunction():
            pass

        def otherfunction():
            pass

        wrapped_functions = self.wrap([somefunction, otherfunction])
        wrapped_somefunction = wrapped_functions[0]
        wrapped_otherfunction = wrapped_functions[1]
        self.otel.assert_does_not_have_span_named("execute_tool somefunction")
        self.otel.assert_does_not_have_span_named("execute_tool otherfunction")
        somefunction()
        otherfunction()
        self.otel.assert_does_not_have_span_named("execute_tool somefunction")
        self.otel.assert_does_not_have_span_named("execute_tool otherfunction")
        wrapped_somefunction()
        self.otel.assert_has_span_named("execute_tool somefunction")
        self.otel.assert_does_not_have_span_named("execute_tool otherfunction")
        wrapped_otherfunction()
        self.otel.assert_has_span_named("execute_tool otherfunction")

    def test_wraps_multiple_tool_functions_as_dict(self):
        def somefunction():
            pass

        def otherfunction():
            pass

        wrapped_functions = self.wrap(
            {"somefunction": somefunction, "otherfunction": otherfunction}
        )
        wrapped_somefunction = wrapped_functions["somefunction"]
        wrapped_otherfunction = wrapped_functions["otherfunction"]
        self.otel.assert_does_not_have_span_named("execute_tool somefunction")
        self.otel.assert_does_not_have_span_named("execute_tool otherfunction")
        somefunction()
        otherfunction()
        self.otel.assert_does_not_have_span_named("execute_tool somefunction")
        self.otel.assert_does_not_have_span_named("execute_tool otherfunction")
        wrapped_somefunction()
        self.otel.assert_has_span_named("execute_tool somefunction")
        self.otel.assert_does_not_have_span_named("execute_tool otherfunction")
        wrapped_otherfunction()
        self.otel.assert_has_span_named("execute_tool otherfunction")

    def test_wraps_async_tool_function(self):
        async def somefunction():
            pass

        wrapped_somefunction = self.wrap(somefunction)
        self.otel.assert_does_not_have_span_named("execute_tool somefunction")
        asyncio.run(somefunction())
        self.otel.assert_does_not_have_span_named("execute_tool somefunction")
        asyncio.run(wrapped_somefunction())
        self.otel.assert_has_span_named("execute_tool somefunction")

    def test_preserves_tool_dict(self):
        tool_dict = genai_types.ToolDict()
        wrapped_tool_dict = self.wrap(tool_dict)
        self.assertEqual(tool_dict, wrapped_tool_dict)

    def test_does_not_have_description_if_no_doc_string(self):
        def somefunction():
            pass

        wrapped_somefunction = self.wrap(somefunction)
        self.otel.assert_does_not_have_span_named("execute_tool somefunction")
        somefunction()
        self.otel.assert_does_not_have_span_named("execute_tool somefunction")
        wrapped_somefunction()
        self.otel.assert_has_span_named("execute_tool somefunction")
        span = self.otel.get_span_named("execute_tool somefunction")
        self.assertNotIn("gen_ai.tool.description", span.attributes)

    def test_has_description_if_doc_string_present(self):
        def somefunction():
            """An example tool call function."""

        wrapped_somefunction = self.wrap(somefunction)
        self.otel.assert_does_not_have_span_named("execute_tool somefunction")
        somefunction()
        self.otel.assert_does_not_have_span_named("execute_tool somefunction")
        wrapped_somefunction()
        self.otel.assert_has_span_named("execute_tool somefunction")
        span = self.otel.get_span_named("execute_tool somefunction")
        self.assertEqual(
            span.attributes["gen_ai.tool.description"],
            "An example tool call function.",
        )

    @patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true"},
    )
    def test_handles_primitive_int_arg(self):
        def somefunction(arg=None):
            pass

        wrapped_somefunction = self.wrap(somefunction)
        self.otel.assert_does_not_have_span_named("execute_tool somefunction")
        somefunction(12345)
        self.otel.assert_does_not_have_span_named("execute_tool somefunction")
        wrapped_somefunction(12345)
        self.otel.assert_has_span_named("execute_tool somefunction")
        span = self.otel.get_span_named("execute_tool somefunction")
        self.assertEqual(
            span.attributes["code.function.parameters.arg.type"], "int"
        )
        self.assertEqual(
            span.attributes["code.function.parameters.arg.value"], 12345
        )

    @patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true"},
    )
    def test_handles_primitive_string_arg(self):
        def somefunction(arg=None):
            pass

        wrapped_somefunction = self.wrap(somefunction)
        self.otel.assert_does_not_have_span_named("execute_tool somefunction")
        somefunction("a string value")
        self.otel.assert_does_not_have_span_named("execute_tool somefunction")
        wrapped_somefunction("a string value")
        self.otel.assert_has_span_named("execute_tool somefunction")
        span = self.otel.get_span_named("execute_tool somefunction")
        self.assertEqual(
            span.attributes["code.function.parameters.arg.type"], "str"
        )
        self.assertEqual(
            span.attributes["code.function.parameters.arg.value"],
            "a string value",
        )

    @patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true"},
    )
    def test_handles_dict_arg(self):
        def somefunction(arg=None):
            pass

        wrapped_somefunction = self.wrap(somefunction)
        self.otel.assert_does_not_have_span_named("execute_tool somefunction")
        somefunction({"key": "value"})
        self.otel.assert_does_not_have_span_named("execute_tool somefunction")
        wrapped_somefunction({"key": "value"})
        self.otel.assert_has_span_named("execute_tool somefunction")
        span = self.otel.get_span_named("execute_tool somefunction")
        self.assertEqual(
            span.attributes["code.function.parameters.arg.type"], "dict"
        )
        self.assertEqual(
            span.attributes["code.function.parameters.arg.value"],
            '{"key": "value"}',
        )

    @patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true"},
    )
    def test_handles_primitive_list_arg(self):
        def somefunction(arg=None):
            pass

        wrapped_somefunction = self.wrap(somefunction)
        self.otel.assert_does_not_have_span_named("execute_tool somefunction")
        somefunction([1, 2, 3])
        self.otel.assert_does_not_have_span_named("execute_tool somefunction")
        wrapped_somefunction([1, 2, 3])
        self.otel.assert_has_span_named("execute_tool somefunction")
        span = self.otel.get_span_named("execute_tool somefunction")
        self.assertEqual(
            span.attributes["code.function.parameters.arg.type"], "list"
        )
        # A conversion is required here, because the Open Telemetry code converts the
        # list into a tuple. (But this conversion isn't happening in "tool_call_wrapper.py").
        self.assertEqual(
            list(span.attributes["code.function.parameters.arg.value"]),
            [1, 2, 3],
        )

    @patch.dict(
        "os.environ",
        {"OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true"},
    )
    def test_handles_heterogenous_list_arg(self):
        def somefunction(arg=None):
            pass

        wrapped_somefunction = self.wrap(somefunction)
        self.otel.assert_does_not_have_span_named("execute_tool somefunction")
        somefunction([123, "abc"])
        self.otel.assert_does_not_have_span_named("execute_tool somefunction")
        wrapped_somefunction([123, "abc"])
        self.otel.assert_has_span_named("execute_tool somefunction")
        span = self.otel.get_span_named("execute_tool somefunction")
        self.assertEqual(
            span.attributes["code.function.parameters.arg.type"], "list"
        )
        self.assertEqual(
            span.attributes["code.function.parameters.arg.value"],
            '[123, "abc"]',
        )

    def test_handle_with_new_sem_conv(self):
        def somefunction(arg=None):
            pass

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
            with self.subTest(f'mode: {mode}', patched_environ=patched_environ):
                self.setUp()
                with patched_environ, patched_otel_mapping:
                    wrapped_somefunction = self.wrap(somefunction)
                    wrapped_somefunction(12345)

                    span = self.otel.get_span_named("execute_tool somefunction")

                    if mode in [
                        ContentCapturingMode.NO_CONTENT,
                        ContentCapturingMode.EVENT_ONLY,
                    ]:
                        self.assertNotIn("code.function.parameters.arg.value", span.attributes)
                    else:
                        self.assertIn("code.function.parameters.arg.value", span.attributes)
                self.tearDown()
