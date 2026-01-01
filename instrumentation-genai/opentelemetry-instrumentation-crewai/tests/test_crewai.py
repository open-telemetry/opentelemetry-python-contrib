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

"""Tests for CrewAI instrumentation."""

import pytest
from unittest.mock import MagicMock, patch

from opentelemetry.instrumentation.crewai import CrewAIInstrumentor
from opentelemetry.instrumentation.crewai.utils import (
    should_capture_content,
    set_span_attribute,
    safe_json_serialize,
)


class TestCrewAIInstrumentor:
    """Test cases for CrewAIInstrumentor."""

    def test_instrumentation_dependencies(self):
        """Test that instrumentation dependencies are correctly defined."""
        instrumentor = CrewAIInstrumentor()
        deps = instrumentor.instrumentation_dependencies()
        assert len(deps) == 1
        assert "crewai >= 0.70.0" in deps

    def test_instrument_uninstrument(self, tracer_provider):
        """Test that instrument and uninstrument work correctly."""
        instrumentor = CrewAIInstrumentor()

        # Mock crewai modules
        with patch.dict("sys.modules", {
            "crewai": MagicMock(),
            "crewai.crew": MagicMock(),
            "crewai.agent": MagicMock(),
            "crewai.task": MagicMock(),
            "crewai.llm": MagicMock(),
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

    def test_set_span_attribute_with_empty_string(self):
        """Test that empty strings are not set."""
        span = MagicMock()
        set_span_attribute(span, "test.attr", "")
        span.set_attribute.assert_not_called()

    def test_safe_json_serialize_dict(self):
        """Test serializing a dictionary."""
        data = {"key": "value", "number": 42}
        result = safe_json_serialize(data)
        assert result == '{"key": "value", "number": 42}'

    def test_safe_json_serialize_list(self):
        """Test serializing a list."""
        data = [1, 2, 3]
        result = safe_json_serialize(data)
        assert result == "[1, 2, 3]"

    def test_safe_json_serialize_unserializable(self):
        """Test serializing an unserializable object."""
        # Create an object that can't be serialized
        class CustomObj:
            pass

        obj = CustomObj()
        result = safe_json_serialize(obj)
        # Should fall back to str()
        assert "CustomObj" in result


class TestPatchFunctions:
    """Test cases for patch wrapper functions."""

    def test_create_kickoff_wrapper(self, tracer_provider, span_exporter):
        """Test kickoff wrapper creates correct span."""
        from opentelemetry.instrumentation.crewai.patch import (
            create_kickoff_wrapper,
        )

        # Use tracer_provider directly to avoid global provider caching issues
        tracer = tracer_provider.get_tracer(__name__)
        wrapper = create_kickoff_wrapper(tracer)

        # Create mock crew instance
        mock_crew = MagicMock()
        mock_crew.tasks = []
        mock_crew.agents = []

        # Create mock wrapped function
        mock_wrapped = MagicMock(return_value="result")

        # Call wrapper
        result = wrapper(mock_wrapped, mock_crew, (), {})

        # Verify wrapped was called
        mock_wrapped.assert_called_once()

        # Verify span was created
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "crewai.workflow"
        assert spans[0].attributes.get("gen_ai.system") == "crewai"
        assert spans[0].attributes.get("gen_ai.operation.name") == "workflow"

    def test_create_agent_execute_task_wrapper(
        self, tracer_provider, span_exporter
    ):
        """Test agent execute task wrapper creates correct span."""
        from opentelemetry.instrumentation.crewai.patch import (
            create_agent_execute_task_wrapper,
        )

        # Use tracer_provider directly to avoid global provider caching issues
        tracer = tracer_provider.get_tracer(__name__)
        wrapper = create_agent_execute_task_wrapper(tracer)

        # Create mock agent instance
        mock_agent = MagicMock()
        mock_agent.role = "Researcher"
        mock_agent.goal = "Research topics"
        mock_agent.backstory = "Expert researcher"
        mock_agent.tools = []
        mock_agent.llm = MagicMock()
        mock_agent.llm.model = "gpt-4"

        # Create mock wrapped function
        mock_wrapped = MagicMock(return_value="result")

        # Call wrapper
        result = wrapper(mock_wrapped, mock_agent, (), {})

        # Verify wrapped was called
        mock_wrapped.assert_called_once()

        # Verify span was created
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "Researcher.agent"
        assert spans[0].attributes.get("gen_ai.system") == "crewai"
        assert spans[0].attributes.get("gen_ai.operation.name") == "agent"
        assert (
            spans[0].attributes.get("gen_ai.crewai.agent.role") == "Researcher"
        )

    def test_create_task_execute_wrapper(self, tracer_provider, span_exporter):
        """Test task execute wrapper creates correct span."""
        from opentelemetry.instrumentation.crewai.patch import (
            create_task_execute_wrapper,
        )

        # Use tracer_provider directly to avoid global provider caching issues
        tracer = tracer_provider.get_tracer(__name__)
        wrapper = create_task_execute_wrapper(tracer)

        # Create mock task instance
        mock_task = MagicMock()
        mock_task.description = "Research AI trends"
        mock_task.expected_output = "A report"
        mock_task.agent = MagicMock()
        mock_task.agent.role = "Researcher"
        mock_task.tools = []
        mock_task.async_execution = False

        # Create mock wrapped function
        mock_wrapped = MagicMock(return_value="result")

        # Call wrapper
        result = wrapper(mock_wrapped, mock_task, (), {})

        # Verify wrapped was called
        mock_wrapped.assert_called_once()

        # Verify span was created
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert "Research AI trends" in spans[0].name
        assert spans[0].attributes.get("gen_ai.system") == "crewai"
        assert spans[0].attributes.get("gen_ai.operation.name") == "task"

    def test_create_llm_call_wrapper(self, tracer_provider, span_exporter):
        """Test LLM call wrapper creates correct span."""
        from opentelemetry.instrumentation.crewai.patch import (
            create_llm_call_wrapper,
        )

        # Use tracer_provider directly to avoid global provider caching issues
        tracer = tracer_provider.get_tracer(__name__)
        wrapper = create_llm_call_wrapper(tracer)

        # Create mock LLM instance
        mock_llm = MagicMock()
        mock_llm.model = "gpt-4"
        mock_llm.temperature = 0.7
        mock_llm.top_p = 1.0
        mock_llm.max_tokens = 1000

        # Create mock wrapped function
        mock_wrapped = MagicMock(return_value="response")

        # Call wrapper
        result = wrapper(mock_wrapped, mock_llm, (), {})

        # Verify wrapped was called
        mock_wrapped.assert_called_once()

        # Verify span was created
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "gpt-4.llm"
        assert spans[0].attributes.get("gen_ai.system") == "crewai"
        assert spans[0].attributes.get("gen_ai.operation.name") == "chat"
        assert spans[0].attributes.get("gen_ai.request.model") == "gpt-4"
