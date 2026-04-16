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

"""Unit tests for on_llm_new_token streaming timing metrics."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.outputs import LLMResult

from opentelemetry.instrumentation.langchain.callback_handler import (
    OpenTelemetryLangChainCallbackHandler,
)
from opentelemetry.util.genai.types import LLMInvocation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_handler():
    """Create a handler with mock telemetry and histogram instruments."""
    telemetry_handler = MagicMock()
    # stop_llm / fail_llm must return an LLMInvocation so on_llm_end works
    telemetry_handler.stop_llm.return_value = LLMInvocation()
    telemetry_handler.fail_llm.return_value = LLMInvocation()

    handler = OpenTelemetryLangChainCallbackHandler(
        telemetry_handler=telemetry_handler,
    )

    # Replace the real histograms with mocks so we can inspect calls.
    ttfc = MagicMock(name="ttfc_histogram")
    tpoc = MagicMock(name="tpoc_histogram")
    handler._ttfc_histogram = ttfc
    handler._tpoc_histogram = tpoc

    return handler, ttfc, tpoc


def _register_llm_invocation(
    handler, run_id, *, monotonic_start_s=100.0, **kwargs
):
    """Register an LLMInvocation in the handler's invocation manager."""
    invocation = LLMInvocation(
        monotonic_start_s=monotonic_start_s,
        operation_name=kwargs.get("operation_name", "chat"),
        request_model=kwargs.get("request_model", "gpt-4"),
        provider=kwargs.get("provider", "openai"),
        response_model_name=kwargs.get("response_model_name"),
        server_address=kwargs.get("server_address", "api.openai.com"),
        server_port=kwargs.get("server_port"),
    )
    # Wire a mock span so on_llm_end doesn't crash
    invocation.span = MagicMock()
    invocation.span.is_recording.return_value = False

    handler._invocation_manager.add_invocation_state(
        run_id=run_id,
        parent_run_id=None,
        invocation=invocation,
    )
    return invocation


def _empty_llm_result():
    return LLMResult(generations=[])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFirstTokenRecordsTTFC:
    """First token records time_to_first_chunk metric."""

    def test_first_token_records_ttfc(self):
        handler, ttfc, tpoc = _make_handler()
        run_id = uuid.uuid4()
        _register_llm_invocation(handler, run_id, monotonic_start_s=100.0)

        with patch(
            "opentelemetry.instrumentation.langchain.callback_handler.timeit"
        ) as mock_timeit:
            mock_timeit.default_timer.return_value = 100.5
            handler.on_llm_new_token("Hello", run_id=run_id)

        ttfc.record.assert_called_once()
        recorded_value = ttfc.record.call_args[0][0]
        assert recorded_value == pytest.approx(0.5)

        # time_per_output_chunk must NOT be recorded for the first token
        tpoc.record.assert_not_called()

    def test_ttfc_includes_metric_attributes(self):
        handler, ttfc, _ = _make_handler()
        run_id = uuid.uuid4()
        _register_llm_invocation(
            handler,
            run_id,
            monotonic_start_s=100.0,
            operation_name="chat",
            request_model="gpt-4",
            provider="openai",
            server_address="api.openai.com",
        )

        with patch(
            "opentelemetry.instrumentation.langchain.callback_handler.timeit"
        ) as mock_timeit:
            mock_timeit.default_timer.return_value = 100.3
            handler.on_llm_new_token("Hi", run_id=run_id)

        attrs = ttfc.record.call_args[1]["attributes"]
        assert attrs["gen_ai.operation.name"] == "chat"
        assert attrs["gen_ai.request.model"] == "gpt-4"
        assert attrs["gen_ai.provider.name"] == "openai"
        assert attrs["server.address"] == "api.openai.com"


class TestSubsequentTokenRecordsTPOC:
    """Subsequent tokens record time_per_output_chunk metric."""

    def test_second_token_records_tpoc(self):
        handler, ttfc, tpoc = _make_handler()
        run_id = uuid.uuid4()
        _register_llm_invocation(handler, run_id, monotonic_start_s=100.0)

        with patch(
            "opentelemetry.instrumentation.langchain.callback_handler.timeit"
        ) as mock_timeit:
            # First token
            mock_timeit.default_timer.return_value = 100.5
            handler.on_llm_new_token("Hello", run_id=run_id)
            # Second token
            mock_timeit.default_timer.return_value = 100.7
            handler.on_llm_new_token(" world", run_id=run_id)

        tpoc.record.assert_called_once()
        recorded_value = tpoc.record.call_args[0][0]
        assert recorded_value == pytest.approx(0.2)

    def test_third_token_also_records_tpoc(self):
        handler, ttfc, tpoc = _make_handler()
        run_id = uuid.uuid4()
        _register_llm_invocation(handler, run_id, monotonic_start_s=100.0)

        with patch(
            "opentelemetry.instrumentation.langchain.callback_handler.timeit"
        ) as mock_timeit:
            mock_timeit.default_timer.return_value = 100.5
            handler.on_llm_new_token("a", run_id=run_id)

            mock_timeit.default_timer.return_value = 100.7
            handler.on_llm_new_token("b", run_id=run_id)

            mock_timeit.default_timer.return_value = 101.0
            handler.on_llm_new_token("c", run_id=run_id)

        assert tpoc.record.call_count == 2
        # Second call (c-b): 101.0 - 100.7 = 0.3
        assert tpoc.record.call_args_list[1][0][0] == pytest.approx(0.3)


