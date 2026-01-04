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

"""Tests for Agno instrumentation."""

import pytest
from unittest.mock import MagicMock, patch

from opentelemetry.instrumentation.agno import AgnoInstrumentor
from opentelemetry.instrumentation.agno.utils import (
    should_capture_content,
    set_span_attribute,
    safe_json_serialize,
)


class TestAgnoInstrumentor:
    """Test cases for AgnoInstrumentor."""

    def test_instrumentation_dependencies(self):
        """Test that instrumentation dependencies are correctly defined."""
        instrumentor = AgnoInstrumentor()
        deps = instrumentor.instrumentation_dependencies()
        assert len(deps) == 1
        assert "agno >= 1.0.0" in deps

    def test_instrument_uninstrument(self, tracer_provider):
        """Test that instrument and uninstrument work correctly."""
        instrumentor = AgnoInstrumentor()

        # Mock agno modules
        with patch.dict("sys.modules", {
            "agno": MagicMock(),
            "agno.agent": MagicMock(),
            "agno.team": MagicMock(),
            "agno.tools": MagicMock(),
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


class TestAgentRunWrapper:
    """Test cases for AgentRunWrapper."""

    def test_agent_run_wrapper(self, tracer_provider, span_exporter):
        """Test agent run wrapper creates correct span."""
        from opentelemetry.instrumentation.agno.patch import AgentRunWrapper

        # Use tracer_provider directly to avoid global provider caching issues
        tracer = tracer_provider.get_tracer(__name__)
        wrapper = AgentRunWrapper(tracer)

        # Create mock agent instance
        mock_agent = MagicMock()
        mock_agent.name = "TestAgent"
        mock_agent.model = MagicMock()
        mock_agent.model.id = "gpt-4"

        # Create mock result
        mock_result = MagicMock()
        mock_result.content = "Hello!"
        mock_result.run_id = "test-run-123"

        # Create mock wrapped function
        mock_wrapped = MagicMock(return_value=mock_result)

        # Call wrapper (non-streaming)
        result = wrapper(mock_wrapped, mock_agent, ("Hello",), {"stream": False})

        # Verify wrapped was called
        mock_wrapped.assert_called_once()

        # Verify span was created
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "TestAgent.agent"
        assert spans[0].attributes.get("gen_ai.system") == "agno"
        assert spans[0].attributes.get("gen_ai.operation.name") == "agent"
        assert spans[0].attributes.get("gen_ai.agent.name") == "TestAgent"


class TestTeamRunWrapper:
    """Test cases for TeamRunWrapper."""

    def test_team_run_wrapper(self, tracer_provider, span_exporter):
        """Test team run wrapper creates correct span."""
        from opentelemetry.instrumentation.agno.patch import TeamRunWrapper

        # Use tracer_provider directly to avoid global provider caching issues
        tracer = tracer_provider.get_tracer(__name__)
        wrapper = TeamRunWrapper(tracer)

        # Create mock team instance
        mock_team = MagicMock()
        mock_team.name = "TestTeam"

        # Create mock result
        mock_result = MagicMock()
        mock_result.content = "Team result"
        mock_result.run_id = "test-team-123"

        # Create mock wrapped function
        mock_wrapped = MagicMock(return_value=mock_result)

        # Call wrapper
        result = wrapper(mock_wrapped, mock_team, ("Query",), {})

        # Verify wrapped was called
        mock_wrapped.assert_called_once()

        # Verify span was created
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "TestTeam.team"
        assert spans[0].attributes.get("gen_ai.system") == "agno"
        assert spans[0].attributes.get("gen_ai.operation.name") == "workflow"


class TestFunctionCallWrapper:
    """Test cases for FunctionCallExecuteWrapper."""

    def test_function_call_wrapper(self, tracer_provider, span_exporter):
        """Test function call wrapper creates correct span."""
        from opentelemetry.instrumentation.agno.patch import FunctionCallExecuteWrapper

        # Use tracer_provider directly to avoid global provider caching issues
        tracer = tracer_provider.get_tracer(__name__)
        wrapper = FunctionCallExecuteWrapper(tracer)

        # Create mock function call instance
        mock_func = MagicMock()
        mock_func.name = "get_weather"
        mock_func.description = "Get weather for a location"

        mock_function_call = MagicMock()
        mock_function_call.function = mock_func
        mock_function_call.arguments = {"location": "NYC"}

        # Create mock wrapped function
        mock_wrapped = MagicMock(return_value="Sunny, 72F")

        # Call wrapper
        result = wrapper(mock_wrapped, mock_function_call, (), {})

        # Verify wrapped was called
        mock_wrapped.assert_called_once()

        # Verify span was created
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "get_weather.tool"
        assert spans[0].attributes.get("gen_ai.system") == "agno"
        assert spans[0].attributes.get("gen_ai.operation.name") == "execute_tool"
