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


import json
from timeit import default_timer
from typing import Any, Optional

from openai import Stream

from opentelemetry._logs import Logger, LogRecord
from opentelemetry.context import get_current
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    openai_attributes as OpenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.trace import Span, SpanKind, Tracer
from opentelemetry.trace.propagation import set_span_in_context
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import (
    ContentCapturingMode,
    Error,
    LLMInvocation,
    OutputMessage,
    Text,
    ToolCall,
)

from .instruments import Instruments
from .utils import (
    _prepare_output_messages,
    choice_to_event,
    create_chat_invocation,
    get_llm_request_attributes,
    handle_span_exception,
    is_streaming,
    message_to_event,
    set_span_attribute,
)


def chat_completions_create_v_old(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `create` method of the `ChatCompletion` class to trace it."""

    def traced_method(wrapped, instance, args, kwargs):
        span_attributes = {
            **get_llm_request_attributes(kwargs, instance, False)
        }

        span_name = f"{span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]} {span_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]}"
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
                    # result is of type LegacyAPIResponse, call parse to get the actual response
                    parsed_result = result.parse()
                else:
                    parsed_result = result
                if is_streaming(kwargs):
                    return StreamWrapperOld(
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
                    GenAIAttributes.GenAiOperationNameValues.CHAT.value,
                )

    return traced_method


def chat_completions_create_v_new(
    handler: TelemetryHandler,
    content_capturing_mode: ContentCapturingMode,
):
    """Wrap the `create` method of the `ChatCompletion` class to trace it."""

    capture_content = content_capturing_mode != ContentCapturingMode.NO_CONTENT

    def traced_method(wrapped, instance, args, kwargs):
        chat_invocation = handler.start_llm(
            create_chat_invocation(
                kwargs, instance, capture_content=capture_content
            )
        )

        try:
            result = wrapped(*args, **kwargs)
            if hasattr(result, "parse"):
                # result is of type LegacyAPIResponse, call parse to get the actual response
                parsed_result = result.parse()
            else:
                parsed_result = result
            if is_streaming(kwargs):
                return StreamWrapperNew(
                    parsed_result, handler, chat_invocation, capture_content
                )

            _set_response_properties(
                chat_invocation, parsed_result, capture_content
            )
            handler.stop_llm(chat_invocation)
            return result
        except Exception as error:
            handler.fail_llm(
                chat_invocation, Error(type=type(error), message=str(error))
            )
            raise

    return traced_method


def async_chat_completions_create_v_old(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `create` method of the `AsyncChatCompletion` class to trace it."""

    async def traced_method(wrapped, instance, args, kwargs):
        span_attributes = {
            **get_llm_request_attributes(kwargs, instance, False)
        }

        span_name = f"{span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]} {span_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]}"
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
                    # result is of type LegacyAPIResponse, calling parse to get the actual response
                    parsed_result = result.parse()
                else:
                    parsed_result = result
                if is_streaming(kwargs):
                    return StreamWrapperOld(
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
                    GenAIAttributes.GenAiOperationNameValues.CHAT.value,
                )

    return traced_method


def async_chat_completions_create_v_new(
    handler: TelemetryHandler,
    content_capturing_mode: ContentCapturingMode,
):
    """Wrap the `create` method of the `AsyncChatCompletion` class to trace it."""
    capture_content = content_capturing_mode != ContentCapturingMode.NO_CONTENT

    async def traced_method(wrapped, instance, args, kwargs):
        chat_invocation = handler.start_llm(
            create_chat_invocation(
                kwargs, instance, capture_content=capture_content
            )
        )

        try:
            result = await wrapped(*args, **kwargs)
            if hasattr(result, "parse"):
                # result is of type LegacyAPIResponse, calling parse to get the actual response
                parsed_result = result.parse()
            else:
                parsed_result = result
            if is_streaming(kwargs):
                return StreamWrapperNew(
                    parsed_result, handler, chat_invocation, capture_content
                )

            _set_response_properties(
                chat_invocation, parsed_result, capture_content
            )
            handler.stop_llm(chat_invocation)
            return result

        except Exception as error:
            handler.fail_llm(
                chat_invocation, Error(type=type(error), message=str(error))
            )
            raise

    return traced_method


def embeddings_create(
    tracer: Tracer,
    instruments: Instruments,
    latest_experimental_enabled: bool,
):
    """Wrap the `create` method of the `Embeddings` class to trace it."""

    def traced_method(wrapped, instance, args, kwargs):
        span_attributes = get_llm_request_attributes(
            kwargs,
            instance,
            latest_experimental_enabled,
            GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value,
        )
        span_name = _get_embeddings_span_name(span_attributes)

        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=True,
        ) as span:
            start = default_timer()
            result = None
            error_type = None

            try:
                result = wrapped(*args, **kwargs)

                if span.is_recording():
                    _set_embeddings_response_attributes(span, result)

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
                    GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value,
                )

    return traced_method


