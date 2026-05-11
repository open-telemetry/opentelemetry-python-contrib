# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from opentelemetry._logs import Logger
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.util.genai._invocation import Error, GenAIInvocation
from opentelemetry.util.genai.completion_hook import CompletionHook
from opentelemetry.util.genai.metrics import InvocationMetricsRecorder
from opentelemetry.util.genai.types import (
    InputMessage,
    OutputMessage,
)
from opentelemetry.util.genai.utils import (
    ContentCapturingMode,
    gen_ai_json_dumps,
    get_content_capturing_mode,
    is_experimental_mode,
)


class WorkflowInvocation(GenAIInvocation):
    """
    Represents a predetermined sequence of operations (e.g. agent, LLM, tool,
    and retrieval invocations). A workflow groups multiple operations together,
    accepting input(s) and producing final output(s).

    Use handler.start_workflow(name) or the handler.workflow(name) context
    manager rather than constructing this directly.
    """

    def __init__(
        self,
        tracer: Tracer,
        metrics_recorder: InvocationMetricsRecorder,
        logger: Logger,
        completion_hook: CompletionHook,
        name: str | None,
    ) -> None:
        """Use handler.start_workflow(name) or handler.workflow(name) instead of calling this directly."""
        _operation_name = "invoke_workflow"
        super().__init__(
            tracer,
            metrics_recorder,
            logger,
            completion_hook,
            operation_name=_operation_name,
            span_name=f"{_operation_name} {name}" if name else _operation_name,
            span_kind=SpanKind.INTERNAL,
        )
        self.name = name
        self.input_messages: list[InputMessage] = []
        self.output_messages: list[OutputMessage] = []
        self._start(self._get_base_attributes())

    def _get_base_attributes(self) -> dict[str, Any]:
        """Return sampling-relevant attributes available at span creation time."""
        attrs: dict[str, Any] = {
            GenAI.GEN_AI_OPERATION_NAME: self._operation_name,
        }
        return attrs

    def _get_messages_for_span(self) -> dict[str, Any]:
        if not is_experimental_mode() or get_content_capturing_mode() not in (
            ContentCapturingMode.SPAN_ONLY,
            ContentCapturingMode.SPAN_AND_EVENT,
        ):
            return {}
        optional_attrs = (
            (
                GenAI.GEN_AI_INPUT_MESSAGES,
                gen_ai_json_dumps([asdict(m) for m in self.input_messages])
                if self.input_messages
                else None,
            ),
            (
                GenAI.GEN_AI_OUTPUT_MESSAGES,
                gen_ai_json_dumps([asdict(m) for m in self.output_messages])
                if self.output_messages
                else None,
            ),
        )
        return {
            key: value for key, value in optional_attrs if value is not None
        }

    def _apply_finish(self, error: Error | None = None) -> None:
        attributes: dict[str, Any] = {
            GenAI.GEN_AI_OPERATION_NAME: self._operation_name
        }
        attributes.update(self._get_messages_for_span())
        if error is not None:
            self._apply_error_attributes(error)
        attributes.update(self.attributes)
        self.span.set_attributes(attributes)
        self._call_completion_hook(
            inputs=self.input_messages,
            outputs=self.output_messages,
        )
        # TODO: Add workflow metrics when supported
