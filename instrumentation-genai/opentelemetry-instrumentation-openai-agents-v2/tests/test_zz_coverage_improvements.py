# pylint: disable=wrong-import-position,wrong-import-order,import-error,no-name-in-module,unexpected-keyword-arg,no-value-for-parameter,redefined-outer-name,too-many-locals,too-many-statements,protected-access,import-outside-toplevel,no-self-use,invalid-name
# ruff: noqa: PLC0415

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

    return (
        AgentSpanData,
        FunctionSpanData,
        GenerationSpanData,
        ResponseSpanData,
    )


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

    def test_resolve_system_matches_enum_name_when_name_differs(self):
        _, init_module = _get_modules()
        from opentelemetry.semconv._incubating.attributes import (
            gen_ai_attributes as GenAI,
        )

        candidate = next(
            (
                member
                for member in GenAI.GenAiSystemValues
                if member.name.lower() != member.value
            ),
            None,
        )
        assert candidate is not None
        assert (
            init_module._resolve_system(candidate.name.lower())
            == candidate.value
        )

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
            assert init_module._resolve_bool(value, False) is True, (
                f"Failed for {value}"
            )

    def test_resolve_bool_parses_false_strings(self):
        _, init_module = _get_modules()
        for value in ["false", "FALSE", "0", "no", "off", "  NO  "]:
            assert init_module._resolve_bool(value, True) is False, (
                f"Failed for {value}"
            )

    def test_resolve_bool_returns_default_for_unknown(self):
        _, init_module = _get_modules()
        assert init_module._resolve_bool("maybe", True) is True
        assert init_module._resolve_bool("maybe", False) is False


class TestResolveContentMode:
    """Tests for _resolve_content_mode function."""

    def test_resolve_content_mode_returns_value_for_enum(self):
        sp, init_module = _get_modules()
        result = init_module._resolve_content_mode(
            sp.ContentCaptureMode.SPAN_ONLY
        )
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
            assert result == sp.ContentCaptureMode.SPAN_ONLY, (
                f"Failed for {value}"
            )

    def test_resolve_content_mode_event_only_variants(self):
        sp, init_module = _get_modules()
        for value in ["event_only", "event-only", "event"]:
            result = init_module._resolve_content_mode(value)
            assert result == sp.ContentCaptureMode.EVENT_ONLY, (
                f"Failed for {value}"
            )

    def test_resolve_content_mode_span_and_event_variants(self):
        sp, init_module = _get_modules()
        for value in [
            "span_and_event",
            "span-and-event",
            "span_and_events",
            "all",
            "true",
            "1",
            "yes",
        ]:
            result = init_module._resolve_content_mode(value)
            assert result == sp.ContentCaptureMode.SPAN_AND_EVENT, (
                f"Failed for {value}"
            )

    def test_resolve_content_mode_no_content_variants(self):
        sp, init_module = _get_modules()
        for value in ["no_content", "false", "0", "no", "none"]:
            result = init_module._resolve_content_mode(value)
            assert result == sp.ContentCaptureMode.NO_CONTENT, (
                f"Failed for {value}"
            )


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

    def test_span_name_unknown_operation(self):
        sp, _ = _get_modules()
        name = sp.get_span_name("unknown_operation")
        assert name == "unknown_operation"


