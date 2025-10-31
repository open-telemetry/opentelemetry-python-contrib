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

# pyright: reportUnknownParameterType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportMissingParameterType=false
# pylint: disable=too-many-arguments
# type: ignore
"""
Pylance/Pyright type checking is disabled for this file because OpenTelemetry 
instrumentation involves dynamic wrapping of external library methods using 
the wrapt library. The wrapped functions, their parameters (args, kwargs), 
and return values have types that are determined at runtime and cannot be 
statically analyzed. This is the expected and correct approach for 
instrumentation code that needs to work generically across different 
versions and configurations of the instrumented library.
"""


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
    set_server_address_and_port,
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

        operation_name = span_attributes.get(GenAIAttributes.GEN_AI_OPERATION_NAME, "chat")
        model_name = span_attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL, "unknown")
        span_name = f"{operation_name} {model_name}"
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

        operation_name = span_attributes.get(GenAIAttributes.GEN_AI_OPERATION_NAME, "chat")
        model_name = span_attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL, "unknown")
        span_name = f"{operation_name} {model_name}"
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
    }

    # Only add request model if it exists in span_attributes
    if GenAIAttributes.GEN_AI_REQUEST_MODEL in span_attributes:
        common_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] = span_attributes[
            GenAIAttributes.GEN_AI_REQUEST_MODEL
        ]

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

                event_attributes = _response_message_to_event_attributes(message, self.capture_content)
                self.span.add_event(name="gen_ai.assistant.message", attributes=event_attributes)

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
        # Handle Responses API ResponseTextDeltaEvent chunks
        if hasattr(chunk, "delta") and isinstance(chunk.delta, str) and chunk.delta:
            # Responses API streams have delta events where delta is the text content directly
            # Ensure we have at least one choice buffer for index 0
            if len(self.choice_buffers) == 0:
                self.choice_buffers.append(ChoiceBuffer(0))
            
            # Append the delta text to the first (and only) choice buffer
            self.choice_buffers[0].append_text_content(chunk.delta)
            return

        # Handle Responses API streaming format (chunk.output) - fallback for other chunk types
        if hasattr(chunk, "output") and chunk.output is not None:
            # Responses API streams have direct output, not choices array
            # Ensure we have at least one choice buffer for index 0
            if len(self.choice_buffers) == 0:
                self.choice_buffers.append(ChoiceBuffer(0))
            
            # Append the output text to the first (and only) choice buffer
            self.choice_buffers[0].append_text_content(chunk.output)
            return

        # Handle Chat Completions API streaming format (chunk.choices)
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
        span_attributes = {**get_llm_request_attributes(kwargs, instance, "responses")}

        operation_name = span_attributes.get(GenAIAttributes.GEN_AI_OPERATION_NAME, "responses")
        model_name = span_attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL)
        
        # Extract agent name for span naming if model is not available
        assistant_name = None
        extra_body = kwargs.get("extra_body")
        if extra_body and isinstance(extra_body, dict):
            agent_info = extra_body.get("agent")
            if agent_info and isinstance(agent_info, dict):
                assistant_name = agent_info.get("name")
        
        # Build span name: prefer model, then assistant name, then just operation
        if model_name:
            span_name = f"{operation_name} {model_name}"
        elif assistant_name:
            span_name = f"{operation_name} {assistant_name}"
        else:
            span_name = operation_name
        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            # Add conversation ID as span attribute if provided
            conversation_id = kwargs.get("conversation")
            if conversation_id:
                set_span_attribute(span, "gen_ai.conversation.id", conversation_id)

            # Add agent name from extra_body if provided
            extra_body = kwargs.get("extra_body")
            if extra_body and isinstance(extra_body, dict):
                agent_info = extra_body.get("agent")
                if agent_info and isinstance(agent_info, dict):
                    agent_name = agent_info.get("name")
                    if agent_name:
                        set_span_attribute(span, "gen_ai.assistant.name", agent_name)

            # Add input message as event if applicable
            input_data = kwargs.get("input")
            if input_data:
                if isinstance(input_data, str):
                    # Simple string input - add as user message event
                    message_dict = {"role": "user", "content": input_data}
                    event_attributes = _response_message_to_event_attributes(message_dict, capture_content)
                    span.add_event(name="gen_ai.user.message", attributes=event_attributes)
                elif isinstance(input_data, dict):
                    # Dictionary input - add as event based on role
                    role = input_data.get("role", "user")
                    event_name = f"gen_ai.{role}.message" if role in ["user", "assistant"] else "gen_ai.message"
                    event_attributes = _response_message_to_event_attributes(input_data, capture_content)
                    span.add_event(name=event_name, attributes=event_attributes)

            start = default_timer()
            result = None
            error_type = None
            try:
                result = wrapped(*args, **kwargs)
                if is_streaming(kwargs):
                    return StreamWrapper(result, span, logger, capture_content)

                if span.is_recording():
                    _set_responses_attributes(span, result, logger, capture_content)
                
                # Add output messages as events
                if hasattr(result, "output") and result.output:
                    for output_item in result.output:
                        if hasattr(output_item, "type") and output_item.type == "message":
                            # Convert output message to event format
                            message_dict = {"role": "assistant"}
                            if hasattr(output_item, "content"):
                                content_items = output_item.content
                                if content_items:
                                    # Extract text content - check for input_text, output_text, and text types
                                    text_parts = []
                                    for content_item in content_items:
                                        if hasattr(content_item, "text"):
                                            if hasattr(content_item, "type") and content_item.type in ["input_text", "output_text", "text"]:
                                                text_parts.append(content_item.text)
                                    if text_parts:
                                        message_dict["content"] = " ".join(text_parts)
                            # Add assistant message as event
                            event_attributes = _response_message_to_event_attributes(message_dict, capture_content)
                            span.add_event(name="gen_ai.assistant.message", attributes=event_attributes)

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
        span_attributes = {**get_llm_request_attributes(kwargs, instance, "responses")}

        operation_name = span_attributes.get(GenAIAttributes.GEN_AI_OPERATION_NAME, "responses")
        model_name = span_attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL)
        
        # Extract agent name for span naming if model is not available
        assistant_name = None
        extra_body = kwargs.get("extra_body")
        if extra_body and isinstance(extra_body, dict):
            agent_info = extra_body.get("agent")
            if agent_info and isinstance(agent_info, dict):
                assistant_name = agent_info.get("name")
        
        # Build span name: prefer model, then assistant name, then just operation
        if model_name:
            span_name = f"{operation_name} {model_name}"
        elif assistant_name:
            span_name = f"{operation_name} {assistant_name}"
        else:
            span_name = operation_name
        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            # Add conversation ID as span attribute if provided
            conversation_id = kwargs.get("conversation")
            if conversation_id:
                set_span_attribute(span, "gen_ai.conversation.id", conversation_id)

            # Add agent name from extra_body if provided
            extra_body = kwargs.get("extra_body")
            if extra_body and isinstance(extra_body, dict):
                agent_info = extra_body.get("agent")
                if agent_info and isinstance(agent_info, dict):
                    agent_name = agent_info.get("name")
                    if agent_name:
                        set_span_attribute(span, "gen_ai.assistant.name", agent_name)

            # Add input message as event if applicable
            input_data = kwargs.get("input")
            if input_data:
                if isinstance(input_data, str):
                    # Simple string input - add as user message event
                    message_dict = {"role": "user", "content": input_data}
                    event_attributes = _response_message_to_event_attributes(message_dict, capture_content)
                    span.add_event(name="gen_ai.user.message", attributes=event_attributes)
                elif isinstance(input_data, dict):
                    # Dictionary input - add as event based on role
                    role = input_data.get("role", "user")
                    event_name = f"gen_ai.{role}.message" if role in ["user", "assistant"] else "gen_ai.message"
                    event_attributes = _response_message_to_event_attributes(input_data, capture_content)
                    span.add_event(name=event_name, attributes=event_attributes)

            start = default_timer()
            result = None
            error_type = None
            try:
                result = await wrapped(*args, **kwargs)
                if is_streaming(kwargs):
                    return StreamWrapper(result, span, logger, capture_content)

                if span.is_recording():
                    _set_responses_attributes(span, result, logger, capture_content)
                
                # Add output messages as events
                if hasattr(result, "output") and result.output:
                    for output_item in result.output:
                        if hasattr(output_item, "type") and output_item.type == "message":
                            # Convert output message to event format
                            message_dict = {"role": "assistant"}
                            if hasattr(output_item, "content"):
                                content_items = output_item.content
                                if content_items:
                                    # Extract text content - check for input_text, output_text, and text types
                                    text_parts = []
                                    for content_item in content_items:
                                        if hasattr(content_item, "text"):
                                            if hasattr(content_item, "type") and content_item.type in ["input_text", "output_text", "text"]:
                                                text_parts.append(content_item.text)
                                    if text_parts:
                                        message_dict["content"] = " ".join(text_parts)
                            # Add assistant message as event
                            event_attributes = _response_message_to_event_attributes(message_dict, capture_content)
                            span.add_event(name="gen_ai.assistant.message", attributes=event_attributes)

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
        GenAIAttributes.GEN_AI_OPERATION_NAME: "responses",
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value,
    }

    # Only add request model if it exists in span_attributes
    if GenAIAttributes.GEN_AI_REQUEST_MODEL in span_attributes:
        common_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] = span_attributes[
            GenAIAttributes.GEN_AI_REQUEST_MODEL
        ]

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


