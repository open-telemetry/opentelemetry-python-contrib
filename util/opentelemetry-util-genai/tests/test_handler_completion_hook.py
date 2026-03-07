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
from unittest import TestCase
from unittest.mock import MagicMock, patch

from tests.test_utils import patch_env_vars

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.util.genai.completion_hook import _NoOpCompletionHook
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
    OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import (
    InputMessage,
    OutputMessage,
    Text,
)

_EXPERIMENTAL_ENV = {
    OTEL_SEMCONV_STABILITY_OPT_IN: "gen_ai_latest_experimental",
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "EVENT_ONLY",
    OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT: "true",
}


class TestHandlerCompletionHook(TestCase):
    def setUp(self) -> None:
        self.span_exporter = InMemorySpanExporter()
        self.tracer_provider = TracerProvider()
        self.tracer_provider.add_span_processor(
            SimpleSpanProcessor(self.span_exporter)
        )
        _OpenTelemetrySemanticConventionStability._initialized = False
        _OpenTelemetrySemanticConventionStability._initialize()

    def tearDown(self) -> None:
        # Reset semconv stability state between tests
        _OpenTelemetrySemanticConventionStability._initialized = False

    def _make_handler(self, hook=None):
        return TelemetryHandler(
            tracer_provider=self.tracer_provider,
            completion_hook=hook,
        )

    def test_hook_called_on_stop(self):
        hook = MagicMock()
        handler = self._make_handler(hook)

        input_messages = [
            InputMessage(role="user", parts=[Text(content="hello")])
        ]
        output_messages = [
            OutputMessage(
                role="assistant",
                parts=[Text(content="hi")],
                finish_reason="stop",
            )
        ]
        system_instruction = [Text(content="be helpful")]

        invocation = handler.start_inference("openai", request_model="gpt-4o")
        invocation.input_messages = input_messages
        invocation.output_messages = output_messages
        invocation.system_instruction = system_instruction
        invocation.stop()

        hook.on_completion.assert_called_once()
        kwargs = hook.on_completion.call_args.kwargs
        self.assertEqual(kwargs["inputs"], input_messages)
        self.assertEqual(kwargs["outputs"], output_messages)
        self.assertEqual(kwargs["system_instruction"], system_instruction)
        self.assertIsNotNone(kwargs["span"])

    def test_hook_called_on_fail(self):
        hook = MagicMock()
        handler = self._make_handler(hook)

        input_messages = [
            InputMessage(role="user", parts=[Text(content="hello")])
        ]

        invocation = handler.start_inference("openai", request_model="gpt-4o")
        invocation.input_messages = input_messages
        invocation.fail(ValueError("boom"))

        hook.on_completion.assert_called_once()
        kwargs = hook.on_completion.call_args.kwargs
        self.assertEqual(kwargs["inputs"], input_messages)
        self.assertIsNotNone(kwargs["span"])

    def test_hook_not_called_when_not_set(self):
        # No hook — stop should not raise
        handler = self._make_handler()
        handler.start_inference("openai", request_model="gpt-4o").stop()

    def test_log_record_is_none_when_events_disabled(self):
        # Default env: no experimental mode, so log_record should be None
        hook = MagicMock()
        handler = self._make_handler(hook)

        handler.start_inference("openai", request_model="gpt-4o").stop()

        kwargs = hook.on_completion.call_args.kwargs
        self.assertIsNone(kwargs["log_record"])

    @patch.dict(os.environ, _EXPERIMENTAL_ENV)
    def test_log_record_passed_when_events_enabled(self):
        _OpenTelemetrySemanticConventionStability._initialized = False
        _OpenTelemetrySemanticConventionStability._initialize()

        hook = MagicMock()
        handler = self._make_handler(hook)

        handler.start_inference("openai", request_model="gpt-4o").stop()

        kwargs = hook.on_completion.call_args.kwargs
        self.assertIsNotNone(kwargs["log_record"])

    @patch.dict(os.environ, _EXPERIMENTAL_ENV)
    def test_hook_can_stamp_attrs_on_log_record(self):
        # Verify that attrs stamped by the hook are on the same log_record that gets emitted
        _OpenTelemetrySemanticConventionStability._initialized = False
        _OpenTelemetrySemanticConventionStability._initialize()

        stamped_record = None

        def stamp_ref(*, log_record, **kwargs):
            nonlocal stamped_record
            stamped_record = log_record
            if log_record is not None:
                log_record.attributes = {
                    **(log_record.attributes or {}),
                    "gen_ai.input_messages_ref": "s3://bucket/inputs.json",
                }

        hook = MagicMock(on_completion=stamp_ref)
        handler = self._make_handler(hook)

        handler.start_inference("openai", request_model="gpt-4o").stop()

        # The record the hook stamped is the same one that would be emitted
        self.assertIsNotNone(stamped_record)
        self.assertEqual(
            stamped_record.attributes.get("gen_ai.input_messages_ref"),
            "s3://bucket/inputs.json",
        )

    @patch.dict(
        os.environ, {OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: ""}
    )
    def test_should_capture_content_false_by_default(self):
        handler = self._make_handler()
        self.assertFalse(handler.should_capture_content())

    def test_should_capture_content_true_when_real_hook_set(self):
        # A real (non-noop) hook forces content capture regardless of env vars
        hook = MagicMock()
        handler = self._make_handler(hook)
        self.assertTrue(handler.should_capture_content())

    @patch.dict(
        os.environ, {OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: ""}
    )
    def test_should_capture_content_false_when_noop_hook(self):
        handler = self._make_handler(_NoOpCompletionHook())
        self.assertFalse(handler.should_capture_content())

    @patch.dict(
        os.environ,
        {OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "true"},
    )
    def test_should_capture_content_true_in_legacy_mode_when_content_env_true(
        self,
    ):
        handler = self._make_handler()
        self.assertTrue(handler.should_capture_content())

    @patch.dict(
        os.environ,
        {OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "false"},
    )
    def test_should_capture_content_false_in_legacy_mode_when_content_env_false(
        self,
    ):
        handler = self._make_handler()
        self.assertFalse(handler.should_capture_content())

    @patch_env_vars("gen_ai_latest_experimental", "span_only", "false")
    def test_should_capture_content_true_in_experimental_mode_with_content(
        self,
    ):
        handler = self._make_handler()
        self.assertTrue(handler.should_capture_content())

    @patch_env_vars("gen_ai_latest_experimental", "no_content", "false")
    def test_should_capture_content_false_in_experimental_mode_with_no_content(
        self,
    ):
        handler = self._make_handler()
        self.assertFalse(handler.should_capture_content())

    @patch_env_vars("gen_ai_latest_experimental", "no_content", "false")
    def test_should_capture_content_true_in_experimental_mode_no_content_but_hook_set(
        self,
    ):
        # Hook overrides no_content mode
        hook = MagicMock()
        handler = self._make_handler(hook)
        self.assertTrue(handler.should_capture_content())

    def test_workflow_hook_called_on_stop_with_messages(self):
        hook = MagicMock()
        handler = self._make_handler(hook)

        input_messages = [
            InputMessage(role="user", parts=[Text(content="what is 2+2?")])
        ]
        output_messages = [
            OutputMessage(
                role="assistant",
                parts=[Text(content="4")],
                finish_reason="stop",
            )
        ]

        invocation = handler.start_workflow(name="my-workflow")
        invocation.input_messages = input_messages
        invocation.output_messages = output_messages
        invocation.stop()

        hook.on_completion.assert_called_once()
        kwargs = hook.on_completion.call_args.kwargs
        self.assertEqual(kwargs["inputs"], input_messages)
        self.assertEqual(kwargs["outputs"], output_messages)
        self.assertEqual(kwargs["system_instruction"], [])
        self.assertIsNotNone(kwargs["span"])
        self.assertIsNone(kwargs["log_record"])

    def test_workflow_hook_called_on_fail(self):
        hook = MagicMock()
        handler = self._make_handler(hook)

        invocation = handler.start_workflow(name="my-workflow")
        invocation.input_messages = [
            InputMessage(role="user", parts=[Text(content="hello")])
        ]
        invocation.fail(RuntimeError("workflow failed"))

        hook.on_completion.assert_called_once()
        kwargs = hook.on_completion.call_args.kwargs
        self.assertIsNotNone(kwargs["span"])

    def test_workflow_hook_called_with_empty_messages_when_none_set(self):
        hook = MagicMock()
        handler = self._make_handler(hook)

        handler.start_workflow(name="my-workflow").stop()

        hook.on_completion.assert_called_once()
        kwargs = hook.on_completion.call_args.kwargs
        self.assertEqual(kwargs["inputs"], [])
        self.assertEqual(kwargs["outputs"], [])
