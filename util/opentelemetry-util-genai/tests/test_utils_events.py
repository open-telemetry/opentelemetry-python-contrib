# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import json
import unittest

from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import error_attributes
from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import Error

from .test_utils import (
    _create_input_message,
    _create_output_message,
    _create_system_instruction,
    _get_single_span,
    _get_span_attributes,
    _normalize_to_dict,
    _normalize_to_list,
    patch_env_vars,
)


class TestTelemetryHandlerEvents(unittest.TestCase):
    def setUp(self):
        self.span_exporter = InMemorySpanExporter()
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(
            SimpleSpanProcessor(self.span_exporter)
        )
        self.log_exporter = InMemoryLogRecordExporter()
        logger_provider = LoggerProvider()
        logger_provider.add_log_record_processor(
            SimpleLogRecordProcessor(self.log_exporter)
        )
        self.telemetry_handler = get_telemetry_handler(
            tracer_provider=tracer_provider, logger_provider=logger_provider
        )

    def tearDown(self):
        self.span_exporter.clear()
        self.log_exporter.clear()
        if hasattr(get_telemetry_handler, "_default_handler"):
            delattr(get_telemetry_handler, "_default_handler")

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="EVENT_ONLY",
        emit_event="true",
    )
    def test_emits_llm_event(self):
        invocation = self.telemetry_handler.inference(
            "test-provider", request_model="event-model"
        )
        invocation.input_messages = [_create_input_message("test query")]
        invocation.system_instruction = _create_system_instruction()
        invocation.temperature = 0.7
        invocation.max_tokens = 100
        invocation.response_model_name = "response-model"
        invocation.response_id = "event-response-id"
        invocation.input_tokens = 10
        invocation.output_tokens = 20
        invocation.output_messages = [_create_output_message("test response")]
        invocation.stop()

        # Check that event was emitted
        logs = self.log_exporter.get_finished_logs()
        self.assertEqual(len(logs), 1)
        log_record = logs[0].log_record

        # Verify event name
        self.assertEqual(
            log_record.event_name, "gen_ai.client.inference.operation.details"
        )

        # Verify event attributes
        attrs = log_record.attributes
        self.assertIsNotNone(attrs)
        self.assertEqual(attrs[GenAI.GEN_AI_OPERATION_NAME], "chat")
        self.assertEqual(attrs[GenAI.GEN_AI_REQUEST_MODEL], "event-model")
        self.assertEqual(attrs[GenAI.GEN_AI_PROVIDER_NAME], "test-provider")
        self.assertEqual(attrs[GenAI.GEN_AI_REQUEST_TEMPERATURE], 0.7)
        self.assertEqual(attrs[GenAI.GEN_AI_REQUEST_MAX_TOKENS], 100)
        self.assertEqual(attrs[GenAI.GEN_AI_RESPONSE_MODEL], "response-model")
        self.assertEqual(attrs[GenAI.GEN_AI_RESPONSE_ID], "event-response-id")
        self.assertEqual(attrs[GenAI.GEN_AI_USAGE_INPUT_TOKENS], 10)
        self.assertEqual(attrs[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS], 20)

        # Verify messages are in structured format (not JSON string)
        # OpenTelemetry may convert lists to tuples, so we normalize
        input_msg = _normalize_to_dict(
            _normalize_to_list(attrs[GenAI.GEN_AI_INPUT_MESSAGES])[0]
        )
        self.assertEqual(input_msg["role"], "Human")
        self.assertEqual(
            _normalize_to_list(input_msg["parts"])[0]["content"], "test query"
        )

        output_msg = _normalize_to_dict(
            _normalize_to_list(attrs[GenAI.GEN_AI_OUTPUT_MESSAGES])[0]
        )
        self.assertEqual(output_msg["role"], "AI")
        self.assertEqual(
            _normalize_to_list(output_msg["parts"])[0]["content"],
            "test response",
        )
        self.assertEqual(output_msg["finish_reason"], "stop")

        # Verify system instruction is present in event in structured format
        sys_instr = _normalize_to_dict(
            _normalize_to_list(attrs[GenAI.GEN_AI_SYSTEM_INSTRUCTIONS])[0]
        )
        self.assertEqual(sys_instr["content"], "You are a helpful assistant.")
        self.assertEqual(sys_instr["type"], "text")

        # Verify event context matches span context
        span = _get_single_span(self.span_exporter)
        self.assertIsNotNone(log_record.trace_id)
        self.assertIsNotNone(log_record.span_id)
        self.assertIsNotNone(span.context)
        self.assertEqual(log_record.trace_id, span.context.trace_id)
        self.assertEqual(log_record.span_id, span.context.span_id)

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="SPAN_AND_EVENT",
        emit_event="true",
    )
    def test_emits_llm_event_and_span(self):
        message = _create_input_message("combined test")
        chat_generation = _create_output_message("combined response")
        system_instruction = _create_system_instruction("System prompt here")

        invocation = self.telemetry_handler.inference(
            "test-provider", request_model="combined-model"
        )
        invocation.input_messages = [message]
        invocation.system_instruction = system_instruction
        invocation.output_messages = [chat_generation]
        invocation.stop()

        # Check span was created
        span = _get_single_span(self.span_exporter)
        span_attrs = _get_span_attributes(span)
        self.assertIn(GenAI.GEN_AI_INPUT_MESSAGES, span_attrs)

        # Check event was emitted
        logs = self.log_exporter.get_finished_logs()
        self.assertEqual(len(logs), 1)
        log_record = logs[0].log_record
        self.assertEqual(
            log_record.event_name, "gen_ai.client.inference.operation.details"
        )
        self.assertIn(GenAI.GEN_AI_INPUT_MESSAGES, log_record.attributes)
        # Verify system instruction in both span and event
        self.assertIn(GenAI.GEN_AI_SYSTEM_INSTRUCTIONS, span_attrs)
        span_system = json.loads(span_attrs[GenAI.GEN_AI_SYSTEM_INSTRUCTIONS])
        self.assertEqual(span_system[0]["content"], "System prompt here")
        event_attrs = log_record.attributes
        self.assertIn(GenAI.GEN_AI_SYSTEM_INSTRUCTIONS, event_attrs)
        event_system = event_attrs[GenAI.GEN_AI_SYSTEM_INSTRUCTIONS]
        event_system_list = (
            list(event_system)
            if isinstance(event_system, tuple)
            else event_system
        )
        event_sys_instr = (
            dict(event_system_list[0])
            if isinstance(event_system_list[0], tuple)
            else event_system_list[0]
        )
        self.assertEqual(event_sys_instr["content"], "System prompt here")
        # Verify event context matches span context
        span = _get_single_span(self.span_exporter)
        self.assertIsNotNone(log_record.trace_id)
        self.assertIsNotNone(log_record.span_id)
        self.assertIsNotNone(span.context)
        self.assertEqual(log_record.trace_id, span.context.trace_id)
        self.assertEqual(log_record.span_id, span.context.span_id)

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="EVENT_ONLY",
        emit_event="true",
    )
    def test_emits_llm_event_with_error(self):
        class TestError(RuntimeError):
            pass

        message = _create_input_message("error test")
        invocation = self.telemetry_handler.inference(
            "test-provider", request_model="error-model"
        )
        invocation.input_messages = [message]
        error = Error(message="Test error occurred", type=TestError)
        invocation.fail(error)

        # Check event was emitted
        logs = self.log_exporter.get_finished_logs()
        self.assertEqual(len(logs), 1)
        log_record = logs[0].log_record
        attrs = log_record.attributes

        # Verify error attribute is present
        self.assertEqual(
            attrs[error_attributes.ERROR_TYPE], TestError.__qualname__
        )
        self.assertEqual(attrs[GenAI.GEN_AI_OPERATION_NAME], "chat")
        self.assertEqual(attrs[GenAI.GEN_AI_REQUEST_MODEL], "error-model")
        # Verify event context matches span context
        span = _get_single_span(self.span_exporter)
        self.assertIsNotNone(log_record.trace_id)
        self.assertIsNotNone(log_record.span_id)
        self.assertIsNotNone(span.context)
        self.assertEqual(log_record.trace_id, span.context.trace_id)
        self.assertEqual(log_record.span_id, span.context.span_id)

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="EVENT_ONLY",
        emit_event="false",
    )
    def test_does_not_emit_llm_event_when_emit_event_false(self):
        message = _create_input_message("emit false test")
        chat_generation = _create_output_message("emit false response")

        invocation = self.telemetry_handler.inference(
            "test-provider", request_model="emit-false-model"
        )
        invocation.input_messages = [message]
        invocation.output_messages = [chat_generation]
        invocation.stop()

        # Check no event was emitted
        logs = self.log_exporter.get_finished_logs()
        self.assertEqual(len(logs), 0)

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="NO_CONTENT",
        emit_event="",
    )
    def test_does_not_emit_llm_event_by_default_for_no_content(self):
        """Test that event is not emitted by default when content_capturing is NO_CONTENT and OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT is not set."""
        invocation = self.telemetry_handler.inference(
            "test-provider", request_model="default-model"
        )
        invocation.input_messages = [_create_input_message("default test")]
        invocation.output_messages = [
            _create_output_message("default response")
        ]
        invocation.stop()

        # Check that no event was emitted (NO_CONTENT defaults to False)
        logs = self.log_exporter.get_finished_logs()
        self.assertEqual(len(logs), 0)

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="SPAN_ONLY",
        emit_event="",
    )
    def test_does_not_emit_llm_event_by_default_for_span_only(self):
        """Test that event is not emitted by default when content_capturing is SPAN_ONLY and OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT is not set."""
        invocation = self.telemetry_handler.inference(
            "test-provider", request_model="default-model"
        )
        invocation.input_messages = [_create_input_message("default test")]
        invocation.output_messages = [
            _create_output_message("default response")
        ]
        invocation.stop()

        # Check that no event was emitted (SPAN_ONLY defaults to False)
        logs = self.log_exporter.get_finished_logs()
        self.assertEqual(len(logs), 0)

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="EVENT_ONLY",
        emit_event="",
    )
    def test_emits_llm_event_by_default_for_event_only(self):
        """Test that event is emitted by default when content_capturing is EVENT_ONLY and OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT is not set."""
        invocation = self.telemetry_handler.inference(
            "test-provider", request_model="default-model"
        )
        invocation.input_messages = [_create_input_message("default test")]
        invocation.output_messages = [
            _create_output_message("default response")
        ]
        invocation.stop()

        # Check that event was emitted (EVENT_ONLY defaults to True)
        logs = self.log_exporter.get_finished_logs()
        self.assertEqual(len(logs), 1)
        log_record = logs[0].log_record
        self.assertEqual(
            log_record.event_name, "gen_ai.client.inference.operation.details"
        )

    @patch_env_vars(
        stability_mode="gen_ai_latest_experimental",
        content_capturing="SPAN_AND_EVENT",
        emit_event="",
    )
    def test_emits_llm_event_by_default_for_span_and_event(self):
        """Test that event is emitted by default when content_capturing is SPAN_AND_EVENT and OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT is not set."""
        message = _create_input_message("span and event test")
        chat_generation = _create_output_message("span and event response")
        system_instruction = _create_system_instruction("System prompt")

        invocation = self.telemetry_handler.inference(
            "test-provider", request_model="span-and-event-model"
        )
        invocation.input_messages = [message]
        invocation.system_instruction = system_instruction
        invocation.output_messages = [chat_generation]
        invocation.stop()

        # Check span was created
        span = _get_single_span(self.span_exporter)
        span_attrs = _get_span_attributes(span)
        self.assertIn(GenAI.GEN_AI_INPUT_MESSAGES, span_attrs)

        # Check that event was emitted (SPAN_AND_EVENT defaults to True)
        logs = self.log_exporter.get_finished_logs()
        self.assertEqual(len(logs), 1)
        log_record = logs[0].log_record
        self.assertEqual(
            log_record.event_name, "gen_ai.client.inference.operation.details"
        )
        self.assertIn(GenAI.GEN_AI_INPUT_MESSAGES, log_record.attributes)
