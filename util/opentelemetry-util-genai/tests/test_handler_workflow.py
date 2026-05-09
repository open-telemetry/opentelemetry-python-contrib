# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

import pytest

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.sdk.trace.sampling import Decision, SamplingResult
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.trace import INVALID_SPAN, SpanKind
from opentelemetry.trace.status import StatusCode
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.invocation import WorkflowInvocation
from opentelemetry.util.genai.types import (
    Error,
    InputMessage,
    OutputMessage,
    Text,
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

    def test_start_workflow_creates_span(self) -> None:
        invocation = self.handler.start_workflow(name="my_workflow")
        self.assertIsNot(invocation.span, INVALID_SPAN)
        invocation.stop()

    def test_start_workflow_span_name(self) -> None:
        invocation = self.handler.start_workflow(name="my_pipeline")
        invocation.stop()

        spans = self._get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "invoke_workflow my_pipeline")

    def test_start_workflow_span_name_without_name(self) -> None:
        invocation = self.handler.start_workflow(name=None)
        invocation.stop()

        spans = self._get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "invoke_workflow")

    def test_start_workflow_span_kind_is_internal(self) -> None:
        invocation = self.handler.start_workflow(name="wf")
        invocation.stop()

        spans = self._get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].kind, SpanKind.INTERNAL)

    def test_start_workflow_records_monotonic_start(self) -> None:
        with patch("timeit.default_timer", return_value=500.0):
            invocation = self.handler.start_workflow(name="wf")
        self.assertEqual(invocation._monotonic_start_s, 500.0)
        invocation.stop()

    # ------------------------------------------------------------------
    # stop_workflow
    # ------------------------------------------------------------------

    def test_stop_workflow_ends_span(self) -> None:
        invocation = self.handler.start_workflow(name="wf")
        invocation.stop()

        spans = self._get_finished_spans()
        self.assertEqual(len(spans), 1)

    def test_stop_workflow_sets_operation_name_attribute(self) -> None:
        invocation = self.handler.start_workflow(name="wf")
        invocation.stop()

        spans = self._get_finished_spans()
        self.assertEqual(
            spans[0].attributes[GenAI.GEN_AI_OPERATION_NAME],
            "invoke_workflow",
        )

    def test_stop_workflow_sets_custom_attributes(self) -> None:
        invocation = self.handler.start_workflow(name="wf")
        invocation.attributes["custom.key"] = "custom_value"
        invocation.stop()

        spans = self._get_finished_spans()
        self.assertEqual(spans[0].attributes["custom.key"], "custom_value")

    def test_stop_workflow_returns_invocation(self) -> None:
        invocation = self.handler.start_workflow(name="wf")
        invocation.stop()
        spans = self._get_finished_spans()
        self.assertEqual(len(spans), 1)

    # ------------------------------------------------------------------
    # fail_workflow
    # ------------------------------------------------------------------

    def test_fail_workflow_sets_error_status(self) -> None:
        invocation = self.handler.start_workflow(name="wf")
        error = Error(message="something broke", type=RuntimeError)
        invocation.fail(error)

        spans = self._get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].status.status_code, StatusCode.ERROR)
        self.assertEqual(spans[0].status.description, "something broke")

    def test_fail_workflow_sets_error_type_attribute(self) -> None:
        invocation = self.handler.start_workflow(name="wf")
        error = Error(message="bad", type=ValueError)
        invocation.fail(error)

        spans = self._get_finished_spans()
        self.assertEqual(spans[0].attributes["error.type"], "ValueError")

    def test_fail_workflow_sets_operation_name_attribute(self) -> None:
        invocation = self.handler.start_workflow(name="wf")
        error = Error(message="fail", type=TypeError)
        invocation.fail(error)

        spans = self._get_finished_spans()
        self.assertEqual(
            spans[0].attributes[GenAI.GEN_AI_OPERATION_NAME],
            "invoke_workflow",
        )

    def test_fail_workflow_ends_span(self) -> None:
        invocation = self.handler.start_workflow(name="wf")
        invocation.fail(Error(message="err", type=RuntimeError))
        spans = self._get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].status.status_code, StatusCode.ERROR)


