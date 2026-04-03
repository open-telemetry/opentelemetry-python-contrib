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

"""Tests for span hierarchy and parent-child resolution in _SpanManager."""

from unittest import mock

import pytest

from opentelemetry.instrumentation.langchain.semconv_attributes import (
    OP_CHAT,
    OP_INVOKE_AGENT,
)
from opentelemetry.instrumentation.langchain.span_manager import _SpanManager
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.trace.status import StatusCode


def _make_mock_span():
    span = mock.MagicMock()
    span.is_recording.return_value = True
    return span


def _make_tracer():
    tracer = mock.MagicMock()
    tracer.start_span.side_effect = lambda **kwargs: _make_mock_span()
    return tracer


@pytest.fixture()
def tracer():
    return _make_tracer()


@pytest.fixture()
def mgr(tracer):
    return _SpanManager(tracer)


# ------------------------------------------------------------------
# resolve_parent_id
# ------------------------------------------------------------------


class TestResolveParentId:
    def test_returns_parent_when_parent_exists_in_spans(self, mgr):
        """Parent run_id is returned directly when it is not ignored."""
        mgr.start_span(
            run_id="parent-1",
            name="agent",
            operation=OP_INVOKE_AGENT,
        )
        assert mgr.resolve_parent_id("parent-1") == "parent-1"

    def test_walks_through_ignored_runs(self, mgr):
        """Children of ignored runs are re-parented to the visible ancestor."""
        mgr.start_span(
            run_id="grandparent",
            name="agent",
            operation=OP_INVOKE_AGENT,
        )
        # Middle run is ignored; its parent is the grandparent.
        mgr.ignore_run("ignored-middle", parent_run_id="grandparent")

        resolved = mgr.resolve_parent_id("ignored-middle")
        assert resolved == "grandparent"

    def test_cycle_in_ignored_chain_returns_none(self, mgr):
        """A cycle among ignored runs must not loop forever."""
        mgr.ignore_run("a", parent_run_id="b")
        mgr.ignore_run("b", parent_run_id="a")

        assert mgr.resolve_parent_id("a") is None

    def test_returns_none_when_parent_not_found(self, mgr):
        assert mgr.resolve_parent_id(None) is None
        # Unknown non-ignored id is returned as-is (it is "visible").
        assert mgr.resolve_parent_id("nonexistent") == "nonexistent"


# ------------------------------------------------------------------
# Agent stacks
# ------------------------------------------------------------------


class TestAgentStacks:
    def test_agent_stacks_track_per_thread(self, mgr):
        """Each thread_key gets its own independent agent stack."""
        mgr.start_span(
            run_id="agent-t1",
            name="agent",
            operation=OP_INVOKE_AGENT,
            thread_key="thread-1",
        )
        mgr.start_span(
            run_id="agent-t2",
            name="agent",
            operation=OP_INVOKE_AGENT,
            thread_key="thread-2",
        )

        assert mgr._agent_stack_by_thread["thread-1"] == ["agent-t1"]
        assert mgr._agent_stack_by_thread["thread-2"] == ["agent-t2"]

    def test_start_span_adds_to_agent_stack(self, mgr):
        """invoke_agent spans are pushed onto the per-thread agent stack."""
        mgr.start_span(
            run_id="agent-a",
            name="outer",
            operation=OP_INVOKE_AGENT,
            thread_key="t",
        )
        mgr.start_span(
            run_id="agent-b",
            name="inner",
            operation=OP_INVOKE_AGENT,
            thread_key="t",
        )

        assert mgr._agent_stack_by_thread["t"] == ["agent-a", "agent-b"]

    def test_end_span_removes_from_agent_stack(self, mgr):
        """Ending an invoke_agent span pops it from the agent stack."""
        mgr.start_span(
            run_id="agent-x",
            name="agent",
            operation=OP_INVOKE_AGENT,
            thread_key="tk",
        )
        assert "tk" in mgr._agent_stack_by_thread

        mgr.end_span("agent-x")

        # Stack should be cleaned up entirely when empty.
        assert "tk" not in mgr._agent_stack_by_thread


# ------------------------------------------------------------------
# Goto routing
# ------------------------------------------------------------------


