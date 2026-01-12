# pylint: disable=wrong-import-position,wrong-import-order,import-error,no-name-in-module,unexpected-keyword-arg,no-value-for-parameter,redefined-outer-name,too-many-locals,too-many-statements,protected-access,import-outside-toplevel

"""
Tests for improving coverage of OpenAI Agents instrumentation.

This file targets uncovered lines identified in the coverage report:
- __init__.py: _resolve_system, _resolve_bool, _resolve_content_mode  
- span_processor.py: normalization utilities, span data handlers, message normalization,
  output type inference, metrics recording, and various edge cases.

NOTE: Imports are done inside functions to avoid module-level import conflicts
that can occur when pytest collects tests across multiple files.
"""

from __future__ import annotations

import pytest


def _get_modules():
    """Lazy import to avoid module conflicts."""
    import importlib
    sp = importlib.import_module(
        "opentelemetry.instrumentation.openai_agents.span_processor"
    )
    init_module = importlib.import_module(
        "opentelemetry.instrumentation.openai_agents"
    )
    return sp, init_module


def _get_span_data_classes():
    """Lazy import span data classes."""
    from agents.tracing import (
        AgentSpanData,
        FunctionSpanData,
        GenerationSpanData,
        ResponseSpanData,
    )
    return AgentSpanData, FunctionSpanData, GenerationSpanData, ResponseSpanData


def _get_otel_test_fixtures():
    """Get OpenTelemetry test fixtures."""
    from opentelemetry.sdk.trace import TracerProvider
    try:
        from opentelemetry.sdk.trace.export import (
            InMemorySpanExporter,
            SimpleSpanProcessor,
        )
    except ImportError:
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )
    return TracerProvider, InMemorySpanExporter, SimpleSpanProcessor


# ============================================================================
# Tests for __init__.py functions
# ============================================================================


class TestResolveSystem:
    """Tests for _resolve_system function."""

    def test_resolve_system_returns_openai_for_none(self):
        _, init_module = _get_modules()
        result = init_module._resolve_system(None)
        assert result == "openai"

    def test_resolve_system_returns_openai_for_empty_string(self):
        _, init_module = _get_modules()
        result = init_module._resolve_system("")
        assert result == "openai"

    def test_resolve_system_matches_enum_value(self):
        _, init_module = _get_modules()
        result = init_module._resolve_system("openai")
        assert result == "openai"

    def test_resolve_system_matches_enum_name(self):
        _, init_module = _get_modules()
        result = init_module._resolve_system("OPENAI")
        assert result == "openai"

    def test_resolve_system_matches_with_whitespace(self):
        _, init_module = _get_modules()
        result = init_module._resolve_system("  openai  ")
        assert result == "openai"

    def test_resolve_system_returns_custom_value_when_not_found(self):
        _, init_module = _get_modules()
        result = init_module._resolve_system("custom_provider")
        assert result == "custom_provider"


class TestResolveBool:
    """Tests for _resolve_bool function."""

    def test_resolve_bool_returns_default_for_none(self):
        _, init_module = _get_modules()
        assert init_module._resolve_bool(None, True) is True
        assert init_module._resolve_bool(None, False) is False

    def test_resolve_bool_returns_value_for_bool(self):
        _, init_module = _get_modules()
        assert init_module._resolve_bool(True, False) is True
        assert init_module._resolve_bool(False, True) is False

    def test_resolve_bool_parses_true_strings(self):
        _, init_module = _get_modules()
        for value in ["true", "TRUE", "1", "yes", "on", "  YES  "]:
            assert init_module._resolve_bool(value, False) is True, f"Failed for {value}"

    def test_resolve_bool_parses_false_strings(self):
        _, init_module = _get_modules()
        for value in ["false", "FALSE", "0", "no", "off", "  NO  "]:
            assert init_module._resolve_bool(value, True) is False, f"Failed for {value}"

    def test_resolve_bool_returns_default_for_unknown(self):
        _, init_module = _get_modules()
        assert init_module._resolve_bool("maybe", True) is True
        assert init_module._resolve_bool("maybe", False) is False


