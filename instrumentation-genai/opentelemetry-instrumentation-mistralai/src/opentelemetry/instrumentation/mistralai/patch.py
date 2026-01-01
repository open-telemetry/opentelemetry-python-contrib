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

"""Patching functions for Mistral AI instrumentation."""

from __future__ import annotations

import logging
from typing import Any, Callable

from opentelemetry import context as context_api
from opentelemetry._logs import Logger
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.trace.status import Status, StatusCode

from opentelemetry.instrumentation.mistralai.utils import (
    dont_throw,
    is_content_enabled,
    set_span_attribute,
)

logger = logging.getLogger(__name__)


def _extract_message_content(message):
    """Extract content from a message dict or object."""
    if isinstance(message, dict):
        return message.get("content"), message.get("role", "user")
    return getattr(message, "content", None), getattr(message, "role", "user")


@dont_throw
def _set_request_attributes(span, kwargs):
    """Set request attributes on span."""
    if not span.is_recording():
        return

    set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_MODEL, kwargs.get("model"))
    set_span_attribute(
        span, GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE, kwargs.get("temperature")
    )
    set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_TOP_P, kwargs.get("top_p"))
    set_span_attribute(
        span, GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS, kwargs.get("max_tokens")
    )

    if kwargs.get("stream"):
        set_span_attribute(span, "gen_ai.request.streaming", True)


@dont_throw
def _emit_request_events(event_logger, kwargs):
    """Emit request events."""
    from opentelemetry._logs import LogRecord

    capture_content = is_content_enabled()

    for message in kwargs.get("messages", []):
        content, role = _extract_message_content(message)
        body = {}

        if capture_content and content:
            body["content"] = content

        log_record = LogRecord(
            event_name=f"gen_ai.{role}.message",
            attributes={GenAIAttributes.GEN_AI_SYSTEM: "mistral"},
            body=body if body else None,
        )
        event_logger.emit(log_record)


@dont_throw
def _set_response_attributes(span, response):
    """Set response attributes on span."""
    if not span.is_recording():
        return

    set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, response.model)
    set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_ID, response.id)

    if hasattr(response, "usage") and response.usage:
        usage = response.usage
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
            getattr(usage, "prompt_tokens", 0),
        )
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS,
            getattr(usage, "completion_tokens", 0),
        )

    if response.choices:
        finish_reasons = [
            getattr(choice, "finish_reason", "unknown") for choice in response.choices
        ]
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS, finish_reasons
        )


@dont_throw
def _emit_response_events(event_logger, response):
    """Emit response events."""
    from opentelemetry._logs import LogRecord

    capture_content = is_content_enabled()

    for choice in response.choices:
        body = {
            "index": choice.index,
            "finish_reason": getattr(choice, "finish_reason", "unknown"),
        }

        message = {"role": "assistant"}
        if capture_content and hasattr(choice, "message"):
            content = getattr(choice.message, "content", None)
            if content:
                message["content"] = content

            # Handle tool calls
            tool_calls = getattr(choice.message, "tool_calls", None)
            if tool_calls:
                message["tool_calls"] = [
                    {
                        "id": getattr(tc, "id", ""),
                        "type": getattr(tc, "type", "function"),
                        "function": {
                            "name": getattr(tc.function, "name", ""),
                            "arguments": getattr(tc.function, "arguments", ""),
                        },
                    }
                    for tc in tool_calls
                ]

        body["message"] = message

        log_record = LogRecord(
            event_name="gen_ai.choice",
            attributes={GenAIAttributes.GEN_AI_SYSTEM: "mistral"},
            body=body,
        )
        event_logger.emit(log_record)


def create_chat_complete_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for Mistral chat.complete."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            "mistral.chat",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "mistral",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.CHAT.value,
            },
        ) as span:
            _set_request_attributes(span, kwargs)
            if event_logger:
                _emit_request_events(event_logger, kwargs)

            try:
                response = wrapped(*args, **kwargs)

                _set_response_attributes(span, response)
                if event_logger:
                    _emit_response_events(event_logger, response)

                if span.is_recording():
                    span.set_status(Status(StatusCode.OK))

                return response
            except Exception as error:
                span.set_status(Status(StatusCode.ERROR, str(error)))
                if span.is_recording():
                    span.set_attribute("error.type", type(error).__qualname__)
                raise

    return wrapper


