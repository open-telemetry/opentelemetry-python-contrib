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

from uuid import uuid4

from opentelemetry.instrumentation.langchain.operation_mapping import (
    OperationName,
    classify_chain_run,
    resolve_agent_name,
    should_ignore_chain,
)

# ---------------------------------------------------------------------------
# classify_chain_run
# ---------------------------------------------------------------------------


class TestClassifyChainRunAgentDetection:
    """Agent signals → invoke_agent."""

    def test_otel_agent_span_true(self):
        result = classify_chain_run(
            serialized={},
            metadata={"otel_agent_span": True},
            kwargs={},
        )
        assert result == OperationName.INVOKE_AGENT

    def test_metadata_agent_name(self):
        result = classify_chain_run(
            serialized={},
            metadata={"agent_name": "my-agent"},
            kwargs={},
        )
        assert result == OperationName.INVOKE_AGENT

    def test_metadata_agent_type(self):
        result = classify_chain_run(
            serialized={},
            metadata={"agent_type": "react"},
            kwargs={},
        )
        assert result == OperationName.INVOKE_AGENT

    def test_langgraph_agent_node(self):
        result = classify_chain_run(
            serialized={},
            metadata={"langgraph_node": "researcher"},
            kwargs={},
        )
        assert result == OperationName.INVOKE_AGENT

    def test_agent_signals_override_workflow(self):
        """Agent signals take priority over workflow heuristics."""
        result = classify_chain_run(
            serialized={"name": "LangGraph"},
            metadata={"otel_agent_span": True},
            kwargs={},
            parent_run_id=None,
        )
        assert result == OperationName.INVOKE_AGENT


class TestClassifyChainRunWorkflowDetection:
    """Workflow signals → invoke_workflow."""

    def test_top_level_langgraph_by_name(self):
        result = classify_chain_run(
            serialized={"name": "LangGraph"},
            metadata={},
            kwargs={},
            parent_run_id=None,
        )
        assert result == OperationName.INVOKE_WORKFLOW

    def test_top_level_langgraph_by_graph_id(self):
        result = classify_chain_run(
            serialized={"name": "other", "graph": {"id": "LangGraph-abc"}},
            metadata={},
            kwargs={},
            parent_run_id=None,
        )
        assert result == OperationName.INVOKE_WORKFLOW

    def test_otel_workflow_span_true(self):
        result = classify_chain_run(
            serialized={},
            metadata={"otel_workflow_span": True},
            kwargs={},
            parent_run_id=None,
        )
        assert result == OperationName.INVOKE_WORKFLOW

    def test_not_workflow_when_has_parent(self):
        """LangGraph name alone is not enough when there is a parent run."""
        result = classify_chain_run(
            serialized={"name": "LangGraph"},
            metadata={},
            kwargs={},
            parent_run_id=uuid4(),
        )
        assert result is None


class TestClassifyChainRunSuppression:
    """Chains that should be suppressed (return None)."""

    def test_start_node_suppressed(self):
        result = classify_chain_run(
            serialized={},
            metadata={"langgraph_node": "__start__"},
            kwargs={},
        )
        assert result is None

    def test_middleware_prefix_suppressed(self):
        result = classify_chain_run(
            serialized={"name": "Middleware.auth"},
            metadata={"langgraph_node": "Middleware.auth"},
            kwargs={"name": "Middleware.auth"},
        )
        assert result is None

    def test_otel_trace_false(self):
        result = classify_chain_run(
            serialized={},
            metadata={"otel_trace": False},
            kwargs={},
        )
        assert result is None

    def test_otel_agent_span_false_no_other_signals(self):
        result = classify_chain_run(
            serialized={},
            metadata={"otel_agent_span": False},
            kwargs={},
        )
        assert result is None

    def test_unclassified_generic_chain(self):
        result = classify_chain_run(
            serialized={"name": "RunnableSequence"},
            metadata={},
            kwargs={},
            parent_run_id=uuid4(),
        )
        assert result is None


# ---------------------------------------------------------------------------
# should_ignore_chain
# ---------------------------------------------------------------------------


