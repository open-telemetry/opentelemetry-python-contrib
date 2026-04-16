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

import json
from unittest.mock import MagicMock
from uuid import uuid4

from langchain_core.agents import AgentAction, AgentFinish

from opentelemetry.instrumentation.langchain.callback_handler import (
    OpenTelemetryLangChainCallbackHandler,
)
from opentelemetry.instrumentation.langchain.span_manager import SpanRecord
from opentelemetry.trace.status import StatusCode

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_handler(span_manager=None):
    telemetry_handler = MagicMock()
    telemetry_handler.meter = MagicMock()
    return OpenTelemetryLangChainCallbackHandler(
        telemetry_handler=telemetry_handler,
        span_manager=span_manager,
    )


def _make_record(run_id=None):
    record = MagicMock(spec=SpanRecord)
    record.run_id = str(run_id or uuid4())
    record.stash = {}
    record.span = MagicMock()
    return record


# ------------------------------------------------------------------
# on_agent_action
# ------------------------------------------------------------------


class TestOnAgentAction:
    def test_stashes_action_on_parent_pending_actions(self):
        run_id = uuid4()
        parent_run_id = uuid4()
        parent_key = str(parent_run_id)
        record = _make_record(parent_run_id)

        span_manager = MagicMock()
        span_manager.resolve_parent_id.return_value = parent_key
        span_manager.get_record.return_value = record

        handler = _make_handler(span_manager)

        action = AgentAction(
            tool="search", tool_input={"query": "weather"}, log="Searching…"
        )
        handler.on_agent_action(
            action, run_id=run_id, parent_run_id=parent_run_id
        )

        span_manager.resolve_parent_id.assert_called_once_with(parent_run_id)
        span_manager.get_record.assert_called_once_with(parent_key)

        pending = record.stash["pending_actions"]
        assert str(run_id) in pending
        entry = pending[str(run_id)]
        assert entry["tool"] == "search"
        assert entry["tool_input"] == {"query": "weather"}
        assert entry["log"] == "Searching…"

    def test_noop_when_span_manager_is_none(self):
        handler = _make_handler(span_manager=None)
        action = AgentAction(tool="t", tool_input="i", log="l")
        # Should not raise
        handler.on_agent_action(action, run_id=uuid4(), parent_run_id=uuid4())

    def test_noop_when_parent_run_id_is_none(self):
        span_manager = MagicMock()
        handler = _make_handler(span_manager)

        action = AgentAction(tool="t", tool_input="i", log="l")
        handler.on_agent_action(action, run_id=uuid4(), parent_run_id=None)

        span_manager.resolve_parent_id.assert_not_called()
        span_manager.get_record.assert_not_called()

    def test_noop_when_parent_record_not_found(self):
        run_id = uuid4()
        parent_run_id = uuid4()
        parent_key = str(parent_run_id)

        span_manager = MagicMock()
        span_manager.resolve_parent_id.return_value = parent_key
        span_manager.get_record.return_value = None

        handler = _make_handler(span_manager)

        action = AgentAction(tool="t", tool_input="i", log="l")
        handler.on_agent_action(
            action, run_id=run_id, parent_run_id=parent_run_id
        )

        # resolve_parent_id was called, but nothing was stashed
        span_manager.resolve_parent_id.assert_called_once_with(parent_run_id)
        span_manager.get_record.assert_called_once_with(parent_key)


# ------------------------------------------------------------------
# on_agent_finish
# ------------------------------------------------------------------


class TestOnAgentFinish:
    def test_sets_output_messages_and_ok_status(self):
        run_id = uuid4()
        record = _make_record(run_id)

        span_manager = MagicMock()
        span_manager.get_record.return_value = record

        handler = _make_handler(span_manager)

        return_values = {"output": "The weather is sunny."}
        finish = AgentFinish(return_values=return_values, log="done")
        handler.on_agent_finish(finish, run_id=run_id)

        record.span.set_attribute.assert_called_once()
        attr_name, attr_value = record.span.set_attribute.call_args[0]
        assert "output" in attr_name.lower() or "message" in attr_name.lower()
        assert json.loads(attr_value) == return_values

        record.span.set_status.assert_called_once()
        status_arg = record.span.set_status.call_args[0][0]
        assert status_arg.status_code is StatusCode.OK
        span_manager.end_span.assert_called_once_with(run_id)

    def test_ok_status_when_no_return_values(self):
        run_id = uuid4()
        record = _make_record(run_id)

        span_manager = MagicMock()
        span_manager.get_record.return_value = record

        handler = _make_handler(span_manager)

        finish = AgentFinish(return_values={}, log="")
        handler.on_agent_finish(finish, run_id=run_id)

        record.span.set_attribute.assert_not_called()
        record.span.set_status.assert_called_once()
        status_arg = record.span.set_status.call_args[0][0]
        assert status_arg.status_code is StatusCode.OK
        span_manager.end_span.assert_called_once_with(run_id)

    def test_noop_when_span_manager_is_none(self):
        handler = _make_handler(span_manager=None)
        finish = AgentFinish(return_values={"output": "x"}, log="")
        # Should not raise
        handler.on_agent_finish(finish, run_id=uuid4())

    def test_noop_when_record_not_found(self):
        run_id = uuid4()
        span_manager = MagicMock()
        span_manager.get_record.return_value = None

        handler = _make_handler(span_manager)

        finish = AgentFinish(return_values={"output": "x"}, log="")
        handler.on_agent_finish(finish, run_id=run_id)

        span_manager.get_record.assert_called_once_with(str(run_id))
        span_manager.end_span.assert_not_called()
