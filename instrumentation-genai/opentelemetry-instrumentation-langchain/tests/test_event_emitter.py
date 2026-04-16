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

from unittest import mock

from opentelemetry.instrumentation.langchain.event_emitter import EventEmitter


def _make_policy(*, should_emit_events: bool, record_content: bool):
    policy = mock.MagicMock()
    policy.should_emit_events = should_emit_events
    policy.record_content = record_content
    return policy


def _make_emitter():
    emitter = EventEmitter()
    emitter._logger = mock.MagicMock()
    return emitter


def test_emits_tool_call_event_with_content(monkeypatch):
    policy = _make_policy(should_emit_events=True, record_content=True)
    monkeypatch.setattr(
        "opentelemetry.instrumentation.langchain.event_emitter.get_content_policy",
        lambda: policy,
    )
    emitter = _make_emitter()

    emitter.emit_tool_call_event(
        mock.MagicMock(),
        "calculator",
        '{"x": 1}',
        "call_123",
    )

    record = emitter._logger.emit.call_args.args[0]
    assert record.event_name == "gen_ai.tool.call"
    assert record.body == {
        "name": "calculator",
        "id": "call_123",
        "arguments": '{"x": 1}',
    }


def test_redacts_tool_result_when_content_recording_disabled(monkeypatch):
    policy = _make_policy(should_emit_events=True, record_content=False)
    monkeypatch.setattr(
        "opentelemetry.instrumentation.langchain.event_emitter.get_content_policy",
        lambda: policy,
    )
    emitter = _make_emitter()

    emitter.emit_tool_result_event(
        mock.MagicMock(),
        "calculator",
        '{"result": 2}',
    )

    record = emitter._logger.emit.call_args.args[0]
    assert record.event_name == "gen_ai.tool.result"
    assert record.body == {
        "name": "calculator",
        "result": "[redacted]",
    }


def test_skips_agent_event_when_disabled(monkeypatch):
    policy = _make_policy(should_emit_events=False, record_content=True)
    monkeypatch.setattr(
        "opentelemetry.instrumentation.langchain.event_emitter.get_content_policy",
        lambda: policy,
    )
    emitter = _make_emitter()

    emitter.emit_agent_start_event(
        mock.MagicMock(),
        "planner",
        '[{"content": "hi"}]',
    )

    emitter._logger.emit.assert_not_called()


def test_emits_retriever_result_event(monkeypatch):
    policy = _make_policy(should_emit_events=True, record_content=True)
    monkeypatch.setattr(
        "opentelemetry.instrumentation.langchain.event_emitter.get_content_policy",
        lambda: policy,
    )
    emitter = _make_emitter()

    emitter.emit_retriever_result_event(
        mock.MagicMock(),
        "vector_store",
        '[{"metadata": {"source": "a.txt"}}]',
    )

    record = emitter._logger.emit.call_args.args[0]
    assert record.event_name == "gen_ai.retriever.result"
    assert record.body == {
        "name": "vector_store",
        "documents": '[{"metadata": {"source": "a.txt"}}]',
    }