class TestResolveContentMode:
    """Tests for _resolve_content_mode function."""

    def test_resolve_content_mode_returns_value_for_enum(self):
        sp, init_module = _get_modules()
        result = init_module._resolve_content_mode(sp.ContentCaptureMode.SPAN_ONLY)
        assert result == sp.ContentCaptureMode.SPAN_ONLY

    def test_resolve_content_mode_for_bool_true(self):
        sp, init_module = _get_modules()
        result = init_module._resolve_content_mode(True)
        assert result == sp.ContentCaptureMode.SPAN_AND_EVENT

    def test_resolve_content_mode_for_bool_false(self):
        sp, init_module = _get_modules()
        result = init_module._resolve_content_mode(False)
        assert result == sp.ContentCaptureMode.NO_CONTENT

    def test_resolve_content_mode_for_none(self):
        sp, init_module = _get_modules()
        result = init_module._resolve_content_mode(None)
        assert result == sp.ContentCaptureMode.SPAN_AND_EVENT

    def test_resolve_content_mode_for_empty_string(self):
        sp, init_module = _get_modules()
        result = init_module._resolve_content_mode("")
        assert result == sp.ContentCaptureMode.SPAN_AND_EVENT

    def test_resolve_content_mode_span_only_variants(self):
        sp, init_module = _get_modules()
        for value in ["span_only", "span-only", "span"]:
            result = init_module._resolve_content_mode(value)
            assert result == sp.ContentCaptureMode.SPAN_ONLY, f"Failed for {value}"

    def test_resolve_content_mode_event_only_variants(self):
        sp, init_module = _get_modules()
        for value in ["event_only", "event-only", "event"]:
            result = init_module._resolve_content_mode(value)
            assert result == sp.ContentCaptureMode.EVENT_ONLY, f"Failed for {value}"

    def test_resolve_content_mode_span_and_event_variants(self):
        sp, init_module = _get_modules()
        for value in ["span_and_event", "span-and-event", "span_and_events", "all", "true", "1", "yes"]:
            result = init_module._resolve_content_mode(value)
            assert result == sp.ContentCaptureMode.SPAN_AND_EVENT, f"Failed for {value}"

    def test_resolve_content_mode_no_content_variants(self):
        sp, init_module = _get_modules()
        for value in ["no_content", "false", "0", "no", "none"]:
            result = init_module._resolve_content_mode(value)
            assert result == sp.ContentCaptureMode.NO_CONTENT, f"Failed for {value}"


# ============================================================================
# Tests for span_processor.py normalization utilities
# ============================================================================


class TestNormalizeProvider:
    """Tests for normalize_provider function."""

    def test_normalize_provider_returns_none_for_none(self):
        sp, _ = _get_modules()
        assert sp.normalize_provider(None) is None

    def test_normalize_provider_returns_none_for_empty(self):
        sp, _ = _get_modules()
        assert sp.normalize_provider("") is None

    def test_normalize_provider_normalizes_valid_provider(self):
        sp, _ = _get_modules()
        result = sp.normalize_provider("OPENAI")
        assert result == "openai"

    def test_normalize_provider_passes_through_unknown(self):
        sp, _ = _get_modules()
        result = sp.normalize_provider("MyCustomProvider")
        assert result == "MyCustomProvider"


class TestValidateToolType:
    """Tests for validate_tool_type function."""

    def test_validate_tool_type_returns_default_for_none(self):
        sp, _ = _get_modules()
        assert sp.validate_tool_type(None) == "function"

    def test_validate_tool_type_returns_default_for_empty(self):
        sp, _ = _get_modules()
        assert sp.validate_tool_type("") == "function"

    def test_validate_tool_type_normalizes_valid_types(self):
        sp, _ = _get_modules()
        assert sp.validate_tool_type("FUNCTION") == "function"
        assert sp.validate_tool_type("extension") == "extension"
        assert sp.validate_tool_type("DATASTORE") == "datastore"

    def test_validate_tool_type_returns_default_for_unknown(self):
        sp, _ = _get_modules()
        assert sp.validate_tool_type("unknown_type") == "function"