class TestInferOutputType:
    """Tests for _infer_output_type method."""

    def _make_processor(self):
        sp, _ = _get_modules()
        TracerProvider, _, _ = _get_otel_test_fixtures()
        provider = TracerProvider()
        tracer = provider.get_tracer(__name__)
        return sp.GenAISemanticProcessor(
            tracer=tracer, system_name="openai", metrics_enabled=False
        )

    def test_infer_output_type_function_span(self):
        _, FunctionSpanData, _, _ = _get_span_data_classes()
        processor = self._make_processor()
        span_data = FunctionSpanData()
        assert processor._infer_output_type(span_data) == "json"

    def test_infer_output_type_embeddings(self):
        _, _, GenerationSpanData, _ = _get_span_data_classes()
        processor = self._make_processor()
        span_data = GenerationSpanData()
        span_data.embedding_dimension = 128
        assert processor._infer_output_type(span_data) == "text"

    def test_infer_output_type_image_output(self):
        _, _, GenerationSpanData, _ = _get_span_data_classes()
        processor = self._make_processor()
        span_data = GenerationSpanData(output=[{"type": "image"}])
        assert processor._infer_output_type(span_data) == "image"

    def test_infer_output_type_audio_output(self):
        _, _, GenerationSpanData, _ = _get_span_data_classes()
        processor = self._make_processor()
        span_data = GenerationSpanData(output=[{"type": "audio"}])
        assert processor._infer_output_type(span_data) == "speech"

    def test_infer_output_type_json_output(self):
        _, _, GenerationSpanData, _ = _get_span_data_classes()
        processor = self._make_processor()
        span_data = GenerationSpanData(output=[{"type": "json_object"}])
        assert processor._infer_output_type(span_data) == "json"

    def test_infer_output_type_text_output(self):
        _, _, GenerationSpanData, _ = _get_span_data_classes()
        processor = self._make_processor()
        span_data = GenerationSpanData(output=[{"type": "text"}])
        assert processor._infer_output_type(span_data) == "text"

    def test_infer_output_type_json_like_keys(self):
        _, _, GenerationSpanData, _ = _get_span_data_classes()
        processor = self._make_processor()
        span_data = GenerationSpanData(
            output=[{"schema": {}, "properties": {}}]
        )
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
            metrics_enabled=False,
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

    def test_normalize_empty_messages_returns_empty_list(self):
        processor = self._make_processor()
        normalized = processor._normalize_messages_to_role_parts([])
        assert normalized == []

    def test_normalize_parts_tool_calls_and_tool_responses(self):
        processor = self._make_processor(sensitive=False)
        messages = [
            {
                "role": "assistant",
                "parts": [
                    {"type": "text", "content": "hello"},
                    {
                        "type": "tool_call",
                        "id": "call_1",
                        "name": "weather",
                        "arguments": {"city": "Paris"},
                    },
                    {
                        "type": "tool_call_response",
                        "id": "call_1",
                        "result": {"temp": 70},
                    },
                    {"type": "weird", "payload": {"x": 1}},
                    123,
                ],
                "content": [
                    {"type": "text", "text": "from-content"},
                    {"type": "image", "url": "http://example.com"},
                    "raw",
                ],
                "tool_calls": [
                    {
                        "id": "call_2",
                        "function": {"name": "calc", "arguments": '{"x":1}'},
                    },
                    "not-dict",
                ],
            },
            {"role": "tool", "tool_call_id": "call_2", "content": {"x": 1}},
        ]

        normalized = processor._normalize_messages_to_role_parts(messages)
        assert normalized[0]["role"] == "assistant"
        assistant_part_types = {p["type"] for p in normalized[0]["parts"]}
        assert "tool_call" in assistant_part_types
        assert "tool_call_response" in assistant_part_types

        tool_call = next(
            p for p in normalized[0]["parts"] if p["type"] == "tool_call"
        )
        assert tool_call["arguments"] == "readacted"

        tool_response = next(
            p
            for p in normalized[0]["parts"]
            if p["type"] == "tool_call_response"
        )
        assert tool_response["result"] == "readacted"

        assert normalized[1]["role"] == "tool"
        assert normalized[1]["parts"][0]["type"] == "tool_call_response"
        assert normalized[1]["parts"][0]["result"] == "readacted"


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

    def test_processor_infers_server_from_base_url(self):
        sp, _ = _get_modules()
        TracerProvider, _, _ = _get_otel_test_fixtures()
        provider = TracerProvider()
        tracer = provider.get_tracer(__name__)

        processor = sp.GenAISemanticProcessor(
            tracer=tracer,
            system_name="openai",
            metrics_enabled=False,
            base_url="https://api.example.com:8443/v1",
        )

        assert processor.server_address == "api.example.com"
        assert processor.server_port == 8443
        server_attrs = processor._get_server_attributes()
        assert (
            server_attrs[sp.ServerAttributes.SERVER_ADDRESS]
            == "api.example.com"
        )
        assert server_attrs[sp.ServerAttributes.SERVER_PORT] == 8443
        processor.shutdown()


