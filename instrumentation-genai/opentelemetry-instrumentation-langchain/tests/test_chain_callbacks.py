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

"""Unit tests for on_chain_start / on_chain_end / on_chain_error callbacks."""

from __future__ import annotations

from unittest import mock
from uuid import uuid4

import pytest

from opentelemetry.instrumentation.langchain.callback_handler import (
    OpenTelemetryLangChainCallbackHandler,
)
from opentelemetry.instrumentation.langchain.operation_mapping import (
    OperationName,
)
from opentelemetry.instrumentation.langchain.span_manager import (
    SpanRecord,
    _SpanManager,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.trace.status import StatusCode

# ---------------------------------------------------------------------------
# Helpers & fixtures
# ---------------------------------------------------------------------------


def _make_mock_span():
    """Create a mock span with the interface used by the callback handler."""
    span = mock.MagicMock()
    span.is_recording.return_value = True
    span.set_attribute = mock.MagicMock()
    span.set_status = mock.MagicMock()
    return span


def _make_span_record(run_id, span=None, operation="invoke_agent"):
    return SpanRecord(
        run_id=str(run_id),
        span=span or _make_mock_span(),
        operation=operation,
    )


@pytest.fixture
def mock_span_manager():
    mgr = mock.MagicMock(spec=_SpanManager)
    # By default runs are not ignored.
    mgr.is_ignored.return_value = False
    mgr.resolve_parent_id.side_effect = lambda parent_run_id: (
        str(parent_run_id) if parent_run_id is not None else None
    )
    # start_span returns a SpanRecord by default.
    mgr.start_span.return_value = _make_span_record(uuid4())
    return mgr


@pytest.fixture
def handler(mock_span_manager):
    telemetry_handler = mock.MagicMock()
    return OpenTelemetryLangChainCallbackHandler(
        telemetry_handler=telemetry_handler,
        span_manager=mock_span_manager,
    )


# ---------------------------------------------------------------------------
# on_chain_start
# ---------------------------------------------------------------------------


class TestOnChainStartInvokeAgent:
    """on_chain_start creates invoke_agent spans for agent signals."""

    def test_creates_span_when_otel_agent_span_true(
        self, handler, mock_span_manager
    ):
        run_id = uuid4()
        handler.on_chain_start(
            serialized={},
            inputs={},
            run_id=run_id,
            metadata={"otel_agent_span": True},
        )
        mock_span_manager.start_span.assert_called_once()
        call_kwargs = mock_span_manager.start_span.call_args
        assert call_kwargs.kwargs["operation"] == OperationName.INVOKE_AGENT
        assert call_kwargs.kwargs["name"].startswith("invoke_agent")

    def test_creates_span_when_agent_name_in_metadata(
        self, handler, mock_span_manager
    ):
        run_id = uuid4()
        handler.on_chain_start(
            serialized={},
            inputs={},
            run_id=run_id,
            metadata={"agent_name": "planner"},
        )
        mock_span_manager.start_span.assert_called_once()
        call_kwargs = mock_span_manager.start_span.call_args
        assert call_kwargs.kwargs["operation"] == OperationName.INVOKE_AGENT
        assert "planner" in call_kwargs.kwargs["name"]


class TestOnChainStartInvokeWorkflow:
    """on_chain_start creates invoke_workflow spans for top-level graphs."""

    def test_creates_workflow_span_for_top_level_langgraph(
        self, handler, mock_span_manager
    ):
        run_id = uuid4()
        handler.on_chain_start(
            serialized={"name": "LangGraph"},
            inputs={},
            run_id=run_id,
            parent_run_id=None,
            metadata={},
        )
        mock_span_manager.start_span.assert_called_once()
        call_kwargs = mock_span_manager.start_span.call_args
        assert call_kwargs.kwargs["operation"] == OperationName.INVOKE_WORKFLOW


class TestOnChainStartSuppression:
    """on_chain_start suppresses (ignores) known noise chains."""

    def test_suppresses_start_node(self, handler, mock_span_manager):
        run_id = uuid4()
        handler.on_chain_start(
            serialized={},
            inputs={},
            run_id=run_id,
            metadata={"langgraph_node": "__start__"},
        )
        mock_span_manager.ignore_run.assert_called_once()
        mock_span_manager.start_span.assert_not_called()

    def test_suppresses_middleware_prefix(self, handler, mock_span_manager):
        run_id = uuid4()
        handler.on_chain_start(
            serialized={"name": "Middleware.auth"},
            inputs={},
            run_id=run_id,
            metadata={"langgraph_node": "Middleware.auth"},
            name="Middleware.auth",
        )
        mock_span_manager.ignore_run.assert_called_once()
        mock_span_manager.start_span.assert_not_called()

    def test_suppresses_unclassified_chain(self, handler, mock_span_manager):
        """A generic chain with no agent/workflow signals is suppressed."""
        run_id = uuid4()
        parent_id = uuid4()
        handler.on_chain_start(
            serialized={"name": "RunnableSequence"},
            inputs={},
            run_id=run_id,
            parent_run_id=parent_id,
            metadata={},
        )
        mock_span_manager.ignore_run.assert_called_once()
        mock_span_manager.start_span.assert_not_called()


class TestOnChainStartAttributes:
    """on_chain_start sets the correct span attributes."""

    def test_sets_agent_name_attribute(self, handler, mock_span_manager):
        run_id = uuid4()
        handler.on_chain_start(
            serialized={},
            inputs={},
            run_id=run_id,
            metadata={"otel_agent_span": True, "agent_name": "researcher"},
        )
        call_kwargs = mock_span_manager.start_span.call_args
        attrs = call_kwargs.kwargs["attributes"]
        assert attrs[GenAI.GEN_AI_AGENT_NAME] == "researcher"

    def test_sets_agent_id_attribute(self, handler, mock_span_manager):
        run_id = uuid4()
        handler.on_chain_start(
            serialized={},
            inputs={},
            run_id=run_id,
            metadata={
                "otel_agent_span": True,
                "agent_id": "agent-42",
            },
        )
        call_kwargs = mock_span_manager.start_span.call_args
        attrs = call_kwargs.kwargs["attributes"]
        assert attrs[GenAI.GEN_AI_AGENT_ID] == "agent-42"

    def test_sets_conversation_id_from_thread_id(
        self, handler, mock_span_manager
    ):
        run_id = uuid4()
        handler.on_chain_start(
            serialized={},
            inputs={},
            run_id=run_id,
            metadata={
                "otel_agent_span": True,
                "thread_id": "thread-abc",
            },
        )
        call_kwargs = mock_span_manager.start_span.call_args
        attrs = call_kwargs.kwargs["attributes"]
        assert attrs[GenAI.GEN_AI_CONVERSATION_ID] == "thread-abc"

    def test_sets_conversation_id_from_session_id(
        self, handler, mock_span_manager
    ):
        run_id = uuid4()
        handler.on_chain_start(
            serialized={},
            inputs={},
            run_id=run_id,
            metadata={
                "otel_agent_span": True,
                "session_id": "sess-123",
            },
        )
        call_kwargs = mock_span_manager.start_span.call_args
        attrs = call_kwargs.kwargs["attributes"]
        assert attrs[GenAI.GEN_AI_CONVERSATION_ID] == "sess-123"

    def test_sets_conversation_id_from_conversation_id(
        self, handler, mock_span_manager
    ):
        run_id = uuid4()
        handler.on_chain_start(
            serialized={},
            inputs={},
            run_id=run_id,
            metadata={
                "otel_agent_span": True,
                "conversation_id": "conv-789",
            },
        )
        call_kwargs = mock_span_manager.start_span.call_args
        attrs = call_kwargs.kwargs["attributes"]
        assert attrs[GenAI.GEN_AI_CONVERSATION_ID] == "conv-789"


class TestOnChainStartContentRecording:
    """on_chain_start records input messages when content policy allows."""

    def test_records_input_messages_when_policy_allows(
        self, handler, mock_span_manager
    ):
        run_id = uuid4()
        with mock.patch(
            "opentelemetry.instrumentation.langchain.callback_handler.get_content_policy"
        ) as mock_policy:
            policy = mock.MagicMock()
            policy.record_content = True
            policy.should_record_content_on_spans = True
            mock_policy.return_value = policy

            handler.on_chain_start(
                serialized={},
                inputs={"input": "Hello, agent!"},
                run_id=run_id,
                metadata={"otel_agent_span": True},
            )

        call_kwargs = mock_span_manager.start_span.call_args
        attrs = call_kwargs.kwargs["attributes"]
        assert GenAI.GEN_AI_INPUT_MESSAGES in attrs

    def test_does_not_record_input_when_policy_disallows(
        self, handler, mock_span_manager
    ):
        run_id = uuid4()
        with mock.patch(
            "opentelemetry.instrumentation.langchain.callback_handler.get_content_policy"
        ) as mock_policy:
            policy = mock.MagicMock()
            policy.record_content = False
            policy.should_record_content_on_spans = False
            mock_policy.return_value = policy

            handler.on_chain_start(
                serialized={},
                inputs={"input": "Hello, agent!"},
                run_id=run_id,
                metadata={"otel_agent_span": True},
            )

        call_kwargs = mock_span_manager.start_span.call_args
        attrs = call_kwargs.kwargs["attributes"]
        assert GenAI.GEN_AI_INPUT_MESSAGES not in attrs


class TestOnChainStartNoSpanManager:
    """on_chain_start is a no-op when span_manager is None."""

    def test_returns_early_when_no_span_manager(self):
        telemetry_handler = mock.MagicMock()
        handler = OpenTelemetryLangChainCallbackHandler(
            telemetry_handler=telemetry_handler,
            span_manager=None,
        )
        # Should not raise.
        handler.on_chain_start(
            serialized={},
            inputs={},
            run_id=uuid4(),
            metadata={"otel_agent_span": True},
        )


# ---------------------------------------------------------------------------
# on_chain_end
# ---------------------------------------------------------------------------


class TestOnChainEnd:
    """on_chain_end ends the span with OK status."""

    def test_ends_span_with_ok_status(self, handler, mock_span_manager):
        run_id = uuid4()
        record = _make_span_record(run_id)
        mock_span_manager.get_record.return_value = record

        handler.on_chain_end(
            outputs={"output": "done"},
            run_id=run_id,
        )

        mock_span_manager.end_span.assert_called_once_with(
            run_id, status=StatusCode.OK
        )

    def test_sets_output_messages_when_policy_allows(
        self, handler, mock_span_manager
    ):
        run_id = uuid4()
        span = _make_mock_span()
        record = _make_span_record(run_id, span=span)
        mock_span_manager.get_record.return_value = record

        with mock.patch(
            "opentelemetry.instrumentation.langchain.callback_handler.get_content_policy"
        ) as mock_policy:
            policy = mock.MagicMock()
            policy.record_content = True
            policy.should_record_content_on_spans = True
            mock_policy.return_value = policy

            handler.on_chain_end(
                outputs={"output": "Agent result"},
                run_id=run_id,
            )

        span.set_attribute.assert_any_call(
            GenAI.GEN_AI_OUTPUT_MESSAGES, mock.ANY
        )

    def test_skips_ignored_runs(self, handler, mock_span_manager):
        run_id = uuid4()
        mock_span_manager.is_ignored.return_value = True

        handler.on_chain_end(
            outputs={"output": "done"},
            run_id=run_id,
        )

        mock_span_manager.end_span.assert_not_called()
        mock_span_manager.clear_ignored_run.assert_called_once_with(run_id)

    def test_returns_early_when_no_record(self, handler, mock_span_manager):
        run_id = uuid4()
        mock_span_manager.get_record.return_value = None

        handler.on_chain_end(
            outputs={"output": "done"},
            run_id=run_id,
        )

        mock_span_manager.end_span.assert_not_called()

    def test_returns_early_when_no_span_manager(self):
        telemetry_handler = mock.MagicMock()
        handler = OpenTelemetryLangChainCallbackHandler(
            telemetry_handler=telemetry_handler,
            span_manager=None,
        )
        # Should not raise.
        handler.on_chain_end(
            outputs={"output": "done"},
            run_id=uuid4(),
        )


# ---------------------------------------------------------------------------
# on_chain_error
# ---------------------------------------------------------------------------


class TestOnChainError:
    """on_chain_error ends the span with error status."""

    def test_ends_span_with_error(self, handler, mock_span_manager):
        run_id = uuid4()

        error = RuntimeError("something went wrong")
        handler.on_chain_error(
            error=error,
            run_id=run_id,
        )

        mock_span_manager.end_span.assert_called_once_with(run_id, error=error)

    def test_skips_ignored_runs(self, handler, mock_span_manager):
        run_id = uuid4()
        mock_span_manager.is_ignored.return_value = True

        handler.on_chain_error(
            error=RuntimeError("boom"),
            run_id=run_id,
        )

        mock_span_manager.end_span.assert_not_called()
        mock_span_manager.clear_ignored_run.assert_called_once_with(run_id)

    def test_returns_early_when_no_span_manager(self):
        telemetry_handler = mock.MagicMock()
        handler = OpenTelemetryLangChainCallbackHandler(
            telemetry_handler=telemetry_handler,
            span_manager=None,
        )
        # Should not raise.
        handler.on_chain_error(
            error=RuntimeError("boom"),
            run_id=uuid4(),
        )
