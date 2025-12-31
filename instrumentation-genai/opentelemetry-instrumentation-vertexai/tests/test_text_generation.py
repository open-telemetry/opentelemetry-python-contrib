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

"""Tests for TextGenerationModel instrumentation."""

from __future__ import annotations

import pytest

try:
    from vertexai.language_models import TextGenerationModel
except ImportError:
    TextGenerationModel = None

from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor

# Backward compatibility for InMemoryLogExporter -> InMemoryLogRecordExporter rename
try:
    from opentelemetry.sdk._logs._internal.export.in_memory_log_exporter import (
        InMemoryLogRecordExporter,
    )
except ImportError:
    from opentelemetry.sdk._logs._internal.export.in_memory_log_exporter import (
        InMemoryLogExporter as InMemoryLogRecordExporter,
    )
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


@pytest.mark.skipif(
    TextGenerationModel is None,
    reason="TextGenerationModel not available in this version",
)
class TestTextGenerationModelInstrumentation:
    """Tests for TextGenerationModel.predict instrumentation."""

    def test_instruments_text_generation_model(
        self,
        instrument_with_content: VertexAIInstrumentor,
    ):
        """Test that TextGenerationModel.predict is wrapped after instrumentation."""
        assert hasattr(TextGenerationModel.predict, "__wrapped__")

    def test_uninstruments_text_generation_model(
        self,
        instrument_with_content: VertexAIInstrumentor,
    ):
        """Test that TextGenerationModel.predict is unwrapped after uninstrumentation."""
        instrument_with_content.uninstrument()
        assert not hasattr(TextGenerationModel.predict, "__wrapped__")

    def test_instruments_predict_streaming(
        self,
        instrument_with_content: VertexAIInstrumentor,
    ):
        """Test that TextGenerationModel.predict_streaming is wrapped."""
        assert hasattr(TextGenerationModel.predict_streaming, "__wrapped__")


@pytest.mark.skipif(
    TextGenerationModel is None,
    reason="TextGenerationModel not available in this version",
)
class TestLegacyChatSessionInstrumentation:
    """Tests for legacy ChatSession (language_models) instrumentation."""

    def test_instruments_chat_session_send_message(
        self,
        instrument_with_content: VertexAIInstrumentor,
    ):
        """Test that ChatSession.send_message is wrapped after instrumentation."""
        from vertexai.language_models import ChatSession

        assert hasattr(ChatSession.send_message, "__wrapped__")

    def test_uninstruments_chat_session(
        self,
        instrument_with_content: VertexAIInstrumentor,
    ):
        """Test that ChatSession.send_message is unwrapped after uninstrumentation."""
        from vertexai.language_models import ChatSession

        instrument_with_content.uninstrument()
        assert not hasattr(ChatSession.send_message, "__wrapped__")
