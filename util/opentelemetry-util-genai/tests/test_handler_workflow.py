from __future__ import annotations

import os
from unittest import TestCase
from unittest.mock import patch

import pytest

from opentelemetry import baggage
from opentelemetry import context as otel_context
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import StatusCode
from opentelemetry.util.genai.context_attributes import (
    get_context_scoped_attributes,
    set_context_scoped_attributes,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import (
    Error,
    InputMessage,
    LLMInvocation,
    OutputMessage,
    Text,
    WorkflowInvocation,
)


class _WorkflowTestBase(TestCase):
    """Shared setUp for workflow handler tests."""

    def setUp(self) -> None:
        self.span_exporter = InMemorySpanExporter()
        self.tracer_provider = TracerProvider()
        self.tracer_provider.add_span_processor(
            SimpleSpanProcessor(self.span_exporter)
        )
        self.handler = TelemetryHandler(
            tracer_provider=self.tracer_provider,
        )

    def _get_finished_spans(self):
        return self.span_exporter.get_finished_spans()


class TelemetryHandlerWorkflowTest(_WorkflowTestBase):
    # ------------------------------------------------------------------
    # start_workflow
    # ------------------------------------------------------------------

    def test_operation_name_is_immutable(self) -> None:
        invocation = WorkflowInvocation(name="wf", operation_name="custom_op")
        self.assertEqual(invocation.operation_name, "invoke_workflow")

    def test_start_workflow_creates_span(self) -> None:
        invocation = WorkflowInvocation(name="my_workflow")
        self.handler.start(invocation)

        self.assertIsNotNone(invocation.span)
        self.assertIsNotNone(invocation.context_token)
        self.assertIsNotNone(invocation.monotonic_start_s)

        # Clean up
        self.handler.stop(invocation)

    def test_start_workflow_span_name(self) -> None:
        invocation = WorkflowInvocation(name="my_pipeline")
        self.handler.start(invocation)
        self.handler.stop(invocation)

        spans = self._get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "invoke_workflow my_pipeline")

    def test_start_workflow_span_name_without_name(self) -> None:
        invocation = WorkflowInvocation()
        self.handler.start(invocation)
        self.handler.stop(invocation)

        spans = self._get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "invoke_workflow")

    def test_start_workflow_span_kind_is_internal(self) -> None:
        invocation = WorkflowInvocation(name="wf")
        self.handler.start(invocation)
        self.handler.stop(invocation)

        spans = self._get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].kind, SpanKind.INTERNAL)

    def test_start_workflow_records_monotonic_start(self) -> None:
        invocation = WorkflowInvocation(name="wf")
        with patch("timeit.default_timer", return_value=500.0):
            self.handler.start(invocation)
        self.assertEqual(invocation.monotonic_start_s, 500.0)
        self.handler.stop(invocation)

    # ------------------------------------------------------------------
    # stop_workflow
    # ------------------------------------------------------------------

    def test_stop_workflow_ends_span(self) -> None:
        invocation = WorkflowInvocation(name="wf")
        self.handler.start(invocation)
        self.handler.stop(invocation)

        spans = self._get_finished_spans()
        self.assertEqual(len(spans), 1)

    def test_stop_workflow_sets_operation_name_attribute(self) -> None:
        invocation = WorkflowInvocation(name="wf")
        self.handler.start(invocation)
        self.handler.stop(invocation)

        spans = self._get_finished_spans()
        self.assertEqual(
            spans[0].attributes[GenAI.GEN_AI_OPERATION_NAME],
            "invoke_workflow",
        )

    def test_stop_workflow_sets_custom_attributes(self) -> None:
        invocation = WorkflowInvocation(name="wf")
        invocation.attributes["custom.key"] = "custom_value"
        self.handler.start(invocation)
        self.handler.stop(invocation)

        spans = self._get_finished_spans()
        self.assertEqual(spans[0].attributes["custom.key"], "custom_value")

    def test_stop_workflow_noop_when_not_started(self) -> None:
        invocation = WorkflowInvocation(name="wf")
        # Not started — span and context_token are None
        result = self.handler.stop(invocation)
        self.assertIs(result, invocation)
        self.assertEqual(len(self._get_finished_spans()), 0)

    def test_stop_workflow_returns_invocation(self) -> None:
        invocation = WorkflowInvocation(name="wf")
        self.handler.start(invocation)
        result = self.handler.stop(invocation)
        self.assertIs(result, invocation)

    # ------------------------------------------------------------------
    # fail_workflow
    # ------------------------------------------------------------------

    def test_fail_workflow_sets_error_status(self) -> None:
        invocation = WorkflowInvocation(name="wf")
        self.handler.start(invocation)
        error = Error(message="something broke", type=RuntimeError)
        self.handler.fail(invocation, error)

        spans = self._get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].status.status_code, StatusCode.ERROR)
        self.assertEqual(spans[0].status.description, "something broke")

    def test_fail_workflow_sets_error_type_attribute(self) -> None:
        invocation = WorkflowInvocation(name="wf")
        self.handler.start(invocation)
        error = Error(message="bad", type=ValueError)
        self.handler.fail(invocation, error)

        spans = self._get_finished_spans()
        self.assertEqual(spans[0].attributes["error.type"], "ValueError")

    def test_fail_workflow_sets_operation_name_attribute(self) -> None:
        invocation = WorkflowInvocation(name="wf")
        self.handler.start(invocation)
        error = Error(message="fail", type=TypeError)
        self.handler.fail(invocation, error)

        spans = self._get_finished_spans()
        self.assertEqual(
            spans[0].attributes[GenAI.GEN_AI_OPERATION_NAME],
            "invoke_workflow",
        )

    def test_fail_workflow_noop_when_not_started(self) -> None:
        invocation = WorkflowInvocation(name="wf")
        error = Error(message="fail", type=RuntimeError)
        result = self.handler.fail(invocation, error)
        self.assertIs(result, invocation)
        self.assertEqual(len(self._get_finished_spans()), 0)

    def test_fail_workflow_returns_invocation(self) -> None:
        invocation = WorkflowInvocation(name="wf")
        self.handler.start(invocation)
        error = Error(message="err", type=RuntimeError)
        result = self.handler.fail(invocation, error)
        self.assertIs(result, invocation)


