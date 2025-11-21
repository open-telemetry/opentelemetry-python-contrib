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
from typing import Any, Mapping, Optional
from unittest.mock import patch

from opentelemetry import trace
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace.status import StatusCode
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


def _create_input_message(
    content: str = "hello world", role: str = "Human"
) -> InputMessage:
    return InputMessage(role=role, parts=[Text(content=content)])


def _create_output_message(
    content: str = "hello back", finish_reason: str = "stop", role: str = "AI"
) -> OutputMessage:
    return OutputMessage(
        role=role, parts=[Text(content=content)], finish_reason=finish_reason
    )


def _get_single_span(span_exporter: InMemorySpanExporter) -> ReadableSpan:
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    return spans[0]


def _assert_span_time_order(span: ReadableSpan) -> None:
    assert span.start_time is not None
    assert span.end_time is not None
    assert span.end_time >= span.start_time


def _get_span_attributes(span: ReadableSpan) -> Mapping[str, Any]:
    attrs = span.attributes
    assert attrs is not None
    return attrs


def _assert_span_attributes(
    span_attrs: Mapping[str, Any], expected_values: Mapping[str, Any]
) -> None:
    for key, value in expected_values.items():
        assert span_attrs.get(key) == value


def _get_messages_from_attr(
    span_attrs: Mapping[str, Any], attribute_name: str
) -> list[dict[str, Any]]:
    payload = span_attrs.get(attribute_name)
    assert payload is not None
    assert isinstance(payload, str)
    return json.loads(payload)


def _get_single_message(
    span_attrs: Mapping[str, Any], attribute_name: str
) -> dict[str, Any]:
    messages = _get_messages_from_attr(span_attrs, attribute_name)
    assert len(messages) == 1
    return messages[0]