def conversations_create(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `create` method of the `Conversations` class to trace it."""

    def traced_method(wrapped, instance, args, kwargs):
        span_attributes = _get_conversation_request_attributes(kwargs, instance)

        span_name = "create_conversation"
        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            start_time = default_timer()
            error_type = None
            try:
                result = wrapped(*args, **kwargs)
                _set_conversation_attributes(span, result)
                return result
            except Exception as e:
                error_type = type(e).__qualname__
                handle_span_exception(span, e)
                raise
            finally:
                if error_type is None:
                    span.end()
                duration = default_timer() - start_time
                _record_conversation_metrics(
                    instruments, duration, result if error_type is None else None, span_attributes, error_type
                )

    return traced_method


def async_conversations_create(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `create` method of the `AsyncConversations` class to trace it."""

    async def traced_method(wrapped, instance, args, kwargs):
        span_attributes = _get_conversation_request_attributes(kwargs, instance)

        span_name = "create_conversation"
        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            start_time = default_timer()
            error_type = None
            try:
                result = await wrapped(*args, **kwargs)
                _set_conversation_attributes(span, result)
                return result
            except Exception as e:
                error_type = type(e).__qualname__
                handle_span_exception(span, e)
                raise
            finally:
                if error_type is None:
                    span.end()
                duration = default_timer() - start_time
                _record_conversation_metrics(
                    instruments, duration, result if error_type is None else None, span_attributes, error_type
                )

    return traced_method


def _get_conversation_request_attributes(kwargs, client_instance):
    """Get span attributes for conversation create requests."""
    attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: "create_conversation",
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value,
    }

    set_server_address_and_port(client_instance, attributes)
    
    # filter out None values
    return {k: v for k, v in attributes.items() if v is not None}


