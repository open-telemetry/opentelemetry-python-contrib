# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import inspect
from timeit import default_timer
from typing import Any, Callable, Optional

from groq import Stream

from opentelemetry._logs import Logger, LogRecord
from opentelemetry.context import get_current
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.trace import Span, SpanKind, Tracer
from opentelemetry.trace.propagation import set_span_in_context
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.invocation import InferenceInvocation
from opentelemetry.util.genai.types import Error

from .chat_buffers import ChoiceBuffer
from .chat_wrappers import AsyncChatStreamWrapper, ChatStreamWrapper
from .instruments import Instruments
from .utils import (
    _GROQ_PROVIDER,
    _prepare_output_messages,
    choice_to_event,
    create_chat_invocation,
    get_llm_request_attributes,
    handle_span_exception,
    is_streaming,
    message_to_event,
    set_span_attribute,
)

_GROQ_SYSTEM = GenAIAttributes.GenAiSystemValues.GROQ.value


def chat_completions_create_v_old(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_content: bool,
) -> Callable[..., Any]:
    """Wrap the sync `Completions.create` on the legacy semconv path."""

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        span_attributes = {
            **get_llm_request_attributes(kwargs, instance, False)
        }

        operation_name = span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        model = span_attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL)
        span_name = f"{operation_name} {model}" if model else operation_name
        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            for message in kwargs.get("messages", []):
                logger.emit(message_to_event(message, capture_content))

            start = default_timer()
            result = None
            error_type = None
            try:
                result = wrapped(*args, **kwargs)
                if hasattr(result, "parse"):
                    parsed_result = result.parse()
                else:
                    parsed_result = result
                if is_streaming(kwargs):
                    return LegacyChatStreamWrapper(
                        parsed_result, span, logger, capture_content
                    )

                if span.is_recording():
                    _set_response_attributes(span, parsed_result)
                for choice in getattr(parsed_result, "choices", []):
                    logger.emit(choice_to_event(choice, capture_content))

                span.end()
                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise
            finally:
                duration = max((default_timer() - start), 0)
                _record_metrics(
                    instruments,
                    duration,
                    result,
                    span_attributes,
                    error_type,
                )

    return traced_method


def chat_completions_create_v_new(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Wrap the sync `Completions.create` on the experimental semconv path."""
    capture_content = handler.should_capture_content()

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        chat_invocation = create_chat_invocation(
            handler, kwargs, instance, capture_content=capture_content
        )

        try:
            result = wrapped(*args, **kwargs)
            if hasattr(result, "parse"):
                parsed_result = result.parse()
            else:
                parsed_result = result
            if is_streaming(kwargs):
                return ChatStreamWrapper(
                    parsed_result, chat_invocation, capture_content
                )

            _set_response_properties(
                chat_invocation, parsed_result, capture_content
            )
            chat_invocation.stop()
            return result
        except Exception as error:
            chat_invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def async_chat_completions_create_v_old(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_content: bool,
) -> Callable[..., Any]:
    """Wrap the async `AsyncCompletions.create` on the legacy semconv path."""

    async def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        span_attributes = {
            **get_llm_request_attributes(kwargs, instance, False)
        }

        operation_name = span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        model = span_attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL)
        span_name = f"{operation_name} {model}" if model else operation_name
        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            for message in kwargs.get("messages", []):
                logger.emit(message_to_event(message, capture_content))

            start = default_timer()
            result = None
            error_type = None
            try:
                result = await wrapped(*args, **kwargs)
                if hasattr(result, "parse"):
                    parsed_result = result.parse()
                else:
                    parsed_result = result
                if is_streaming(kwargs):
                    return LegacyChatStreamWrapper(
                        parsed_result, span, logger, capture_content
                    )

                if span.is_recording():
                    _set_response_attributes(span, parsed_result)
                for choice in getattr(parsed_result, "choices", []):
                    logger.emit(choice_to_event(choice, capture_content))

                span.end()
                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise
            finally:
                duration = max((default_timer() - start), 0)
                _record_metrics(
                    instruments,
                    duration,
                    result,
                    span_attributes,
                    error_type,
                )

    return traced_method


def async_chat_completions_create_v_new(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Wrap the async `AsyncCompletions.create` on the experimental path."""
    capture_content = handler.should_capture_content()

    async def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        chat_invocation = create_chat_invocation(
            handler, kwargs, instance, capture_content=capture_content
        )

        try:
            result = await wrapped(*args, **kwargs)
            if hasattr(result, "parse"):
                parsed_result = result.parse()
            else:
                parsed_result = result
            if is_streaming(kwargs):
                return AsyncChatStreamWrapper(
                    parsed_result, chat_invocation, capture_content
                )

            _set_response_properties(
                chat_invocation, parsed_result, capture_content
            )
            chat_invocation.stop()
            return result

        except Exception as error:
            chat_invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def _record_metrics(
    instruments: Instruments,
    duration: float,
    result: Any,
    request_attributes: dict[str, Any],
    error_type: Optional[str],
) -> None:
    common_attributes: dict[str, Any] = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.CHAT.value,
        GenAIAttributes.GEN_AI_SYSTEM: _GROQ_SYSTEM,
        GenAIAttributes.GEN_AI_REQUEST_MODEL: request_attributes.get(
            GenAIAttributes.GEN_AI_REQUEST_MODEL, ""
        ),
    }

    if error_type:
        common_attributes[ErrorAttributes.ERROR_TYPE] = error_type

    if result and getattr(result, "model", None):
        common_attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL] = result.model

    if ServerAttributes.SERVER_ADDRESS in request_attributes:
        common_attributes[ServerAttributes.SERVER_ADDRESS] = (
            request_attributes[ServerAttributes.SERVER_ADDRESS]
        )

    if ServerAttributes.SERVER_PORT in request_attributes:
        common_attributes[ServerAttributes.SERVER_PORT] = request_attributes[
            ServerAttributes.SERVER_PORT
        ]

    instruments.operation_duration_histogram.record(
        duration,
        attributes=common_attributes,
    )

    if result and getattr(result, "usage", None):
        input_attributes = {
            **common_attributes,
            GenAIAttributes.GEN_AI_TOKEN_TYPE: GenAIAttributes.GenAiTokenTypeValues.INPUT.value,
        }
        instruments.token_usage_histogram.record(
            result.usage.prompt_tokens,
            attributes=input_attributes,
        )

        output_attributes = {
            **common_attributes,
            GenAIAttributes.GEN_AI_TOKEN_TYPE: GenAIAttributes.GenAiTokenTypeValues.COMPLETION.value,
        }
        instruments.token_usage_histogram.record(
            result.usage.completion_tokens, attributes=output_attributes
        )


