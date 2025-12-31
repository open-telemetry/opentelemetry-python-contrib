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

"""Tests for LangGraph instrumentation."""

from typing import TypedDict

import pytest
from langgraph.graph import END, START, StateGraph

from opentelemetry.instrumentation.langgraph.patch import (
    LANGGRAPH_GRAPH_NAME,
    LANGGRAPH_STEP,
    LANGGRAPH_STREAM_MODE,
)
from opentelemetry.trace import StatusCode


class SimpleState(TypedDict):
    """Simple state for testing."""

    value: str
    count: int


def increment_node(state: SimpleState) -> dict:
    """A simple node that increments count."""
    return {"count": state["count"] + 1}


def process_node(state: SimpleState) -> dict:
    """A simple node that processes value."""
    return {"value": state["value"] + " processed"}


@pytest.fixture
def simple_graph():
    """Create a simple graph for testing."""
    graph = StateGraph(SimpleState)
    graph.add_node("increment", increment_node)
    graph.add_node("process", process_node)
    graph.add_edge(START, "increment")
    graph.add_edge("increment", "process")
    graph.add_edge("process", END)
    return graph.compile()


class TestInvokeInstrumentation:
    """Tests for invoke/ainvoke instrumentation."""

    def test_invoke_creates_span(
        self, span_exporter, instrumentation, simple_graph
    ):
        """Test that invoke creates a workflow span."""
        result = simple_graph.invoke({"value": "hello", "count": 0})

        assert result["value"] == "hello processed"
        assert result["count"] == 1

        spans = span_exporter.get_finished_spans()
        assert len(spans) >= 1

        # Find the workflow span
        workflow_spans = [
            s for s in spans if "langgraph.workflow" in s.name
        ]
        assert len(workflow_spans) >= 1

        workflow_span = workflow_spans[0]
        assert workflow_span.status.status_code == StatusCode.OK
        assert LANGGRAPH_GRAPH_NAME in workflow_span.attributes

    def test_invoke_captures_graph_name(
        self, span_exporter, instrumentation, simple_graph
    ):
        """Test that invoke captures the graph name attribute."""
        simple_graph.invoke({"value": "test", "count": 0})

        spans = span_exporter.get_finished_spans()
        workflow_spans = [
            s for s in spans if "langgraph.workflow" in s.name
        ]
        assert len(workflow_spans) >= 1

        workflow_span = workflow_spans[0]
        graph_name = workflow_span.attributes.get(LANGGRAPH_GRAPH_NAME)
        assert graph_name is not None

    def test_invoke_error_handling(
        self, span_exporter, instrumentation
    ):
        """Test that invoke properly records errors."""

        def error_node(state: SimpleState) -> dict:
            raise ValueError("Test error")

        graph = StateGraph(SimpleState)
        graph.add_node("error", error_node)
        graph.add_edge(START, "error")
        graph.add_edge("error", END)
        compiled = graph.compile()

        with pytest.raises(ValueError, match="Test error"):
            compiled.invoke({"value": "test", "count": 0})

        spans = span_exporter.get_finished_spans()
        workflow_spans = [
            s for s in spans if "langgraph.workflow" in s.name
        ]
        assert len(workflow_spans) >= 1

        workflow_span = workflow_spans[0]
        assert workflow_span.status.status_code == StatusCode.ERROR

    @pytest.mark.asyncio
    async def test_ainvoke_creates_span(
        self, span_exporter, instrumentation, simple_graph
    ):
        """Test that ainvoke creates a workflow span."""
        result = await simple_graph.ainvoke({"value": "hello", "count": 0})

        assert result["value"] == "hello processed"
        assert result["count"] == 1

        spans = span_exporter.get_finished_spans()
        workflow_spans = [
            s for s in spans if "langgraph.workflow" in s.name
        ]
        assert len(workflow_spans) >= 1


