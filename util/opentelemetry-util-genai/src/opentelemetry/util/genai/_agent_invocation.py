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

from dataclasses import asdict
from typing import Any, Union

from opentelemetry._logs import Logger
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import server_attributes
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.util.genai._invocation import Error, GenAIInvocation
from opentelemetry.util.genai.metrics import InvocationMetricsRecorder
from opentelemetry.util.genai.types import (
    FunctionToolDefinition,
    GenericToolDefinition,
    InputMessage,
    MessagePart,
    OutputMessage,
)
from opentelemetry.util.genai.utils import (
    ContentCapturingMode,
    gen_ai_json_dumps,
    get_content_capturing_mode,
    is_experimental_mode,
)

ToolDefinition = Union[FunctionToolDefinition, GenericToolDefinition]


class AgentInvocation(GenAIInvocation):
    """Represents a single agent invocation (invoke_agent span).

    Use handler.start_agent() or the handler.invoke_agent() context manager
    rather than constructing this directly.

    Reference: https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-agent-spans.md#invoke-agent-span
    """

    def __init__(
        self,
        tracer: Tracer,
        metrics_recorder: InvocationMetricsRecorder,
        logger: Logger,
        *,
        provider: str | None = None,
        request_model: str | None = None,
        server_address: str | None = None,
        server_port: int | None = None,
        agent_name: str | None = None,
        attributes: dict[str, Any] | None = None,
        metric_attributes: dict[str, Any] | None = None,
    ) -> None:
        """Use handler.start_agent() or handler.invoke_agent() instead of calling this directly."""
        _operation_name = GenAI.GenAiOperationNameValues.INVOKE_AGENT.value
        super().__init__(
            tracer,
            metrics_recorder,
            logger,
            operation_name=_operation_name,
            span_name=f"{_operation_name} {agent_name}"
            if agent_name
            else _operation_name,
            span_kind=SpanKind.CLIENT,
            attributes=attributes,
            metric_attributes=metric_attributes,
        )
        self.provider = provider
        self.request_model = request_model
        self.server_address = server_address
        self.server_port = server_port

        self.agent_name = agent_name
        self.agent_id: str | None = None
        self.agent_description: str | None = None
        self.agent_version: str | None = None

        self.conversation_id: str | None = None
        self.data_source_id: str | None = None
        self.output_type: str | None = None

        self.temperature: float | None = None
        self.top_p: float | None = None
        self.frequency_penalty: float | None = None
        self.presence_penalty: float | None = None
        self.max_tokens: int | None = None
        self.stop_sequences: list[str] | None = None
        self.seed: int | None = None
        self.choice_count: int | None = None

        self.finish_reasons: list[str] | None = None
        self.response_model_name: str | None = None
        self.response_id: str | None = None
        self.input_tokens: int | None = None
        self.output_tokens: int | None = None
        self.cache_creation_input_tokens: int | None = None
        self.cache_read_input_tokens: int | None = None

        self.input_messages: list[InputMessage] = []
        self.output_messages: list[OutputMessage] = []
        self.system_instruction: list[MessagePart] = []
        self.tool_definitions: list[ToolDefinition] | None = None

        self._start()

    def _get_common_attributes(self) -> dict[str, Any]:
        optional_attrs = (
            (GenAI.GEN_AI_PROVIDER_NAME, self.provider),
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
            **{k: v for k, v in optional_attrs if v is not None},
        }

    def _get_request_attributes(self) -> dict[str, Any]:
        optional_attrs = (
            (GenAI.GEN_AI_CONVERSATION_ID, self.conversation_id),
            (GenAI.GEN_AI_DATA_SOURCE_ID, self.data_source_id),
            (GenAI.GEN_AI_OUTPUT_TYPE, self.output_type),
            (GenAI.GEN_AI_REQUEST_TEMPERATURE, self.temperature),
            (GenAI.GEN_AI_REQUEST_TOP_P, self.top_p),
            (GenAI.GEN_AI_REQUEST_FREQUENCY_PENALTY, self.frequency_penalty),
            (GenAI.GEN_AI_REQUEST_PRESENCE_PENALTY, self.presence_penalty),
            (GenAI.GEN_AI_REQUEST_MAX_TOKENS, self.max_tokens),
            (GenAI.GEN_AI_REQUEST_STOP_SEQUENCES, self.stop_sequences),
            (GenAI.GEN_AI_REQUEST_SEED, self.seed),
            (GenAI.GEN_AI_REQUEST_CHOICE_COUNT, self.choice_count),
        )
        return {k: v for k, v in optional_attrs if v is not None}

    def _get_response_attributes(self) -> dict[str, Any]:
        optional_attrs = (
            (GenAI.GEN_AI_RESPONSE_FINISH_REASONS, self.finish_reasons),
            (GenAI.GEN_AI_RESPONSE_MODEL, self.response_model_name),
            (GenAI.GEN_AI_RESPONSE_ID, self.response_id),
            (GenAI.GEN_AI_USAGE_INPUT_TOKENS, self.input_tokens),
            (GenAI.GEN_AI_USAGE_OUTPUT_TOKENS, self.output_tokens),
            (
                GenAI.GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS,
                self.cache_creation_input_tokens,
            ),
            (
                GenAI.GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS,
                self.cache_read_input_tokens,
            ),
        )
        return {k: v for k, v in optional_attrs if v is not None}

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
            (
                GenAI.GEN_AI_SYSTEM_INSTRUCTIONS,
                gen_ai_json_dumps([asdict(p) for p in self.system_instruction])
                if self.system_instruction
                else None,
            ),
            (
                GenAI.GEN_AI_TOOL_DEFINITIONS,
                gen_ai_json_dumps([asdict(t) for t in self.tool_definitions])
                if self.tool_definitions
                else None,
            ),
        )
        return {
            key: value for key, value in optional_attrs if value is not None
        }

    def _get_metric_attributes(self) -> dict[str, Any]:
        optional_attrs = (
            (GenAI.GEN_AI_PROVIDER_NAME, self.provider),
            (GenAI.GEN_AI_REQUEST_MODEL, self.request_model),
            (GenAI.GEN_AI_RESPONSE_MODEL, self.response_model_name),
            (server_attributes.SERVER_ADDRESS, self.server_address),
            (server_attributes.SERVER_PORT, self.server_port),
        )
        attrs: dict[str, Any] = {
            GenAI.GEN_AI_OPERATION_NAME: self._operation_name,
            **{k: v for k, v in optional_attrs if v is not None},
        }
        attrs.update(self.metric_attributes)
        return attrs

    def _get_metric_token_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        if self.input_tokens is not None:
            counts[GenAI.GenAiTokenTypeValues.INPUT.value] = self.input_tokens
        if self.output_tokens is not None:
            counts[GenAI.GenAiTokenTypeValues.OUTPUT.value] = (
                self.output_tokens
            )
        return counts

    def _apply_finish(self, error: Error | None = None) -> None:
        if error is not None:
            self._apply_error_attributes(error)

        # Update span name if agent_name was set after construction
        if self.agent_name:
            self.span.update_name(f"{self._operation_name} {self.agent_name}")

        attributes: dict[str, Any] = {}
        attributes.update(self._get_common_attributes())
        attributes.update(self._get_request_attributes())
        attributes.update(self._get_response_attributes())
        attributes.update(self._get_messages_for_span())
        attributes.update(self.attributes)
        self.span.set_attributes(attributes)
        self._metrics_recorder.record(self)
