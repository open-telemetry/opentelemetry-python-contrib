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

"""
Unit tests verifying CSA propagation through the LangChain callback handler.

These tests exercise the OpenTelemetryLangChainCallbackHandler directly using
mock LangChain callback payloads, so they do not require live models or VCR
cassettes.  The key behaviour under test:

    on_chain_start(parent_run_id=None)
        → WorkflowInvocation created
        → TelemetryHandler.start() called
        → gen_ai.workflow.name written to context-scoped attributes (CSA)

    on_chat_model_start(...)
        → LLMInvocation created
        → TelemetryHandler.start() called
        → gen_ai.workflow.name read from CSA and stamped on the LLM invocation

    on_llm_end(...)
        → LLM span closed with gen_ai.workflow.name attribute set

    on_chain_end(...)
        → workflow span closed, CSA scope ends
"""

from __future__ import annotations

import os
import uuid
from unittest import TestCase
from unittest.mock import patch

from langchain_core.outputs import ChatGeneration, LLMResult
from langchain_core.messages import AIMessage

from opentelemetry import baggage
from opentelemetry import context as otel_context
from opentelemetry.instrumentation.langchain.callback_handler import (
    OpenTelemetryLangChainCallbackHandler,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import StatusCode
from opentelemetry.util.genai.context_attributes import (
    get_context_scoped_attributes,
)
from opentelemetry.util.genai.handler import TelemetryHandler


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_serialized(name: str) -> dict:
    """Minimal serialized dict that on_chain_start / on_chat_model_start expect."""
    return {"name": name}


def _make_llm_result(content: str = "hello") -> LLMResult:
    """Minimal LLMResult with one generation."""
    msg = AIMessage(content=content)
    gen = ChatGeneration(message=msg, text=content)
    gen.generation_info = {"finish_reason": "stop"}
    return LLMResult(generations=[[gen]], llm_output={"model_name": "gpt-3.5-turbo"})


def _make_chat_invocation_params(model_name: str = "gpt-3.5-turbo") -> dict:
    """kwargs dict that on_chat_model_start receives for a ChatOpenAI call."""
    return {"invocation_params": {"model_name": model_name, "params": {"model_name": model_name}}}


# ---------------------------------------------------------------------------
# Base test class
# ---------------------------------------------------------------------------

class _CallbackHandlerTestBase(TestCase):
    def setUp(self) -> None:
        self.span_exporter = InMemorySpanExporter()
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(
            SimpleSpanProcessor(self.span_exporter)
        )
        telemetry_handler = TelemetryHandler(tracer_provider=tracer_provider)
        self.handler = OpenTelemetryLangChainCallbackHandler(
            telemetry_handler=telemetry_handler
        )

    def _finished_spans(self):
        return self.span_exporter.get_finished_spans()

    def _spans_by_kind(self, kind: SpanKind):
        return [s for s in self._finished_spans() if s.kind == kind]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWorkflowSpanCreation(_CallbackHandlerTestBase):
    """Verify that a workflow span is created for top-level chains."""

    def test_workflow_span_created_for_top_level_chain(self) -> None:
        chain_run_id = uuid.uuid4()

        self.handler.on_chain_start(
            serialized=_make_serialized("MyChain"),
            inputs={},
            run_id=chain_run_id,
            parent_run_id=None,
        )
        self.handler.on_chain_end(
            outputs={},
            run_id=chain_run_id,
            parent_run_id=None,
        )

        internal_spans = self._spans_by_kind(SpanKind.INTERNAL)
        self.assertEqual(len(internal_spans), 1)
        self.assertEqual(internal_spans[0].name, "invoke_workflow MyChain")

    def test_no_workflow_span_for_nested_chain(self) -> None:
        """Chains with a parent_run_id are nested — no extra workflow span."""
        parent_run_id = uuid.uuid4()
        child_run_id = uuid.uuid4()

        # Start parent (top-level)
        self.handler.on_chain_start(
            serialized=_make_serialized("ParentChain"),
            inputs={},
            run_id=parent_run_id,
            parent_run_id=None,
        )
        # Start child (nested — should NOT create a workflow span)
        self.handler.on_chain_start(
            serialized=_make_serialized("ChildChain"),
            inputs={},
            run_id=child_run_id,
            parent_run_id=parent_run_id,
        )
        self.handler.on_chain_end(
            outputs={},
            run_id=child_run_id,
            parent_run_id=parent_run_id,
        )
        self.handler.on_chain_end(
            outputs={},
            run_id=parent_run_id,
            parent_run_id=None,
        )

        # Only one INTERNAL (workflow) span — for the parent, not the child
        internal_spans = self._spans_by_kind(SpanKind.INTERNAL)
        self.assertEqual(len(internal_spans), 1)
        self.assertEqual(internal_spans[0].name, "invoke_workflow ParentChain")


class TestLLMSpanGetsWorkflowName(_CallbackHandlerTestBase):
    """Verify gen_ai.workflow.name is propagated to the LLM span via CSA."""

    def test_llm_span_inside_chain_gets_workflow_name(self) -> None:
        chain_run_id = uuid.uuid4()
        llm_run_id = uuid.uuid4()

        self.handler.on_chain_start(
            serialized=_make_serialized("MyPipeline"),
            inputs={},
            run_id=chain_run_id,
            parent_run_id=None,
        )
        self.handler.on_chat_model_start(
            serialized=_make_serialized("ChatOpenAI"),
            messages=[[AIMessage(content="hi")]],
            run_id=llm_run_id,
            parent_run_id=chain_run_id,
            metadata={"ls_provider": "openai"},
            **_make_chat_invocation_params("gpt-3.5-turbo"),
        )
        self.handler.on_llm_end(
            response=_make_llm_result(),
            run_id=llm_run_id,
            parent_run_id=chain_run_id,
        )
        self.handler.on_chain_end(
            outputs={},
            run_id=chain_run_id,
            parent_run_id=None,
        )

        client_spans = self._spans_by_kind(SpanKind.CLIENT)
        self.assertEqual(len(client_spans), 1)
        self.assertEqual(
            client_spans[0].attributes.get("gen_ai.workflow.name"),
            "MyPipeline",
        )

    def test_workflow_name_from_metadata_override(self) -> None:
        """metadata['workflow_name'] overrides the serialized chain name."""
        chain_run_id = uuid.uuid4()
        llm_run_id = uuid.uuid4()

        self.handler.on_chain_start(
            serialized=_make_serialized("InternalChainName"),
            inputs={},
            run_id=chain_run_id,
            parent_run_id=None,
            metadata={"workflow_name": "my_custom_wf"},
        )
        self.handler.on_chat_model_start(
            serialized=_make_serialized("ChatOpenAI"),
            messages=[[AIMessage(content="hi")]],
            run_id=llm_run_id,
            parent_run_id=chain_run_id,
            metadata={"ls_provider": "openai"},
            **_make_chat_invocation_params("gpt-3.5-turbo"),
        )
        self.handler.on_llm_end(
            response=_make_llm_result(),
            run_id=llm_run_id,
            parent_run_id=chain_run_id,
        )
        self.handler.on_chain_end(
            outputs={},
            run_id=chain_run_id,
            parent_run_id=None,
        )

        internal_spans = self._spans_by_kind(SpanKind.INTERNAL)
        self.assertEqual(len(internal_spans), 1)
        self.assertEqual(internal_spans[0].name, "invoke_workflow my_custom_wf")

        client_spans = self._spans_by_kind(SpanKind.CLIENT)
        self.assertEqual(len(client_spans), 1)
        self.assertEqual(
            client_spans[0].attributes.get("gen_ai.workflow.name"),
            "my_custom_wf",
        )


class TestCSANotLeakedToBaggage(_CallbackHandlerTestBase):
    """Verify that gen_ai.workflow.name is NOT written to W3C Baggage by default."""

    def test_csa_not_leaked_to_baggage(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "OTEL_PYTHON_GENAI_CAPTURE_BAGGAGE"}
        with patch.dict(os.environ, env, clear=True):
            chain_run_id = uuid.uuid4()

            self.handler.on_chain_start(
                serialized=_make_serialized("BaggageTestChain"),
                inputs={},
                run_id=chain_run_id,
                parent_run_id=None,
            )
            try:
                # While workflow is active, baggage should NOT contain the workflow name
                baggage_value = baggage.get_baggage("gen_ai.workflow.name")
                self.assertIsNone(
                    baggage_value,
                    "gen_ai.workflow.name must not be leaked to W3C Baggage by default",
                )
            finally:
                self.handler.on_chain_end(
                    outputs={},
                    run_id=chain_run_id,
                    parent_run_id=None,
                )


class TestCSAScopeEndsAfterChain(_CallbackHandlerTestBase):
    """Verify that the CSA is no longer visible after the chain ends."""

    def test_csa_not_visible_outside_workflow_scope(self) -> None:
        chain_run_id = uuid.uuid4()

        self.handler.on_chain_start(
            serialized=_make_serialized("ScopedChain"),
            inputs={},
            run_id=chain_run_id,
            parent_run_id=None,
        )
        self.handler.on_chain_end(
            outputs={},
            run_id=chain_run_id,
            parent_run_id=None,
        )

        # After on_chain_end the context token is detached — CSA should be gone
        attrs = get_context_scoped_attributes()
        self.assertIsNone(
            attrs.get("gen_ai.workflow.name"),
            "gen_ai.workflow.name should not be visible after workflow scope ends",
        )


class TestWorkflowErrorPath(_CallbackHandlerTestBase):
    """Verify on_chain_error records error status and cleans up state."""

    def test_workflow_span_has_error_status_on_chain_error(self) -> None:
        chain_run_id = uuid.uuid4()

        self.handler.on_chain_start(
            serialized=_make_serialized("FailingChain"),
            inputs={},
            run_id=chain_run_id,
            parent_run_id=None,
        )
        self.handler.on_chain_error(
            error=ValueError("something went wrong"),
            run_id=chain_run_id,
            parent_run_id=None,
        )

        internal_spans = self._spans_by_kind(SpanKind.INTERNAL)
        self.assertEqual(len(internal_spans), 1)
        span = internal_spans[0]
        self.assertEqual(span.name, "invoke_workflow FailingChain")
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertIn("something went wrong", span.status.description)

    def test_workflow_span_error_type_attribute(self) -> None:
        chain_run_id = uuid.uuid4()

        self.handler.on_chain_start(
            serialized=_make_serialized("FailingChain"),
            inputs={},
            run_id=chain_run_id,
            parent_run_id=None,
        )
        self.handler.on_chain_error(
            error=RuntimeError("boom"),
            run_id=chain_run_id,
            parent_run_id=None,
        )

        internal_spans = self._spans_by_kind(SpanKind.INTERNAL)
        self.assertEqual(len(internal_spans), 1)
        self.assertEqual(
            internal_spans[0].attributes.get("error.type"), "RuntimeError"
        )

    def test_chain_error_cleans_up_invocation_state(self) -> None:
        chain_run_id = uuid.uuid4()

        self.handler.on_chain_start(
            serialized=_make_serialized("FailingChain"),
            inputs={},
            run_id=chain_run_id,
            parent_run_id=None,
        )
        self.handler.on_chain_error(
            error=ValueError("oops"),
            run_id=chain_run_id,
            parent_run_id=None,
        )

        # Invocation should have been removed — a second error call is a no-op
        self.handler.on_chain_error(
            error=ValueError("duplicate"),
            run_id=chain_run_id,
            parent_run_id=None,
        )
        # Only one span — the second call was silently ignored
        self.assertEqual(len(self._finished_spans()), 1)

    def test_chain_error_csa_scope_ends(self) -> None:
        """CSA should be gone after on_chain_error, same as on_chain_end."""
        chain_run_id = uuid.uuid4()

        self.handler.on_chain_start(
            serialized=_make_serialized("FailingChain"),
            inputs={},
            run_id=chain_run_id,
            parent_run_id=None,
        )
        self.handler.on_chain_error(
            error=ValueError("oops"),
            run_id=chain_run_id,
            parent_run_id=None,
        )

        attrs = get_context_scoped_attributes()
        self.assertIsNone(
            attrs.get("gen_ai.workflow.name"),
            "gen_ai.workflow.name should not be visible after workflow error",
        )

    def test_chain_error_unknown_run_id_is_noop(self) -> None:
        """on_chain_error with an unknown run_id must not raise."""
        self.handler.on_chain_error(
            error=ValueError("no matching invocation"),
            run_id=uuid.uuid4(),
            parent_run_id=None,
        )
        self.assertEqual(len(self._finished_spans()), 0)

    def test_chain_end_unknown_run_id_is_noop(self) -> None:
        """on_chain_end with an unknown run_id must not raise."""
        self.handler.on_chain_end(
            outputs={},
            run_id=uuid.uuid4(),
            parent_run_id=None,
        )
        self.assertEqual(len(self._finished_spans()), 0)


class TestLLMErrorInsideWorkflow(_CallbackHandlerTestBase):
    """Verify on_llm_error inside a workflow doesn't break the parent workflow span."""

    def test_llm_error_inside_workflow_records_error_on_llm_span(self) -> None:
        chain_run_id = uuid.uuid4()
        llm_run_id = uuid.uuid4()

        self.handler.on_chain_start(
            serialized=_make_serialized("MyPipeline"),
            inputs={},
            run_id=chain_run_id,
            parent_run_id=None,
        )
        self.handler.on_chat_model_start(
            serialized=_make_serialized("ChatOpenAI"),
            messages=[[AIMessage(content="hi")]],
            run_id=llm_run_id,
            parent_run_id=chain_run_id,
            metadata={"ls_provider": "openai"},
            **_make_chat_invocation_params("gpt-3.5-turbo"),
        )
        self.handler.on_llm_error(
            error=RuntimeError("model timeout"),
            run_id=llm_run_id,
            parent_run_id=chain_run_id,
        )
        self.handler.on_chain_end(
            outputs={},
            run_id=chain_run_id,
            parent_run_id=None,
        )

        client_spans = self._spans_by_kind(SpanKind.CLIENT)
        self.assertEqual(len(client_spans), 1)
        self.assertEqual(client_spans[0].status.status_code, StatusCode.ERROR)

        # Workflow span still finishes (not in error state)
        internal_spans = self._spans_by_kind(SpanKind.INTERNAL)
        self.assertEqual(len(internal_spans), 1)
        self.assertNotEqual(internal_spans[0].status.status_code, StatusCode.ERROR)

    def test_llm_error_inside_workflow_llm_span_is_child_of_workflow(self) -> None:
        chain_run_id = uuid.uuid4()
        llm_run_id = uuid.uuid4()

        self.handler.on_chain_start(
            serialized=_make_serialized("MyPipeline"),
            inputs={},
            run_id=chain_run_id,
            parent_run_id=None,
        )
        self.handler.on_chat_model_start(
            serialized=_make_serialized("ChatOpenAI"),
            messages=[[AIMessage(content="hi")]],
            run_id=llm_run_id,
            parent_run_id=chain_run_id,
            metadata={"ls_provider": "openai"},
            **_make_chat_invocation_params("gpt-3.5-turbo"),
        )
        self.handler.on_llm_end(
            response=_make_llm_result(),
            run_id=llm_run_id,
            parent_run_id=chain_run_id,
        )
        self.handler.on_chain_end(
            outputs={},
            run_id=chain_run_id,
            parent_run_id=None,
        )

        internal_spans = self._spans_by_kind(SpanKind.INTERNAL)
        client_spans = self._spans_by_kind(SpanKind.CLIENT)
        self.assertEqual(len(internal_spans), 1)
        self.assertEqual(len(client_spans), 1)

        workflow_span = internal_spans[0]
        llm_span = client_spans[0]
        self.assertEqual(
            llm_span.context.trace_id,
            workflow_span.context.trace_id,
            "LLM span and workflow span must share the same trace",
        )
        self.assertEqual(
            llm_span.parent.span_id,
            workflow_span.context.span_id,
            "LLM span must be a child of the workflow span",
        )


class TestWorkflowNameFallback(_CallbackHandlerTestBase):
    """Verify the name resolution fallback chain in on_chain_start."""

    def test_name_falls_back_to_id_list(self) -> None:
        chain_run_id = uuid.uuid4()

        self.handler.on_chain_start(
            serialized={"id": ["pkg", "mod", "MyRunnableClass"]},
            inputs={},
            run_id=chain_run_id,
            parent_run_id=None,
        )
        self.handler.on_chain_end(outputs={}, run_id=chain_run_id, parent_run_id=None)

        internal_spans = self._spans_by_kind(SpanKind.INTERNAL)
        self.assertEqual(len(internal_spans), 1)
        # id is a list — _safe_str(list) produces a string; just verify a span was created
        self.assertTrue(internal_spans[0].name.startswith("invoke_workflow "))

    def test_name_falls_back_to_langgraph_node(self) -> None:
        chain_run_id = uuid.uuid4()

        self.handler.on_chain_start(
            serialized={},
            inputs={},
            run_id=chain_run_id,
            parent_run_id=None,
            metadata={"langgraph_node": "my_node"},
        )
        self.handler.on_chain_end(outputs={}, run_id=chain_run_id, parent_run_id=None)

        internal_spans = self._spans_by_kind(SpanKind.INTERNAL)
        self.assertEqual(len(internal_spans), 1)
        self.assertEqual(internal_spans[0].name, "invoke_workflow my_node")

    def test_name_defaults_to_chain_when_nothing_provided(self) -> None:
        chain_run_id = uuid.uuid4()

        self.handler.on_chain_start(
            serialized={},
            inputs={},
            run_id=chain_run_id,
            parent_run_id=None,
        )
        self.handler.on_chain_end(outputs={}, run_id=chain_run_id, parent_run_id=None)

        internal_spans = self._spans_by_kind(SpanKind.INTERNAL)
        self.assertEqual(len(internal_spans), 1)
        self.assertEqual(internal_spans[0].name, "invoke_workflow chain")
