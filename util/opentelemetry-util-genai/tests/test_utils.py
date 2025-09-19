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
import unittest
from unittest.mock import patch
from uuid import uuid4

from opentelemetry import trace
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
)
from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import (
    ContentCapturingMode,
    InputMessage,
    OutputMessage,
    Text,
)
from opentelemetry.util.genai.utils import get_content_capturing_mode


def patch_env_vars(stability_mode, content_capturing):
    def decorator(test_case):
        @patch.dict(
            os.environ,
            {
                OTEL_SEMCONV_STABILITY_OPT_IN: stability_mode,
                OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: content_capturing,
            },
        )
        def wrapper(*args, **kwargs):
            # Reset state.
            _OpenTelemetrySemanticConventionStability._initialized = False
            _OpenTelemetrySemanticConventionStability._initialize()
            return test_case(*args, **kwargs)

        return wrapper

    return decorator


class TestVersion(unittest.TestCase):
    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="SPAN_ONLY",
    )
    def test_get_content_capturing_mode_parses_valid_envvar(self):  # pylint: disable=no-self-use
        assert get_content_capturing_mode() == ContentCapturingMode.SPAN_ONLY

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental", content_capturing=""
    )
    def test_empty_content_capturing_envvar(self):  # pylint: disable=no-self-use
        assert get_content_capturing_mode() == ContentCapturingMode.NO_CONTENT

    @patch_env_vars(stability_mode="default", content_capturing="True")
    def test_get_content_capturing_mode_raises_exception_when_semconv_stability_default(
        self,
    ):  # pylint: disable=no-self-use
        with self.assertRaises(ValueError):
            get_content_capturing_mode()

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="INVALID_VALUE",
    )
    def test_get_content_capturing_mode_raises_exception_on_invalid_envvar(
        self,
    ):  # pylint: disable=no-self-use
        with self.assertLogs(level="WARNING") as cm:
            assert (
                get_content_capturing_mode() == ContentCapturingMode.NO_CONTENT
            )
        self.assertEqual(len(cm.output), 1)
        self.assertIn("INVALID_VALUE is not a valid option for ", cm.output[0])


class TestTelemetryHandler(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.span_exporter = InMemorySpanExporter()
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(
            SimpleSpanProcessor(cls.span_exporter)
        )
        trace.set_tracer_provider(tracer_provider)

    def setUp(self):
        self.span_exporter = self.__class__.span_exporter
        self.span_exporter.clear()
        self.telemetry_handler = get_telemetry_handler()

    def tearDown(self):
        # Clear spans and reset the singleton telemetry handler so each test starts clean
        self.span_exporter.clear()
        if hasattr(get_telemetry_handler, "_default_handler"):
            delattr(get_telemetry_handler, "_default_handler")

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="SPAN_ONLY",
    )
    def test_llm_start_and_stop_creates_span(self):  # pylint: disable=no-self-use
        message = InputMessage(
            role="Human", parts=[Text(content="hello world")]
        )
        chat_generation = OutputMessage(
            role="AI", parts=[Text(content="hello back")], finish_reason="stop"
        )

        # Start and stop LLM invocation
        invocation = self.telemetry_handler.start_llm(
            request_model="test-model",
            input_messages=[message],
            custom_attr="value",
            provider="test-provider",
        )
        self.telemetry_handler.stop_llm(
            invocation,
            output_messages=[chat_generation],
            extra="info",
        )

        # Get the spans that were created
        spans = self.span_exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.name == "chat test-model"
        assert span.kind == trace.SpanKind.CLIENT

        # Verify span attributes
        assert span.attributes is not None
        span_attrs = span.attributes
        assert span_attrs.get("gen_ai.operation.name") == "chat"
        assert span_attrs.get("gen_ai.provider.name") == "test-provider"
        assert span.start_time is not None
        assert span.end_time is not None
        assert span.end_time > span.start_time
        assert invocation.attributes.get("custom_attr") == "value"
        assert invocation.attributes.get("extra") == "info"

        # Check messages captured on span
        input_messages_json = span_attrs.get("gen_ai.input.messages")
        output_messages_json = span_attrs.get("gen_ai.output.messages")
        assert input_messages_json is not None
        assert output_messages_json is not None

        assert isinstance(input_messages_json, str)
        assert isinstance(output_messages_json, str)

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="SPAN_ONLY",
    )
    def test_parent_child_span_relationship(self):
        parent_id = uuid4()
        child_id = uuid4()
        message = InputMessage(role="Human", parts=[Text(content="hi")])
        chat_generation = OutputMessage(
            role="AI", parts=[Text(content="ok")], finish_reason="stop"
        )

        # Start parent and child (child references parent_run_id)
        parent_invocation = self.telemetry_handler.start_llm(
            request_model="parent-model",
            input_messages=[message],
            run_id=parent_id,
            provider="test-provider",
        )
        child_invocation = self.telemetry_handler.start_llm(
            request_model="child-model",
            input_messages=[message],
            run_id=child_id,
            parent_run_id=parent_id,
            provider="test-provider",
        )

        # Stop child first, then parent (order should not matter)
        self.telemetry_handler.stop_llm(
            child_invocation, output_messages=[chat_generation]
        )
        self.telemetry_handler.stop_llm(
            parent_invocation, output_messages=[chat_generation]
        )

        spans = self.span_exporter.get_finished_spans()
        assert len(spans) == 2

        # Identify spans irrespective of export order
        child_span = next(s for s in spans if s.name == "chat child-model")
        parent_span = next(s for s in spans if s.name == "chat parent-model")

        # Same trace
        assert child_span.context.trace_id == parent_span.context.trace_id
        # Child has parent set to parent's span id
        assert child_span.parent is not None
        assert child_span.parent.span_id == parent_span.context.span_id
        # Parent should not have a parent (root)
        assert parent_span.parent is None