class TestShouldIgnoreChain:
    """Suppression logic for known noise chains."""

    def test_ignores_start_node(self):
        assert should_ignore_chain(
            metadata={"langgraph_node": "__start__"},
            agent_name=None,
            parent_run_id=None,
            kwargs={},
        )

    def test_ignores_middleware_agent_name(self):
        assert should_ignore_chain(
            metadata={},
            agent_name="Middleware.something",
            parent_run_id=None,
            kwargs={},
        )

    def test_ignores_middleware_in_kwargs_name(self):
        assert should_ignore_chain(
            metadata={},
            agent_name=None,
            parent_run_id=None,
            kwargs={"name": "Middleware.guard"},
        )

    def test_ignores_otel_trace_false(self):
        assert should_ignore_chain(
            metadata={"otel_trace": False},
            agent_name=None,
            parent_run_id=None,
            kwargs={},
        )

    def test_ignores_otel_agent_span_false_no_signals(self):
        assert should_ignore_chain(
            metadata={"otel_agent_span": False},
            agent_name=None,
            parent_run_id=None,
            kwargs={},
        )

    def test_does_not_ignore_otel_agent_span_false_with_agent_name(self):
        """otel_agent_span=False is overridden when agent_name is present."""
        assert not should_ignore_chain(
            metadata={"otel_agent_span": False, "agent_name": "planner"},
            agent_name="planner",
            parent_run_id=None,
            kwargs={},
        )

    def test_does_not_ignore_normal_agent_node(self):
        assert not should_ignore_chain(
            metadata={"langgraph_node": "researcher"},
            agent_name="researcher",
            parent_run_id=uuid4(),
            kwargs={},
        )


# ---------------------------------------------------------------------------
# resolve_agent_name
# ---------------------------------------------------------------------------


class TestResolveAgentName:
    """Best-effort agent name resolution from callback arguments."""

    def test_from_metadata_agent_name(self):
        assert (
            resolve_agent_name(
                serialized={},
                metadata={"agent_name": "planner"},
                kwargs={},
            )
            == "planner"
        )

    def test_from_kwargs_name(self):
        assert (
            resolve_agent_name(
                serialized={},
                metadata={},
                kwargs={"name": "tool-caller"},
            )
            == "tool-caller"
        )

    def test_from_serialized_name(self):
        assert (
            resolve_agent_name(
                serialized={"name": "MyAgent"},
                metadata={},
                kwargs={},
            )
            == "MyAgent"
        )

    def test_from_langgraph_node(self):
        assert (
            resolve_agent_name(
                serialized={},
                metadata={"langgraph_node": "researcher"},
                kwargs={},
            )
            == "researcher"
        )

    def test_langgraph_start_node_excluded(self):
        assert (
            resolve_agent_name(
                serialized={},
                metadata={"langgraph_node": "__start__"},
                kwargs={},
            )
            is None
        )

    def test_returns_none_when_nothing_available(self):
        assert (
            resolve_agent_name(serialized={}, metadata={}, kwargs={}) is None
        )

    def test_returns_none_with_none_metadata(self):
        assert (
            resolve_agent_name(serialized={}, metadata=None, kwargs={}) is None
        )

    def test_priority_metadata_over_kwargs(self):
        """metadata agent_name has higher priority than kwargs name."""
        assert (
            resolve_agent_name(
                serialized={"name": "ser"},
                metadata={"agent_name": "meta"},
                kwargs={"name": "kw"},
            )
            == "meta"
        )

    def test_priority_kwargs_over_serialized(self):
        assert (
            resolve_agent_name(
                serialized={"name": "ser"},
                metadata={},
                kwargs={"name": "kw"},
            )
            == "kw"
        )


# ---------------------------------------------------------------------------
# OperationName constants
# ---------------------------------------------------------------------------


class TestOperationNameConstants:
    def test_chat(self):
        assert OperationName.CHAT == "chat"

    def test_text_completion(self):
        assert OperationName.TEXT_COMPLETION == "text_completion"

    def test_invoke_agent(self):
        assert OperationName.INVOKE_AGENT == "invoke_agent"

    def test_execute_tool(self):
        assert OperationName.EXECUTE_TOOL == "execute_tool"

    def test_invoke_workflow(self):
        assert OperationName.INVOKE_WORKFLOW == "invoke_workflow"
