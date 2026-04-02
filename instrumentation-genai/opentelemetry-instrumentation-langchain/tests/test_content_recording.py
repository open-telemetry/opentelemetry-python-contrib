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

import pytest

from opentelemetry.instrumentation._semconv import (
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.langchain.content_recording import (
    ContentPolicy,
    should_record_messages,
    should_record_retriever_content,
    should_record_system_instructions,
    should_record_tool_content,
)
from opentelemetry.util.genai.types import ContentCapturingMode


@pytest.fixture(autouse=True)
def _reset_semconv_stability(monkeypatch):
    """Reset semconv stability cache so each test can set its own env vars."""
    orig_initialized = _OpenTelemetrySemanticConventionStability._initialized
    orig_mapping = _OpenTelemetrySemanticConventionStability._OTEL_SEMCONV_STABILITY_SIGNAL_MAPPING.copy()

    _OpenTelemetrySemanticConventionStability._initialized = False
    _OpenTelemetrySemanticConventionStability._OTEL_SEMCONV_STABILITY_SIGNAL_MAPPING = {}

    monkeypatch.delenv("OTEL_SEMCONV_STABILITY_OPT_IN", raising=False)
    monkeypatch.delenv(
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", raising=False
    )
    monkeypatch.delenv("OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT", raising=False)

    yield

    _OpenTelemetrySemanticConventionStability._initialized = orig_initialized
    _OpenTelemetrySemanticConventionStability._OTEL_SEMCONV_STABILITY_SIGNAL_MAPPING = orig_mapping


def _enter_experimental(monkeypatch, capture_mode):
    """Set env vars for experimental mode and re-initialize stability."""
    monkeypatch.setenv(
        "OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental"
    )
    monkeypatch.setenv(
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", capture_mode
    )
    _OpenTelemetrySemanticConventionStability._initialize()


# ---------------------------------------------------------------------------
# ContentPolicy – experimental mode with each ContentCapturingMode
# ---------------------------------------------------------------------------


class TestContentPolicySpanOnly:
    """SPAN_ONLY: content on spans, no events."""

    def test_should_record_content_on_spans(self, monkeypatch):
        _enter_experimental(monkeypatch, "SPAN_ONLY")
        assert ContentPolicy().should_record_content_on_spans is True

    def test_should_emit_events(self, monkeypatch):
        _enter_experimental(monkeypatch, "SPAN_ONLY")
        assert ContentPolicy().should_emit_events is False

    def test_record_content(self, monkeypatch):
        _enter_experimental(monkeypatch, "SPAN_ONLY")
        assert ContentPolicy().record_content is True

    def test_mode(self, monkeypatch):
        _enter_experimental(monkeypatch, "SPAN_ONLY")
        assert ContentPolicy().mode == ContentCapturingMode.SPAN_ONLY


class TestContentPolicyEventOnly:
    """EVENT_ONLY: events enabled without duplicating content on spans."""

    def test_should_record_content_on_spans(self, monkeypatch):
        _enter_experimental(monkeypatch, "EVENT_ONLY")
        assert ContentPolicy().should_record_content_on_spans is False

    def test_should_emit_events(self, monkeypatch):
        _enter_experimental(monkeypatch, "EVENT_ONLY")
        assert ContentPolicy().should_emit_events is True

    def test_record_content(self, monkeypatch):
        _enter_experimental(monkeypatch, "EVENT_ONLY")
        assert ContentPolicy().record_content is True

    def test_mode(self, monkeypatch):
        _enter_experimental(monkeypatch, "EVENT_ONLY")
        assert ContentPolicy().mode == ContentCapturingMode.EVENT_ONLY


class TestContentPolicySpanAndEvent:
    """SPAN_AND_EVENT: both spans and events active."""

    def test_should_record_content_on_spans(self, monkeypatch):
        _enter_experimental(monkeypatch, "SPAN_AND_EVENT")
        assert ContentPolicy().should_record_content_on_spans is True

    def test_should_emit_events(self, monkeypatch):
        _enter_experimental(monkeypatch, "SPAN_AND_EVENT")
        assert ContentPolicy().should_emit_events is True

    def test_record_content(self, monkeypatch):
        _enter_experimental(monkeypatch, "SPAN_AND_EVENT")
        assert ContentPolicy().record_content is True

    def test_mode(self, monkeypatch):
        _enter_experimental(monkeypatch, "SPAN_AND_EVENT")
        assert ContentPolicy().mode == ContentCapturingMode.SPAN_AND_EVENT


class TestContentPolicyNoContent:
    """NO_CONTENT: nothing recorded."""

    def test_should_record_content_on_spans(self, monkeypatch):
        _enter_experimental(monkeypatch, "NO_CONTENT")
        assert ContentPolicy().should_record_content_on_spans is False

    def test_should_emit_events(self, monkeypatch):
        _enter_experimental(monkeypatch, "NO_CONTENT")
        assert ContentPolicy().should_emit_events is False

    def test_record_content(self, monkeypatch):
        _enter_experimental(monkeypatch, "NO_CONTENT")
        assert ContentPolicy().record_content is False

    def test_mode(self, monkeypatch):
        _enter_experimental(monkeypatch, "NO_CONTENT")
        assert ContentPolicy().mode == ContentCapturingMode.NO_CONTENT


class TestContentPolicyRecordContentCombined:
    """record_content is True when either spans or events are enabled."""

    @pytest.mark.parametrize(
        "capture_mode, expected",
        [
            ("SPAN_ONLY", True),
            ("EVENT_ONLY", True),
            ("SPAN_AND_EVENT", True),
            ("NO_CONTENT", False),
        ],
    )
    def test_record_content(self, monkeypatch, capture_mode, expected):
        _enter_experimental(monkeypatch, capture_mode)
        assert ContentPolicy().record_content is expected


# ---------------------------------------------------------------------------
# ContentPolicy – outside experimental mode
# ---------------------------------------------------------------------------


class TestContentPolicyNonExperimental:
    """Without experimental opt-in everything is disabled."""

    def test_should_record_content_on_spans(self):
        _OpenTelemetrySemanticConventionStability._initialize()
        assert ContentPolicy().should_record_content_on_spans is False

    def test_should_emit_events(self):
        _OpenTelemetrySemanticConventionStability._initialize()
        assert ContentPolicy().should_emit_events is False

    def test_record_content(self):
        _OpenTelemetrySemanticConventionStability._initialize()
        assert ContentPolicy().record_content is False

    def test_mode_is_no_content(self):
        _OpenTelemetrySemanticConventionStability._initialize()
        assert ContentPolicy().mode == ContentCapturingMode.NO_CONTENT


# ---------------------------------------------------------------------------
# Helper functions – delegates to policy.should_record_content_on_spans
# ---------------------------------------------------------------------------


class _StubPolicy:
    """Minimal stand-in for ContentPolicy with a fixed boolean."""

    def __init__(self, value: bool):
        self.should_record_content_on_spans = value


class TestShouldRecordMessages:
    def test_true_when_policy_enabled(self):
        assert should_record_messages(_StubPolicy(True)) is True

    def test_false_when_policy_disabled(self):
        assert should_record_messages(_StubPolicy(False)) is False


class TestShouldRecordToolContent:
    def test_true_when_policy_enabled(self):
        assert should_record_tool_content(_StubPolicy(True)) is True

    def test_false_when_policy_disabled(self):
        assert should_record_tool_content(_StubPolicy(False)) is False


class TestShouldRecordRetrieverContent:
    def test_true_when_policy_enabled(self):
        assert should_record_retriever_content(_StubPolicy(True)) is True

    def test_false_when_policy_disabled(self):
        assert should_record_retriever_content(_StubPolicy(False)) is False


class TestShouldRecordSystemInstructions:
    def test_true_when_policy_enabled(self):
        assert should_record_system_instructions(_StubPolicy(True)) is True

    def test_false_when_policy_disabled(self):
        assert should_record_system_instructions(_StubPolicy(False)) is False


# ---------------------------------------------------------------------------
# Helper functions – integration with real ContentPolicy via env vars
# ---------------------------------------------------------------------------


class TestHelperFunctionsIntegration:
    """Verify helpers produce correct results with a real ContentPolicy."""

    def test_all_helpers_true_with_span_only(self, monkeypatch):
        _enter_experimental(monkeypatch, "SPAN_ONLY")
        policy = ContentPolicy()
        assert should_record_messages(policy) is True
        assert should_record_tool_content(policy) is True
        assert should_record_retriever_content(policy) is True
        assert should_record_system_instructions(policy) is True

    def test_all_helpers_false_with_no_content(self, monkeypatch):
        _enter_experimental(monkeypatch, "NO_CONTENT")
        policy = ContentPolicy()
        assert should_record_messages(policy) is False
        assert should_record_tool_content(policy) is False
        assert should_record_retriever_content(policy) is False
        assert should_record_system_instructions(policy) is False

    def test_all_helpers_false_outside_experimental(self):
        _OpenTelemetrySemanticConventionStability._initialize()
        policy = ContentPolicy()
        assert should_record_messages(policy) is False
        assert should_record_tool_content(policy) is False
        assert should_record_retriever_content(policy) is False
        assert should_record_system_instructions(policy) is False