class TestNoOpWhenInvocationNotFound:
    """No-op when run_id is not in the invocation manager."""

    def test_unknown_run_id_does_nothing(self):
        handler, ttfc, tpoc = _make_handler()
        unknown_run_id = uuid.uuid4()

        # Should not raise
        handler.on_llm_new_token("token", run_id=unknown_run_id)

        ttfc.record.assert_not_called()
        tpoc.record.assert_not_called()


class TestNoOpWhenMonotonicStartIsNone:
    """No-op when invocation.monotonic_start_s is None."""

    def test_none_monotonic_start_does_nothing(self):
        handler, ttfc, tpoc = _make_handler()
        run_id = uuid.uuid4()

        # Register invocation with monotonic_start_s=None
        invocation = LLMInvocation(monotonic_start_s=None)
        invocation.span = MagicMock()
        handler._invocation_manager.add_invocation_state(
            run_id=run_id,
            parent_run_id=None,
            invocation=invocation,
        )

        handler.on_llm_new_token("token", run_id=run_id)

        ttfc.record.assert_not_called()
        tpoc.record.assert_not_called()
        # Streaming state should not be updated either
        assert str(run_id) not in handler._streaming_state


class TestStreamingStateCleanupOnLLMEnd:
    """Streaming state is cleaned up in on_llm_end."""

    def test_on_llm_end_removes_streaming_state(self):
        handler, ttfc, tpoc = _make_handler()
        run_id = uuid.uuid4()
        _register_llm_invocation(handler, run_id, monotonic_start_s=100.0)

        with patch(
            "opentelemetry.instrumentation.langchain.callback_handler.timeit"
        ) as mock_timeit:
            mock_timeit.default_timer.return_value = 100.5
            handler.on_llm_new_token("Hello", run_id=run_id)

        # Streaming state should exist now
        assert str(run_id) in handler._streaming_state

        handler.on_llm_end(_empty_llm_result(), run_id=run_id)

        assert str(run_id) not in handler._streaming_state


class TestStreamingStateCleanupOnLLMError:
    """Streaming state is cleaned up in on_llm_error."""

    def test_on_llm_error_removes_streaming_state(self):
        handler, ttfc, tpoc = _make_handler()
        run_id = uuid.uuid4()
        _register_llm_invocation(handler, run_id, monotonic_start_s=100.0)

        with patch(
            "opentelemetry.instrumentation.langchain.callback_handler.timeit"
        ) as mock_timeit:
            mock_timeit.default_timer.return_value = 100.5
            handler.on_llm_new_token("Hello", run_id=run_id)

        assert str(run_id) in handler._streaming_state

        handler.on_llm_error(RuntimeError("boom"), run_id=run_id)

        assert str(run_id) not in handler._streaming_state


class TestMultipleStreamingSequences:
    """Multiple streaming sequences (different run_ids) don't interfere."""

    def test_independent_run_ids(self):
        handler, ttfc, tpoc = _make_handler()
        run_a = uuid.uuid4()
        run_b = uuid.uuid4()
        _register_llm_invocation(handler, run_a, monotonic_start_s=100.0)
        _register_llm_invocation(handler, run_b, monotonic_start_s=200.0)

        with patch(
            "opentelemetry.instrumentation.langchain.callback_handler.timeit"
        ) as mock_timeit:
            # First token for run_a at t=100.5
            mock_timeit.default_timer.return_value = 100.5
            handler.on_llm_new_token("A1", run_id=run_a)

            # First token for run_b at t=200.3
            mock_timeit.default_timer.return_value = 200.3
            handler.on_llm_new_token("B1", run_id=run_b)

            # Second token for run_a at t=100.8
            mock_timeit.default_timer.return_value = 100.8
            handler.on_llm_new_token("A2", run_id=run_a)

            # Second token for run_b at t=200.6
            mock_timeit.default_timer.return_value = 200.6
            handler.on_llm_new_token("B2", run_id=run_b)

        # TTFC calls: run_a (0.5), run_b (0.3)
        assert ttfc.record.call_count == 2
        ttfc_values = [call[0][0] for call in ttfc.record.call_args_list]
        assert pytest.approx(0.5) in ttfc_values
        assert pytest.approx(0.3) in ttfc_values

        # TPOC calls: run_a (0.3), run_b (0.3)
        assert tpoc.record.call_count == 2
        tpoc_values = [call[0][0] for call in tpoc.record.call_args_list]
        assert pytest.approx(0.3) in tpoc_values

    def test_ending_one_stream_does_not_affect_another(self):
        handler, ttfc, tpoc = _make_handler()
        run_a = uuid.uuid4()
        run_b = uuid.uuid4()
        _register_llm_invocation(handler, run_a, monotonic_start_s=100.0)
        _register_llm_invocation(handler, run_b, monotonic_start_s=200.0)

        with patch(
            "opentelemetry.instrumentation.langchain.callback_handler.timeit"
        ) as mock_timeit:
            mock_timeit.default_timer.return_value = 100.5
            handler.on_llm_new_token("A1", run_id=run_a)

            mock_timeit.default_timer.return_value = 200.3
            handler.on_llm_new_token("B1", run_id=run_b)

        # End run_a
        handler.on_llm_end(_empty_llm_result(), run_id=run_a)
        assert str(run_a) not in handler._streaming_state
        # run_b should still be present
        assert str(run_b) in handler._streaming_state

        with patch(
            "opentelemetry.instrumentation.langchain.callback_handler.timeit"
        ) as mock_timeit:
            # run_b second token should still work
            mock_timeit.default_timer.return_value = 200.6
            handler.on_llm_new_token("B2", run_id=run_b)

        tpoc.record.assert_called_once()
        assert tpoc.record.call_args[0][0] == pytest.approx(0.3)