def async_embeddings_create(
    tracer: Tracer,
    instruments: Instruments,
    latest_experimental_enabled: bool,
):
    """Wrap the `create` method of the `AsyncEmbeddings` class to trace it."""

    async def traced_method(wrapped, instance, args, kwargs):
        span_attributes = get_llm_request_attributes(
            kwargs,
            instance,
            latest_experimental_enabled,
            GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value,
        )
        span_name = _get_embeddings_span_name(span_attributes)

        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=True,
        ) as span:
            start = default_timer()
            result = None
            error_type = None

            try:
                result = await wrapped(*args, **kwargs)

                if span.is_recording():
                    _set_embeddings_response_attributes(span, result)

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
                    GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value,
                )

    return traced_method


def _get_embeddings_span_name(span_attributes):
    """Get span name for embeddings operations."""
    return f"{span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]} {span_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]}"


def _record_metrics(
    instruments: Instruments,
    duration: float,
    result,
    request_attributes: dict,
    error_type: Optional[str],
    operation_name: str,
):
    common_attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: operation_name,
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value,
        GenAIAttributes.GEN_AI_REQUEST_MODEL: request_attributes[
            GenAIAttributes.GEN_AI_REQUEST_MODEL
        ],
    }

    if "gen_ai.embeddings.dimension.count" in request_attributes:
        common_attributes["gen_ai.embeddings.dimension.count"] = (
            request_attributes["gen_ai.embeddings.dimension.count"]
        )

    if error_type:
        common_attributes["error.type"] = error_type

    if result and getattr(result, "model", None):
        common_attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL] = result.model

    if result and getattr(result, "service_tier", None):
        common_attributes[
            GenAIAttributes.GEN_AI_OPENAI_RESPONSE_SERVICE_TIER
        ] = result.service_tier

    if result and getattr(result, "system_fingerprint", None):
        common_attributes[
            GenAIAttributes.GEN_AI_OPENAI_RESPONSE_SYSTEM_FINGERPRINT
        ] = result.system_fingerprint

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
        # Always record input tokens
        input_attributes = {
            **common_attributes,
            GenAIAttributes.GEN_AI_TOKEN_TYPE: GenAIAttributes.GenAiTokenTypeValues.INPUT.value,
        }
        instruments.token_usage_histogram.record(
            result.usage.prompt_tokens,
            attributes=input_attributes,
        )

        # For embeddings, don't record output tokens as all tokens are input tokens
        if (
            operation_name
            != GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value
        ):
            output_attributes = {
                **common_attributes,
                GenAIAttributes.GEN_AI_TOKEN_TYPE: GenAIAttributes.GenAiTokenTypeValues.COMPLETION.value,
            }
            instruments.token_usage_histogram.record(
                result.usage.completion_tokens, attributes=output_attributes
            )


def _set_response_attributes(span, result):
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

    if getattr(result, "service_tier", None):
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_OPENAI_RESPONSE_SERVICE_TIER,
            result.service_tier,
        )

    # Get the usage
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
    chat_invocation: LLMInvocation, result, capture_content: bool
) -> LLMInvocation:
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

    if getattr(result, "service_tier", None):
        chat_invocation.attributes.update(
            {
                OpenAIAttributes.OPENAI_RESPONSE_SERVICE_TIER: result.service_tier
            },
        )
        chat_invocation.metric_attributes.update(
            {
                OpenAIAttributes.OPENAI_RESPONSE_SERVICE_TIER: result.service_tier
            },
        )

    if getattr(result, "usage", None):
        chat_invocation.input_tokens = result.usage.prompt_tokens
        chat_invocation.output_tokens = result.usage.completion_tokens

    if getattr(result, "system_fingerprint", None):
        chat_invocation.attributes.update(
            {
                OpenAIAttributes.OPENAI_RESPONSE_SYSTEM_FINGERPRINT: result.system_fingerprint
            },
        )
        chat_invocation.metric_attributes.update(
            {
                OpenAIAttributes.OPENAI_RESPONSE_SYSTEM_FINGERPRINT: result.system_fingerprint
            },
        )

    return chat_invocation