def _set_response_attributes(span: Span, result: Any) -> None:
    if getattr(result, "model", None):
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, result.model
        )

    if getattr(result, "choices", None):
        finish_reasons = []
        for choice in result.choices:
            finish_reasons.append(choice.finish_reason or "error")

        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS,
            finish_reasons,
        )

    if getattr(result, "id", None):
        set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_ID, result.id)

    if getattr(result, "usage", None):
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
            result.usage.prompt_tokens,
        )
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS,
            result.usage.completion_tokens,
        )


def _set_response_properties(
    chat_invocation: InferenceInvocation, result: Any, capture_content: bool
) -> InferenceInvocation:
    if getattr(result, "model", None):
        chat_invocation.response_model_name = result.model

    if getattr(result, "choices", None):
        finish_reasons = []
        for choice in result.choices:
            finish_reasons.append(choice.finish_reason or "error")

        chat_invocation.finish_reasons = finish_reasons

        if capture_content:  # optimization
            chat_invocation.output_messages = _prepare_output_messages(
                result.choices
            )

    if getattr(result, "id", None):
        chat_invocation.response_id = result.id

    if getattr(result, "usage", None):
        chat_invocation.input_tokens = result.usage.prompt_tokens
        chat_invocation.output_tokens = result.usage.completion_tokens

    return chat_invocation