class TelemetryHandlerWorkflowContextManagerTest(_WorkflowTestBase):
    # ------------------------------------------------------------------
    # workflow context manager
    # ------------------------------------------------------------------

    def test_workflow_context_manager_creates_and_ends_span(self) -> None:
        with self.handler.workflow(name="ctx_wf") as inv:
            self.assertIsNot(inv.span, INVALID_SPAN)

        spans = self._get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "invoke_workflow ctx_wf")

    def test_workflow_context_manager_default_invocation(self) -> None:
        with self.handler.workflow() as inv:
            self.assertIsInstance(inv, WorkflowInvocation)
            self.assertIsNone(inv.name)
            self.assertEqual(inv._operation_name, "invoke_workflow")


class TelemetryHandlerWorkflowSamplingTest(_WorkflowTestBase):
    def test_start_workflow_passes_sampling_attributes_at_span_creation(
        self,
    ) -> None:
        """Verify that sampling-relevant attributes are available at start_span() time for workflows."""
        captured_attributes = {}

        class AttributeCapturingSampler:  # pylint: disable=no-self-use
            def should_sample(
                self,
                parent_context,
                trace_id,
                name,
                kind=None,
                attributes=None,
                links=None,
            ):
                captured_attributes.update(attributes or {})
                return SamplingResult(Decision.RECORD_AND_SAMPLE, attributes)

            def get_description(self):
                return "AttributeCapturingSampler"

        sampler_provider = TracerProvider(sampler=AttributeCapturingSampler())
        sampler_provider.add_span_processor(
            SimpleSpanProcessor(self.span_exporter)
        )
        handler = TelemetryHandler(tracer_provider=sampler_provider)

        invocation = handler.start_workflow(name="my-workflow")
        invocation.stop()

        self.assertEqual(
            captured_attributes[GenAI.GEN_AI_OPERATION_NAME], "invoke_workflow"
        )

        spans = self._get_finished_spans()
        self.assertEqual(len(spans), 1)

    def test_workflow_context_manager_sets_attributes_on_span(self) -> None:
        with self.handler.workflow("wf") as inv:
            inv.attributes["my.attr"] = "hello"

        spans = self._get_finished_spans()
        self.assertEqual(spans[0].attributes["my.attr"], "hello")

    def test_workflow_context_manager_reraises_exception(self) -> None:
        with pytest.raises(ValueError, match="test error"):
            with self.handler.workflow("wf"):
                raise ValueError("test error")

    def test_workflow_context_manager_marks_error_on_exception(self) -> None:
        with pytest.raises(ValueError):
            with self.handler.workflow("wf"):
                raise ValueError("boom")

        spans = self._get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].status.status_code, StatusCode.ERROR)
        self.assertEqual(spans[0].status.description, "boom")
        self.assertEqual(spans[0].attributes["error.type"], "ValueError")

    def test_workflow_context_manager_success_has_unset_status(self) -> None:
        with self.handler.workflow("wf"):
            pass

        spans = self._get_finished_spans()
        self.assertEqual(spans[0].status.status_code, StatusCode.UNSET)

    def test_workflow_context_manager_with_messages(self) -> None:
        inp = InputMessage(role="user", parts=[Text(content="hello")])
        out = OutputMessage(
            role="assistant", parts=[Text(content="hi")], finish_reason="stop"
        )
        with self.handler.workflow("msg_wf") as inv:
            inv.input_messages = [inp]
            inv.output_messages = [out]

        spans = self._get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(
            spans[0].attributes[GenAI.GEN_AI_OPERATION_NAME],
            "invoke_workflow",
        )
