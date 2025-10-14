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


from timeit import default_timer
from typing import Optional

from openai import Stream

from opentelemetry._logs import Logger, LogRecord
from opentelemetry.context import get_current
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.trace import Span, SpanKind, Tracer
from opentelemetry.trace.propagation import set_span_in_context

from .instruments import Instruments
from .utils import (
    choice_to_event,
    get_llm_request_attributes,
    handle_span_exception,
    is_streaming,
    message_to_event,
    set_span_attribute,
    get_property_value,
)


def chat_completions_create(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `create` method of the `ChatCompletion` class to trace it."""

    def traced_method(wrapped, instance, args, kwargs):
        span_attributes = {**get_llm_request_attributes(kwargs, instance)}

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
                if is_streaming(kwargs):
                    return StreamWrapper(result, span, logger, capture_content)

                if span.is_recording():
                    _set_response_attributes(
                        span, result, logger, capture_content
                    )
                for choice in getattr(result, "choices", []):
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


def async_chat_completions_create(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `create` method of the `AsyncChatCompletion` class to trace it."""

    async def traced_method(wrapped, instance, args, kwargs):
        span_attributes = {**get_llm_request_attributes(kwargs, instance)}

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
                if is_streaming(kwargs):
                    return StreamWrapper(result, span, logger, capture_content)

                if span.is_recording():
                    _set_response_attributes(
                        span, result, logger, capture_content
                    )
                for choice in getattr(result, "choices", []):
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


def _record_metrics(
    instruments: Instruments,
    duration: float,
    result,
    span_attributes: dict,
    error_type: Optional[str],
):
    common_attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.CHAT.value,
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value,
        GenAIAttributes.GEN_AI_REQUEST_MODEL: span_attributes[
            GenAIAttributes.GEN_AI_REQUEST_MODEL
        ],
    }

    if error_type:
        common_attributes["error.type"] = error_type

    if result and getattr(result, "model", None):
        common_attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL] = result.model

    if result and getattr(result, "service_tier", None):
        common_attributes[
            GenAIAttributes.GEN_AI_OPENAI_RESPONSE_SERVICE_TIER
        ] = result.service_tier

    if result and getattr(result, "system_fingerprint", None):
        common_attributes["gen_ai.openai.response.system_fingerprint"] = (
            result.system_fingerprint
        )

    if ServerAttributes.SERVER_ADDRESS in span_attributes:
        common_attributes[ServerAttributes.SERVER_ADDRESS] = span_attributes[
            ServerAttributes.SERVER_ADDRESS
        ]

    if ServerAttributes.SERVER_PORT in span_attributes:
        common_attributes[ServerAttributes.SERVER_PORT] = span_attributes[
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

        completion_attributes = {
            **common_attributes,
            GenAIAttributes.GEN_AI_TOKEN_TYPE: GenAIAttributes.GenAiTokenTypeValues.COMPLETION.value,
        }
        instruments.token_usage_histogram.record(
            result.usage.completion_tokens,
            attributes=completion_attributes,
        )


def _set_response_attributes(
    span, result, logger: Logger, capture_content: bool
):
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
            GenAIAttributes.GEN_AI_OPENAI_REQUEST_SERVICE_TIER,
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


class StreamWrapper:
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
        self.stream = stream
        self.span = span
        self.choice_buffers = []
        self._span_started = False
        self.capture_content = capture_content

        self.logger = logger
        self.setup()

    def setup(self):
        if not self._span_started:
            self._span_started = True

    def cleanup(self):
        if self._span_started:
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
                            function["arguments"] = "".join(
                                tool_call.arguments
                            )
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

            self.span.end()
            self._span_started = False

    def __enter__(self):
        self.setup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                handle_span_exception(self.span, exc_val)
        finally:
            self.cleanup()
        return False  # Propagate the exception

    async def __aenter__(self):
        self.setup()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                handle_span_exception(self.span, exc_val)
        finally:
            self.cleanup()
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
            handle_span_exception(self.span, error)
            self.cleanup()
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
            handle_span_exception(self.span, error)
            self.cleanup()
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


def responses_create(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `create` method of the `Responses` class to trace it."""

    def traced_method(wrapped, instance, args, kwargs):
        span_attributes = {**get_llm_request_attributes(kwargs, instance)}

        span_name = f"{span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]} {span_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]}"
        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            # Log input if applicable
            input_data = kwargs.get("input")
            if input_data and capture_content:
                if isinstance(input_data, str):
                    # Simple string input
                    logger.emit(message_to_event({"role": "user", "content": input_data}, capture_content))
                elif isinstance(input_data, dict):
                    # Dictionary input
                    logger.emit(message_to_event(input_data, capture_content))

            start = default_timer()
            result = None
            error_type = None
            try:
                result = wrapped(*args, **kwargs)
                if is_streaming(kwargs):
                    return StreamWrapper(result, span, logger, capture_content)

                if span.is_recording():
                    _set_responses_attributes(span, result, logger, capture_content)
                
                # Log output messages
                if hasattr(result, "output") and result.output:
                    for output_item in result.output:
                        if hasattr(output_item, "type") and output_item.type == "message":
                            # Convert output message to event format
                            message_dict = {"role": "assistant"}
                            if capture_content and hasattr(output_item, "content"):
                                content_items = output_item.content
                                if content_items:
                                    # Extract text content
                                    text_parts = []
                                    for content_item in content_items:
                                        if hasattr(content_item, "type") and content_item.type == "text":
                                            text_parts.append(content_item.text)
                                    if text_parts:
                                        message_dict["content"] = " ".join(text_parts)
                            logger.emit(message_to_event(message_dict, capture_content))

                span.end()
                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise
            finally:
                duration = max((default_timer() - start), 0)
                _record_responses_metrics(
                    instruments,
                    duration,
                    result,
                    span_attributes,
                    error_type,
                )

    return traced_method


def async_responses_create(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `create` method of the `AsyncResponses` class to trace it."""

    async def traced_method(wrapped, instance, args, kwargs):
        span_attributes = {**get_llm_request_attributes(kwargs, instance)}

        span_name = f"{span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]} {span_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]}"
        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            # Log input if applicable
            input_data = kwargs.get("input")
            if input_data and capture_content:
                if isinstance(input_data, str):
                    # Simple string input
                    logger.emit(message_to_event({"role": "user", "content": input_data}, capture_content))
                elif isinstance(input_data, dict):
                    # Dictionary input
                    logger.emit(message_to_event(input_data, capture_content))

            start = default_timer()
            result = None
            error_type = None
            try:
                result = await wrapped(*args, **kwargs)
                if is_streaming(kwargs):
                    return StreamWrapper(result, span, logger, capture_content)

                if span.is_recording():
                    _set_responses_attributes(span, result, logger, capture_content)
                
                # Log output messages
                if hasattr(result, "output") and result.output:
                    for output_item in result.output:
                        if hasattr(output_item, "type") and output_item.type == "message":
                            # Convert output message to event format
                            message_dict = {"role": "assistant"}
                            if capture_content and hasattr(output_item, "content"):
                                content_items = output_item.content
                                if content_items:
                                    # Extract text content
                                    text_parts = []
                                    for content_item in content_items:
                                        if hasattr(content_item, "type") and content_item.type == "text":
                                            text_parts.append(content_item.text)
                                    if text_parts:
                                        message_dict["content"] = " ".join(text_parts)
                            logger.emit(message_to_event(message_dict, capture_content))

                span.end()
                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise
            finally:
                duration = max((default_timer() - start), 0)
                _record_responses_metrics(
                    instruments,
                    duration,
                    result,
                    span_attributes,
                    error_type,
                )

    return traced_method


def _set_responses_attributes(span, result, logger: Logger, capture_content: bool):
    """Set span attributes for responses API."""
    model = get_property_value(result, "model")
    if model:
        set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, model)

    response_id = get_property_value(result, "id")
    if response_id:
        set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_ID, response_id)

    service_tier = get_property_value(result, "service_tier")
    if service_tier:
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_OPENAI_REQUEST_SERVICE_TIER,
            service_tier,
        )

    # Get the usage
    usage = get_property_value(result, "usage")
    if usage:
        input_tokens = get_property_value(usage, "input_tokens")
        if input_tokens is not None:
            set_span_attribute(
                span,
                GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
                input_tokens,
            )
        output_tokens = get_property_value(usage, "output_tokens")
        if output_tokens is not None:
            set_span_attribute(
                span,
                GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS,
                output_tokens,
            )

    # Set finish reasons from output
    output = get_property_value(result, "output")
    if output:
        finish_reasons = []
        for item in output:
            if hasattr(item, "type") and item.type == "message":
                # For message type, we can consider it as "stop"
                finish_reasons.append("stop")
        if finish_reasons:
            set_span_attribute(
                span,
                GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS,
                finish_reasons,
            )


