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

"""Tests for Haystack instrumentation."""

import pytest
from unittest.mock import MagicMock, patch

from opentelemetry.instrumentation.haystack import HaystackInstrumentor
from opentelemetry.instrumentation.haystack.utils import (
    should_capture_content,
    set_span_attribute,
    safe_json_serialize,
)
from opentelemetry.instrumentation.haystack.patch import (
    LLMRequestTypeValues,
    _llm_request_type_by_object,
)


class TestHaystackInstrumentor:
    """Test cases for HaystackInstrumentor."""

    def test_instrumentation_dependencies(self):
        """Test that instrumentation dependencies are correctly defined."""
        instrumentor = HaystackInstrumentor()
        deps = instrumentor.instrumentation_dependencies()
        assert len(deps) == 1
        assert "haystack-ai >= 2.0.0" in deps

    def test_instrument_uninstrument(self, tracer_provider):
        """Test that instrument and uninstrument work correctly."""
        instrumentor = HaystackInstrumentor()

        # Mock haystack modules
        with patch.dict("sys.modules", {
            "haystack": MagicMock(),
            "haystack.core": MagicMock(),
            "haystack.core.pipeline": MagicMock(),
            "haystack.core.pipeline.pipeline": MagicMock(),
            "haystack.components": MagicMock(),
            "haystack.components.generators": MagicMock(),
            "haystack.components.generators.openai": MagicMock(),
            "haystack.components.generators.chat": MagicMock(),
            "haystack.components.generators.chat.openai": MagicMock(),
        }):
            # Should not raise
            instrumentor.instrument(tracer_provider=tracer_provider)
            instrumentor.uninstrument()


class TestUtils:
    """Test cases for utility functions."""

    def test_should_capture_content_default(self, disable_content_capture):
        """Test that content capture is disabled by default."""
        assert should_capture_content() is False

    def test_should_capture_content_enabled(self, enable_content_capture):
        """Test that content capture can be enabled."""
        assert should_capture_content() is True

    def test_set_span_attribute_with_value(self):
        """Test setting span attribute with valid value."""
        span = MagicMock()
        set_span_attribute(span, "test.attr", "test_value")
        span.set_attribute.assert_called_once_with("test.attr", "test_value")

    def test_set_span_attribute_with_none(self):
        """Test that None values are not set."""
        span = MagicMock()
        set_span_attribute(span, "test.attr", None)
        span.set_attribute.assert_not_called()

    def test_safe_json_serialize_dict(self):
        """Test serializing a dictionary."""
        data = {"key": "value", "number": 42}
        result = safe_json_serialize(data)
        assert '"key": "value"' in result
        assert '"number": 42' in result


class TestLLMRequestType:
    """Test cases for LLM request type detection."""

    def test_openai_generator_type(self):
        """Test OpenAIGenerator returns completion type."""
        result = _llm_request_type_by_object("OpenAIGenerator")
        assert result == LLMRequestTypeValues.COMPLETION

    def test_openai_chat_generator_type(self):
        """Test OpenAIChatGenerator returns chat type."""
        result = _llm_request_type_by_object("OpenAIChatGenerator")
        assert result == LLMRequestTypeValues.CHAT

    def test_unknown_generator_type(self):
        """Test unknown generator returns unknown type."""
        result = _llm_request_type_by_object("UnknownGenerator")
        assert result == LLMRequestTypeValues.UNKNOWN


class TestPipelineWrapper:
    """Test cases for pipeline wrapper."""

    def test_wrap_pipeline(self, tracer_provider, span_exporter):
        """Test pipeline wrapper creates correct span."""
        from opentelemetry.instrumentation.haystack.patch import wrap_pipeline
        from opentelemetry.trace import get_tracer

        tracer = get_tracer(__name__)

        # Create the wrapper
        to_wrap = {"package": "haystack.core.pipeline.pipeline", "object": "Pipeline"}
        wrapper = wrap_pipeline(tracer, to_wrap)

        # Create mock pipeline instance
        mock_pipeline = MagicMock()

        # Create mock wrapped function
        mock_wrapped = MagicMock(return_value={"result": "success"})

        # Call wrapper
        result = wrapper(mock_wrapped, mock_pipeline, (), {})

        # Verify wrapped was called
        mock_wrapped.assert_called_once()

        # Verify span was created
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert "haystack_pipeline.workflow" in spans[0].name
        assert spans[0].attributes.get("gen_ai.system") == "haystack"
        assert spans[0].attributes.get("gen_ai.operation.name") == "workflow"


class TestOpenAIGeneratorWrapper:
    """Test cases for OpenAI generator wrapper."""

    def test_wrap_openai_chat_generator(self, tracer_provider, span_exporter):
        """Test OpenAI chat generator wrapper creates correct span."""
        from opentelemetry.instrumentation.haystack.patch import wrap_openai_generator
        from opentelemetry.trace import get_tracer

        tracer = get_tracer(__name__)

        # Create the wrapper
        to_wrap = {
            "package": "haystack.components.generators.chat.openai",
            "object": "OpenAIChatGenerator",
        }
        wrapper = wrap_openai_generator(tracer, to_wrap)

        # Create mock generator instance
        mock_generator = MagicMock()

        # Create mock wrapped function
        mock_wrapped = MagicMock(return_value={"replies": ["Hello!"]})

        # Call wrapper with chat messages
        result = wrapper(
            mock_wrapped,
            mock_generator,
            (),
            {"messages": [MagicMock(content="Hi")]},
        )

        # Verify wrapped was called
        mock_wrapped.assert_called_once()

        # Verify span was created
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "haystack.openai.chat"
        assert spans[0].attributes.get("gen_ai.system") == "openai"
        assert spans[0].attributes.get("gen_ai.operation.name") == "chat"

    def test_wrap_openai_completion_generator(self, tracer_provider, span_exporter):
        """Test OpenAI completion generator wrapper creates correct span."""
        from opentelemetry.instrumentation.haystack.patch import wrap_openai_generator
        from opentelemetry.trace import get_tracer

        tracer = get_tracer(__name__)

        # Create the wrapper
        to_wrap = {
            "package": "haystack.components.generators.openai",
            "object": "OpenAIGenerator",
        }
        wrapper = wrap_openai_generator(tracer, to_wrap)

        # Create mock generator instance
        mock_generator = MagicMock()

        # Create mock wrapped function
        mock_wrapped = MagicMock(return_value={"replies": ["Response"]})

        # Call wrapper with prompt
        result = wrapper(
            mock_wrapped,
            mock_generator,
            (),
            {"prompt": "What is AI?"},
        )

        # Verify wrapped was called
        mock_wrapped.assert_called_once()

        # Verify span was created
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "haystack.openai.completion"
        assert spans[0].attributes.get("gen_ai.system") == "openai"
        assert spans[0].attributes.get("gen_ai.operation.name") == "text_completion"
