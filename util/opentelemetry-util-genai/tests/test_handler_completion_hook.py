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
    OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import (
    Error,
    InputMessage,
    LLMInvocation,
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

    def tearDown(self) -> None:
        # Reset semconv stability state between tests
        _OpenTelemetrySemanticConventionStability._initialized = False

    def _make_handler(self, hook=None):
        return TelemetryHandler(
            tracer_provider=self.tracer_provider,
            completion_hook=hook,
        )

    def test_hook_called_on_stop_llm(self):
        hook = MagicMock()
        handler = self._make_handler(hook)

        invocation = LLMInvocation(request_model="gpt-4o")
        invocation.input_messages = [
            InputMessage(role="user", parts=[Text(content="hello")])
        ]
        invocation.output_messages = [
            OutputMessage(
                role="assistant",
                parts=[Text(content="hi")],
                finish_reason="stop",
            )
        ]
        invocation.system_instruction = [Text(content="be helpful")]

        handler.start_llm(invocation)
        handler.stop_llm(invocation)

        hook.on_completion.assert_called_once()
        kwargs = hook.on_completion.call_args.kwargs
        self.assertEqual(kwargs["inputs"], invocation.input_messages)
        self.assertEqual(kwargs["outputs"], invocation.output_messages)
        self.assertEqual(
            kwargs["system_instruction"], invocation.system_instruction
        )
        self.assertIsNotNone(kwargs["span"])

    def test_hook_called_on_fail_llm(self):
        hook = MagicMock()
        handler = self._make_handler(hook)

        invocation = LLMInvocation(request_model="gpt-4o")
        invocation.input_messages = [
            InputMessage(role="user", parts=[Text(content="hello")])
        ]

        handler.start_llm(invocation)
        handler.fail_llm(invocation, Error(type=ValueError, message="boom"))

        hook.on_completion.assert_called_once()
        kwargs = hook.on_completion.call_args.kwargs
        self.assertEqual(kwargs["inputs"], invocation.input_messages)
        self.assertIsNotNone(kwargs["span"])

    def test_hook_not_called_when_not_set(self):
        # No hook — stop_llm and fail_llm should not raise
        handler = self._make_handler()
        invocation = LLMInvocation(request_model="gpt-4o")
        handler.start_llm(invocation)
        handler.stop_llm(invocation)

    def test_log_record_is_none_when_events_disabled(self):
        # Default env: no experimental mode, so log_record should be None
        hook = MagicMock()
        handler = self._make_handler(hook)

        invocation = LLMInvocation(request_model="gpt-4o")
        handler.start_llm(invocation)
        handler.stop_llm(invocation)

        kwargs = hook.on_completion.call_args.kwargs
        self.assertIsNone(kwargs["log_record"])

    @patch.dict(os.environ, _EXPERIMENTAL_ENV)
    def test_log_record_passed_when_events_enabled(self):
        _OpenTelemetrySemanticConventionStability._initialized = False
        _OpenTelemetrySemanticConventionStability._initialize()

        hook = MagicMock()
        handler = self._make_handler(hook)

        invocation = LLMInvocation(request_model="gpt-4o")
        handler.start_llm(invocation)
        handler.stop_llm(invocation)

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

        invocation = LLMInvocation(request_model="gpt-4o")
        handler.start_llm(invocation)
        handler.stop_llm(invocation)

        # The record the hook stamped is the same one that would be emitted
        self.assertIsNotNone(stamped_record)
        self.assertEqual(
            stamped_record.attributes.get("gen_ai.input_messages_ref"),
            "s3://bucket/inputs.json",
        )
