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

"""Tests for vLLM instrumentation — spans."""

import pytest

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import StatusCode


# ── generate() span tests ────────────────────────────────────────────


def test_generate_creates_span(span_exporter, instrument, mock_llm):
    """generate() should produce a span with correct name and kind."""
    mock_llm.generate(["Hello"])

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "text_completion meta-llama/Llama-2-7b-hf"
    assert span.kind == SpanKind.INTERNAL


def test_generate_span_attributes(span_exporter, instrument, mock_llm):
    """generate() span has required GenAI semantic convention attributes."""
    mock_llm.generate(["Hello"])

    span = span_exporter.get_finished_spans()[0]
    attrs = dict(span.attributes)
    assert attrs[GenAIAttributes.GEN_AI_SYSTEM] == "vllm"
    assert (
        attrs[GenAIAttributes.GEN_AI_OPERATION_NAME] == "text_completion"
    )
    assert (
        attrs[GenAIAttributes.GEN_AI_REQUEST_MODEL]
        == "meta-llama/Llama-2-7b-hf"
    )


def test_generate_span_response_attributes(
    span_exporter, instrument, mock_llm
):
    """generate() span records response attributes (tokens, finish reason)."""
    mock_llm.generate(["Hello"])

    span = span_exporter.get_finished_spans()[0]
    attrs = dict(span.attributes)
    assert attrs[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS] == 10
    assert attrs[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS] == 5
    assert attrs[GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS] == ("stop",)
    assert attrs[GenAIAttributes.GEN_AI_RESPONSE_ID] == "req-001"


def test_generate_with_sampling_params(span_exporter, instrument):
    """generate() should capture sampling params as span attributes."""
    from tests.conftest import MockLLM
    from unittest.mock import MagicMock

    sp = MagicMock()
    sp.temperature = 0.7
    sp.max_tokens = 256
    sp.top_p = 0.9
    sp.top_k = 50
    sp.frequency_penalty = 0.1
    sp.presence_penalty = 0.2

    llm = MockLLM(model="test-model")
    llm.generate(["Hello"], sampling_params=sp)

    span = span_exporter.get_finished_spans()[0]
    attrs = dict(span.attributes)
    assert attrs[GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE] == 0.7
    assert attrs[GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS] == 256
    assert attrs[GenAIAttributes.GEN_AI_REQUEST_TOP_P] == 0.9
    assert attrs[GenAIAttributes.GEN_AI_REQUEST_TOP_K] == 50
    assert attrs[GenAIAttributes.GEN_AI_REQUEST_FREQUENCY_PENALTY] == 0.1
    assert attrs[GenAIAttributes.GEN_AI_REQUEST_PRESENCE_PENALTY] == 0.2


# ── chat() span tests ────────────────────────────────────────────────


def test_chat_creates_span(span_exporter, instrument, mock_llm):
    """chat() should produce a span with correct name and kind."""
    mock_llm.chat([{"role": "user", "content": "Hi"}])

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "chat meta-llama/Llama-2-7b-hf"
    assert span.kind == SpanKind.INTERNAL


def test_chat_span_attributes(span_exporter, instrument, mock_llm):
    """chat() span has correct operation name."""
    mock_llm.chat([{"role": "user", "content": "Hi"}])

    span = span_exporter.get_finished_spans()[0]
    attrs = dict(span.attributes)
    assert attrs[GenAIAttributes.GEN_AI_OPERATION_NAME] == "chat"
    assert attrs[GenAIAttributes.GEN_AI_SYSTEM] == "vllm"


# ── Error handling ────────────────────────────────────────────────────


def test_generate_error_sets_span_status(span_exporter, instrument):
    """When generate() raises, span should be marked as ERROR."""
    from tests.conftest import MockLLM

    llm = MockLLM(model="bad-model")
    llm._fail_with = RuntimeError("GPU OOM")

    with pytest.raises(RuntimeError, match="GPU OOM"):
        llm.generate(["Hello"])

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.status.status_code == StatusCode.ERROR
    assert "GPU OOM" in span.status.description


def test_chat_error_sets_span_status(span_exporter, instrument):
    """When chat() raises, span should be marked as ERROR."""
    from tests.conftest import MockLLM

    llm = MockLLM(model="bad-model")
    llm._fail_with = ValueError("Invalid messages")

    with pytest.raises(ValueError, match="Invalid messages"):
        llm.chat([{"role": "user", "content": "Hi"}])

    span = span_exporter.get_finished_spans()[0]
    assert span.status.status_code == StatusCode.ERROR


# ── Uninstrument ──────────────────────────────────────────────────────


def test_uninstrument_removes_wrapping(
    span_exporter, tracer_provider, meter_provider
):
    """After uninstrument(), no spans should be produced."""
    from opentelemetry.instrumentation.vllm import VLLMInstrumentor
    from tests.conftest import MockLLM

    instrumentor = VLLMInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        skip_dep_check=True,
    )

    llm = MockLLM(model="test-model")
    llm.generate(["Hello"])
    assert len(span_exporter.get_finished_spans()) == 1

    instrumentor.uninstrument()
    span_exporter.clear()

    llm2 = MockLLM(model="test-model")
    llm2.generate(["Hello"])
    assert len(span_exporter.get_finished_spans()) == 0


# ── Multiple calls ────────────────────────────────────────────────────


def test_multiple_generate_calls(span_exporter, instrument, mock_llm):
    """Multiple generate() calls should produce multiple spans."""
    mock_llm.generate(["Hello"])
    mock_llm.generate(["World"])
    mock_llm.generate(["Foo"])

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 3


# ── No model edge case ───────────────────────────────────────────────


def test_generate_without_model_in_engine(span_exporter, instrument):
    """generate() should work even if model cannot be extracted from engine."""
    from tests.conftest import MockLLM

    llm = MockLLM(model="some-model")
    llm.llm_engine = None
    llm.model = None

    llm.generate(["Hello"])

    span = span_exporter.get_finished_spans()[0]
    assert span.name == "text_completion"
    assert GenAIAttributes.GEN_AI_REQUEST_MODEL not in span.attributes