class TestStreamInstrumentation:
    """Tests for stream/astream instrumentation."""

    def test_stream_creates_span(
        self, span_exporter, instrumentation, simple_graph
    ):
        """Test that stream creates a workflow span."""
        chunks = list(
            simple_graph.stream({"value": "hello", "count": 0})
        )

        assert len(chunks) > 0

        spans = span_exporter.get_finished_spans()
        stream_spans = [
            s for s in spans if "langgraph.workflow.stream" in s.name
        ]
        assert len(stream_spans) >= 1

        stream_span = stream_spans[0]
        assert stream_span.status.status_code == StatusCode.OK

    def test_stream_captures_mode(
        self, span_exporter, instrumentation, simple_graph
    ):
        """Test that stream captures the stream_mode attribute."""
        list(
            simple_graph.stream(
                {"value": "hello", "count": 0},
                stream_mode="updates",
            )
        )

        spans = span_exporter.get_finished_spans()
        stream_spans = [
            s for s in spans if "langgraph.workflow.stream" in s.name
        ]
        assert len(stream_spans) >= 1

        stream_span = stream_spans[0]
        stream_mode = stream_span.attributes.get(LANGGRAPH_STREAM_MODE)
        assert stream_mode == "updates"

    def test_stream_captures_step_count(
        self, span_exporter, instrumentation, simple_graph
    ):
        """Test that stream captures the step count."""
        chunks = list(
            simple_graph.stream({"value": "hello", "count": 0})
        )

        spans = span_exporter.get_finished_spans()
        stream_spans = [
            s for s in spans if "langgraph.workflow.stream" in s.name
        ]
        assert len(stream_spans) >= 1

        stream_span = stream_spans[0]
        step_count = stream_span.attributes.get(LANGGRAPH_STEP)
        assert step_count is not None
        assert step_count == len(chunks)

    @pytest.mark.asyncio
    async def test_astream_creates_span(
        self, span_exporter, instrumentation, simple_graph
    ):
        """Test that astream creates a workflow span."""
        chunks = []
        async for chunk in simple_graph.astream(
            {"value": "hello", "count": 0}
        ):
            chunks.append(chunk)

        assert len(chunks) > 0

        spans = span_exporter.get_finished_spans()
        stream_spans = [
            s for s in spans if "langgraph.workflow.stream" in s.name
        ]
        assert len(stream_spans) >= 1


class TestInstrumentorLifecycle:
    """Tests for instrumentor lifecycle (instrument/uninstrument)."""

    def test_instrument_uninstrument_cycle(
        self, span_exporter, tracer_provider
    ):
        """Test that we can instrument and uninstrument cleanly."""
        from opentelemetry.instrumentation.langgraph import (
            LangGraphInstrumentor,
        )

        instrumentor = LangGraphInstrumentor()

        # First instrumentation
        instrumentor.instrument(tracer_provider=tracer_provider)

        graph = StateGraph(SimpleState)
        graph.add_node("process", process_node)
        graph.add_edge(START, "process")
        graph.add_edge("process", END)
        compiled = graph.compile()

        compiled.invoke({"value": "test", "count": 0})
        spans_before = span_exporter.get_finished_spans()
        assert len(spans_before) >= 1

        # Uninstrument
        instrumentor.uninstrument()
        span_exporter.clear()

        # After uninstrument, no new spans should be created
        compiled.invoke({"value": "test2", "count": 0})
        spans_after = span_exporter.get_finished_spans()
        # The span count should be 0 or the same (no new workflow spans)
        workflow_spans = [
            s for s in spans_after if "langgraph.workflow" in s.name
        ]
        assert len(workflow_spans) == 0

    def test_instrumentation_dependencies(self):
        """Test that instrumentation reports correct dependencies."""
        from opentelemetry.instrumentation.langgraph import (
            LangGraphInstrumentor,
        )

        instrumentor = LangGraphInstrumentor()
        deps = instrumentor.instrumentation_dependencies()

        assert len(deps) > 0
        assert any("langgraph" in dep for dep in deps)


class TestMultipleStreamModes:
    """Tests for multiple stream modes (LangGraph 1.0+ feature)."""

    def test_stream_mode_values(
        self, span_exporter, instrumentation, simple_graph
    ):
        """Test stream with values mode."""
        list(
            simple_graph.stream(
                {"value": "hello", "count": 0},
                stream_mode="values",
            )
        )

        spans = span_exporter.get_finished_spans()
        stream_spans = [
            s for s in spans if "langgraph.workflow.stream" in s.name
        ]
        assert len(stream_spans) >= 1

        stream_span = stream_spans[0]
        assert stream_span.attributes.get(LANGGRAPH_STREAM_MODE) == "values"

    def test_stream_mode_updates(
        self, span_exporter, instrumentation, simple_graph
    ):
        """Test stream with updates mode."""
        list(
            simple_graph.stream(
                {"value": "hello", "count": 0},
                stream_mode="updates",
            )
        )

        spans = span_exporter.get_finished_spans()
        stream_spans = [
            s for s in spans if "langgraph.workflow.stream" in s.name
        ]
        assert len(stream_spans) >= 1

        stream_span = stream_spans[0]
        assert stream_span.attributes.get(LANGGRAPH_STREAM_MODE) == "updates"