class TestGotoRouting:
    def test_push_pop_lifo(self, mgr):
        """push/pop follows LIFO order."""
        mgr.push_goto_parent("t1", "parent-a")
        mgr.push_goto_parent("t1", "parent-b")

        assert mgr.pop_goto_parent("t1") == "parent-b"
        assert mgr.pop_goto_parent("t1") == "parent-a"

    def test_pop_empty_returns_none(self, mgr):
        assert mgr.pop_goto_parent("nonexistent-thread") is None

    def test_cleanup_of_empty_stacks(self, mgr):
        """Once the last goto parent is popped the thread key is removed."""
        mgr.push_goto_parent("t1", "p1")
        mgr.pop_goto_parent("t1")

        assert "t1" not in mgr._goto_parent_stack


# ------------------------------------------------------------------
# accumulate_usage_to_parent
# ------------------------------------------------------------------


class TestAccumulateUsageToParent:
    def test_accumulates_on_nearest_agent_parent(self, mgr):
        """Token counts propagate to the nearest invoke_agent ancestor."""
        agent_rec = mgr.start_span(
            run_id="agent",
            name="agent",
            operation=OP_INVOKE_AGENT,
        )
        chat_rec = mgr.start_span(
            run_id="chat",
            name="chat gpt-4o",
            operation=OP_CHAT,
            parent_run_id="agent",
        )

        mgr.accumulate_usage_to_parent(
            chat_rec, input_tokens=10, output_tokens=5
        )

        agent_span = agent_rec.span
        agent_span.set_attribute.assert_any_call(
            GenAI.GEN_AI_USAGE_INPUT_TOKENS, 10
        )
        agent_span.set_attribute.assert_any_call(
            GenAI.GEN_AI_USAGE_OUTPUT_TOKENS, 5
        )

    def test_noop_when_no_agent_parent(self, mgr):
        """No error when the parent chain has no invoke_agent span."""
        chat_rec = mgr.start_span(
            run_id="chat-orphan",
            name="chat",
            operation=OP_CHAT,
        )
        # Should not raise.
        mgr.accumulate_usage_to_parent(
            chat_rec, input_tokens=1, output_tokens=2
        )

    def test_handles_none_token_values(self, mgr):
        """Both tokens None → early return, no side-effects."""
        agent_rec = mgr.start_span(
            run_id="agent",
            name="agent",
            operation=OP_INVOKE_AGENT,
        )
        chat_rec = mgr.start_span(
            run_id="chat",
            name="chat",
            operation=OP_CHAT,
            parent_run_id="agent",
        )

        # Reset call tracking after start_span's own set_attribute calls.
        agent_rec.span.set_attribute.reset_mock()

        mgr.accumulate_usage_to_parent(
            chat_rec, input_tokens=None, output_tokens=None
        )

        # No token attributes should have been set on the agent span.
        agent_rec.span.set_attribute.assert_not_called()


# ------------------------------------------------------------------
# start_span / end_span
# ------------------------------------------------------------------


class TestStartEndSpan:
    def test_creates_span_with_correct_parent_context(self, mgr, tracer):
        """start_span passes the parent span's context to the tracer."""
        mgr.start_span(
            run_id="parent",
            name="parent-agent",
            operation=OP_INVOKE_AGENT,
        )

        mgr.start_span(
            run_id="child",
            name="child-chat",
            operation=OP_CHAT,
            parent_run_id="parent",
        )

        # The second start_span call should pass a non-None context.
        calls = tracer.start_span.call_args_list
        assert len(calls) == 2
        child_call_kwargs = calls[1][1]
        assert child_call_kwargs["context"] is not None

    def test_end_span_with_error_sets_attributes(self, mgr):
        """end_span records error type and ERROR status on the span."""
        rec = mgr.start_span(
            run_id="err-run",
            name="failing",
            operation=OP_CHAT,
        )
        span = rec.span

        mgr.end_span("err-run", error=ValueError("boom"))

        span.set_attribute.assert_any_call("error.type", "ValueError")
        span.set_status.assert_called_once()
        status_arg = span.set_status.call_args[0][0]
        assert status_arg.status_code == StatusCode.ERROR

    def test_end_span_removes_record(self, mgr):
        """After end_span the run_id is no longer tracked."""
        mgr.start_span(
            run_id="temp",
            name="temp",
            operation=OP_CHAT,
        )
        assert mgr.get_record("temp") is not None

        mgr.end_span("temp")
        assert mgr.get_record("temp") is None