class TestRecordMetrics:
    def test_record_metrics_noop_when_disabled(self):
        sp, _ = _get_modules()
        processor = sp.GenAISemanticProcessor(metrics_enabled=False)
        processor._record_metrics(object(), {})

    def test_record_metrics_records_duration_and_tokens(self):
        from types import SimpleNamespace

        sp, _ = _get_modules()
        TracerProvider, _, _ = _get_otel_test_fixtures()
        provider = TracerProvider()
        tracer = provider.get_tracer(__name__)

        class _Histogram:
            def __init__(self) -> None:
                self.records = []

            def record(self, value, attributes) -> None:
                self.records.append((value, attributes))

        duration_histogram = _Histogram()
        token_histogram = _Histogram()

        processor = sp.GenAISemanticProcessor(
            tracer=tracer, system_name="openai", metrics_enabled=False
        )
        processor._metrics_enabled = True
        processor._duration_histogram = duration_histogram
        processor._token_usage_histogram = token_histogram

        span = SimpleNamespace(
            started_at="2024-01-01T00:00:00+00:00",
            ended_at="2024-01-01T00:00:02+00:00",
            error={"type": "timeout"},
        )
        attributes = {
            sp.GEN_AI_PROVIDER_NAME: "openai",
            sp.GEN_AI_OPERATION_NAME: sp.GenAIOperationName.CHAT,
            sp.GEN_AI_REQUEST_MODEL: "gpt-4o-mini",
            sp.ServerAttributes.SERVER_ADDRESS: "api.example.com",
            sp.ServerAttributes.SERVER_PORT: 443,
            sp.GEN_AI_USAGE_INPUT_TOKENS: 2,
            sp.GEN_AI_USAGE_OUTPUT_TOKENS: 3,
        }

        processor._record_metrics(span, attributes)

        assert duration_histogram.records
        duration_value, duration_attrs = duration_histogram.records[0]
        assert duration_value == 2.0
        assert duration_attrs["error.type"] == "timeout"

        assert len(token_histogram.records) == 2
        token_types = {
            token_attrs[sp.GEN_AI_TOKEN_TYPE]
            for _, token_attrs in token_histogram.records
        }
        assert token_types == {"input", "output"}

    def test_record_metrics_swallows_exceptions(self):
        from types import SimpleNamespace

        sp, _ = _get_modules()
        TracerProvider, _, _ = _get_otel_test_fixtures()
        provider = TracerProvider()
        tracer = provider.get_tracer(__name__)

        class _BoomHistogram:
            def record(self, value, attributes) -> None:
                raise RuntimeError("boom")

        processor = sp.GenAISemanticProcessor(
            tracer=tracer, system_name="openai", metrics_enabled=False
        )
        processor._metrics_enabled = True
        processor._duration_histogram = _BoomHistogram()

        span = SimpleNamespace(
            started_at="2024-01-01T00:00:00+00:00",
            ended_at="2024-01-01T00:00:02+00:00",
        )
        attributes = {
            sp.GEN_AI_PROVIDER_NAME: "openai",
            sp.GEN_AI_OPERATION_NAME: sp.GenAIOperationName.CHAT,
            sp.GEN_AI_REQUEST_MODEL: "gpt-4o-mini",
        }

        processor._record_metrics(span, attributes)


class TestVersionModule:
    def test_version_importable(self):
        import importlib

        version_module = importlib.import_module(
            "opentelemetry.instrumentation.openai_agents.version"
        )
        assert isinstance(version_module.__version__, str)
        assert version_module.__version__


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
        return sp.GenAISemanticProcessor(
            tracer=tracer, system_name="openai", metrics_enabled=False
        )

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

    def test_normalize_list_with_dict_missing_text_and_other_types(self):
        processor = self._make_processor()
        parts = processor._normalize_to_text_parts(
            [{"nope": "missing"}, 123, "ok"]
        )
        assert [part["content"] for part in parts] == [
            "{'nope': 'missing'}",
            "123",
            "ok",
        ]

    def test_normalize_dict_content_with_text(self):
        processor = self._make_processor()
        parts = processor._normalize_to_text_parts({"text": "From text key"})
        assert len(parts) == 1
        assert parts[0]["content"] == "From text key"

    def test_normalize_dict_without_text_or_content(self):
        processor = self._make_processor()
        parts = processor._normalize_to_text_parts({"nope": "missing"})
        assert parts[0]["content"] == "{'nope': 'missing'}"

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
        return sp.GenAISemanticProcessor(
            tracer=tracer, system_name="openai", metrics_enabled=False
        )

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

    def test_collect_skips_non_dict_messages(self):
        processor = self._make_processor()
        collected = processor._collect_system_instructions(
            ["not-a-dict", {"role": "system", "content": "hi"}]
        )
        assert collected[0]["content"] == "hi"