def _assert_text_message(
    message: Mapping[str, Any],
    role: str,
    content: str,
    finish_reason: Optional[str] = None,
) -> None:
    assert message.get("role") == role
    parts = message.get("parts")
    assert isinstance(parts, list) and parts
    assert parts[0].get("content") == content
    if finish_reason is not None:
        assert message.get("finish_reason") == finish_reason


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
    def setUp(self):
        self.span_exporter = InMemorySpanExporter()
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(
            SimpleSpanProcessor(self.span_exporter)
        )
        self.telemetry_handler = get_telemetry_handler(
            tracer_provider=tracer_provider
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
        message = _create_input_message("hello world")
        chat_generation = _create_output_message("hello back")

        with self.telemetry_handler.llm() as invocation:
            for attr, value in {
                "request_model": "test-model",
                "input_messages": [message],
                "provider": "test-provider",
                "attributes": {"custom_attr": "value"},
                "temperature": 0.5,
                "top_p": 0.9,
                "stop_sequences": ["stop"],
                "finish_reasons": ["stop"],
                "response_model_name": "test-response-model",
                "response_id": "response-id",
                "input_tokens": 321,
                "output_tokens": 654,
            }.items():
                setattr(invocation, attr, value)
            assert invocation.span is not None
            invocation.output_messages = [chat_generation]
            invocation.attributes.update({"extra": "info"})

        span = _get_single_span(self.span_exporter)
        self.assertEqual(span.name, "chat test-model")
        self.assertEqual(span.kind, trace.SpanKind.CLIENT)
        _assert_span_time_order(span)

        span_attrs = _get_span_attributes(span)
        _assert_span_attributes(
            span_attrs,
            {
                GenAI.GEN_AI_OPERATION_NAME: "chat",
                GenAI.GEN_AI_PROVIDER_NAME: "test-provider",
                GenAI.GEN_AI_REQUEST_TEMPERATURE: 0.5,
                GenAI.GEN_AI_REQUEST_TOP_P: 0.9,
                GenAI.GEN_AI_REQUEST_STOP_SEQUENCES: ("stop",),
                GenAI.GEN_AI_RESPONSE_FINISH_REASONS: ("stop",),
                GenAI.GEN_AI_RESPONSE_MODEL: "test-response-model",
                GenAI.GEN_AI_RESPONSE_ID: "response-id",
                GenAI.GEN_AI_USAGE_INPUT_TOKENS: 321,
                GenAI.GEN_AI_USAGE_OUTPUT_TOKENS: 654,
                "extra": "info",
                "custom_attr": "value",
            },
        )

        input_message = _get_single_message(
            span_attrs, "gen_ai.input.messages"
        )
        output_message = _get_single_message(
            span_attrs, "gen_ai.output.messages"
        )
        _assert_text_message(input_message, "Human", "hello world")
        _assert_text_message(output_message, "AI", "hello back", "stop")
        self.assertEqual(invocation.attributes.get("custom_attr"), "value")
        self.assertEqual(invocation.attributes.get("extra"), "info")

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="SPAN_ONLY",
    )
    def test_llm_manual_start_and_stop_creates_span(self):
        message = _create_input_message("hi")
        chat_generation = _create_output_message("ok")

        invocation = LLMInvocation(
            request_model="manual-model",
            input_messages=[message],
            provider="test-provider",
            attributes={"manual": True},
        )

        self.telemetry_handler.start_llm(invocation)
        assert invocation.span is not None
        invocation.output_messages = [chat_generation]
        invocation.attributes.update({"extra_manual": "yes"})
        self.telemetry_handler.stop_llm(invocation)

        span = _get_single_span(self.span_exporter)
        assert span.name == "chat manual-model"
        assert span.kind == trace.SpanKind.CLIENT
        _assert_span_time_order(span)

        attrs = _get_span_attributes(span)
        _assert_span_attributes(
            attrs,
            {
                "manual": True,
                "extra_manual": "yes",
            },
        )

    def test_llm_span_finish_reasons_without_output_messages(self):
        invocation = LLMInvocation(
            request_model="model-without-output",
            provider="test-provider",
            finish_reasons=["length"],
            response_model_name="alt-model",
            response_id="resp-001",
            input_tokens=12,
            output_tokens=34,
        )

        self.telemetry_handler.start_llm(invocation)
        assert invocation.span is not None
        self.telemetry_handler.stop_llm(invocation)

        span = _get_single_span(self.span_exporter)
        _assert_span_time_order(span)
        attrs = _get_span_attributes(span)
        _assert_span_attributes(
            attrs,
            {
                GenAI.GEN_AI_RESPONSE_FINISH_REASONS: ("length",),
                GenAI.GEN_AI_RESPONSE_MODEL: "alt-model",
                GenAI.GEN_AI_RESPONSE_ID: "resp-001",
                GenAI.GEN_AI_USAGE_INPUT_TOKENS: 12,
                GenAI.GEN_AI_USAGE_OUTPUT_TOKENS: 34,
            },
        )

    def test_llm_span_finish_reasons_deduplicated_from_invocation(self):
        invocation = LLMInvocation(
            request_model="model-dedup",
            provider="test-provider",
            finish_reasons=["stop", "length", "stop"],
        )

        self.telemetry_handler.start_llm(invocation)
        assert invocation.span is not None
        self.telemetry_handler.stop_llm(invocation)

        span = _get_single_span(self.span_exporter)
        attrs = _get_span_attributes(span)
        self.assertEqual(
            attrs[GenAI.GEN_AI_RESPONSE_FINISH_REASONS],
            ("length", "stop"),
        )

    def test_llm_span_finish_reasons_deduplicated_from_output_messages(self):
        invocation = LLMInvocation(
            request_model="model-output-dedup",
            provider="test-provider",
        )

        self.telemetry_handler.start_llm(invocation)
        assert invocation.span is not None
        invocation.output_messages = [
            _create_output_message("response-1", finish_reason="stop"),
            _create_output_message("response-2", finish_reason="length"),
            _create_output_message("response-3", finish_reason="stop"),
        ]
        self.telemetry_handler.stop_llm(invocation)

        span = _get_single_span(self.span_exporter)
        attrs = _get_span_attributes(span)
        self.assertEqual(
            attrs[GenAI.GEN_AI_RESPONSE_FINISH_REASONS],
            ("length", "stop"),
        )

    def test_llm_span_uses_expected_schema_url(self):
        invocation = LLMInvocation(
            request_model="schema-model",
            provider="schema-provider",
        )

        self.telemetry_handler.start_llm(invocation)
        assert invocation.span is not None
        self.telemetry_handler.stop_llm(invocation)

        span = _get_single_span(self.span_exporter)
        instrumentation = getattr(span, "instrumentation_scope", None)
        if instrumentation is None:
            instrumentation = getattr(span, "instrumentation_info", None)

        assert instrumentation is not None
        assert (
            getattr(instrumentation, "schema_url", None)
            == Schemas.V1_37_0.value
        )

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="SPAN_ONLY",
    )
    def test_parent_child_span_relationship(self):
        message = _create_input_message("hi")
        chat_generation = _create_output_message("ok")

        with self.telemetry_handler.llm() as parent_invocation:
            for attr, value in {
                "request_model": "parent-model",
                "input_messages": [message],
                "provider": "test-provider",
            }.items():
                setattr(parent_invocation, attr, value)
            with self.telemetry_handler.llm() as child_invocation:
                for attr, value in {
                    "request_model": "child-model",
                    "input_messages": [message],
                    "provider": "test-provider",
                }.items():
                    setattr(child_invocation, attr, value)
                # Stop child first by exiting inner context
                child_invocation.output_messages = [chat_generation]
            # Then stop parent by exiting outer context
            parent_invocation.output_messages = [chat_generation]

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

    def test_llm_context_manager_error_path_records_error_status_and_attrs(
        self,
    ):
        class BoomError(RuntimeError):
            pass

        message = _create_input_message("hi", role="user")
        invocation = LLMInvocation(
            request_model="test-model",
            input_messages=[message],
            provider="test-provider",
        )

        with self.assertRaises(BoomError):
            with self.telemetry_handler.llm(invocation):
                for attr, value in {
                    "max_tokens": 128,
                    "seed": 123,
                    "finish_reasons": ["error"],
                    "response_model_name": "error-model",
                    "response_id": "error-response",
                    "input_tokens": 11,
                    "output_tokens": 22,
                }.items():
                    setattr(invocation, attr, value)
                raise BoomError("boom")

        span = _get_single_span(self.span_exporter)
        assert span.status.status_code == StatusCode.ERROR
        _assert_span_time_order(span)
        span_attrs = _get_span_attributes(span)
        _assert_span_attributes(
            span_attrs,
            {
                ErrorAttributes.ERROR_TYPE: BoomError.__qualname__,
                GenAI.GEN_AI_REQUEST_MAX_TOKENS: 128,
                GenAI.GEN_AI_REQUEST_SEED: 123,
                GenAI.GEN_AI_RESPONSE_FINISH_REASONS: ("error",),
                GenAI.GEN_AI_RESPONSE_MODEL: "error-model",
                GenAI.GEN_AI_RESPONSE_ID: "error-response",
                GenAI.GEN_AI_USAGE_INPUT_TOKENS: 11,
                GenAI.GEN_AI_USAGE_OUTPUT_TOKENS: 22,
            },
        )
