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

"""End-to-end scenario tests that simulate realistic LangChain/LangGraph
callback sequences.

These tests feed events directly into the callback handler and verify
the resulting span structure managed by a real ``_SpanManager`` backed
by a mock tracer.  No actual LangChain runtime is invoked.
"""

from __future__ import annotations

from unittest import mock
from uuid import uuid4

from opentelemetry.instrumentation.langchain.callback_handler import (
    OpenTelemetryLangChainCallbackHandler,
)
from opentelemetry.instrumentation.langchain.semconv_attributes import (
    OP_EXECUTE_TOOL,
    OP_INVOKE_AGENT,
)
from opentelemetry.instrumentation.langchain.span_manager import (
    _SpanManager,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import error_attributes
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import StatusCode

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _mock_tracer():
    """Return a mock Tracer whose ``start_span`` produces unique mock spans."""
    tracer = mock.MagicMock()

    def _new_span(**kwargs):
        span = mock.MagicMock()
        span.is_recording.return_value = True
        span._name = kwargs.get("name", "unnamed")
        span._attributes = {}

        original_set_attr = span.set_attribute

        def _track_attr(key, value):
            span._attributes[key] = value
            return original_set_attr(key, value)

        span.set_attribute = mock.MagicMock(side_effect=_track_attr)
        return span

    tracer.start_span = mock.MagicMock(side_effect=_new_span)
    return tracer


def _make_handler_and_manager():
    """Create a handler backed by a real ``_SpanManager`` with a mock tracer."""
    tracer = _mock_tracer()
    span_manager = _SpanManager(tracer)
    telemetry_handler = mock.MagicMock()
    handler = OpenTelemetryLangChainCallbackHandler(
        telemetry_handler=telemetry_handler,
        span_manager=span_manager,
    )
    return handler, span_manager, tracer


def _agent_metadata(name: str, **extra) -> dict:
    """Metadata dict that causes ``classify_chain_run`` to emit an agent span."""
    meta = {"otel_agent_span": True, "agent_name": name}
    meta.update(extra)
    return meta


def _get_span(span_manager: _SpanManager, run_id) -> mock.MagicMock:
    """Return the mock span for *run_id*, which must still be active."""
    record = span_manager.get_record(run_id)
    assert record is not None, f"No active record for {run_id}"
    return record.span


def _get_set_attributes(span: mock.MagicMock) -> dict:
    """Collect all attributes set on a mock span via ``set_attribute``."""
    return dict(span._attributes)


# ------------------------------------------------------------------
# Scenario 1: Simple agent with tool call
# ------------------------------------------------------------------


class TestSimpleAgentWithToolCall:
    """Agent starts → LLM called → tool called → LLM called again → agent ends.

    Verifies:
    - Agent span parents LLM and tool spans.
    - Token usage accumulates on agent span.
    """

    def test_span_hierarchy_and_token_accumulation(self, monkeypatch):
        monkeypatch.setattr(
            "opentelemetry.instrumentation.langchain.callback_handler.should_record_tool_content",
            lambda policy: False,
        )
        handler, sm, tracer = _make_handler_and_manager()

        agent_id = uuid4()
        tool_id = uuid4()

        # 1) Agent starts
        handler.on_chain_start(
            serialized={"name": "my_agent"},
            inputs={"messages": []},
            run_id=agent_id,
            parent_run_id=None,
            metadata=_agent_metadata("my_agent"),
        )

        agent_record = sm.get_record(agent_id)
        assert agent_record is not None
        assert agent_record.operation == OP_INVOKE_AGENT

        # 2) First LLM call (child of agent via an ignored intermediate chain)
        #    LLM spans are managed by TelemetryHandler, but token accumulation
        #    flows through SpanManager.  Simulate by calling
        #    accumulate_llm_usage_to_agent directly.
        sm.accumulate_llm_usage_to_agent(
            agent_id, input_tokens=100, output_tokens=50
        )

        # 3) Tool call
        handler.on_tool_start(
            serialized={"name": "web_search", "description": "Search the web"},
            input_str="latest news",
            run_id=tool_id,
            parent_run_id=agent_id,
        )

        tool_record = sm.get_record(tool_id)
        assert tool_record is not None
        assert tool_record.operation == OP_EXECUTE_TOOL
        assert tool_record.parent_run_id == str(agent_id)

        handler.on_tool_end(output="some results", run_id=tool_id)
        assert sm.get_record(tool_id) is None  # span ended, record removed

        # 4) Second LLM call
        sm.accumulate_llm_usage_to_agent(
            agent_id, input_tokens=200, output_tokens=80
        )

        # 5) Agent ends
        handler.on_chain_end(outputs={"output": "done"}, run_id=agent_id)
        assert sm.get_record(agent_id) is None  # span ended

        # Verify token accumulation on the agent span.
        # Token accumulation calls set_attribute on agent_record.span.
        agent_span_obj = agent_record.span
        attrs = _get_set_attributes(agent_span_obj)

        assert attrs[GenAI.GEN_AI_USAGE_INPUT_TOKENS] == 300  # 100 + 200
        assert attrs[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] == 130  # 50 + 80

    def test_tool_span_created_with_correct_kind(self, monkeypatch):
        monkeypatch.setattr(
            "opentelemetry.instrumentation.langchain.callback_handler.should_record_tool_content",
            lambda policy: False,
        )
        handler, sm, tracer = _make_handler_and_manager()

        agent_id = uuid4()
        tool_id = uuid4()

        handler.on_chain_start(
            serialized={"name": "agent"},
            inputs={},
            run_id=agent_id,
            metadata=_agent_metadata("agent"),
        )

        handler.on_tool_start(
            serialized={"name": "calc"},
            input_str="2+2",
            run_id=tool_id,
            parent_run_id=agent_id,
        )

        # Agent span → SpanKind.CLIENT, Tool span → SpanKind.INTERNAL
        calls = tracer.start_span.call_args_list
        agent_call_kwargs = calls[0][1]
        tool_call_kwargs = calls[1][1]
        assert agent_call_kwargs["kind"] == SpanKind.CLIENT
        assert tool_call_kwargs["kind"] == SpanKind.INTERNAL

        handler.on_tool_end(output="4", run_id=tool_id)
        handler.on_chain_end(outputs={}, run_id=agent_id)


# ------------------------------------------------------------------
# Scenario 2: Nested agents
# ------------------------------------------------------------------


class TestNestedAgents:
    """Outer agent → inner agent → LLM → inner agent ends → outer agent ends.

    Verifies:
    - Inner agent is a child of outer agent.
    - Token usage propagates up through both levels.
    """

    def test_nested_agent_parenting(self):
        handler, sm, tracer = _make_handler_and_manager()

        outer_id = uuid4()
        inner_id = uuid4()

        # 1) Outer agent starts
        handler.on_chain_start(
            serialized={"name": "outer_agent"},
            inputs={},
            run_id=outer_id,
            parent_run_id=None,
            metadata=_agent_metadata("outer_agent"),
        )

        # 2) Inner agent starts (child of outer)
        handler.on_chain_start(
            serialized={"name": "inner_agent"},
            inputs={},
            run_id=inner_id,
            parent_run_id=outer_id,
            metadata=_agent_metadata("inner_agent"),
        )

        inner_record = sm.get_record(inner_id)
        assert inner_record is not None
        assert inner_record.parent_run_id == str(outer_id)

        # The tracer should have been called with the outer's span as context
        # for the inner span.
        assert tracer.start_span.call_count == 2

        # 3) LLM call inside inner agent — accumulate tokens on inner agent
        sm.accumulate_llm_usage_to_agent(
            inner_id, input_tokens=50, output_tokens=25
        )

        inner_attrs = _get_set_attributes(inner_record.span)
        assert inner_attrs[GenAI.GEN_AI_USAGE_INPUT_TOKENS] == 50
        assert inner_attrs[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] == 25

        # 4) Inner agent ends
        handler.on_chain_end(outputs={}, run_id=inner_id)
        assert sm.get_record(inner_id) is None

        # 5) Outer agent ends
        handler.on_chain_end(outputs={}, run_id=outer_id)
        assert sm.get_record(outer_id) is None

    def test_token_usage_propagates_to_nearest_agent(self):
        """Token usage from an LLM call accumulates on the nearest agent ancestor."""
        handler, sm, tracer = _make_handler_and_manager()

        outer_id = uuid4()
        inner_id = uuid4()

        handler.on_chain_start(
            serialized={"name": "outer"},
            inputs={},
            run_id=outer_id,
            metadata=_agent_metadata("outer"),
        )
        handler.on_chain_start(
            serialized={"name": "inner"},
            inputs={},
            run_id=inner_id,
            parent_run_id=outer_id,
            metadata=_agent_metadata("inner"),
        )

        outer_record = sm.get_record(outer_id)
        inner_record = sm.get_record(inner_id)

        # Accumulate on the inner agent (the nearest)
        sm.accumulate_llm_usage_to_agent(
            inner_id, input_tokens=10, output_tokens=5
        )

        inner_attrs = _get_set_attributes(inner_record.span)
        assert inner_attrs.get(GenAI.GEN_AI_USAGE_INPUT_TOKENS) == 10

        # Outer should NOT have received tokens (accumulation stops at nearest agent)
        outer_attrs = _get_set_attributes(outer_record.span)
        assert GenAI.GEN_AI_USAGE_INPUT_TOKENS not in outer_attrs

        handler.on_chain_end(outputs={}, run_id=inner_id)
        handler.on_chain_end(outputs={}, run_id=outer_id)


# ------------------------------------------------------------------
# Scenario 3: Ignored intermediate chain
# ------------------------------------------------------------------


class TestIgnoredIntermediateChain:
    """Agent → internal chain (ignored) → LLM → internal chain ends → agent ends.

    Verifies:
    - Internal chain produces no span.
    - LLM-related operations walk through the ignored run to the agent.
    """

    def test_ignored_chain_produces_no_span(self):
        handler, sm, tracer = _make_handler_and_manager()

        agent_id = uuid4()
        chain_id = uuid4()

        # 1) Agent starts
        handler.on_chain_start(
            serialized={"name": "my_agent"},
            inputs={},
            run_id=agent_id,
            metadata=_agent_metadata("my_agent"),
        )

        # 2) Internal chain starts — no agent/workflow signals → ignored
        handler.on_chain_start(
            serialized={"name": "RunnableSequence"},
            inputs={},
            run_id=chain_id,
            parent_run_id=agent_id,
            metadata=None,
        )

        # The chain should be ignored: no span record created
        assert sm.get_record(chain_id) is None
        assert sm.is_ignored(chain_id)

        # Only one span created (the agent)
        assert tracer.start_span.call_count == 1

        # 3) Internal chain ends (no-op for ignored)
        handler.on_chain_end(outputs={}, run_id=chain_id)

        # 4) Agent ends
        handler.on_chain_end(outputs={}, run_id=agent_id)
        assert sm.get_record(agent_id) is None

    def test_tool_parents_through_ignored_chain(self, monkeypatch):
        """A tool whose parent_run_id points to an ignored chain should
        resolve to the agent span as its effective parent."""
        monkeypatch.setattr(
            "opentelemetry.instrumentation.langchain.callback_handler.should_record_tool_content",
            lambda policy: False,
        )
        handler, sm, tracer = _make_handler_and_manager()

        agent_id = uuid4()
        chain_id = uuid4()
        tool_id = uuid4()

        handler.on_chain_start(
            serialized={"name": "my_agent"},
            inputs={},
            run_id=agent_id,
            metadata=_agent_metadata("my_agent"),
        )

        # Internal chain is ignored
        handler.on_chain_start(
            serialized={"name": "RunnableSequence"},
            inputs={},
            run_id=chain_id,
            parent_run_id=agent_id,
            metadata=None,
        )
        assert sm.is_ignored(chain_id)

        # Tool claims chain_id as parent → should resolve to agent_id
        handler.on_tool_start(
            serialized={"name": "search"},
            input_str="query",
            run_id=tool_id,
            parent_run_id=chain_id,
        )

        tool_record = sm.get_record(tool_id)
        assert tool_record is not None
        # The tool's raw parent_run_id is the chain, but start_span resolves
        # through the ignored run. Verify the tracer was called with the
        # agent's context.
        tool_start_call = tracer.start_span.call_args_list[1]  # second call
        ctx = tool_start_call[1].get("context")
        assert ctx is not None  # parent context was set (the agent's)

        handler.on_tool_end(output="ok", run_id=tool_id)
        handler.on_chain_end(outputs={}, run_id=chain_id)
        handler.on_chain_end(outputs={}, run_id=agent_id)

    def test_llm_token_accumulation_through_ignored_chain(self):
        """Token usage from an LLM whose parent is an ignored chain should
        still accumulate on the agent."""
        handler, sm, tracer = _make_handler_and_manager()

        agent_id = uuid4()
        chain_id = uuid4()

        handler.on_chain_start(
            serialized={"name": "my_agent"},
            inputs={},
            run_id=agent_id,
            metadata=_agent_metadata("my_agent"),
        )

        # Ignored chain
        handler.on_chain_start(
            serialized={"name": "RunnableSequence"},
            inputs={},
            run_id=chain_id,
            parent_run_id=agent_id,
            metadata=None,
        )

        agent_record = sm.get_record(agent_id)

        # LLM call with chain_id as parent → accumulate_llm_usage_to_agent
        # should walk through the ignored chain to the agent.
        sm.accumulate_llm_usage_to_agent(
            chain_id, input_tokens=75, output_tokens=30
        )

        attrs = _get_set_attributes(agent_record.span)
        assert attrs[GenAI.GEN_AI_USAGE_INPUT_TOKENS] == 75
        assert attrs[GenAI.GEN_AI_USAGE_OUTPUT_TOKENS] == 30

        handler.on_chain_end(outputs={}, run_id=chain_id)
        handler.on_chain_end(outputs={}, run_id=agent_id)


# ------------------------------------------------------------------
# Scenario 4: Tool with error
# ------------------------------------------------------------------


class TestToolWithError:
    """Agent → tool starts → tool errors → agent ends with error.

    Verifies:
    - Tool span has error status.
    - Agent span has error status.
    """

    def test_tool_error_sets_error_status(self, monkeypatch):
        monkeypatch.setattr(
            "opentelemetry.instrumentation.langchain.callback_handler.should_record_tool_content",
            lambda policy: False,
        )
        handler, sm, tracer = _make_handler_and_manager()

        agent_id = uuid4()
        tool_id = uuid4()
        error = ValueError("tool exploded")

        handler.on_chain_start(
            serialized={"name": "my_agent"},
            inputs={},
            run_id=agent_id,
            metadata=_agent_metadata("my_agent"),
        )

        handler.on_tool_start(
            serialized={"name": "risky_tool"},
            input_str="danger",
            run_id=tool_id,
            parent_run_id=agent_id,
        )

        tool_record = sm.get_record(tool_id)
        tool_span = tool_record.span

        # Tool errors
        handler.on_tool_error(error=error, run_id=tool_id)

        # Tool span should be ended with error attributes
        tool_span.set_attribute.assert_any_call(
            error_attributes.ERROR_TYPE, "ValueError"
        )
        tool_span.set_status.assert_called_once()
        status_call = tool_span.set_status.call_args[0][0]
        assert status_call.status_code == StatusCode.ERROR
        assert "tool exploded" in str(status_call.description)
        tool_span.end.assert_called_once()

        # Tool record should be removed
        assert sm.get_record(tool_id) is None

    def test_agent_error_after_tool_error(self, monkeypatch):
        monkeypatch.setattr(
            "opentelemetry.instrumentation.langchain.callback_handler.should_record_tool_content",
            lambda policy: False,
        )
        handler, sm, tracer = _make_handler_and_manager()

        agent_id = uuid4()
        tool_id = uuid4()
        tool_error = RuntimeError("timeout")
        agent_error = RuntimeError("agent failed due to tool error")

        handler.on_chain_start(
            serialized={"name": "my_agent"},
            inputs={},
            run_id=agent_id,
            metadata=_agent_metadata("my_agent"),
        )

        handler.on_tool_start(
            serialized={"name": "slow_tool"},
            input_str="data",
            run_id=tool_id,
            parent_run_id=agent_id,
        )

        agent_record = sm.get_record(agent_id)
        agent_span = agent_record.span

        # Tool errors
        handler.on_tool_error(error=tool_error, run_id=tool_id)
        assert sm.get_record(tool_id) is None

        # Agent errors
        handler.on_chain_error(error=agent_error, run_id=agent_id)

        # Agent span should have error status
        agent_span.set_attribute.assert_any_call(
            error_attributes.ERROR_TYPE, "RuntimeError"
        )
        agent_span.set_status.assert_called_once()
        agent_status = agent_span.set_status.call_args[0][0]
        assert agent_status.status_code == StatusCode.ERROR
        assert "agent failed" in str(agent_status.description)
        agent_span.end.assert_called_once()

        assert sm.get_record(agent_id) is None

    def test_error_does_not_leak_across_runs(self, monkeypatch):
        """A tool error in one run should not affect a sibling tool."""
        monkeypatch.setattr(
            "opentelemetry.instrumentation.langchain.callback_handler.should_record_tool_content",
            lambda policy: False,
        )
        handler, sm, tracer = _make_handler_and_manager()

        agent_id = uuid4()
        tool_ok_id = uuid4()
        tool_err_id = uuid4()

        handler.on_chain_start(
            serialized={"name": "my_agent"},
            inputs={},
            run_id=agent_id,
            metadata=_agent_metadata("my_agent"),
        )

        # Two tools start
        handler.on_tool_start(
            serialized={"name": "good_tool"},
            input_str="",
            run_id=tool_ok_id,
            parent_run_id=agent_id,
        )
        handler.on_tool_start(
            serialized={"name": "bad_tool"},
            input_str="",
            run_id=tool_err_id,
            parent_run_id=agent_id,
        )

        ok_record = sm.get_record(tool_ok_id)
        ok_span = ok_record.span

        # One tool errors
        handler.on_tool_error(error=ValueError("boom"), run_id=tool_err_id)
        assert sm.get_record(tool_err_id) is None

        # Other tool completes normally
        handler.on_tool_end(output="all good", run_id=tool_ok_id)
        # The OK tool's span should NOT have error status set
        for call in ok_span.set_status.call_args_list:
            assert call[0][0].status_code != StatusCode.ERROR

        handler.on_chain_end(outputs={}, run_id=agent_id)


# ------------------------------------------------------------------
# Scenario 5: Span manager cleanup
# ------------------------------------------------------------------


class TestSpanManagerCleanup:
    """Verify that all internal state is cleaned up after a full lifecycle."""

    def test_no_leftover_state(self, monkeypatch):
        monkeypatch.setattr(
            "opentelemetry.instrumentation.langchain.callback_handler.should_record_tool_content",
            lambda policy: False,
        )
        handler, sm, tracer = _make_handler_and_manager()

        agent_id = uuid4()
        chain_id = uuid4()
        tool_id = uuid4()

        handler.on_chain_start(
            serialized={"name": "agent"},
            inputs={},
            run_id=agent_id,
            metadata=_agent_metadata("agent"),
        )
        handler.on_chain_start(
            serialized={"name": "inner"},
            inputs={},
            run_id=chain_id,
            parent_run_id=agent_id,
        )
        handler.on_tool_start(
            serialized={"name": "tool"},
            input_str="",
            run_id=tool_id,
            parent_run_id=chain_id,
        )

        handler.on_tool_end(output="ok", run_id=tool_id)
        handler.on_chain_end(outputs={}, run_id=chain_id)
        handler.on_chain_end(outputs={}, run_id=agent_id)

        # All span records should be cleared
        assert len(sm._spans) == 0
