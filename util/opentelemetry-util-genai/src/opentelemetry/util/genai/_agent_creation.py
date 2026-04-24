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

"""Agent creation invocation type.

Represents a ``create_agent`` operation as defined by the OpenTelemetry
GenAI semantic conventions:
https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-agent-spans.md#create-agent
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from opentelemetry._logs import Logger
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import server_attributes
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.util.genai._invocation import Error, GenAIInvocation
from opentelemetry.util.genai.metrics import InvocationMetricsRecorder
from opentelemetry.util.genai.types import MessagePart
from opentelemetry.util.genai.utils import (
    ContentCapturingMode,
    gen_ai_json_dumps,
    get_content_capturing_mode,
    is_experimental_mode,
)


class AgentCreation(GenAIInvocation):
    """Represents an agent creation/initialization.

    Use ``handler.start_create_agent()`` or ``handler.create_agent()``
    context manager rather than constructing this directly.

    Spec:
    https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-agent-spans.md#create-agent
    """

    def __init__(
        self,
        tracer: Tracer,
        metrics_recorder: InvocationMetricsRecorder,
        logger: Logger,
        provider: str,
        *,
        request_model: str | None = None,
        server_address: str | None = None,
        server_port: int | None = None,
        attributes: dict[str, Any] | None = None,
        metric_attributes: dict[str, Any] | None = None,
    ) -> None:
        """Use handler.start_create_agent() or handler.create_agent() instead of calling this directly."""
        _operation_name = GenAI.GenAiOperationNameValues.CREATE_AGENT.value
        super().__init__(
            tracer,
            metrics_recorder,
            logger,
            operation_name=_operation_name,
            span_name=_operation_name,
            span_kind=SpanKind.CLIENT,
            attributes=attributes,
            metric_attributes=metric_attributes,
        )
        self.provider = provider
        self.request_model = request_model
        self.server_address = server_address
        self.server_port = server_port

        self.agent_name: str | None = None
        self.agent_id: str | None = None
        self.agent_description: str | None = None
        self.agent_version: str | None = None

        self.system_instruction: list[MessagePart] = []

        self._start()

    def _get_common_attributes(self) -> dict[str, Any]:
        optional_attrs = (
            (GenAI.GEN_AI_REQUEST_MODEL, self.request_model),
            (server_attributes.SERVER_ADDRESS, self.server_address),
            (server_attributes.SERVER_PORT, self.server_port),
            (GenAI.GEN_AI_AGENT_NAME, self.agent_name),
            (GenAI.GEN_AI_AGENT_ID, self.agent_id),
            (GenAI.GEN_AI_AGENT_DESCRIPTION, self.agent_description),
            (GenAI.GEN_AI_AGENT_VERSION, self.agent_version),
        )
        return {
            GenAI.GEN_AI_OPERATION_NAME: self._operation_name,
            GenAI.GEN_AI_PROVIDER_NAME: self.provider,
            **{k: v for k, v in optional_attrs if v is not None},
        }

    def _get_system_instructions_for_span(self) -> dict[str, Any]:
        if (
            not is_experimental_mode()
            or get_content_capturing_mode()
            not in (
                ContentCapturingMode.SPAN_ONLY,
                ContentCapturingMode.SPAN_AND_EVENT,
            )
            or not self.system_instruction
        ):
            return {}
        return {
            GenAI.GEN_AI_SYSTEM_INSTRUCTIONS: gen_ai_json_dumps(
                [asdict(p) for p in self.system_instruction]
            ),
        }

    def _get_metric_attributes(self) -> dict[str, Any]:
        optional_attrs = (
            (GenAI.GEN_AI_PROVIDER_NAME, self.provider),
            (GenAI.GEN_AI_REQUEST_MODEL, self.request_model),
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

        # Update span name if agent_name was set after construction
        if self.agent_name:
            self.span.update_name(f"{self._operation_name} {self.agent_name}")

        attributes: dict[str, Any] = {}
        attributes.update(self._get_common_attributes())
        attributes.update(self._get_system_instructions_for_span())
        attributes.update(self.attributes)
        self.span.set_attributes(attributes)
        self._metrics_recorder.record(self)