def _set_embeddings_response_attributes(
    span: Span,
    result: Any,
):
    set_span_attribute(
        span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, result.model
    )

    # Set embeddings dimensions if we can determine it from the response
    if getattr(result, "data", None) and len(result.data) > 0:
        first_embedding = result.data[0]
        if getattr(first_embedding, "embedding", None):
            set_span_attribute(
                span,
                "gen_ai.embeddings.dimension.count",
                len(first_embedding.embedding),
            )

    # Get the usage
    if getattr(result, "usage", None):
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
            result.usage.prompt_tokens,
        )
        # Don't set output tokens for embeddings as all tokens are input tokens


class ToolCallBuffer:
    def __init__(self, index, tool_call_id, function_name):
        self.index = index
        self.function_name = function_name
        self.tool_call_id = tool_call_id
        self.arguments = []

    def append_arguments(self, arguments):
        self.arguments.append(arguments)


class ChoiceBuffer:
    def __init__(self, index):
        self.index = index
        self.finish_reason = None
        self.text_content = []
        self.tool_calls_buffers = []

    def append_text_content(self, content):
        self.text_content.append(content)

    def append_tool_call(self, tool_call):
        idx = tool_call.index
        # make sure we have enough tool call buffers
        for _ in range(len(self.tool_calls_buffers), idx + 1):
            self.tool_calls_buffers.append(None)

        if not self.tool_calls_buffers[idx]:
            self.tool_calls_buffers[idx] = ToolCallBuffer(
                idx, tool_call.id, tool_call.function.name
            )
        self.tool_calls_buffers[idx].append_arguments(
            tool_call.function.arguments
        )


class BaseStreamWrapper:
    response_id: Optional[str] = None
    response_model: Optional[str] = None
    service_tier: Optional[str] = None
    finish_reasons: list = []
    prompt_tokens: Optional[int] = 0
    completion_tokens: Optional[int] = 0

    def __init__(
        self,
        stream: Stream,
        capture_content: bool,
    ):
        self.stream = stream
        self.choice_buffers = []
        self._started = False
        self.capture_content = capture_content
        self._setup()

    def _setup(self):
        if not self._started:
            self._started = True

    def cleanup(self, error: Optional[Error] = None):
        pass

    def __enter__(self):
        self._setup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        error = None
        try:
            if exc_type is not None:
                error = Error(message=str(exc_val), type=exc_type)
        finally:
            self.cleanup(error)
        return False  # Propagate the exception

    async def __aenter__(self):
        self._setup()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        error = None
        try:
            if exc_type is not None:
                error = Error(message=str(exc_val), type=exc_type)
        finally:
            self.cleanup(error)
        return False  # Propagate the exception

    def close(self):
        self.stream.close()
        self.cleanup()

    def __iter__(self):
        return self

    def __aiter__(self):
        return self

    def __next__(self):
        try:
            chunk = next(self.stream)
            self.process_chunk(chunk)
            return chunk
        except StopIteration:
            self.cleanup()
            raise
        except Exception as error:
            self.cleanup(Error(message=str(error), type=type(error)))
            raise

    async def __anext__(self):
        try:
            chunk = await self.stream.__anext__()
            self.process_chunk(chunk)
            return chunk
        except StopAsyncIteration:
            self.cleanup()
            raise
        except Exception as error:
            self.cleanup(Error(message=str(error), type=type(error)))
            raise

    def set_response_model(self, chunk):
        if self.response_model:
            return

        if getattr(chunk, "model", None):
            self.response_model = chunk.model

    def set_response_id(self, chunk):
        if self.response_id:
            return

        if getattr(chunk, "id", None):
            self.response_id = chunk.id

    def set_response_service_tier(self, chunk):
        if self.service_tier:
            return

        if getattr(chunk, "service_tier", None):
            self.service_tier = chunk.service_tier

    def build_streaming_response(self, chunk):
        if getattr(chunk, "choices", None) is None:
            return

        choices = chunk.choices
        for choice in choices:
            if not choice.delta:
                continue

            # make sure we have enough choice buffers
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

    def set_usage(self, chunk):
        if getattr(chunk, "usage", None):
            self.completion_tokens = chunk.usage.completion_tokens
            self.prompt_tokens = chunk.usage.prompt_tokens

    def process_chunk(self, chunk):
        self.set_response_id(chunk)
        self.set_response_model(chunk)
        self.set_response_service_tier(chunk)
        self.build_streaming_response(chunk)
        self.set_usage(chunk)

    def parse(self):
        """Called when using with_raw_response with stream=True"""
        return self