def _record_responses_metrics(
    instruments: Instruments,
    duration: float,
    result,
    span_attributes: dict,
    error_type: Optional[str],
):
    """Record metrics for responses API."""
    common_attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.CHAT.value,
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value,
        GenAIAttributes.GEN_AI_REQUEST_MODEL: span_attributes[
            GenAIAttributes.GEN_AI_REQUEST_MODEL
        ],
    }

    if error_type:
        common_attributes["error.type"] = error_type

    if result:
        model = get_property_value(result, "model")
        if model:
            common_attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL] = model

        service_tier = get_property_value(result, "service_tier")
        if service_tier:
            common_attributes[
                GenAIAttributes.GEN_AI_OPENAI_RESPONSE_SERVICE_TIER
            ] = service_tier

    if ServerAttributes.SERVER_ADDRESS in span_attributes:
        common_attributes[ServerAttributes.SERVER_ADDRESS] = span_attributes[
            ServerAttributes.SERVER_ADDRESS
        ]

    if ServerAttributes.SERVER_PORT in span_attributes:
        common_attributes[ServerAttributes.SERVER_PORT] = span_attributes[
            ServerAttributes.SERVER_PORT
        ]

    instruments.operation_duration_histogram.record(
        duration,
        attributes=common_attributes,
    )

    if result:
        usage = get_property_value(result, "usage")
        if usage:
            input_tokens = get_property_value(usage, "input_tokens")
            if input_tokens is not None:
                input_attributes = {
                    **common_attributes,
                    GenAIAttributes.GEN_AI_TOKEN_TYPE: GenAIAttributes.GenAiTokenTypeValues.INPUT.value,
                }
                instruments.token_usage_histogram.record(
                    input_tokens,
                    attributes=input_attributes,
                )

            output_tokens = get_property_value(usage, "output_tokens")
            if output_tokens is not None:
                completion_attributes = {
                    **common_attributes,
                    GenAIAttributes.GEN_AI_TOKEN_TYPE: GenAIAttributes.GenAiTokenTypeValues.COMPLETION.value,
                }
                instruments.token_usage_histogram.record(
                    output_tokens,
                    attributes=completion_attributes,
                )