class TestNormalizeOutputType:
    """Tests for normalize_output_type function."""

    def test_normalize_output_type_returns_text_for_none(self):
        sp, _ = _get_modules()
        assert sp.normalize_output_type(None) == "text"

    def test_normalize_output_type_returns_text_for_empty(self):
        sp, _ = _get_modules()
        assert sp.normalize_output_type("") == "text"

    def test_normalize_output_type_normalizes_known_types(self):
        sp, _ = _get_modules()
        assert sp.normalize_output_type("TEXT") == "text"
        assert sp.normalize_output_type("json") == "json"
        assert sp.normalize_output_type("image") == "image"
        assert sp.normalize_output_type("speech") == "speech"

    def test_normalize_output_type_handles_mappings(self):
        sp, _ = _get_modules()
        assert sp.normalize_output_type("json_object") == "json"
        assert sp.normalize_output_type("jsonschema") == "json"
        assert sp.normalize_output_type("speech_audio") == "speech"
        assert sp.normalize_output_type("audio_speech") == "speech"
        assert sp.normalize_output_type("image_png") == "image"
        assert sp.normalize_output_type("function_arguments_json") == "json"
        assert sp.normalize_output_type("tool_call") == "json"
        assert sp.normalize_output_type("transcription_json") == "json"

    def test_normalize_output_type_returns_text_for_unknown(self):
        sp, _ = _get_modules()
        assert sp.normalize_output_type("unknown_type") == "text"


# ============================================================================
# Tests for span naming and output type inference
# ============================================================================


class TestGetSpanName:
    """Tests for get_span_name function."""

    def test_span_name_handoff(self):
        sp, _ = _get_modules()
        name = sp.get_span_name("agent_handoff", agent_name="target_agent")
        assert name == "agent_handoff target_agent"

    def test_span_name_handoff_no_agent(self):
        sp, _ = _get_modules()
        name = sp.get_span_name("agent_handoff")
        assert name == "agent_handoff"

    def test_span_name_transcription(self):
        sp, _ = _get_modules()
        name = sp.get_span_name("transcription", model="whisper-1")
        assert name == "transcription whisper-1"

    def test_span_name_speech(self):
        sp, _ = _get_modules()
        name = sp.get_span_name("speech_generation", model="tts-1")
        assert name == "speech_generation tts-1"


class TestInferOutputType:
    """Tests for _infer_output_type method."""

    def _make_processor(self):
        sp, _ = _get_modules()
        TracerProvider, _, _ = _get_otel_test_fixtures()
        provider = TracerProvider()
        tracer = provider.get_tracer(__name__)
        return sp.GenAISemanticProcessor(tracer=tracer, system_name="openai", metrics_enabled=False)

    def test_infer_output_type_function_span(self):
        sp, _ = _get_modules()
        _, FunctionSpanData, _, _ = _get_span_data_classes()
        processor = self._make_processor()
        span_data = FunctionSpanData()
        assert processor._infer_output_type(span_data) == "json"

    def test_infer_output_type_embeddings(self):
        sp, _ = _get_modules()
        _, _, GenerationSpanData, _ = _get_span_data_classes()
        processor = self._make_processor()
        span_data = GenerationSpanData()
        span_data.embedding_dimension = 128
        assert processor._infer_output_type(span_data) == "text"

    def test_infer_output_type_image_output(self):
        sp, _ = _get_modules()
        _, _, GenerationSpanData, _ = _get_span_data_classes()
        processor = self._make_processor()
        span_data = GenerationSpanData(output=[{"type": "image"}])
        assert processor._infer_output_type(span_data) == "image"

    def test_infer_output_type_audio_output(self):
        sp, _ = _get_modules()
        _, _, GenerationSpanData, _ = _get_span_data_classes()
        processor = self._make_processor()
        span_data = GenerationSpanData(output=[{"type": "audio"}])
        assert processor._infer_output_type(span_data) == "speech"

    def test_infer_output_type_json_output(self):
        sp, _ = _get_modules()
        _, _, GenerationSpanData, _ = _get_span_data_classes()
        processor = self._make_processor()
        span_data = GenerationSpanData(output=[{"type": "json_object"}])
        assert processor._infer_output_type(span_data) == "json"

    def test_infer_output_type_text_output(self):
        sp, _ = _get_modules()
        _, _, GenerationSpanData, _ = _get_span_data_classes()
        processor = self._make_processor()
        span_data = GenerationSpanData(output=[{"type": "text"}])
        assert processor._infer_output_type(span_data) == "text"

    def test_infer_output_type_json_like_keys(self):
        sp, _ = _get_modules()
        _, _, GenerationSpanData, _ = _get_span_data_classes()
        processor = self._make_processor()
        span_data = GenerationSpanData(output=[{"schema": {}, "properties": {}}])
        assert processor._infer_output_type(span_data) == "json"


