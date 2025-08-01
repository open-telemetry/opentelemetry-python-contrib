import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler  # type: ignore
from langchain_core.messages import BaseMessage  # type: ignore
from langchain_core.outputs import LLMResult  # type: ignore

from opentelemetry.context import Context, get_current
from opentelemetry.instrumentation.langchain.utils import dont_throw
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.trace import Span, SpanKind, Tracer, set_span_in_context
from opentelemetry.trace.status import Status, StatusCode


@dataclass
class _SpanState:
    span: Span
    span_context: Context
    start_time: float = field(default_factory=time.time)
    children: List[UUID] = field(default_factory=list)


class OpenTelemetryLangChainCallbackHandler(BaseCallbackHandler):  # type: ignore[misc]
    """
    A callback handler for LangChain that uses OpenTelemetry to create spans for LLM calls and chains, tools etc,. in future.
    """

    def __init__(
        self,
        tracer: Tracer,
    ) -> None:
        super().__init__()  # type: ignore
        self._tracer = tracer

        # Map from run_id -> _SpanState, to keep track of spans and parent/child relationships
        self.spans: Dict[UUID, _SpanState] = {}
        self.run_inline = True  # Whether to run the callback inline.

    def _create_span(
        self,
        run_id: UUID,
        parent_run_id: Optional[UUID],
        span_name: str,
        kind: SpanKind = SpanKind.INTERNAL,
    ) -> Span:
        if parent_run_id is not None and parent_run_id in self.spans:
            parent_span = self.spans[parent_run_id].span
            ctx = set_span_in_context(parent_span)
            span = self._tracer.start_span(
                name=span_name, kind=kind, context=ctx
            )
        else:
            # top-level or missing parent
            span = self._tracer.start_span(name=span_name, kind=kind)

        span_state = _SpanState(span=span, span_context=get_current())
        self.spans[run_id] = span_state

        if parent_run_id is not None and parent_run_id in self.spans:
            self.spans[parent_run_id].children.append(run_id)

        return span

    def _create_llm_span(
        self,
        run_id: UUID,
        parent_run_id: Optional[UUID],
        name: str,
    ) -> Span:
        span = self._create_span(
            run_id=run_id,
            parent_run_id=parent_run_id,
            span_name=f"{name}.{GenAI.GenAiOperationNameValues.CHAT.value}",
            kind=SpanKind.CLIENT,
        )
        span.set_attribute(
            GenAI.GEN_AI_OPERATION_NAME,
            GenAI.GenAiOperationNameValues.CHAT.value,
        )
        span.set_attribute(GenAI.GEN_AI_SYSTEM, name)

        return span

    def _end_span(self, run_id: UUID) -> None:
        state = self.spans[run_id]
        for child_id in state.children:
            child_state = self.spans.get(child_id)
            if child_state:
                # Always end child spans as OpenTelemetry spans don't expose end_time directly
                child_state.span.end()
            # Always end the span as OpenTelemetry spans don't expose end_time directly
        state.span.end()

    def _get_span(self, run_id: UUID) -> Span:
        return self.spans[run_id].span

    @dont_throw
    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[BaseMessage]],  # type: ignore
        *,
        run_id: UUID,
        tags: Optional[List[str]] = None,
        parent_run_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        name = serialized.get("name") or kwargs.get("name") or "ChatLLM"
        span = self._create_llm_span(
            run_id=run_id,
            parent_run_id=parent_run_id,
            name=name,
        )

        invocation_params = kwargs.get("invocation_params")
        if invocation_params is not None:
            request_model = invocation_params.get("model_name")
            if request_model is not None:
                span.set_attribute(GenAI.GEN_AI_REQUEST_MODEL, request_model)
            top_p = invocation_params.get("top_p")
            if top_p is not None:
                span.set_attribute(GenAI.GEN_AI_REQUEST_TOP_P, top_p)
            frequency_penalty = invocation_params.get("frequency_penalty")
            if frequency_penalty is not None:
                span.set_attribute(
                    GenAI.GEN_AI_REQUEST_FREQUENCY_PENALTY, frequency_penalty
                )
            presence_penalty = invocation_params.get("presence_penalty")
            if presence_penalty is not None:
                span.set_attribute(
                    GenAI.GEN_AI_REQUEST_PRESENCE_PENALTY, presence_penalty
                )
            stop_sequences = invocation_params.get("stop")
            if stop_sequences is not None:
                span.set_attribute(
                    GenAI.GEN_AI_REQUEST_STOP_SEQUENCES, stop_sequences
                )
            seed = invocation_params.get("seed")
            if seed is not None:
                span.set_attribute(GenAI.GEN_AI_REQUEST_SEED, seed)

        if metadata is not None:
            max_tokens = metadata.get("ls_max_tokens")
            if max_tokens is not None:
                span.set_attribute(GenAI.GEN_AI_REQUEST_MAX_TOKENS, max_tokens)
            provider = metadata.get("ls_provider")
            if provider is not None:
                # TODO: add to semantic conventions
                span.set_attribute("gen_ai.provider.name", provider)
            temperature = metadata.get("ls_temperature")
            if temperature is not None:
                span.set_attribute(
                    GenAI.GEN_AI_REQUEST_TEMPERATURE, temperature
                )

    @dont_throw
    def on_llm_end(
        self,
        response: LLMResult,  # type: ignore
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        span = self._get_span(run_id)

        finish_reasons: List[str] = []
        for generation in getattr(response, "generations", []):  # type: ignore
            for chat_generation in generation:
                generation_info = getattr(
                    chat_generation, "generation_info", None
                )
                if generation_info is not None:
                    finish_reason = generation_info.get("finish_reason")
                    if finish_reason is not None:
                        finish_reasons.append(str(finish_reason) or "error")

        span.set_attribute(
            GenAI.GEN_AI_RESPONSE_FINISH_REASONS, finish_reasons
        )

        llm_output = getattr(response, "llm_output", None)  # type: ignore
        if llm_output is not None:
            response_model = llm_output.get("model_name") or llm_output.get(
                "model"
            )
            if response_model is not None:
                span.set_attribute(
                    GenAI.GEN_AI_RESPONSE_MODEL, str(response_model)
                )

            response_id = llm_output.get("id")
            if response_id is not None:
                span.set_attribute(GenAI.GEN_AI_RESPONSE_ID, str(response_id))

            # usage
            usage = llm_output.get("usage") or llm_output.get("token_usage")
            if usage:
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                span.set_attribute(
                    GenAI.GEN_AI_USAGE_INPUT_TOKENS,
                    int(prompt_tokens) if prompt_tokens is not None else 0,
                )
                span.set_attribute(
                    GenAI.GEN_AI_USAGE_OUTPUT_TOKENS,
                    int(completion_tokens)
                    if completion_tokens is not None
                    else 0,
                )

        # End the LLM span
        self._end_span(run_id)

    @dont_throw
    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        self._handle_error(error, run_id)

    def _handle_error(self, error: BaseException, run_id: UUID):
        span = self._get_span(run_id)
        span.set_status(Status(StatusCode.ERROR, str(error)))
        span.set_attribute(
            ErrorAttributes.ERROR_TYPE, type(error).__qualname__
        )
        self._end_span(run_id)
