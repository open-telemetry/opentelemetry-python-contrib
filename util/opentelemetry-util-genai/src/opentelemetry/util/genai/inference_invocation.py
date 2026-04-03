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
from typing import Any

from typing_extensions import deprecated

from opentelemetry._logs import Logger, LogRecord
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import server_attributes
from opentelemetry.trace import (
    INVALID_SPAN,
    SpanKind,
    Tracer,
    set_span_in_context,
)
from opentelemetry.util.genai._invocation import Error, GenAIInvocation
from opentelemetry.util.genai.metrics import InvocationMetricsRecorder
from opentelemetry.util.genai.types import (
    InputMessage,
    MessagePart,
    OutputMessage,
)
from opentelemetry.util.genai.utils import (
    ContentCapturingMode,
    gen_ai_json_dumps,
    get_content_capturing_mode,
    is_experimental_mode,
    should_emit_event,
)


class InferenceInvocation(GenAIInvocation):
    """Represents a single LLM chat/completion call.

    Use handler.start_inference(provider) or the handler.inference(provider)
    context manager rather than constructing this directly.
    """

    def __init__(  # pylint: disable=too-many-locals
        self,
        tracer: Tracer,
        metrics_recorder: InvocationMetricsRecorder,
        logger: Logger,
        provider: str,
        *,
        request_model: str | None = None,
        input_messages: list[InputMessage] | None = None,
        output_messages: list[OutputMessage] | None = None,
        system_instruction: list[MessagePart] | None = None,
        response_model_name: str | None = None,
        response_id: str | None = None,
        finish_reasons: list[str] | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
        max_tokens: int | None = None,
        stop_sequences: list[str] | None = None,
        seed: int | None = None,
        server_address: str | None = None,
        server_port: int | None = None,
        attributes: dict[str, Any] | None = None,
        metric_attributes: dict[str, Any] | None = None,
    ) -> None:
        """Use handler.start_inference(provider) or handler.inference(provider) instead of calling this directly."""
        _operation_name = GenAI.GenAiOperationNameValues.CHAT.value
        super().__init__(
            tracer,
            metrics_recorder,
            logger,
            operation_name=_operation_name,
            span_name=f"{_operation_name} {request_model}"
            if request_model
            else _operation_name,
            span_kind=SpanKind.CLIENT,
            attributes=attributes,
            metric_attributes=metric_attributes,
        )
        self.provider = provider
        self.request_model = request_model
        self.input_messages: list[InputMessage] = (
            [] if input_messages is None else input_messages
        )
        self.output_messages: list[OutputMessage] = (
            [] if output_messages is None else output_messages
        )
        self.system_instruction: list[MessagePart] = (
            [] if system_instruction is None else system_instruction
        )
        self.response_model_name = response_model_name
        self.response_id = response_id
        self.finish_reasons = finish_reasons
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.frequency_penalty = frequency_penalty
        self.presence_penalty = presence_penalty
        self.max_tokens = max_tokens
        self.stop_sequences = stop_sequences
        self.seed = seed
        self.server_address = server_address
        self.server_port = server_port
        self._start()

    def _get_message_attributes(self, *, for_span: bool) -> dict[str, Any]:
        if not is_experimental_mode():
            return {}
        mode = get_content_capturing_mode()
        allowed_modes = (
            (
                ContentCapturingMode.SPAN_ONLY,
                ContentCapturingMode.SPAN_AND_EVENT,
            )
            if for_span
            else (
                ContentCapturingMode.EVENT_ONLY,
                ContentCapturingMode.SPAN_AND_EVENT,
            )
        )
        if mode not in allowed_modes:
            return {}

        def serialize(items: list[Any]) -> Any:
            dicts = [asdict(item) for item in items]
            return gen_ai_json_dumps(dicts) if for_span else dicts

        optional_attrs = (
            (
                GenAI.GEN_AI_INPUT_MESSAGES,
                serialize(self.input_messages)
                if self.input_messages
                else None,
            ),
            (
                GenAI.GEN_AI_OUTPUT_MESSAGES,
                serialize(self.output_messages)
                if self.output_messages
                else None,
            ),
            (
                GenAI.GEN_AI_SYSTEM_INSTRUCTIONS,
                serialize(self.system_instruction)
                if self.system_instruction
                else None,
            ),
        )
        return {
            key: value for key, value in optional_attrs if value is not None
        }

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
            (GenAI.GEN_AI_USAGE_OUTPUT_TOKENS, self.output_tokens),
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
        self._metrics_recorder.record(self)  # pyright: ignore[reportOptionalMemberAccess]
        self._emit_event()

    def _emit_event(self) -> None:
        """Emit a gen_ai.client.inference.operation.details event.

        For more details, see the semantic convention documentation:
        https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-events.md#event-eventgen_aiclientinferenceoperationdetails
        """
        if not is_experimental_mode() or not should_emit_event():
            return

        attributes = self._get_attributes()
        attributes.update(self._get_message_attributes(for_span=False))
        attributes.update(self.attributes)
        self._logger.emit(  # pyright: ignore[reportOptionalMemberAccess]
            LogRecord(
                event_name="gen_ai.client.inference.operation.details",
                attributes=attributes,
                context=self._span_context,
            )
        )