def _set_conversation_attributes(span, result):
    """Set span attributes for conversation create response."""
    conversation_id = get_property_value(result, "id")
    if conversation_id:
        set_span_attribute(span, "gen_ai.conversation.id", conversation_id)


def _record_conversation_metrics(
    instruments: Instruments,
    duration: float,
    result,
    span_attributes: dict,
    error_type: Optional[str],
):
    """Record metrics for conversation create API."""
    common_attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: "create_conversation",
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value,
    }

    if error_type:
        common_attributes["error.type"] = error_type

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


def conversation_items_list(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `list` method of the `Items` class to trace it."""

    def traced_method(wrapped, instance, args, kwargs):
        span_attributes = _get_conversation_items_request_attributes(kwargs, instance)

        span_name = "list_conversation_items"
        span = tracer.start_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
        )
        
        start_time = default_timer()
        error_type = None
        try:
            result = wrapped(*args, **kwargs)
            _set_conversation_items_attributes(span, result, args, kwargs)
            
            # Wrap the result to trace individual items as they are iterated
            return ConversationItemsWrapper(
                result, span, logger, capture_content, tracer, start_time, instruments, span_attributes
            )
        except Exception as e:
            error_type = type(e).__qualname__
            handle_span_exception(span, e)
            span.end()
            duration = default_timer() - start_time
            _record_conversation_items_metrics(
                instruments, duration, None, span_attributes, error_type
            )
            raise

    return traced_method


def async_conversation_items_list(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `list` method of the `AsyncItems` class to trace it."""

    async def traced_method(wrapped, instance, args, kwargs):
        span_attributes = _get_conversation_items_request_attributes(kwargs, instance)

        span_name = "list_conversation_items"
        span = tracer.start_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
        )
        
        start_time = default_timer()
        error_type = None
        try:
            result = await wrapped(*args, **kwargs)
            _set_conversation_items_attributes(span, result, args, kwargs)
            
            # Wrap the result to trace individual items as they are iterated
            return AsyncConversationItemsWrapper(
                result, span, logger, capture_content, tracer, start_time, instruments, span_attributes
            )
        except Exception as e:
            error_type = type(e).__qualname__
            handle_span_exception(span, e)
            span.end()
            duration = default_timer() - start_time
            _record_conversation_items_metrics(
                instruments, duration, None, span_attributes, error_type
            )
            raise

    return traced_method


