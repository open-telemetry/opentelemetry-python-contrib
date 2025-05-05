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

from google.genai import types as genai_types

from opentelemetry._events import get_event_logger_provider
from opentelemetry.metrics import get_meter_provider
from opentelemetry.trace import get_tracer_provider

from opentelemetry.instrumentation.google_genai import tool_call_wrapper
from opentelemetry.instrumentation.google_genai import otel_wrapper
from ..common import otel_mocker


class TestCase(unittest.TestCase):

    def setUp(self):
        self._otel = otel_mocker.OTelMocker()
        self._otel.install()
        self._otel_wrapper = otel_wrapper.OTelWrapper.from_providers(
            get_tracer_provider(),
            get_event_logger_provider(),
            get_meter_provider())
    
    @property
    def otel(self):
        return self._otel

    @property
    def otel_wrapper(self):
        return self._otel_wrapper

    def wrap(self, tool_or_tools, **kwargs):
        return tool_call_wrapper.wrapped(
            tool_or_tools,
            self.otel_wrapper,
            **kwargs)

    def test_wraps_none(self):
        result = self.wrap(None)
        self.assertIsNone(result)

    def test_wraps_single_tool_function(self):
        def foo():
            pass
        wrapped_foo = self.wrap(foo)
        self.otel.assert_does_not_have_span_named("tool_call foo")
        foo()
        self.otel.assert_does_not_have_span_named("tool_call foo")
        wrapped_foo()
        self.otel.assert_has_span_named("tool_call foo")

    def test_wraps_multiple_tool_functions_as_list(self):
        def foo():
            pass
        def bar():
            pass
        wrapped_functions = self.wrap([foo, bar])
        wrapped_foo = wrapped_functions[0]
        wrapped_bar = wrapped_functions[1]
        self.otel.assert_does_not_have_span_named("tool_call foo")
        self.otel.assert_does_not_have_span_named("tool_call bar")
        foo()
        bar()
        self.otel.assert_does_not_have_span_named("tool_call foo")
        self.otel.assert_does_not_have_span_named("tool_call bar")
        wrapped_foo()
        self.otel.assert_has_span_named("tool_call foo")
        self.otel.assert_does_not_have_span_named("tool_call bar")
        wrapped_bar()
        self.otel.assert_has_span_named("tool_call bar")


    def test_wraps_multiple_tool_functions_as_dict(self):
        def foo():
            pass
        def bar():
            pass
        wrapped_functions = self.wrap({
            "foo": foo,
            "bar": bar
        })
        wrapped_foo = wrapped_functions["foo"]
        wrapped_bar = wrapped_functions["bar"]
        self.otel.assert_does_not_have_span_named("tool_call foo")
        self.otel.assert_does_not_have_span_named("tool_call bar")
        foo()
        bar()
        self.otel.assert_does_not_have_span_named("tool_call foo")
        self.otel.assert_does_not_have_span_named("tool_call bar")
        wrapped_foo()
        self.otel.assert_has_span_named("tool_call foo")
        self.otel.assert_does_not_have_span_named("tool_call bar")
        wrapped_bar()
        self.otel.assert_has_span_named("tool_call bar")

    def test_wraps_async_tool_function(self):
        async def foo():
            pass
        wrapped_foo = self.wrap(foo)
        self.otel.assert_does_not_have_span_named("tool_call foo")
        asyncio.run(foo())
        self.otel.assert_does_not_have_span_named("tool_call foo")
        asyncio.run(wrapped_foo())
        self.otel.assert_has_span_named("tool_call foo")

    def test_preserves_tool_dict(self):
        tool_dict = genai_types.ToolDict()
        wrapped_tool_dict = self.wrap(tool_dict)
        self.assertEqual(tool_dict, wrapped_tool_dict)
