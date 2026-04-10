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

"""Tests for token usage accumulation from LLM spans to parent agent spans."""

from unittest.mock import MagicMock
from uuid import uuid4

from opentelemetry.instrumentation.langchain.semconv_attributes import (
    OP_CHAT,
    OP_INVOKE_AGENT,
)
from opentelemetry.instrumentation.langchain.span_manager import (
    SpanRecord,
    _SpanManager,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)

INPUT_TOKENS = GenAI.GEN_AI_USAGE_INPUT_TOKENS
OUTPUT_TOKENS = GenAI.GEN_AI_USAGE_OUTPUT_TOKENS


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_mock_span():
    span = MagicMock()
    span.set_attribute = MagicMock()
    return span


def _make_tracer():
    """Return a mock Tracer whose start_span returns fresh mock spans."""
    tracer = MagicMock()
    tracer.start_span = MagicMock(side_effect=lambda **kw: _make_mock_span())
    return tracer


def _make_manager():
    tracer = _make_tracer()
    return _SpanManager(tracer), tracer


def _register_record(mgr, run_id, operation, parent_run_id=None):
    """Register a SpanRecord directly in the manager for test isolation."""
    rid = str(run_id)
    prid = str(parent_run_id) if parent_run_id is not None else None
    span = _make_mock_span()
    record = SpanRecord(
        run_id=rid,
        span=span,
        operation=operation,
        parent_run_id=prid,
    )
    mgr._spans[rid] = record
    return record


# ------------------------------------------------------------------
# accumulate_usage_to_parent
# ------------------------------------------------------------------


class TestAccumulateUsageToParent:
    """Tests for _SpanManager.accumulate_usage_to_parent."""

    def test_accumulates_tokens_on_nearest_agent_parent(self):
        mgr, _ = _make_manager()
        agent_id = str(uuid4())
        llm_id = str(uuid4())

        agent_rec = _register_record(mgr, agent_id, OP_INVOKE_AGENT)
        llm_rec = _register_record(
            mgr, llm_id, OP_CHAT, parent_run_id=agent_id
        )

        mgr.accumulate_usage_to_parent(
            llm_rec, input_tokens=10, output_tokens=20
        )

        agent_rec.span.set_attribute.assert_any_call(INPUT_TOKENS, 10)
        agent_rec.span.set_attribute.assert_any_call(OUTPUT_TOKENS, 20)

    def test_accumulates_across_multiple_llm_calls(self):
        mgr, _ = _make_manager()
        agent_id = str(uuid4())
        llm1_id = str(uuid4())
        llm2_id = str(uuid4())

        agent_rec = _register_record(mgr, agent_id, OP_INVOKE_AGENT)
        llm1_rec = _register_record(
            mgr, llm1_id, OP_CHAT, parent_run_id=agent_id
        )
        llm2_rec = _register_record(
            mgr, llm2_id, OP_CHAT, parent_run_id=agent_id
        )

        mgr.accumulate_usage_to_parent(
            llm1_rec, input_tokens=10, output_tokens=5
        )
        mgr.accumulate_usage_to_parent(
            llm2_rec, input_tokens=20, output_tokens=15
        )

        # After two calls the values should be additive.
        agent_rec.span.set_attribute.assert_any_call(INPUT_TOKENS, 30)
        agent_rec.span.set_attribute.assert_any_call(OUTPUT_TOKENS, 20)

    def test_skips_non_agent_parents(self):
        """Walk up through a non-agent (chat) intermediate to the agent."""
        mgr, _ = _make_manager()
        agent_id = str(uuid4())
        chain_id = str(uuid4())
        llm_id = str(uuid4())

        agent_rec = _register_record(mgr, agent_id, OP_INVOKE_AGENT)
        _register_record(mgr, chain_id, OP_CHAT, parent_run_id=agent_id)
        llm_rec = _register_record(
            mgr, llm_id, OP_CHAT, parent_run_id=chain_id
        )

        mgr.accumulate_usage_to_parent(
            llm_rec, input_tokens=7, output_tokens=3
        )

        agent_rec.span.set_attribute.assert_any_call(INPUT_TOKENS, 7)
        agent_rec.span.set_attribute.assert_any_call(OUTPUT_TOKENS, 3)

    def test_noop_when_both_tokens_none(self):
        mgr, _ = _make_manager()
        agent_id = str(uuid4())
        llm_id = str(uuid4())

        agent_rec = _register_record(mgr, agent_id, OP_INVOKE_AGENT)
        llm_rec = _register_record(
            mgr, llm_id, OP_CHAT, parent_run_id=agent_id
        )

        mgr.accumulate_usage_to_parent(
            llm_rec, input_tokens=None, output_tokens=None
        )

        agent_rec.span.set_attribute.assert_not_called()

    def test_handles_only_input_tokens(self):
        mgr, _ = _make_manager()
        agent_id = str(uuid4())
        llm_id = str(uuid4())

        agent_rec = _register_record(mgr, agent_id, OP_INVOKE_AGENT)
        llm_rec = _register_record(
            mgr, llm_id, OP_CHAT, parent_run_id=agent_id
        )

        mgr.accumulate_usage_to_parent(
            llm_rec, input_tokens=42, output_tokens=None
        )

        agent_rec.span.set_attribute.assert_called_once_with(INPUT_TOKENS, 42)

    def test_handles_only_output_tokens(self):
        mgr, _ = _make_manager()
        agent_id = str(uuid4())
        llm_id = str(uuid4())

        agent_rec = _register_record(mgr, agent_id, OP_INVOKE_AGENT)
        llm_rec = _register_record(
            mgr, llm_id, OP_CHAT, parent_run_id=agent_id
        )

        mgr.accumulate_usage_to_parent(
            llm_rec, input_tokens=None, output_tokens=99
        )

        agent_rec.span.set_attribute.assert_called_once_with(OUTPUT_TOKENS, 99)


# ------------------------------------------------------------------
# accumulate_llm_usage_to_agent
# ------------------------------------------------------------------


class TestAccumulateLlmUsageToAgent:
    """Tests for _SpanManager.accumulate_llm_usage_to_agent."""

    def test_resolves_through_ignored_runs(self):
        mgr, _ = _make_manager()
        agent_id = str(uuid4())
        ignored_id = str(uuid4())

        agent_rec = _register_record(mgr, agent_id, OP_INVOKE_AGENT)
        mgr.ignore_run(ignored_id, parent_run_id=agent_id)

        mgr.accumulate_llm_usage_to_agent(
            parent_run_id=ignored_id, input_tokens=15, output_tokens=25
        )

        agent_rec.span.set_attribute.assert_any_call(INPUT_TOKENS, 15)
        agent_rec.span.set_attribute.assert_any_call(OUTPUT_TOKENS, 25)

    def test_noop_when_parent_run_id_is_none(self):
        mgr, _ = _make_manager()
        agent_id = str(uuid4())
        agent_rec = _register_record(mgr, agent_id, OP_INVOKE_AGENT)

        mgr.accumulate_llm_usage_to_agent(
            parent_run_id=None, input_tokens=10, output_tokens=20
        )

        agent_rec.span.set_attribute.assert_not_called()

    def test_noop_when_no_agent_in_chain(self):
        mgr, _ = _make_manager()
        chat_id = str(uuid4())

        chat_rec = _register_record(mgr, chat_id, OP_CHAT)

        mgr.accumulate_llm_usage_to_agent(
            parent_run_id=chat_id, input_tokens=10, output_tokens=20
        )

        chat_rec.span.set_attribute.assert_not_called()
