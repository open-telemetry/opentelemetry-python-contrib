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
from unittest import mock
from uuid import uuid4

from opentelemetry.instrumentation.langchain.callback_handler import (
    OpenTelemetryLangChainCallbackHandler,
)
from opentelemetry.instrumentation.langchain.semconv_attributes import (
    OP_EXECUTE_TOOL,
)
from opentelemetry.instrumentation.langchain.span_manager import (
    SpanRecord,
    _SpanManager,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.trace.status import StatusCode
from opentelemetry.util.genai.handler import TelemetryHandler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_handler(span_manager=None):
    """Create a callback handler with mocked dependencies."""
    telemetry_handler = mock.MagicMock(spec=TelemetryHandler)
    handler = OpenTelemetryLangChainCallbackHandler(
        telemetry_handler=telemetry_handler,
        span_manager=span_manager,
    )
    return handler


def _make_span_manager():
    """Create a mock _SpanManager."""
    sm = mock.MagicMock(spec=_SpanManager)
    sm.resolve_parent_id.side_effect = lambda parent_run_id: (
        str(parent_run_id) if parent_run_id is not None else None
    )
    return sm


def _make_span_record(run_id, attributes=None):
    """Create a SpanRecord with a mock span."""
    span = mock.MagicMock()
    return SpanRecord(
        run_id=str(run_id),
        span=span,
        operation=OP_EXECUTE_TOOL,
        attributes=attributes or {},
    )


def _enable_content_recording(monkeypatch):
    """Patch content_recording to enable tool content capture."""
    policy = mock.MagicMock()
    policy.record_content = True
    policy.should_emit_events = False
    monkeypatch.setattr(
        "opentelemetry.instrumentation.langchain.callback_handler.get_content_policy",
        lambda: policy,
    )
    monkeypatch.setattr(
        "opentelemetry.instrumentation.langchain.callback_handler.should_record_tool_content",
        lambda policy: True,
    )


def _disable_content_recording(monkeypatch):
    """Patch content_recording to disable tool content capture."""
    policy = mock.MagicMock()
    policy.record_content = False
    policy.should_emit_events = False
    monkeypatch.setattr(
        "opentelemetry.instrumentation.langchain.callback_handler.get_content_policy",
        lambda: policy,
    )
    monkeypatch.setattr(
        "opentelemetry.instrumentation.langchain.callback_handler.should_record_tool_content",
        lambda policy: False,
    )


# ---------------------------------------------------------------------------
# on_tool_start
# ---------------------------------------------------------------------------


class TestOnToolStart:
    """Tests for the on_tool_start callback method."""

    def test_creates_span_with_correct_attributes(self, monkeypatch):
        """Span is created with operation_name, tool_name, and tool_description."""
        _disable_content_recording(monkeypatch)
        sm = _make_span_manager()
        handler = _make_handler(span_manager=sm)
        run_id = uuid4()

        handler.on_tool_start(
            serialized={"name": "web_search", "description": "Search the web"},
            input_str="query text",
            run_id=run_id,
        )

        sm.start_span.assert_called_once()
        call_kwargs = sm.start_span.call_args[1]

        assert call_kwargs["name"] == f"{OP_EXECUTE_TOOL} web_search"
        assert call_kwargs["operation"] == OP_EXECUTE_TOOL
        assert call_kwargs["run_id"] == str(run_id)

        attrs = call_kwargs["attributes"]
        assert attrs[GenAI.GEN_AI_OPERATION_NAME] == OP_EXECUTE_TOOL
        assert attrs[GenAI.GEN_AI_TOOL_NAME] == "web_search"
        assert attrs[GenAI.GEN_AI_TOOL_DESCRIPTION] == "Search the web"

    def test_sets_tool_call_id_from_inputs(self, monkeypatch):
        """tool_call_id is set when present in the inputs dict."""
        _disable_content_recording(monkeypatch)
        sm = _make_span_manager()
        handler = _make_handler(span_manager=sm)

        handler.on_tool_start(
            serialized={"name": "calc"},
            input_str="",
            run_id=uuid4(),
            inputs={"tool_call_id": "call_abc123", "x": 42},
        )

        attrs = sm.start_span.call_args[1]["attributes"]
        assert attrs[GenAI.GEN_AI_TOOL_CALL_ID] == "call_abc123"

    def test_sets_tool_call_id_from_metadata(self, monkeypatch):
        """tool_call_id falls back to metadata when not in inputs."""
        _disable_content_recording(monkeypatch)
        sm = _make_span_manager()
        handler = _make_handler(span_manager=sm)

        handler.on_tool_start(
            serialized={"name": "calc"},
            input_str="",
            run_id=uuid4(),
            metadata={"tool_call_id": "call_meta_456"},
        )

        attrs = sm.start_span.call_args[1]["attributes"]
        assert attrs[GenAI.GEN_AI_TOOL_CALL_ID] == "call_meta_456"

    def test_includes_tool_arguments_when_content_recording_enabled(
        self, monkeypatch
    ):
        """Tool call arguments are recorded when content recording is on."""
        _enable_content_recording(monkeypatch)
        sm = _make_span_manager()
        handler = _make_handler(span_manager=sm)

        handler.on_tool_start(
            serialized={"name": "calc"},
            input_str="fallback",
            run_id=uuid4(),
            inputs={"tool_call_id": "call_1", "x": 42, "op": "add"},
        )

        attrs = sm.start_span.call_args[1]["attributes"]
        arguments = json.loads(attrs[GenAI.GEN_AI_TOOL_CALL_ARGUMENTS])
        assert arguments == {"x": 42, "op": "add"}
        # tool_call_id should be excluded from arguments
        assert "tool_call_id" not in arguments

    def test_uses_input_str_as_arguments_fallback(self, monkeypatch):
        """input_str is used as arguments when inputs has no useful data."""
        _enable_content_recording(monkeypatch)
        sm = _make_span_manager()
        handler = _make_handler(span_manager=sm)

        handler.on_tool_start(
            serialized={"name": "calc"},
            input_str="raw query text",
            run_id=uuid4(),
            inputs={},
        )

        attrs = sm.start_span.call_args[1]["attributes"]
        assert attrs[GenAI.GEN_AI_TOOL_CALL_ARGUMENTS] == "raw query text"

    def test_redacts_tool_arguments_when_content_recording_disabled(
        self, monkeypatch
    ):
        """Tool arguments are not recorded when content recording is off."""
        _disable_content_recording(monkeypatch)
        sm = _make_span_manager()
        handler = _make_handler(span_manager=sm)

        handler.on_tool_start(
            serialized={"name": "calc"},
            input_str="secret input",
            run_id=uuid4(),
            inputs={"x": 42},
        )

        attrs = sm.start_span.call_args[1]["attributes"]
        assert GenAI.GEN_AI_TOOL_CALL_ARGUMENTS not in attrs

    def test_inherits_provider_from_parent_span(self, monkeypatch):
        """Provider name is inherited from the parent span record."""
        _disable_content_recording(monkeypatch)
        sm = _make_span_manager()
        parent_run_id = uuid4()

        parent_record = _make_span_record(
            parent_run_id,
            attributes={GenAI.GEN_AI_PROVIDER_NAME: "openai"},
        )
        sm.get_record.return_value = parent_record

        handler = _make_handler(span_manager=sm)

        handler.on_tool_start(
            serialized={"name": "tool"},
            input_str="",
            run_id=uuid4(),
            parent_run_id=parent_run_id,
        )

        attrs = sm.start_span.call_args[1]["attributes"]
        assert attrs[GenAI.GEN_AI_PROVIDER_NAME] == "openai"

    def test_no_provider_when_parent_has_none(self, monkeypatch):
        """No provider attribute when parent record has no provider."""
        _disable_content_recording(monkeypatch)
        sm = _make_span_manager()
        parent_run_id = uuid4()

        parent_record = _make_span_record(parent_run_id, attributes={})
        sm.get_record.return_value = parent_record

        handler = _make_handler(span_manager=sm)

        handler.on_tool_start(
            serialized={"name": "tool"},
            input_str="",
            run_id=uuid4(),
            parent_run_id=parent_run_id,
        )

        attrs = sm.start_span.call_args[1]["attributes"]
        assert GenAI.GEN_AI_PROVIDER_NAME not in attrs

    def test_noop_when_span_manager_is_none(self):
        """No exception or span creation when span_manager is None."""
        handler = _make_handler(span_manager=None)

        # Should not raise
        handler.on_tool_start(
            serialized={"name": "tool"},
            input_str="query",
            run_id=uuid4(),
        )

    def test_sets_tool_type_from_serialized(self, monkeypatch):
        """Tool type is set from serialized dict."""
        _disable_content_recording(monkeypatch)
        sm = _make_span_manager()
        handler = _make_handler(span_manager=sm)

        handler.on_tool_start(
            serialized={"name": "search", "type": "function"},
            input_str="",
            run_id=uuid4(),
        )

        attrs = sm.start_span.call_args[1]["attributes"]
        assert attrs[GenAI.GEN_AI_TOOL_TYPE] == "function"

    def test_resolves_tool_name_from_metadata(self, monkeypatch):
        """Tool name falls back to metadata when not in serialized."""
        _disable_content_recording(monkeypatch)
        sm = _make_span_manager()
        handler = _make_handler(span_manager=sm)

        handler.on_tool_start(
            serialized={},
            input_str="",
            run_id=uuid4(),
            metadata={"tool_name": "my_custom_tool"},
        )

        attrs = sm.start_span.call_args[1]["attributes"]
        assert attrs[GenAI.GEN_AI_TOOL_NAME] == "my_custom_tool"

    def test_resolves_tool_name_from_kwargs(self, monkeypatch):
        """Tool name falls back to kwargs when not in serialized or metadata."""
        _disable_content_recording(monkeypatch)
        sm = _make_span_manager()
        handler = _make_handler(span_manager=sm)

        handler.on_tool_start(
            serialized={},
            input_str="",
            run_id=uuid4(),
            name="kwargs_tool",
        )

        attrs = sm.start_span.call_args[1]["attributes"]
        assert attrs[GenAI.GEN_AI_TOOL_NAME] == "kwargs_tool"

    def test_defaults_tool_name_to_unknown(self, monkeypatch):
        """Tool name defaults to 'unknown_tool' when no source provides it."""
        _disable_content_recording(monkeypatch)
        sm = _make_span_manager()
        handler = _make_handler(span_manager=sm)

        handler.on_tool_start(
            serialized={},
            input_str="",
            run_id=uuid4(),
        )

        attrs = sm.start_span.call_args[1]["attributes"]
        assert attrs[GenAI.GEN_AI_TOOL_NAME] == "unknown_tool"


# ---------------------------------------------------------------------------
# on_tool_end
# ---------------------------------------------------------------------------


class TestOnToolEnd:
    """Tests for the on_tool_end callback method."""

    def test_sets_tool_result_when_content_recording_enabled(
        self, monkeypatch
    ):
        """Tool result is set as span attribute when content recording is on."""
        _enable_content_recording(monkeypatch)
        sm = _make_span_manager()
        run_id = uuid4()
        record = _make_span_record(run_id)
        sm.get_record.return_value = record

        handler = _make_handler(span_manager=sm)
        handler.on_tool_end(output={"answer": 42}, run_id=run_id)

        record.span.set_attribute.assert_called_once()
        key, value = record.span.set_attribute.call_args.args
        assert key == GenAI.GEN_AI_TOOL_CALL_RESULT
        assert json.loads(value) == {"answer": 42}

    def test_redacts_tool_result_when_content_recording_disabled(
        self, monkeypatch
    ):
        """Tool result is not recorded when content recording is off."""
        _disable_content_recording(monkeypatch)
        sm = _make_span_manager()
        run_id = uuid4()
        record = _make_span_record(run_id)
        sm.get_record.return_value = record

        handler = _make_handler(span_manager=sm)
        handler.on_tool_end(output={"secret": "data"}, run_id=run_id)

        record.span.set_attribute.assert_not_called()

    def test_ends_span_with_ok_status(self, monkeypatch):
        """Span is ended with OK status."""
        _disable_content_recording(monkeypatch)
        sm = _make_span_manager()
        run_id = uuid4()
        record = _make_span_record(run_id)
        sm.get_record.return_value = record

        handler = _make_handler(span_manager=sm)
        handler.on_tool_end(output="result", run_id=run_id)

        sm.end_span.assert_called_once_with(
            run_id=str(run_id), status=StatusCode.OK
        )

    def test_noop_when_record_not_found(self, monkeypatch):
        """No-op when span record is not found for the run_id."""
        _disable_content_recording(monkeypatch)
        sm = _make_span_manager()
        sm.get_record.return_value = None

        handler = _make_handler(span_manager=sm)
        handler.on_tool_end(output="result", run_id=uuid4())

        sm.end_span.assert_not_called()

    def test_noop_when_span_manager_is_none(self):
        """No exception when span_manager is None."""
        handler = _make_handler(span_manager=None)
        handler.on_tool_end(output="result", run_id=uuid4())

    def test_handles_non_json_serializable_output(self, monkeypatch):
        """Non-JSON-serializable output falls back to str()."""
        _enable_content_recording(monkeypatch)
        sm = _make_span_manager()
        run_id = uuid4()
        record = _make_span_record(run_id)
        sm.get_record.return_value = record

        class Custom:
            def __str__(self):
                return "custom_output"

        handler = _make_handler(span_manager=sm)
        handler.on_tool_end(output=Custom(), run_id=run_id)

        record.span.set_attribute.assert_called_once()
        call_args = record.span.set_attribute.call_args
        assert call_args[0][0] == GenAI.GEN_AI_TOOL_CALL_RESULT

    def test_skips_result_when_output_is_none(self, monkeypatch):
        """No result attribute when output is None, even with content recording on."""
        _enable_content_recording(monkeypatch)
        sm = _make_span_manager()
        run_id = uuid4()
        record = _make_span_record(run_id)
        sm.get_record.return_value = record

        handler = _make_handler(span_manager=sm)
        handler.on_tool_end(output=None, run_id=run_id)

        record.span.set_attribute.assert_not_called()
        sm.end_span.assert_called_once_with(
            run_id=str(run_id), status=StatusCode.OK
        )


# ---------------------------------------------------------------------------
# on_tool_error
# ---------------------------------------------------------------------------


class TestOnToolError:
    """Tests for the on_tool_error callback method."""

    def test_ends_span_with_error(self):
        """Span is ended with the error passed through."""
        sm = _make_span_manager()
        handler = _make_handler(span_manager=sm)
        run_id = uuid4()
        error = ValueError("tool failed")

        handler.on_tool_error(error=error, run_id=run_id)

        sm.end_span.assert_called_once_with(run_id=str(run_id), error=error)

    def test_noop_when_span_manager_is_none(self):
        """No exception when span_manager is None."""
        handler = _make_handler(span_manager=None)
        handler.on_tool_error(error=RuntimeError("boom"), run_id=uuid4())

    def test_noop_when_record_not_found(self):
        """end_span is still called (it handles missing records internally)."""
        sm = _make_span_manager()
        handler = _make_handler(span_manager=sm)
        run_id = uuid4()
        error = RuntimeError("oops")

        handler.on_tool_error(error=error, run_id=run_id)

        sm.end_span.assert_called_once_with(run_id=str(run_id), error=error)
