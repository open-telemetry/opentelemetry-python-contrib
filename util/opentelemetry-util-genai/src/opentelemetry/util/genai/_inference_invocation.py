# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from opentelemetry._logs import Logger, LogRecord
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import server_attributes
from opentelemetry.trace import INVALID_SPAN, Span, SpanKind, Tracer
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
from opentelemetry.util.genai.utils import (
    is_experimental_mode,
    should_emit_event,
)

# TODO: Migrate to GenAI constants once available in semconv package
_GEN_AI_REASONING_OUTPUT_TOKENS = "gen_ai.usage.reasoning.output_tokens"


class InferenceInvocation(GenAIInvocation):
    """Represents a single LLM chat/completion call.

    Use handler.start_inference(provider) or the handler.inference(provider)
    context manager rather than constructing this directly.
    """

    def __init__(
        self,
        tracer: Tracer,
        metrics_recorder: InvocationMetricsRecorder,
        logger: Logger,
        completion_hook: CompletionHook,
        provider: str,
        *,
        request_model: str | None = None,
        server_address: str | None = None,
        server_port: int | None = None,
        operation_name: str | None = None,
    ) -> None:
        operation_name = (
            operation_name or GenAI.GenAiOperationNameValues.CHAT.value
        )
        """Use handler.start_inference(provider) or handler.inference(provider) instead of calling this directly."""
        super().__init__(
            tracer,
            metrics_recorder,
            logger,
            completion_hook,
            operation_name=operation_name,
            span_name=f"{operation_name} {request_model}"
            if request_model
            else operation_name,
            span_kind=SpanKind.CLIENT,
        )
        self.provider = provider
        self.request_model = request_model
        self.server_address = server_address
        self.server_port = server_port

        self.input_messages: list[InputMessage] = []
        self.output_messages: list[OutputMessage] = []
        self.system_instruction: list[MessagePart] = []
        self.response_model_name: str | None = None
        self.response_id: str | None = None
        self.finish_reasons: list[str] | None = None
        self.input_tokens: int | None = None
        # Output tokens will ultimately be the sum of normal output tokens and thinking tokens.
        self.output_tokens: int | None = None
        self.thinking_tokens: int | None = None
        self.temperature: float | None = None
        self.top_p: float | None = None
        self.frequency_penalty: float | None = None
        self.presence_penalty: float | None = None
        self.max_tokens: int | None = None
        self.stop_sequences: list[str] | None = None
        self.seed: int | None = None
        self.cache_creation_input_tokens: int | None = None
        self.cache_read_input_tokens: int | None = None
        self.tool_definitions: list[ToolDefinition] | None = None
        self._start(self._get_base_attributes())

    def _get_message_attributes(self, *, for_span: bool) -> dict[str, Any]:
        return get_content_attributes(
            input_messages=self.input_messages,
            output_messages=self.output_messages,
            system_instruction=self.system_instruction,
            tool_definitions=self.tool_definitions,
            for_span=for_span,
        )

    def _get_finish_reasons(self) -> list[str] | None:
        if self.finish_reasons is not None:
            return self.finish_reasons or None
        if self.output_messages:
            reasons = [
                msg.finish_reason
                for msg in self.output_messages
                if msg.finish_reason
            ]
            return reasons or None
        return None

    def _get_base_attributes(self) -> dict[str, Any]:
        optional_attrs = (
            (GenAI.GEN_AI_REQUEST_MODEL, self.request_model),
            (GenAI.GEN_AI_PROVIDER_NAME, self.provider),
            (server_attributes.SERVER_ADDRESS, self.server_address),
            (server_attributes.SERVER_PORT, self.server_port),
        )
        return {
            GenAI.GEN_AI_OPERATION_NAME: self._operation_name,
            **{k: v for k, v in optional_attrs if v is not None},
        }

    def _get_attributes(self) -> dict[str, Any]:
        attrs = self._get_base_attributes()
        if self.output_tokens is None and self.thinking_tokens is None:
            output_tokens = None
        else:
            output_tokens = (self.output_tokens or 0) + (
                self.thinking_tokens or 0
            )
        optional_attrs = (
            (GenAI.GEN_AI_REQUEST_TEMPERATURE, self.temperature),
            (GenAI.GEN_AI_REQUEST_TOP_P, self.top_p),
            (GenAI.GEN_AI_REQUEST_FREQUENCY_PENALTY, self.frequency_penalty),
            (GenAI.GEN_AI_REQUEST_PRESENCE_PENALTY, self.presence_penalty),
            (GenAI.GEN_AI_REQUEST_MAX_TOKENS, self.max_tokens),
            (GenAI.GEN_AI_REQUEST_STOP_SEQUENCES, self.stop_sequences),
            (GenAI.GEN_AI_REQUEST_SEED, self.seed),
            (GenAI.GEN_AI_RESPONSE_FINISH_REASONS, self._get_finish_reasons()),
            (GenAI.GEN_AI_RESPONSE_MODEL, self.response_model_name),
            (GenAI.GEN_AI_RESPONSE_ID, self.response_id),
            (GenAI.GEN_AI_USAGE_INPUT_TOKENS, self.input_tokens),
            (GenAI.GEN_AI_USAGE_OUTPUT_TOKENS, output_tokens),
            (
                GenAI.GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS,
                self.cache_creation_input_tokens,
            ),
            (
                GenAI.GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS,
                self.cache_read_input_tokens,
            ),
            (
                _GEN_AI_REASONING_OUTPUT_TOKENS,
                self.thinking_tokens,
            ),
        )
        attrs.update({k: v for k, v in optional_attrs if v is not None})
        return attrs

    def _get_metric_attributes(self) -> dict[str, Any]:
        attrs = self._get_base_attributes()
        if self.response_model_name is not None:
            attrs[GenAI.GEN_AI_RESPONSE_MODEL] = self.response_model_name
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
        attributes = self._get_attributes()
        attributes.update(self._get_message_attributes(for_span=True))
        attributes.update(self.attributes)
        self.span.set_attributes(attributes)
        self._metrics_recorder.record(self)
        log_record = self._maybe_create_event()
        self._call_completion_hook(
            inputs=self.input_messages,
            outputs=self.output_messages,
            system_instruction=self.system_instruction,
            tool_definitions=self.tool_definitions,
            log_record=log_record,
        )
        if log_record is not None:
            self._logger.emit(log_record)

    def _maybe_create_event(self) -> LogRecord | None:
        """Emit a gen_ai.client.inference.operation.details event.

        For more details, see the semantic convention documentation:
        https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-events.md#event-eventgen_aiclientinferenceoperationdetails
        """
        if not is_experimental_mode() or not should_emit_event():
            return None

        attributes = self._get_attributes()
        attributes.update(self._get_message_attributes(for_span=False))
        attributes.update(self.attributes)
        return LogRecord(
            event_name="gen_ai.client.inference.operation.details",
            attributes=attributes,
            context=self._span_context,
        )


