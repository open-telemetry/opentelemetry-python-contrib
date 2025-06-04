import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult
from opentelemetry._events import EventLogger
from opentelemetry.context import get_current, Context
from opentelemetry.semconv._incubating.attributes import gen_ai_attributes as GenAI
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.trace import Span, SpanKind, set_span_in_context, use_span
from opentelemetry.trace.status import Status, StatusCode

from opentelemetry.instrumentation.langchain.config import Config
from opentelemetry.instrumentation.langchain.utils import (
    dont_throw,
)
from .instruments import Instruments
from .utils import (
    chat_generation_to_event,
    message_to_event,
)

logger = logging.getLogger(__name__)


@dataclass
class _SpanState:
    span: Span
    span_context: Context
    start_time: float = field(default_factory=time.time)
    request_model: Optional[str] = None
    system: Optional[str] = None
    children: List[UUID] = field(default_factory=list)


class OpenTelemetryLangChainCallbackHandler(BaseCallbackHandler):
    """
    A callback handler for LangChain that uses OpenTelemetry to create spans
    for chains, LLM calls, and tools.
    """

    def __init__(
        self,
        tracer,
        instruments: Instruments,
        event_logger: EventLogger,
    ) -> None:
        super().__init__()
        self._tracer = tracer
        self._duration_histogram = instruments.operation_duration_histogram
        self._token_histogram = instruments.token_usage_histogram
        self._event_logger = event_logger

        # Map from run_id -> _SpanState, to keep track of spans and parent/child relationships
        self.spans: Dict[UUID, _SpanState] = {}
        self.run_inline = True  # Whether to run the callback inline.

    def _start_span(
        self,
        name: str,
        kind: SpanKind,
        parent_run_id: Optional[UUID] = None,
    ) -> Span:
        if parent_run_id is not None and parent_run_id in self.spans:
            parent_span = self.spans[parent_run_id].span
            ctx = set_span_in_context(parent_span)
            span = self._tracer.start_span(name=name, kind=kind, context=ctx)
        else:
            # top-level or missing parent
            span = self._tracer.start_span(name=name, kind=kind)

        return span

    def _end_span(self, run_id: UUID):
        state = self.spans[run_id]
        for child_id in state.children:
            child_state = self.spans.get(child_id)
            if child_state and child_state.span.end_time is None:
                child_state.span.end()
        if state.span.end_time is None:
            state.span.end()

    def _record_duration_metric(self, run_id: UUID, request_model: Optional[str], response_model: Optional[str], operation_name: Optional[str], system: Optional[str]):
        """
        Records a histogram measurement for how long the operation took.
        """
        if run_id not in self.spans:
            return

        elapsed = time.time() - self.spans[run_id].start_time
        attributes = {
            # TODO: add below to opentelemetry.semconv._incubating.attributes.gen_ai_attributes
            "gen_ai.framework":"langchain",
        }
        if system:
            attributes[GenAI.GEN_AI_SYSTEM] = system
        if operation_name:
            attributes[GenAI.GEN_AI_OPERATION_NAME] = operation_name
        if request_model:
            attributes[GenAI.GEN_AI_REQUEST_MODEL] = request_model
        if response_model:
             attributes[GenAI.GEN_AI_RESPONSE_MODEL] = response_model

        self._duration_histogram.record(elapsed, attributes=attributes)

    def _record_token_usage(self, token_count: int, request_model: Optional[str], response_model: Optional[str], token_type: str, operation_name: Optional[str], system: Optional[str]):
        """
        Record usage of input or output tokens to a histogram.
        """
        if token_count <= 0:
            return
        attributes = {
            # TODO: add below to opentelemetry.semconv._incubating.attributes.gen_ai_attributes
            "gen_ai.framework": "langchain",
            GenAI.GEN_AI_TOKEN_TYPE: token_type,
        }
        if system:
            attributes[GenAI.GEN_AI_SYSTEM] = system
        if operation_name:
            attributes[GenAI.GEN_AI_OPERATION_NAME] = operation_name
        if request_model:
            attributes[GenAI.GEN_AI_REQUEST_MODEL] = request_model
        if response_model:
            attributes[GenAI.GEN_AI_RESPONSE_MODEL] = response_model

        self._token_histogram.record(token_count, attributes=attributes)

    @dont_throw
    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Union[UUID, None] = None,
        **kwargs,
    ):
        if Config.is_instrumentation_suppressed():
            return

        state = self.spans.get(run_id)
        if not state:
            return

        with use_span(
            state.span,
            end_on_exit=False,
        ) as span:
            finish_reasons = []
            for generation in getattr(response, "generations", []):
                for index, chat_generation in enumerate(generation):
                    self._event_logger.emit(chat_generation_to_event(chat_generation, index, state.system))
                    generation_info = chat_generation.generation_info
                    if generation_info is not None:
                        finish_reason = generation_info.get("finish_reason")
                        if finish_reason is not None:
                            finish_reasons.append(finish_reason or "error")

            span.set_attribute(GenAI.GEN_AI_RESPONSE_FINISH_REASONS, finish_reasons)

            response_model = None
            if response.llm_output is not None:
                response_model = response.llm_output.get("model_name") or response.llm_output.get("model")
                if response_model is not None:
                    span.set_attribute(GenAI.GEN_AI_RESPONSE_MODEL, response_model)

                response_id = response.llm_output.get("id")
                if response_id is not None:
                    span.set_attribute(GenAI.GEN_AI_RESPONSE_ID, response_id)

                # usage
                usage = response.llm_output.get("usage") or response.llm_output.get("token_usage")
                if usage:
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                    span.set_attribute(GenAI.GEN_AI_USAGE_INPUT_TOKENS, prompt_tokens)
                    span.set_attribute(GenAI.GEN_AI_USAGE_OUTPUT_TOKENS, completion_tokens)

                    # Record token usage metrics
                    self._record_token_usage(prompt_tokens, state.request_model, response_model, GenAI.GenAiTokenTypeValues.INPUT.value, GenAI.GenAiOperationNameValues.CHAT.value, state.system)
                    self._record_token_usage(completion_tokens, state.request_model, response_model, GenAI.GenAiTokenTypeValues.COMPLETION.value, GenAI.GenAiOperationNameValues.CHAT.value, state.system)

            # End the LLM span
            self._end_span(run_id)

            # Record overall duration metric
            self._record_duration_metric(run_id, state.request_model, response_model, GenAI.GenAiOperationNameValues.CHAT.value, state.system)

    @dont_throw
    def on_chat_model_start(
        self,
        serialized: dict,
        messages: List[List[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs,
    ):
        if Config.is_instrumentation_suppressed():
            return

        system = serialized.get("name") or kwargs.get("name") or "ChatLLM"
        span = self._start_span(
            name=f"{system}.chat",
            kind=SpanKind.CLIENT,
            parent_run_id=parent_run_id,
        )

        with use_span(
            span,
            end_on_exit=False,
        ) as span:
            span.set_attribute(GenAI.GEN_AI_OPERATION_NAME, GenAI.GenAiOperationNameValues.CHAT.value)
            request_model = kwargs.get("invocation_params").get("model_name") if kwargs.get("invocation_params") and kwargs.get("invocation_params").get("model_name") else None
            span.set_attribute(GenAI.GEN_AI_REQUEST_MODEL, request_model)

            # TODO: add below to opentelemetry.semconv._incubating.attributes.gen_ai_attributes
            span.set_attribute("gen_ai.framework", "langchain")
            span.set_attribute(GenAI.GEN_AI_SYSTEM, system)

            span_state = _SpanState(span=span, span_context=get_current(), request_model=request_model, system=system)
            self.spans[run_id] = span_state

            for sub_messages in messages:
                for message in sub_messages:
                    self._event_logger.emit(message_to_event(message, system))

            if parent_run_id is not None and parent_run_id in self.spans:
                self.spans[parent_run_id].children.append(run_id)


    @dont_throw
    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs,
    ):
        self._handle_error(error, run_id)


    def _handle_error(self, error: BaseException, run_id: UUID):
        if Config.is_instrumentation_suppressed():
            return
        state = self.spans.get(run_id)

        if not state:
            return

        # Record overall duration metric
        self._record_duration_metric(run_id, state.request_model, None, GenAI.GenAiOperationNameValues.CHAT.value, state.system)

        span = state.span
        span.set_status(Status(StatusCode.ERROR, str(error)))
        if span.is_recording():
            span.set_attribute(
                ErrorAttributes.ERROR_TYPE, type(error).__qualname__
            )
        self._end_span(run_id)