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

from __future__ import annotations

from typing import Any

from opentelemetry._logs import Logger
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import server_attributes
from opentelemetry.trace import Tracer
from opentelemetry.util.genai._invocation import Error, GenAIInvocation
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

    def __init__(  # pylint: disable=too-many-locals
        self,
        tracer: Tracer,
        metrics_recorder: InvocationMetricsRecorder,
        logger: Logger,
        name: str,
        *,
        arguments: Any = None,
        tool_call_id: str | None = None,
        tool_type: str | None = None,
        tool_description: str | None = None,
        tool_result: Any = None,
        provider: str | None = None,
        server_address: str | None = None,
        server_port: int | None = None,
        attributes: dict[str, Any] | None = None,
        metric_attributes: dict[str, Any] | None = None,
    ) -> None:
        """Use handler.start_tool(name) or handler.tool(name) instead of calling this directly."""
        _operation_name = GenAI.GenAiOperationNameValues.EXECUTE_TOOL.value
        super().__init__(
            tracer,
            metrics_recorder,
            logger,
            operation_name=_operation_name,
            span_name=f"{_operation_name} {name}" if name else _operation_name,
            attributes=attributes,
            metric_attributes=metric_attributes,
        )
        self.name = name
        self.arguments = arguments
        self.tool_call_id = tool_call_id
        self.tool_type = tool_type
        self.tool_description = tool_description
        self.tool_result = tool_result
        self.provider = provider
        self.server_address = server_address
        self.server_port = server_port
        self._start()

    def _get_metric_attributes(self) -> dict[str, Any]:
        optional_attrs = (
            (GenAI.GEN_AI_PROVIDER_NAME, self.provider),
            (server_attributes.SERVER_ADDRESS, self.server_address),
            (server_attributes.SERVER_PORT, self.server_port),
        )
        attrs: dict[str, Any] = {
            GenAI.GEN_AI_OPERATION_NAME: self._operation_name,
            **{k: v for k, v in optional_attrs if v is not None},
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
        )
        attributes: dict[str, Any] = {
            GenAI.GEN_AI_OPERATION_NAME: self._operation_name,
            **{k: v for k, v in optional_attrs if v is not None},
        }
        attributes.update(self.attributes)
        self.span.set_attributes(attributes)
        self._metrics_recorder.record(self)
