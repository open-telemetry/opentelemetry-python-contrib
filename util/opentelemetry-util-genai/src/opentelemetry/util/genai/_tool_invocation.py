# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from opentelemetry._logs import Logger
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.trace import Tracer
from opentelemetry.util.genai._invocation import Error, GenAIInvocation
from opentelemetry.util.genai.completion_hook import CompletionHook
from opentelemetry.util.genai.metrics import InvocationMetricsRecorder


class ToolInvocation(GenAIInvocation):
    """Represents a tool call invocation for execute_tool span tracking.

    Not used as a message part — use ToolCallRequest for that purpose.

    Use handler.start_tool(name) rather than constructing this directly.

    Reference: https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-spans.md#execute-tool-span

    Semantic convention attributes for execute_tool spans:
    - gen_ai.operation.name: "execute_tool" (Required)
    - gen_ai.tool.name: Name of the tool (Recommended)
    - gen_ai.tool.call.id: Tool call identifier (Recommended if available)
    - gen_ai.tool.type: Type classification - "function", "extension", or "datastore" (Recommended if available)
    - gen_ai.tool.description: Tool description (Recommended if available)
    - gen_ai.tool.call.arguments: Parameters passed to tool (Opt-In, may contain sensitive data)
    - gen_ai.tool.call.result: Result returned by tool (Opt-In, may contain sensitive data)
    - error.type: Error type if operation failed (Conditionally Required)
    """

    def __init__(
        self,
        tracer: Tracer,
        metrics_recorder: InvocationMetricsRecorder,
        logger: Logger,
        completion_hook: CompletionHook,
        name: str,
        *,
        arguments: Any = None,
        tool_call_id: str | None = None,
        tool_type: str | None = None,
        tool_description: str | None = None,
    ) -> None:
        """Use handler.start_tool(name) or handler.tool(name) instead of calling this directly."""
        _operation_name = GenAI.GenAiOperationNameValues.EXECUTE_TOOL.value
        super().__init__(
            tracer,
            metrics_recorder,
            logger,
            completion_hook,
            operation_name=_operation_name,
            span_name=f"{_operation_name} {name}" if name else _operation_name,
        )
        self.name = name
        self.arguments = arguments
        self.tool_call_id = tool_call_id
        self.tool_type = tool_type
        self.tool_description = tool_description
        self.tool_result: Any = None
        self._start(self._get_base_attributes())

    def _get_base_attributes(self) -> dict[str, Any]:
        """Return sampling-relevant attributes available at span creation time."""
        optional_attrs = (
            (GenAI.GEN_AI_TOOL_NAME, self.name),
            (GenAI.GEN_AI_TOOL_CALL_ID, self.tool_call_id),
            (GenAI.GEN_AI_TOOL_TYPE, self.tool_type),
            (GenAI.GEN_AI_TOOL_DESCRIPTION, self.tool_description),
        )
        return {
            GenAI.GEN_AI_OPERATION_NAME: self._operation_name,
            **{k: v for k, v in optional_attrs if v is not None},
        }

    def _get_metric_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            GenAI.GEN_AI_OPERATION_NAME: self._operation_name,
        }
        attrs.update(self.metric_attributes)
        return attrs

    def _apply_finish(self, error: Error | None = None) -> None:
        if error is not None:
            self._apply_error_attributes(error)
        optional_attrs = (
            (GenAI.GEN_AI_TOOL_NAME, self.name),
            (GenAI.GEN_AI_TOOL_CALL_ID, self.tool_call_id),
            (GenAI.GEN_AI_TOOL_TYPE, self.tool_type),
            (GenAI.GEN_AI_TOOL_DESCRIPTION, self.tool_description),
            (GenAI.GEN_AI_TOOL_CALL_ARGUMENTS, self.arguments),
        )
        attributes: dict[str, Any] = {
            GenAI.GEN_AI_OPERATION_NAME: self._operation_name,
            **{k: v for k, v in optional_attrs if v is not None},
        }
        attributes.update(self.attributes)
        self.span.set_attributes(attributes)
        self._metrics_recorder.record(self)