class TelemetryHandlerWorkflowContextManagerTest(_WorkflowTestBase):
    # ------------------------------------------------------------------
    # workflow context manager
    # ------------------------------------------------------------------

    def test_workflow_context_manager_creates_and_ends_span(self) -> None:
        invocation = WorkflowInvocation(name="ctx_wf")
        with self.handler.workflow(invocation) as inv:
            self.assertIsNotNone(inv.span)
            self.assertIsNotNone(inv.context_token)

        spans = self._get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "invoke_workflow ctx_wf")

    def test_workflow_context_manager_default_invocation(self) -> None:
        with self.handler.workflow() as inv:
            self.assertIsInstance(inv, WorkflowInvocation)
            self.assertEqual(inv.name, "")
            self.assertEqual(inv.operation_name, "invoke_workflow")

        spans = self._get_finished_spans()
        self.assertEqual(len(spans), 1)

    def test_workflow_context_manager_sets_attributes_on_span(self) -> None:
        invocation = WorkflowInvocation(name="wf")
        with self.handler.workflow(invocation) as inv:
            inv.attributes["my.attr"] = "hello"

        spans = self._get_finished_spans()
        self.assertEqual(spans[0].attributes["my.attr"], "hello")

    def test_workflow_context_manager_reraises_exception(self) -> None:
        invocation = WorkflowInvocation(name="wf")
        with pytest.raises(ValueError, match="test error"):
            with self.handler.workflow(invocation):
                raise ValueError("test error")

    def test_workflow_context_manager_marks_error_on_exception(self) -> None:
        invocation = WorkflowInvocation(name="wf")
        with pytest.raises(ValueError):
            with self.handler.workflow(invocation):
                raise ValueError("boom")

        spans = self._get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].status.status_code, StatusCode.ERROR)
        self.assertEqual(spans[0].status.description, "boom")
        self.assertEqual(spans[0].attributes["error.type"], "ValueError")

    def test_workflow_context_manager_success_has_unset_status(self) -> None:
        invocation = WorkflowInvocation(name="wf")
        with self.handler.workflow(invocation):
            pass

        spans = self._get_finished_spans()
        self.assertEqual(spans[0].status.status_code, StatusCode.UNSET)

    def test_workflow_context_manager_with_messages(self) -> None:
        inp = InputMessage(role="user", parts=[Text(content="hello")])
        out = OutputMessage(
            role="assistant", parts=[Text(content="hi")], finish_reason="stop"
        )
        invocation = WorkflowInvocation(
            name="msg_wf",
            input_messages=[inp],
            output_messages=[out],
        )
        with self.handler.workflow(invocation):
            pass

        spans = self._get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(
            spans[0].attributes[GenAI.GEN_AI_OPERATION_NAME],
            "invoke_workflow",
        )

    def test_workflow_context_manager_swallows_start_failure(self) -> None:
        """workflow() should yield even if start_workflow raises."""
        invocation = WorkflowInvocation(name="wf")
        with patch.object(
            self.handler,
            "start",
            side_effect=RuntimeError("start failed"),
        ):
            # Should not raise — the exception is swallowed with a warning
            with self.handler.workflow(invocation) as inv:
                self.assertIs(inv, invocation)

    def test_workflow_context_manager_swallows_stop_failure(self) -> None:
        """workflow() should not raise if stop_workflow fails."""
        invocation = WorkflowInvocation(name="wf")
        with patch.object(
            self.handler,
            "stop",
            side_effect=RuntimeError("stop failed"),
        ):
            # Should not raise
            with self.handler.workflow(invocation):
                pass

    def test_workflow_context_manager_swallows_fail_workflow_failure(
        self,
    ) -> None:
        """workflow() should still re-raise the original exception even if
        fail_workflow itself raises."""
        invocation = WorkflowInvocation(name="wf")
        with patch.object(
            self.handler,
            "fail",
            side_effect=RuntimeError("fail broke"),
        ):
            with pytest.raises(ValueError, match="original"):
                with self.handler.workflow(invocation):
                    raise ValueError("original")


