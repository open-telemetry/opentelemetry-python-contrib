# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from opentelemetry._logs import Logger
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import server_attributes
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.util.genai._invocation import (
    Error,
    GenAIInvocation,
    get_content_attributes,
)
from opentelemetry.util.genai.completion_hook import CompletionHook
from opentelemetry.util.genai.metrics import InvocationMetricsRecorder
from opentelemetry.util.genai.types import (
    InputMessage,
    MessagePart,
    OutputMessage,
    ToolDefinition,
)

# TODO: Migrate to GenAI constants once available in semconv package
_GEN_AI_AGENT_VERSION = "gen_ai.agent.version"
_GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS = (
    "gen_ai.usage.cache_creation.input_tokens"
)
_GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS = "gen_ai.usage.cache_read.input_tokens"


class AgentInvocation(GenAIInvocation):
    """Represents a single agent invocation (invoke_agent span).

    Use handler.start_invoke_local_agent() / handler.start_invoke_remote_agent()
    or the handler.invoke_local_agent() / handler.invoke_remote_agent() context
    managers rather than constructing this directly.

    Reference:
        Client span: https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-agent-spans.md#invoke-agent-client-span
        Internal span: https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-agent-spans.md#invoke-agent-internal-span
    """

    def __init__(
        self,
        tracer: Tracer,
        metrics_recorder: InvocationMetricsRecorder,
        logger: Logger,
        completion_hook: CompletionHook,
        provider: str,
        *,
        span_kind: SpanKind = SpanKind.INTERNAL,
        request_model: str | None = None,
        server_address: str | None = None,
        server_port: int | None = None,
        attributes: dict[str, Any] | None = None,
        metric_attributes: dict[str, Any] | None = None,
    ) -> None:
        """Use handler.start_invoke_local_agent() or handler.start_invoke_remote_agent() instead of calling this directly."""
        _operation_name = GenAI.GenAiOperationNameValues.INVOKE_AGENT.value
        super().__init__(
            tracer,
            metrics_recorder,
            logger,
            completion_hook,
            operation_name=_operation_name,
            span_name=_operation_name,
            span_kind=span_kind,
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
            (GenAI.GEN_AI_REQUEST_MODEL, self.request_model),
            (server_attributes.SERVER_ADDRESS, self.server_address),
            (server_attributes.SERVER_PORT, self.server_port),
            (GenAI.GEN_AI_AGENT_NAME, self.agent_name),
            (GenAI.GEN_AI_AGENT_ID, self.agent_id),
            (GenAI.GEN_AI_AGENT_DESCRIPTION, self.agent_description),
            (_GEN_AI_AGENT_VERSION, self.agent_version),
        )
        return {
            GenAI.GEN_AI_OPERATION_NAME: self._operation_name,
            GenAI.GEN_AI_PROVIDER_NAME: self.provider,
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
        if self.finish_reasons:
            return {GenAI.GEN_AI_RESPONSE_FINISH_REASONS: self.finish_reasons}
        return {}

    def _get_usage_attributes(self) -> dict[str, Any]:
        optional_attrs = (
            (GenAI.GEN_AI_USAGE_INPUT_TOKENS, self.input_tokens),
            (GenAI.GEN_AI_USAGE_OUTPUT_TOKENS, self.output_tokens),
            (
                _GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS,
                self.cache_creation_input_tokens,
            ),
            (
                _GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS,
                self.cache_read_input_tokens,
            ),
        )
        return {k: v for k, v in optional_attrs if v is not None}

    def _get_content_attributes_for_span(self) -> dict[str, Any]:
        return get_content_attributes(
            input_messages=self.input_messages,
            output_messages=self.output_messages,
            system_instruction=self.system_instruction,
            tool_definitions=self.tool_definitions,
            for_span=True,
        )

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
        attributes.update(self._get_usage_attributes())
        attributes.update(self._get_content_attributes_for_span())
        attributes.update(self.attributes)
        self.span.set_attributes(attributes)
        self._call_completion_hook(
            inputs=self.input_messages,
            outputs=self.output_messages,
            system_instruction=self.system_instruction,
            tool_definitions=self.tool_definitions,
        )
        self._metrics_recorder.record(self)
