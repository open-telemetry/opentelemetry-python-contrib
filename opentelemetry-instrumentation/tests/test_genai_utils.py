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

from opentelemetry.instrumentation.genai_utils import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
    get_span_name,
    handle_span_exception,
    is_content_enabled,
)
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace.status import StatusCode


class MyTestException(Exception):
    pass


class TestGenaiUtils(TestBase):
    @patch.dict(
        "os.environ",
        {},
    )
    def test_is_content_enabled_default(self):
        self.assertFalse(is_content_enabled())

    def test_is_content_enabled_true(self):
        for env_value in "true", "TRUE", "True", "tRue":
            with patch.dict(
                "os.environ",
                {
                    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: env_value
                },
            ):
                self.assertTrue(is_content_enabled())

    def test_is_content_enabled_false(self):
        for env_value in "false", "FALSE", "False", "fAlse":
            with patch.dict(
                "os.environ",
                {
                    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: env_value
                },
            ):
                self.assertFalse(is_content_enabled())

    def test_get_span_name(self):
        span_attributes = {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": "mymodel",
        }
        self.assertEqual(get_span_name(span_attributes), "chat mymodel")

        span_attributes = {
            "gen_ai.operation.name": "chat",
        }
        self.assertEqual(get_span_name(span_attributes), "chat ")

        span_attributes = {
            "gen_ai.request.model": "mymodel",
        }
        self.assertEqual(get_span_name(span_attributes), " mymodel")

        span_attributes = {}
        self.assertEqual(get_span_name(span_attributes), " ")

    def test_handle_span_exception(self):
        tracer = self.tracer_provider.get_tracer("test_handle_span_exception")
        with tracer.start_as_current_span("foo") as span:
            handle_span_exception(span, MyTestException())

        self.assertEqual(len(self.get_finished_spans()), 1)
        finished_span: ReadableSpan = self.get_finished_spans()[0]
        self.assertEqual(finished_span.name, "foo")
        self.assertIs(finished_span.status.status_code, StatusCode.ERROR)
        self.assertEqual(
            finished_span.attributes["error.type"], "MyTestException"
        )