# ============================================================================
# Tests for content capture mode properties
# ============================================================================


class TestContentCaptureMode:
    """Tests for ContentCaptureMode properties."""

    def test_capture_in_span(self):
        sp, _ = _get_modules()
        assert sp.ContentCaptureMode.NO_CONTENT.capture_in_span is False
        assert sp.ContentCaptureMode.SPAN_ONLY.capture_in_span is True
        assert sp.ContentCaptureMode.EVENT_ONLY.capture_in_span is False
        assert sp.ContentCaptureMode.SPAN_AND_EVENT.capture_in_span is True

    def test_capture_in_event(self):
        sp, _ = _get_modules()
        assert sp.ContentCaptureMode.NO_CONTENT.capture_in_event is False
        assert sp.ContentCaptureMode.SPAN_ONLY.capture_in_event is False
        assert sp.ContentCaptureMode.EVENT_ONLY.capture_in_event is True
        assert sp.ContentCaptureMode.SPAN_AND_EVENT.capture_in_event is True


# ============================================================================
# Tests for sanitize usage payload
# ============================================================================


class TestSanitizeUsagePayload:
    """Tests for _sanitize_usage_payload method."""

    def test_sanitize_dict_usage(self):
        sp, _ = _get_modules()
        usage = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        sp.GenAISemanticProcessor._sanitize_usage_payload(usage)
        assert "total_tokens" not in usage
        assert usage["input_tokens"] == 10

    def test_sanitize_object_usage(self):
        sp, _ = _get_modules()
        
        class Usage:
            def __init__(self):
                self.input_tokens = 10
                self.output_tokens = 5
                self.total_tokens = 15

        usage = Usage()
        sp.GenAISemanticProcessor._sanitize_usage_payload(usage)
        assert usage.total_tokens is None

    def test_sanitize_none_usage(self):
        sp, _ = _get_modules()
        # Should not raise
        sp.GenAISemanticProcessor._sanitize_usage_payload(None)


# ============================================================================
# Tests for message normalization
# ============================================================================


class TestNormalizeMessagesToRoleParts:
    """Tests for _normalize_messages_to_role_parts method."""

    def _make_processor(self, sensitive=True):
        sp, _ = _get_modules()
        TracerProvider, _, _ = _get_otel_test_fixtures()
        provider = TracerProvider()
        tracer = provider.get_tracer(__name__)
        return sp.GenAISemanticProcessor(
            tracer=tracer, 
            system_name="openai", 
            include_sensitive_data=sensitive,
            metrics_enabled=False
        )

    def test_normalize_non_dict_message(self):
        processor = self._make_processor()
        messages = ["plain text message"]
        normalized = processor._normalize_messages_to_role_parts(messages)
        assert len(normalized) == 1
        assert normalized[0]["role"] == "user"
        assert normalized[0]["parts"][0]["type"] == "text"

    def test_normalize_with_redaction(self):
        processor = self._make_processor(sensitive=False)
        messages = [{"role": "user", "content": "Secret message"}]
        normalized = processor._normalize_messages_to_role_parts(messages)
        assert normalized[0]["parts"][0]["content"] == "readacted"


# ============================================================================
# Tests for helper functions
# ============================================================================


class TestHelperFunctions:
    """Tests for various helper functions."""

    def test_is_instance_of_single_class(self):
        sp, _ = _get_modules()
        assert sp._is_instance_of("hello", str) is True
        assert sp._is_instance_of(123, str) is False

    def test_is_instance_of_tuple_classes(self):
        sp, _ = _get_modules()
        assert sp._is_instance_of("hello", (str, int)) is True
        assert sp._is_instance_of(123, (str, int)) is True
        assert sp._is_instance_of(3.14, (str, int)) is False

    def test_span_status_helper(self):
        from types import SimpleNamespace
        from opentelemetry.trace.status import StatusCode
        sp, _ = _get_modules()
        
        status = sp._get_span_status(
            SimpleNamespace(error={"message": "boom", "data": "bad"})
        )
        assert status.status_code is StatusCode.ERROR
        assert status.description == "boom: bad"

        ok_status = sp._get_span_status(SimpleNamespace(error=None))
        assert ok_status.status_code is StatusCode.OK


# ============================================================================
# Tests for processor initialization and configuration
# ============================================================================


