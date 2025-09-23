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
from unittest.mock import patch

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
    LLMInvocation,
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
        cls.tracer_provider = tracer_provider

    def setUp(self):
        self.span_exporter = self.__class__.span_exporter
        self.span_exporter.clear()
        # Always recreate handler with our test provider to avoid stale singleton referencing old provider
        if hasattr(get_telemetry_handler, "_default_handler"):
            delattr(get_telemetry_handler, "_default_handler")
        self.telemetry_handler = get_telemetry_handler(
            tracer_provider=self.__class__.tracer_provider
        )

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
        invocation = LLMInvocation(
            request_model="test-model",
            input_messages=[message],
            provider="test-provider",
            attributes={"custom_attr": "value"},
        )

        self.telemetry_handler.start_llm(invocation)
        assert invocation.span is not None
        invocation.output_messages = [chat_generation]
        invocation.attributes.update({"extra": "info"})
        self.telemetry_handler.stop_llm(invocation)

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
        input_messages = json.loads(input_messages_json)
        output_messages = json.loads(output_messages_json)
        assert len(input_messages) == 1
        assert len(output_messages) == 1
        assert input_messages[0].get("role") == "Human"
        assert output_messages[0].get("role") == "AI"
        assert output_messages[0].get("finish_reason") == "stop"
        assert (
            output_messages[0].get("parts")[0].get("content") == "hello back"
        )

        # Check that extra attributes are added to the span
        assert span_attrs.get("extra") == "info"
        assert span_attrs.get("custom_attr") == "value"

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="SPAN_ONLY",
    )
    def test_parent_child_span_relationship(self):
        message = InputMessage(role="Human", parts=[Text(content="hi")])
        chat_generation = OutputMessage(
            role="AI", parts=[Text(content="ok")], finish_reason="stop"
        )

        # Start parent and child (child references parent_run_id)
        parent_invocation = LLMInvocation(
            request_model="parent-model",
            input_messages=[message],
            provider="test-provider",
        )
        child_invocation = LLMInvocation(
            request_model="child-model",
            input_messages=[message],
            provider="test-provider",
        )

        # Pass invocation data to start_llm
        self.telemetry_handler.start_llm(parent_invocation)
        self.telemetry_handler.start_llm(child_invocation)

        # Stop child first, then parent (order should not matter)
        child_invocation.output_messages = [chat_generation]
        parent_invocation.output_messages = [chat_generation]
        self.telemetry_handler.stop_llm(child_invocation)
        self.telemetry_handler.stop_llm(parent_invocation)

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

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="EVENT_ONLY",
    )
    def test_span_metric_event_generator_event_only_no_span_messages(self):
        from opentelemetry.util.genai.environment_variables import (
            OTEL_INSTRUMENTATION_GENAI_GENERATOR,
        )

        with patch.dict(
            os.environ,
            {OTEL_INSTRUMENTATION_GENAI_GENERATOR: "span_metric_event"},
        ):
            # Reset singleton to pick up generator env var
            if hasattr(get_telemetry_handler, "_default_handler"):
                delattr(get_telemetry_handler, "_default_handler")
            handler = get_telemetry_handler(
                tracer_provider=self.__class__.tracer_provider
            )
            message = InputMessage(
                role="Human", parts=[Text(content="hello world")]
            )
            generation = OutputMessage(
                role="AI", parts=[Text(content="ok")], finish_reason="stop"
            )
            invocation = LLMInvocation(
                request_model="event-model",
                input_messages=[message],
                provider="test-provider",
            )
            handler.start_llm(invocation)
            invocation.output_messages = [generation]
            handler.stop_llm(invocation)
            spans = self.span_exporter.get_finished_spans()
            assert len(spans) == 1
            span = spans[0]
            # Should have basic attrs
            assert span.attributes.get("gen_ai.operation.name") == "chat"
            # Should NOT have message content attributes for event flavor
            assert span.attributes.get("gen_ai.input.messages") is None
            assert span.attributes.get("gen_ai.output.messages") is None

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="SPAN_ONLY",
    )
    def test_span_metric_event_generator_span_only_mode_still_no_span_messages(
        self,
    ):
        from opentelemetry.util.genai.environment_variables import (
            OTEL_INSTRUMENTATION_GENAI_GENERATOR,
        )

        with patch.dict(
            os.environ,
            {OTEL_INSTRUMENTATION_GENAI_GENERATOR: "span_metric_event"},
        ):
            if hasattr(get_telemetry_handler, "_default_handler"):
                delattr(get_telemetry_handler, "_default_handler")
            handler = get_telemetry_handler(
                tracer_provider=self.__class__.tracer_provider
            )
            message = InputMessage(
                role="Human", parts=[Text(content="hello world")]
            )
            generation = OutputMessage(
                role="AI", parts=[Text(content="ok")], finish_reason="stop"
            )
            invocation = LLMInvocation(
                request_model="event-model-2",
                input_messages=[message],
                provider="test-provider",
            )
            handler.start_llm(invocation)
            invocation.output_messages = [generation]
            handler.stop_llm(invocation)
            spans = self.span_exporter.get_finished_spans()
            assert len(spans) == 1
            span = spans[0]
            assert span.attributes.get("gen_ai.operation.name") == "chat"
            # Even though capture mode requested SPAN_ONLY, event flavor suppresses span message attrs
            assert span.attributes.get("gen_ai.input.messages") is None
            assert span.attributes.get("gen_ai.output.messages") is None

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="SPAN_AND_EVENT",
    )
    def test_span_metric_event_generator_span_and_event_mode_behaves_like_event_only(
        self,
    ):
        from opentelemetry.util.genai.environment_variables import (
            OTEL_INSTRUMENTATION_GENAI_GENERATOR,
        )

        with patch.dict(
            os.environ,
            {OTEL_INSTRUMENTATION_GENAI_GENERATOR: "span_metric_event"},
        ):
            if hasattr(get_telemetry_handler, "_default_handler"):
                delattr(get_telemetry_handler, "_default_handler")
            handler = get_telemetry_handler(
                tracer_provider=self.__class__.tracer_provider
            )
            message = InputMessage(role="Human", parts=[Text(content="hi")])
            gen = OutputMessage(
                role="AI", parts=[Text(content="ok")], finish_reason="stop"
            )
            inv = LLMInvocation(
                request_model="event-model-3",
                input_messages=[message],
                provider="prov",
            )
            handler.start_llm(inv)
            inv.output_messages = [gen]
            handler.stop_llm(inv)
            spans = self.span_exporter.get_finished_spans()
            assert len(spans) == 1
            span = spans[0]
            assert span.attributes.get("gen_ai.input.messages") is None
            assert span.attributes.get("gen_ai.output.messages") is None

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="SPAN_AND_EVENT",
    )
    def test_span_generator_span_and_event_mode_adds_messages(self):
        # span flavor should capture on span when SPAN_AND_EVENT
        from opentelemetry.util.genai.environment_variables import (
            OTEL_INSTRUMENTATION_GENAI_GENERATOR,
        )

        with patch.dict(
            os.environ, {OTEL_INSTRUMENTATION_GENAI_GENERATOR: "span"}
        ):
            if hasattr(get_telemetry_handler, "_default_handler"):
                delattr(get_telemetry_handler, "_default_handler")
            handler = get_telemetry_handler(
                tracer_provider=self.__class__.tracer_provider
            )
            message = InputMessage(role="Human", parts=[Text(content="hi2")])
            gen = OutputMessage(
                role="AI", parts=[Text(content="ok2")], finish_reason="stop"
            )
            inv = LLMInvocation(
                request_model="span-and-event",
                input_messages=[message],
                provider="prov",
            )
            handler.start_llm(inv)
            inv.output_messages = [gen]
            handler.stop_llm(inv)
            span = self.span_exporter.get_finished_spans()[0]
            assert span.attributes.get("gen_ai.input.messages") is not None
            assert span.attributes.get("gen_ai.output.messages") is not None

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="EVENT_ONLY",
    )
    def test_span_generator_event_only_mode_does_not_add_messages(self):
        from opentelemetry.util.genai.environment_variables import (
            OTEL_INSTRUMENTATION_GENAI_GENERATOR,
        )

        with patch.dict(
            os.environ, {OTEL_INSTRUMENTATION_GENAI_GENERATOR: "span"}
        ):
            if hasattr(get_telemetry_handler, "_default_handler"):
                delattr(get_telemetry_handler, "_default_handler")
            handler = get_telemetry_handler(
                tracer_provider=self.__class__.tracer_provider
            )
            inv = LLMInvocation(
                request_model="span-event-only",
                input_messages=[],
                provider="prov",
            )
            handler.start_llm(inv)
            handler.stop_llm(inv)
            span = self.span_exporter.get_finished_spans()[0]
            assert span.attributes.get("gen_ai.input.messages") is None
            assert span.attributes.get("gen_ai.output.messages") is None