class StreamWrapperOld(BaseStreamWrapper):
    span: Span
    response_id: Optional[str] = None
    response_model: Optional[str] = None
    service_tier: Optional[str] = None
    finish_reasons: list = []
    prompt_tokens: Optional[int] = 0
    completion_tokens: Optional[int] = 0

    def __init__(
        self,
        stream: Stream,
        span: Span,
        logger: Logger,
        capture_content: bool,
    ):
        super().__init__(stream, capture_content=capture_content)
        self.span = span
        self.logger = logger

    def cleanup(self, error: Optional[Error] = None):
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
            if self.service_tier:
                set_span_attribute(
                    self.span,
                    GenAIAttributes.GEN_AI_OPENAI_RESPONSE_SERVICE_TIER,
                    self.service_tier,
                )

            set_span_attribute(
                self.span,
                GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS,
                self.finish_reasons,
            )

        for idx, choice in enumerate(self.choice_buffers):
            message = {"role": "assistant"}
            if self.capture_content and choice.text_content:
                message["content"] = "".join(choice.text_content)
            if choice.tool_calls_buffers:
                tool_calls = []
                for tool_call in choice.tool_calls_buffers:
                    function = {"name": tool_call.function_name}
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
                GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value
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


class StreamWrapperNew(BaseStreamWrapper):
    handler: TelemetryHandler
    invocation: LLMInvocation
    response_id: Optional[str] = None
    response_model: Optional[str] = None
    service_tier: Optional[str] = None
    finish_reasons: list = []
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None

    def __init__(
        self,
        stream: Stream,
        handler: TelemetryHandler,
        invocation: LLMInvocation,
        capture_content: bool,
    ):
        super().__init__(stream, capture_content=capture_content)
        self.stream = stream
        self.handler = handler
        self.invocation = invocation
        self.choice_buffers = []

    def _set_output_messages(self):
        if not self.capture_content:  # optimization
            return
        output_messages = []
        for choice in self.choice_buffers:
            message = OutputMessage(
                role="assistant",
                finish_reason=choice.finish_reason or "error",
                parts=[],
            )
            if choice.text_content:
                message.parts.append(
                    Text(content="".join(choice.text_content))
                )
            if choice.tool_calls_buffers:
                tool_calls = []
                for tool_call in choice.tool_calls_buffers:
                    arguments = None
                    arguments_str = "".join(tool_call.arguments)
                    if arguments_str:
                        try:
                            arguments = json.loads(arguments_str)
                        except json.JSONDecodeError:
                            arguments = arguments_str
                    tool_call_part = ToolCall(
                        name=tool_call.function_name,
                        id=tool_call.tool_call_id,
                        arguments=arguments,
                    )
                    tool_calls.append(tool_call_part)
                message.parts.extend(tool_calls)
            output_messages.append(message)

        self.invocation.output_messages = output_messages

    def cleanup(self, error: Optional[Error] = None):
        if not self._started:
            return

        self.invocation.response_model_name = self.response_model
        self.invocation.response_id = self.response_id
        self.invocation.input_tokens = self.prompt_tokens
        self.invocation.output_tokens = self.completion_tokens
        self.invocation.finish_reasons = self.finish_reasons
        if self.service_tier:
            self.invocation.attributes.update(
                {
                    OpenAIAttributes.OPENAI_RESPONSE_SERVICE_TIER: self.service_tier
                },
            )

        self._set_output_messages()

        if error:
            self.handler.fail_llm(self.invocation, error)
        else:
            self.handler.stop_llm(self.invocation)
        self._started = False