@deprecated("LLMInvocation is deprecated. Use InferenceInvocation instead.")
class LLMInvocation(InferenceInvocation):
    """Deprecated. Use InferenceInvocation instead."""

    def __init__(  # pylint: disable=too-many-locals
        self,
        tracer: Tracer | None = None,
        metrics_recorder: InvocationMetricsRecorder | None = None,
        logger: Logger | None = None,
        provider: str = "",
        *,
        request_model: str | None = None,
        input_messages: list[InputMessage] | None = None,
        output_messages: list[OutputMessage] | None = None,
        system_instruction: list[MessagePart] | None = None,
        response_model_name: str | None = None,
        response_id: str | None = None,
        finish_reasons: list[str] | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
        max_tokens: int | None = None,
        stop_sequences: list[str] | None = None,
        seed: int | None = None,
        server_address: str | None = None,
        server_port: int | None = None,
        attributes: dict[str, Any] | None = None,
        metric_attributes: dict[str, Any] | None = None,
    ) -> None:
        if tracer is not None:
            super().__init__(
                tracer,
                metrics_recorder,  # pyright: ignore[reportArgumentType]
                logger,  # pyright: ignore[reportArgumentType]
                provider,
                request_model=request_model,
                input_messages=input_messages,
                output_messages=output_messages,
                system_instruction=system_instruction,
                response_model_name=response_model_name,
                response_id=response_id,
                finish_reasons=finish_reasons,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                temperature=temperature,
                top_p=top_p,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                max_tokens=max_tokens,
                stop_sequences=stop_sequences,
                seed=seed,
                server_address=server_address,
                server_port=server_port,
                attributes=attributes,
                metric_attributes=metric_attributes,
            )
            return
        # Old-style: data container, started later via handler.start_llm()
        # _tracer/_metrics_recorder/_logger are set by _start_with_handler() in that case
        self._operation_name = GenAI.GenAiOperationNameValues.CHAT.value
        self._tracer = None
        self._metrics_recorder = None
        self._logger = None
        self.attributes = {} if attributes is None else attributes
        self.metric_attributes = (
            {} if metric_attributes is None else metric_attributes
        )
        self.span = INVALID_SPAN
        self._span_context = set_span_in_context(INVALID_SPAN)
        self._span_kind = SpanKind.CLIENT
        self._context_token = None
        self._monotonic_start_s = None
        self.provider = provider
        self.request_model = request_model
        self.input_messages = [] if input_messages is None else input_messages
        self.output_messages = (
            [] if output_messages is None else output_messages
        )
        self.system_instruction = (
            [] if system_instruction is None else system_instruction
        )
        self.response_model_name = response_model_name
        self.response_id = response_id
        self.finish_reasons = finish_reasons
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.frequency_penalty = frequency_penalty
        self.presence_penalty = presence_penalty
        self.max_tokens = max_tokens
        self.stop_sequences = stop_sequences
        self.seed = seed
        self.server_address = server_address
        self.server_port = server_port
        self._span_name = (
            f"{self._operation_name} {request_model}"
            if request_model
            else self._operation_name
        )

    @property
    def invocation(self) -> "LLMInvocation | None":  # pyright: ignore[reportDeprecated]
        """Returns self once started, None before handler.start_llm() is called."""
        return self if self._context_token is not None else None

    def _start_with_handler(
        self,
        tracer: Tracer,
        metrics_recorder: InvocationMetricsRecorder,
        logger: Logger,
    ) -> None:
        """Attach telemetry components and start the span. Called by handler.start_llm()."""
        self._tracer = tracer
        self._metrics_recorder = metrics_recorder
        self._logger = logger
        self._start()