def _get_conversation_items_request_attributes(kwargs, client_instance):
    """Get span attributes for conversation items list requests."""
    attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: "list_conversation_items", 
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value,
    }

    set_server_address_and_port(client_instance, attributes)
    
    # filter out None values
    return {k: v for k, v in attributes.items() if v is not None}


def _set_conversation_items_attributes(span, result, args, kwargs):
    """Set span attributes for conversation items list response."""
    # Add conversation_id from arguments (check both positional and keyword args)
    conversation_id = None
    if len(args) > 0:
        conversation_id = args[0]
    elif "conversation_id" in kwargs:
        conversation_id = kwargs["conversation_id"]
    
    if conversation_id:
        set_span_attribute(span, "gen_ai.conversation.id", conversation_id)
    
    # Add pagination info if available
    if hasattr(result, "object") and result.object == "list":
        set_span_attribute(span, "gen_ai.response.object", result.object)
    
    if hasattr(result, "has_more"):
        set_span_attribute(span, "gen_ai.response.has_more", result.has_more)


def _record_conversation_items_metrics(
    instruments: Instruments,
    duration: float,
    result,
    span_attributes: dict,
    error_type: Optional[str],
):
    """Record metrics for conversation items list API."""
    common_attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: "list_conversation_items",
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value,
    }

    if error_type:
        common_attributes["error.type"] = error_type

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


def _conversation_item_to_event_attributes(item, capture_content: bool):
    """Convert a conversation item to event attributes for logging."""
    event_attributes = {
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value
    }

    # Add item ID
    if hasattr(item, "id") and item.id:
        event_attributes["gen_ai.conversation.item.id"] = item.id

    # Add item type  
    if hasattr(item, "type") and item.type:
        event_attributes["gen_ai.conversation.item.type"] = item.type

    # Add item role
    if hasattr(item, "role") and item.role:
        event_attributes["gen_ai.conversation.item.role"] = item.role

    # Add content if capture is enabled
    if capture_content and hasattr(item, "content") and item.content:
        content_list = []
        for content_item in item.content:
            if hasattr(content_item, "type") and content_item.type == "input_text":
                if hasattr(content_item, "text"):
                    content_list.append(content_item.text)
            elif hasattr(content_item, "type") and content_item.type == "output_text":
                if hasattr(content_item, "text"):
                    content_list.append(content_item.text)
            elif hasattr(content_item, "type") and content_item.type == "text":
                if hasattr(content_item, "text"):
                    content_list.append(content_item.text)
        if content_list:
            # Store content as JSON string similar to Azure AI Agents pattern
            import json
            content_json = json.dumps({"content": " ".join(content_list), "role": getattr(item, "role", "unknown")})
            event_attributes["gen_ai.event.content"] = content_json

    return event_attributes


def _response_message_to_event_attributes(message_dict: dict, capture_content: bool):
    """Convert a response message to event attributes for logging."""
    event_attributes = {
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value
    }

    # Add role 
    if "role" in message_dict:
        event_attributes["gen_ai.message.role"] = message_dict["role"]

    # Add content if capture is enabled and available
    if capture_content and "content" in message_dict:
        import json
        content_json = json.dumps({
            "content": message_dict["content"], 
            "role": message_dict.get("role", "unknown")
        })
        event_attributes["gen_ai.event.content"] = content_json

    return event_attributes