@dataclass
class LLMInvocation:
    """Deprecated. Use InferenceInvocation instead.

    Data container for an LLM invocation. Pass to handler.start_llm() to start
    the span, then update fields and call handler.stop_llm() or handler.fail_llm().
    """

    request_model: str | None = None
    input_messages: list[InputMessage] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    output_messages: list[OutputMessage] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    system_instruction: list[MessagePart] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    provider: str | None = None
    response_model_name: str | None = None
    response_id: str | None = None
    finish_reasons: list[str] | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    attributes: dict[str, Any] = field(default_factory=dict)  # pyright: ignore[reportUnknownVariableType]
    """Additional attributes to set on spans and/or events. Not set on metrics."""
    metric_attributes: dict[str, Any] = field(default_factory=dict)  # pyright: ignore[reportUnknownVariableType]
    """Additional attributes to set on metrics. Must be low cardinality. Not set on spans or events."""
    temperature: float | None = None
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    max_tokens: int | None = None
    stop_sequences: list[str] | None = None
    seed: int | None = None
    server_address: str | None = None
    server_port: int | None = None

    _inference_invocation: InferenceInvocation | None = field(
        default=None, init=False, repr=False
    )

    def _start_with_handler(
        self,
        tracer: Tracer,
        metrics_recorder: InvocationMetricsRecorder,
        logger: Logger,
        completion_hook: CompletionHook,
    ) -> None:
        """Create and start an InferenceInvocation from this data container. Called by handler.start_llm()."""
        inv = InferenceInvocation(
            tracer,
            metrics_recorder,
            logger,
            completion_hook,
            self.provider or "",
            request_model=self.request_model,
            server_address=self.server_address,
            server_port=self.server_port,
        )
        inv.input_messages = self.input_messages
        inv.output_messages = self.output_messages
        inv.system_instruction = self.system_instruction
        inv.response_model_name = self.response_model_name
        inv.response_id = self.response_id
        inv.finish_reasons = self.finish_reasons
        inv.input_tokens = self.input_tokens
        inv.output_tokens = self.output_tokens
        inv.temperature = self.temperature
        inv.top_p = self.top_p
        inv.frequency_penalty = self.frequency_penalty
        inv.presence_penalty = self.presence_penalty
        inv.max_tokens = self.max_tokens
        inv.stop_sequences = self.stop_sequences
        inv.seed = self.seed
        inv.attributes.update(self.attributes)
        inv.metric_attributes.update(self.metric_attributes)
        self._inference_invocation = inv

    def _sync_to_invocation(self) -> None:
        inv = self._inference_invocation
        if inv is None:
            return
        inv.provider = self.provider or ""
        inv.request_model = self.request_model
        inv.input_messages = self.input_messages
        inv.output_messages = self.output_messages
        inv.system_instruction = self.system_instruction
        inv.response_model_name = self.response_model_name
        inv.response_id = self.response_id
        inv.finish_reasons = self.finish_reasons
        inv.input_tokens = self.input_tokens
        inv.output_tokens = self.output_tokens
        inv.temperature = self.temperature
        inv.top_p = self.top_p
        inv.frequency_penalty = self.frequency_penalty
        inv.presence_penalty = self.presence_penalty
        inv.max_tokens = self.max_tokens
        inv.stop_sequences = self.stop_sequences
        inv.seed = self.seed
        inv.server_address = self.server_address
        inv.server_port = self.server_port
        inv.attributes = self.attributes
        inv.metric_attributes = self.metric_attributes

    @property
    def span(self) -> Span:
        """The underlying span, for back-compat with code that checks span.is_recording()."""
        return (
            self._inference_invocation.span
            if self._inference_invocation is not None
            else INVALID_SPAN
        )