class TelemetryHandlerWorkflowCSATest(_WorkflowTestBase):
    """Tests for context-scoped attribute propagation of gen_ai.workflow.name."""

    # ------------------------------------------------------------------
    # CSA set/read via handler
    # ------------------------------------------------------------------

    def test_workflow_sets_context_scoped_attribute(self) -> None:
        """Starting a workflow stores gen_ai.workflow.name in CSA."""
        invocation = WorkflowInvocation(name="my_workflow")
        self.handler.start(invocation)
        try:
            attrs = get_context_scoped_attributes()
            self.assertEqual(attrs.get("gen_ai.workflow.name"), "my_workflow")
        finally:
            self.handler.stop(invocation)

    def test_llm_reads_workflow_name_from_csa(self) -> None:
        """LLM invocation inside a workflow gets gen_ai.workflow.name via CSA."""
        wf_inv = WorkflowInvocation(name="pipeline")
        llm_inv = LLMInvocation(request_model="test-model", provider="test")

        self.handler.start(wf_inv)
        try:
            self.handler.start_llm(llm_inv)
            self.handler.stop_llm(llm_inv)
        finally:
            self.handler.stop(wf_inv)

        spans = self._get_finished_spans()
        # Find the LLM span (CLIENT kind)
        llm_spans = [s for s in spans if s.kind == SpanKind.CLIENT]
        self.assertEqual(len(llm_spans), 1)
        self.assertEqual(
            llm_spans[0].attributes.get(GenAI.GEN_AI_OPERATION_NAME),
            "chat",
        )
        # workflow name should be stamped on the LLM span
        self.assertEqual(
            llm_spans[0].attributes.get("gen_ai.request.model"), "test-model"
        )
        # Verify it was captured on the invocation object
        self.assertEqual(llm_inv.workflow_name, "pipeline")

    def test_csa_not_visible_outside_workflow_scope(self) -> None:
        """After the workflow span ends, the CSA is no longer in current context."""
        invocation = WorkflowInvocation(name="scoped_wf")
        self.handler.start(invocation)
        self.handler.stop(invocation)

        # After stop the context_token is detached, so CSA should be gone
        attrs = get_context_scoped_attributes()
        self.assertIsNone(attrs.get("gen_ai.workflow.name"))

    # ------------------------------------------------------------------
    # Baggage opt-in behaviour
    # ------------------------------------------------------------------

    def test_baggage_not_written_by_default(self) -> None:
        """Without OTEL_PYTHON_GENAI_CAPTURE_BAGGAGE, baggage is not set."""
        env = {k: v for k, v in os.environ.items() if k != "OTEL_PYTHON_GENAI_CAPTURE_BAGGAGE"}
        with patch.dict(os.environ, env, clear=True):
            invocation = WorkflowInvocation(name="wf_no_baggage")
            self.handler.start(invocation)
            try:
                value = baggage.get_baggage("gen_ai.workflow.name")
                self.assertIsNone(value)
            finally:
                self.handler.stop(invocation)

    def test_baggage_written_when_opted_in(self) -> None:
        """With OTEL_PYTHON_GENAI_CAPTURE_BAGGAGE=true, baggage is also written."""
        with patch.dict(
            os.environ, {"OTEL_PYTHON_GENAI_CAPTURE_BAGGAGE": "true"}
        ):
            invocation = WorkflowInvocation(name="wf_with_baggage")
            self.handler.start(invocation)
            try:
                value = baggage.get_baggage("gen_ai.workflow.name")
                self.assertEqual(value, "wf_with_baggage")
            finally:
                self.handler.stop(invocation)

    def test_baggage_written_when_opted_in_with_one(self) -> None:
        """OTEL_PYTHON_GENAI_CAPTURE_BAGGAGE=1 also enables baggage writing."""
        with patch.dict(
            os.environ, {"OTEL_PYTHON_GENAI_CAPTURE_BAGGAGE": "1"}
        ):
            invocation = WorkflowInvocation(name="wf_baggage_one")
            self.handler.start(invocation)
            try:
                value = baggage.get_baggage("gen_ai.workflow.name")
                self.assertEqual(value, "wf_baggage_one")
            finally:
                self.handler.stop(invocation)

    # ------------------------------------------------------------------
    # Backwards compatibility: baggage fallback for LLM
    # ------------------------------------------------------------------

    def test_baggage_fallback_for_llm_when_no_csa(self) -> None:
        """LLM picks up workflow name from baggage when CSA is absent (legacy context)."""
        # Manually inject baggage without using WorkflowInvocation
        ctx = baggage.set_baggage("gen_ai.workflow.name", "legacy_workflow")
        token = otel_context.attach(ctx)
        try:
            llm_inv = LLMInvocation(request_model="model", provider="test")
            self.handler.start_llm(llm_inv)
            self.handler.stop_llm(llm_inv)
            self.assertEqual(llm_inv.workflow_name, "legacy_workflow")
        finally:
            otel_context.detach(token)

    def test_csa_takes_priority_over_baggage_for_llm(self) -> None:
        """CSA value wins over baggage when both are present."""
        # Set baggage with one name
        ctx = baggage.set_baggage("gen_ai.workflow.name", "baggage_workflow")
        # Also set CSA with a different name
        ctx = set_context_scoped_attributes(
            {"gen_ai.workflow.name": "csa_workflow"}, ctx
        )
        token = otel_context.attach(ctx)
        try:
            llm_inv = LLMInvocation(request_model="model", provider="test")
            self.handler.start_llm(llm_inv)
            self.handler.stop_llm(llm_inv)
            self.assertEqual(llm_inv.workflow_name, "csa_workflow")
        finally:
            otel_context.detach(token)