class ConversationItemsWrapper:
    """Wrapper for sync conversation items pagination that traces individual items."""
    
    def __init__(self, items_page, span, logger, capture_content, tracer, start_time, instruments, span_attributes):
        self.items_page = items_page
        self.span = span
        self.logger = logger 
        self.capture_content = capture_content
        self.tracer = tracer
        self.start_time = start_time
        self.instruments = instruments
        self.span_attributes = span_attributes
        self._iter = None
        self._span_ended = False

    def __getattr__(self, name):
        """Delegate attribute access to the wrapped items_page."""
        return getattr(self.items_page, name)

    def _end_span_if_needed(self):
        """End the span if it hasn't been ended yet."""
        if not self._span_ended:
            self.span.end()
            duration = default_timer() - self.start_time
            _record_conversation_items_metrics(
                self.instruments, duration, self.items_page, self.span_attributes, None
            )
            self._span_ended = True

    def __iter__(self):
        def _item_generator():
            try:
                for item in self.items_page:
                    # Add the item as an event within the main span
                    event_attributes = _conversation_item_to_event_attributes(item, self.capture_content)
                    
                    # Determine event name based on role (similar to Azure AI Agents pattern)
                    role = getattr(item, "role", "unknown")
                    if role == "assistant":
                        event_name = "gen_ai.assistant.message"
                    elif role == "user":
                        event_name = "gen_ai.user.message"
                    else:
                        event_name = "gen_ai.conversation.item"
                    
                    # Add event directly to the span
                    self.span.add_event(
                        name=event_name,
                        attributes=event_attributes
                    )
                    
                    yield item
            finally:
                # End the span when iteration is complete
                self._end_span_if_needed()
                    
        if self._iter is None:
            self._iter = _item_generator()
        return self._iter

    def __del__(self):
        """Ensure span is ended if the wrapper is garbage collected."""
        try:
            self._end_span_if_needed()
        except:
            pass  # Ignore any errors during cleanup


class AsyncConversationItemsWrapper:
    """Wrapper for async conversation items pagination that traces individual items."""
    
    def __init__(self, items_page, span, logger, capture_content, tracer, start_time, instruments, span_attributes):
        self.items_page = items_page
        self.span = span
        self.logger = logger
        self.capture_content = capture_content
        self.tracer = tracer
        self.start_time = start_time
        self.instruments = instruments
        self.span_attributes = span_attributes
        self._iter = None
        self._span_ended = False

    def __getattr__(self, name):
        """Delegate attribute access to the wrapped items_page."""
        return getattr(self.items_page, name)

    def _end_span_if_needed(self):
        """End the span if it hasn't been ended yet."""
        if not self._span_ended:
            self.span.end()
            duration = default_timer() - self.start_time
            _record_conversation_items_metrics(
                self.instruments, duration, self.items_page, self.span_attributes, None
            )
            self._span_ended = True

    def __aiter__(self):
        async def _async_item_generator():
            try:
                async for item in self.items_page:
                    # Add the item as an event within the main span
                    event_attributes = _conversation_item_to_event_attributes(item, self.capture_content)
                    
                    # Determine event name based on role (similar to Azure AI Agents pattern)
                    role = getattr(item, "role", "unknown")
                    if role == "assistant":
                        event_name = "gen_ai.assistant.message"
                    elif role == "user":
                        event_name = "gen_ai.user.message"
                    else:
                        event_name = "gen_ai.conversation.item"
                    
                    # Add event directly to the span
                    self.span.add_event(
                        name=event_name,
                        attributes=event_attributes
                    )
                        
                    yield item
            finally:
                # End the span when iteration is complete
                self._end_span_if_needed()
                    
        if self._iter is None:
            self._iter = _async_item_generator()
        return self._iter

    def __del__(self):
        """Ensure span is ended if the wrapper is garbage collected."""
        try:
            self._end_span_if_needed()
        except:
            pass  # Ignore any errors during cleanup