class LegacyChatStreamWrapper:
    """Stream wrapper for the legacy semconv path.

    Mirrors the OpenAI v2 legacy wrapper: buffers streamed chunks, then
    finalizes the span and emits ``gen_ai.choice`` events on completion.
    """

    def __init__(
        self,
        stream: Stream,
        span: Span,
        logger: Logger,
        capture_content: bool,
    ) -> None:
        self.stream = stream
        self.span = span
        self.logger = logger
        self.capture_content = capture_content
        self.choice_buffers: list[ChoiceBuffer] = []
        self._started = True
        self.response_id: Optional[str] = None
        self.response_model: Optional[str] = None
        self.finish_reasons: list[str] = []
        self.prompt_tokens: Optional[int] = 0
        self.completion_tokens: Optional[int] = 0

    def __enter__(self) -> LegacyChatStreamWrapper:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        error = exc_val if exc_type else None
        self.cleanup(error)
        return False  # Propagate the exception

    async def __aenter__(self) -> LegacyChatStreamWrapper:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        error = exc_val if exc_type else None
        self.cleanup(error)
        return False  # Propagate the exception

    def close(self) -> None:
        result = self.stream.close()
        if inspect.isawaitable(result):
            # Async stream closed from a sync caller: finalize the coroutine so
            # it is not left un-awaited. Use aclose() to truly close it.
            result.close()
        self.cleanup()

    async def aclose(self) -> None:
        result = self.stream.close()
        if inspect.isawaitable(result):
            await result
        self.cleanup()

    def __iter__(self) -> LegacyChatStreamWrapper:
        return self

    def __aiter__(self) -> LegacyChatStreamWrapper:
        return self

    def __next__(self) -> Any:
        try:
            chunk = next(self.stream)
            self.process_chunk(chunk)
            return chunk
        except StopIteration:
            self.cleanup()
            raise
        except Exception as error:
            self.cleanup(error)
            raise

    async def __anext__(self) -> Any:
        try:
            chunk = await self.stream.__anext__()
            self.process_chunk(chunk)
            return chunk
        except StopAsyncIteration:
            self.cleanup()
            raise
        except Exception as error:
            self.cleanup(error)
            raise

    def set_response_model(self, chunk: Any) -> None:
        if self.response_model:
            return
        if getattr(chunk, "model", None):
            self.response_model = chunk.model

    def set_response_id(self, chunk: Any) -> None:
        if self.response_id:
            return
        if getattr(chunk, "id", None):
            self.response_id = chunk.id

    def build_streaming_response(self, chunk: Any) -> None:
        if getattr(chunk, "choices", None) is None:
            return

        for choice in chunk.choices:
            if not choice.delta:
                continue

            for idx in range(len(self.choice_buffers), choice.index + 1):
                self.choice_buffers.append(ChoiceBuffer(idx))

            if choice.finish_reason:
                self.choice_buffers[
                    choice.index
                ].finish_reason = choice.finish_reason

            if choice.delta.content is not None:
                self.choice_buffers[choice.index].append_text_content(
                    choice.delta.content
                )

            if choice.delta.tool_calls is not None:
                for tool_call in choice.delta.tool_calls:
                    self.choice_buffers[choice.index].append_tool_call(
                        tool_call
                    )

    def set_usage(self, chunk: Any) -> None:
        usage = getattr(chunk, "usage", None)
        if usage is None:
            x_groq = getattr(chunk, "x_groq", None)
            usage = getattr(x_groq, "usage", None) if x_groq else None
        if usage:
            self.completion_tokens = usage.completion_tokens
            self.prompt_tokens = usage.prompt_tokens

    def process_chunk(self, chunk: Any) -> None:
        self.set_response_id(chunk)
        self.set_response_model(chunk)
        self.build_streaming_response(chunk)
        self.set_usage(chunk)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.stream, name)

    def parse(self) -> LegacyChatStreamWrapper:
        """Called when using with_raw_response with stream=True."""
        return self

    def cleanup(self, error: Optional[BaseException] = None) -> None:
        if not self._started:
            return
        if self.span.is_recording():
            if self.response_model:
                set_span_attribute(
                    self.span,
                    GenAIAttributes.GEN_AI_RESPONSE_MODEL,
                    self.response_model,
                )

            if self.response_id:
                set_span_attribute(
                    self.span,
                    GenAIAttributes.GEN_AI_RESPONSE_ID,
                    self.response_id,
                )

            set_span_attribute(
                self.span,
                GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
                self.prompt_tokens,
            )
            set_span_attribute(
                self.span,
                GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS,
                self.completion_tokens,
            )

            set_span_attribute(
                self.span,
                GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS,
                [
                    choice.finish_reason or "error"
                    for choice in self.choice_buffers
                ],
            )

        for idx, choice in enumerate(self.choice_buffers):
            message: dict[str, Any] = {"role": "assistant"}
            if self.capture_content and choice.text_content:
                message["content"] = "".join(choice.text_content)
            if choice.tool_calls_buffers:
                tool_calls = []
                for tool_call in filter(None, choice.tool_calls_buffers):
                    function: dict[str, Any] = {
                        "name": tool_call.function_name
                    }
                    if self.capture_content:
                        function["arguments"] = "".join(tool_call.arguments)
                    tool_call_dict = {
                        "id": tool_call.tool_call_id,
                        "type": "function",
                        "function": function,
                    }
                    tool_calls.append(tool_call_dict)
                message["tool_calls"] = tool_calls

            body = {
                "index": idx,
                "finish_reason": choice.finish_reason or "error",
                "message": message,
            }

            event_attributes = {
                GenAIAttributes.GEN_AI_SYSTEM: _GROQ_SYSTEM
            }
            context = set_span_in_context(self.span, get_current())
            self.logger.emit(
                LogRecord(
                    event_name="gen_ai.choice",
                    attributes=event_attributes,
                    body=body,
                    context=context,
                )
            )

        if error:
            handle_span_exception(self.span, error)
        else:
            self.span.end()
        self._started = False


# `_GROQ_PROVIDER` is re-exported for symmetry with the openai-v2 layout.
__all__ = [
    "_GROQ_PROVIDER",
    "async_chat_completions_create_v_new",
    "async_chat_completions_create_v_old",
    "chat_completions_create_v_new",
    "chat_completions_create_v_old",
]