def create_chat_stream_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for Mistral chat.stream."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        span = tracer.start_span(
            "mistral.chat.stream",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "mistral",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.CHAT.value,
            },
        )

        _set_request_attributes(span, kwargs)
        if event_logger:
            _emit_request_events(event_logger, kwargs)

        try:
            response = wrapped(*args, **kwargs)

            def instrumented_stream():
                accumulated_content = []
                finish_reason = None
                model = None
                input_tokens = 0
                output_tokens = 0

                try:
                    for chunk in response:
                        if hasattr(chunk, "data"):
                            data = chunk.data
                            if hasattr(data, "model"):
                                model = data.model
                            if hasattr(data, "choices") and data.choices:
                                choice = data.choices[0]
                                if hasattr(choice, "delta") and choice.delta:
                                    content = getattr(choice.delta, "content", None)
                                    if content:
                                        accumulated_content.append(content)
                                if hasattr(choice, "finish_reason") and choice.finish_reason:
                                    finish_reason = choice.finish_reason
                            if hasattr(data, "usage") and data.usage:
                                input_tokens = getattr(data.usage, "prompt_tokens", 0)
                                output_tokens = getattr(data.usage, "completion_tokens", 0)
                        yield chunk

                    if span.is_recording():
                        if model:
                            set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, model)
                        if finish_reason:
                            set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS, [finish_reason])
                        if input_tokens:
                            set_span_attribute(span, GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS, input_tokens)
                        if output_tokens:
                            set_span_attribute(span, GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS, output_tokens)
                        span.set_status(Status(StatusCode.OK))

                    if event_logger:
                        from opentelemetry._logs import LogRecord

                        body = {"index": 0, "finish_reason": finish_reason or "stop"}
                        message = {"role": "assistant"}
                        if is_content_enabled() and accumulated_content:
                            message["content"] = "".join(accumulated_content)
                        body["message"] = message

                        log_record = LogRecord(
                            event_name="gen_ai.choice",
                            attributes={GenAIAttributes.GEN_AI_SYSTEM: "mistral"},
                            body=body,
                        )
                        event_logger.emit(log_record)
                except Exception as error:
                    span.set_status(Status(StatusCode.ERROR, str(error)))
                    if span.is_recording():
                        span.set_attribute("error.type", type(error).__qualname__)
                    raise
                finally:
                    span.end()

            return instrumented_stream()
        except Exception as error:
            span.set_status(Status(StatusCode.ERROR, str(error)))
            if span.is_recording():
                span.set_attribute("error.type", type(error).__qualname__)
            span.end()
            raise

    return wrapper


def create_embeddings_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for Mistral embeddings.create."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            "mistral.embeddings",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "mistral",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value,
            },
        ) as span:
            set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_MODEL, kwargs.get("model"))

            inputs = kwargs.get("inputs", [])
            if isinstance(inputs, str):
                inputs = [inputs]
            set_span_attribute(span, "gen_ai.embeddings.input_count", len(inputs))

            try:
                response = wrapped(*args, **kwargs)

                if hasattr(response, "model"):
                    set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, response.model)
                if hasattr(response, "data"):
                    set_span_attribute(span, "gen_ai.embeddings.output_count", len(response.data))
                if hasattr(response, "usage") and response.usage:
                    set_span_attribute(span, GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS, response.usage.prompt_tokens)

                if span.is_recording():
                    span.set_status(Status(StatusCode.OK))

                return response
            except Exception as error:
                span.set_status(Status(StatusCode.ERROR, str(error)))
                if span.is_recording():
                    span.set_attribute("error.type", type(error).__qualname__)
                raise

    return wrapper


def create_async_chat_complete_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for async Mistral chat.complete."""

    async def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return await wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            "mistral.chat",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "mistral",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.CHAT.value,
            },
        ) as span:
            _set_request_attributes(span, kwargs)
            if event_logger:
                _emit_request_events(event_logger, kwargs)

            try:
                response = await wrapped(*args, **kwargs)

                _set_response_attributes(span, response)
                if event_logger:
                    _emit_response_events(event_logger, response)

                if span.is_recording():
                    span.set_status(Status(StatusCode.OK))

                return response
            except Exception as error:
                span.set_status(Status(StatusCode.ERROR, str(error)))
                if span.is_recording():
                    span.set_attribute("error.type", type(error).__qualname__)
                raise

    return wrapper