class TestProcessorConfiguration:
    """Tests for GenAISemanticProcessor configuration."""

    def test_processor_with_metrics_disabled(self):
        sp, _ = _get_modules()
        TracerProvider, _, _ = _get_otel_test_fixtures()
        provider = TracerProvider()
        tracer = provider.get_tracer(__name__)
        
        processor = sp.GenAISemanticProcessor(
            tracer=tracer,
            system_name="openai",
            metrics_enabled=False,
        )
        
        assert processor._metrics_enabled is False
        assert processor._duration_histogram is None
        assert processor._token_usage_histogram is None
        processor.shutdown()

    def test_processor_with_custom_system_name(self):
        sp, _ = _get_modules()
        TracerProvider, _, _ = _get_otel_test_fixtures()
        provider = TracerProvider()
        tracer = provider.get_tracer(__name__)
        
        processor = sp.GenAISemanticProcessor(
            tracer=tracer,
            system_name="azure.ai.inference",
            metrics_enabled=False,
        )
        
        assert processor.system_name == "azure.ai.inference"
        processor.shutdown()

    def test_processor_force_flush_is_noop(self):
        sp, _ = _get_modules()
        TracerProvider, _, _ = _get_otel_test_fixtures()
        provider = TracerProvider()
        tracer = provider.get_tracer(__name__)
        
        processor = sp.GenAISemanticProcessor(
            tracer=tracer,
            system_name="openai",
            metrics_enabled=False,
        )
        
        # Should not raise
        result = processor.force_flush()
        assert result is None
        processor.shutdown()


# ============================================================================
# Tests for normalize_to_text_parts
# ============================================================================


class TestNormalizeToTextParts:
    """Tests for _normalize_to_text_parts method."""

    def _make_processor(self):
        sp, _ = _get_modules()
        TracerProvider, _, _ = _get_otel_test_fixtures()
        provider = TracerProvider()
        tracer = provider.get_tracer(__name__)
        return sp.GenAISemanticProcessor(tracer=tracer, system_name="openai", metrics_enabled=False)

    def test_normalize_string_content(self):
        processor = self._make_processor()
        parts = processor._normalize_to_text_parts("Hello")
        assert len(parts) == 1
        assert parts[0] == {"type": "text", "content": "Hello"}

    def test_normalize_list_content(self):
        processor = self._make_processor()
        parts = processor._normalize_to_text_parts(["Hello", "World"])
        assert len(parts) == 2
        assert parts[0]["content"] == "Hello"
        assert parts[1]["content"] == "World"

    def test_normalize_dict_content_with_text(self):
        processor = self._make_processor()
        parts = processor._normalize_to_text_parts({"text": "From text key"})
        assert len(parts) == 1
        assert parts[0]["content"] == "From text key"

    def test_normalize_none_content(self):
        processor = self._make_processor()
        parts = processor._normalize_to_text_parts(None)
        assert parts == []

    def test_normalize_other_type_content(self):
        processor = self._make_processor()
        parts = processor._normalize_to_text_parts(123)
        assert len(parts) == 1
        assert parts[0]["content"] == "123"


# ============================================================================
# Tests for collect_system_instructions
# ============================================================================


class TestCollectSystemInstructions:
    """Tests for _collect_system_instructions method."""

    def _make_processor(self):
        sp, _ = _get_modules()
        TracerProvider, _, _ = _get_otel_test_fixtures()
        provider = TracerProvider()
        tracer = provider.get_tracer(__name__)
        return sp.GenAISemanticProcessor(tracer=tracer, system_name="openai", metrics_enabled=False)

    def test_collect_system_role_message(self):
        processor = self._make_processor()
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
        ]
        collected = processor._collect_system_instructions(messages)
        assert len(collected) == 1
        assert collected[0]["type"] == "text"
        assert collected[0]["content"] == "You are a helpful assistant."

    def test_collect_ai_role_message(self):
        processor = self._make_processor()
        messages = [
            {"role": "ai", "content": "AI assistant instructions."},
        ]
        collected = processor._collect_system_instructions(messages)
        assert len(collected) == 1
        assert collected[0]["content"] == "AI assistant instructions."

    def test_collect_empty_messages(self):
        processor = self._make_processor()
        collected = processor._collect_system_instructions([])
        assert collected == []

    def test_collect_none_messages(self):
        processor = self._make_processor()
        collected = processor._collect_system_instructions(None)
        assert collected == []
