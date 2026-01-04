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

"""Patching functions for Groq instrumentation."""

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

from opentelemetry.instrumentation.groq.utils import (
    dont_throw,
    is_content_enabled,
    set_span_attribute,
)

logger = logging.getLogger(__name__)


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
    set_span_attribute(
        span,
        GenAIAttributes.GEN_AI_REQUEST_FREQUENCY_PENALTY,
        kwargs.get("frequency_penalty"),
    )
    set_span_attribute(
        span,
        GenAIAttributes.GEN_AI_REQUEST_PRESENCE_PENALTY,
        kwargs.get("presence_penalty"),
    )

    if kwargs.get("stream"):
        set_span_attribute(span, "gen_ai.request.streaming", True)


@dont_throw
def _emit_request_events(event_logger, kwargs):
    """Emit request events."""
    from opentelemetry._logs import LogRecord

    capture_content = is_content_enabled()

    for message in kwargs.get("messages", []):
        body = {}
        role = message.get("role", "user")

        if capture_content:
            content = message.get("content")
            if content:
                body["content"] = content

        log_record = LogRecord(
            event_name=f"gen_ai.{role}.message",
            attributes={GenAIAttributes.GEN_AI_SYSTEM: "groq"},
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
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ]

        body["message"] = message

        log_record = LogRecord(
            event_name="gen_ai.choice",
            attributes={GenAIAttributes.GEN_AI_SYSTEM: "groq"},
            body=body,
        )
        event_logger.emit(log_record)


def create_chat_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for Groq chat completions."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            "groq.chat",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "groq",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.CHAT.value,
            },
        ) as span:
            _set_request_attributes(span, kwargs)
            if event_logger:
                _emit_request_events(event_logger, kwargs)

            try:
                response = wrapped(*args, **kwargs)

                # Handle streaming
                if kwargs.get("stream"):
                    return _wrap_stream(span, event_logger, response)

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


def _wrap_stream(span, event_logger, response):
    """Wrap streaming response."""
    accumulated_content = []
    finish_reason = None
    input_tokens = 0
    output_tokens = 0
    model = None

    for chunk in response:
        if hasattr(chunk, "model"):
            model = chunk.model

        if hasattr(chunk, "choices") and chunk.choices:
            choice = chunk.choices[0]
            if hasattr(choice, "delta") and choice.delta:
                content = getattr(choice.delta, "content", None)
                if content:
                    accumulated_content.append(content)
            if hasattr(choice, "finish_reason") and choice.finish_reason:
                finish_reason = choice.finish_reason

        if hasattr(chunk, "usage") and chunk.usage:
            input_tokens = getattr(chunk.usage, "prompt_tokens", 0)
            output_tokens = getattr(chunk.usage, "completion_tokens", 0)

        yield chunk

    # Set final attributes
    if span.is_recording():
        if model:
            set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, model)
        if finish_reason:
            set_span_attribute(
                span, GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS, [finish_reason]
            )
        if input_tokens:
            set_span_attribute(
                span, GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS, input_tokens
            )
        if output_tokens:
            set_span_attribute(
                span, GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS, output_tokens
            )
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
            attributes={GenAIAttributes.GEN_AI_SYSTEM: "groq"},
            body=body,
        )
        event_logger.emit(log_record)

    span.end()


async def _wrap_async_stream(span, event_logger, response):
    """Wrap async streaming response."""
    accumulated_content = []
    finish_reason = None
    input_tokens = 0
    output_tokens = 0
    model = None

    async for chunk in response:
        if hasattr(chunk, "model"):
            model = chunk.model

        if hasattr(chunk, "choices") and chunk.choices:
            choice = chunk.choices[0]
            if hasattr(choice, "delta") and choice.delta:
                content = getattr(choice.delta, "content", None)
                if content:
                    accumulated_content.append(content)
            if hasattr(choice, "finish_reason") and choice.finish_reason:
                finish_reason = choice.finish_reason

        if hasattr(chunk, "usage") and chunk.usage:
            input_tokens = getattr(chunk.usage, "prompt_tokens", 0)
            output_tokens = getattr(chunk.usage, "completion_tokens", 0)

        yield chunk

    # Set final attributes
    if span.is_recording():
        if model:
            set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, model)
        if finish_reason:
            set_span_attribute(
                span, GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS, [finish_reason]
            )
        if input_tokens:
            set_span_attribute(
                span, GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS, input_tokens
            )
        if output_tokens:
            set_span_attribute(
                span, GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS, output_tokens
            )
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
            attributes={GenAIAttributes.GEN_AI_SYSTEM: "groq"},
            body=body,
        )
        event_logger.emit(log_record)

    span.end()


def create_async_chat_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for async Groq chat completions."""

    async def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return await wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            "groq.chat",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "groq",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.CHAT.value,
            },
        ) as span:
            _set_request_attributes(span, kwargs)
            if event_logger:
                _emit_request_events(event_logger, kwargs)

            try:
                response = await wrapped(*args, **kwargs)

                # Handle streaming
                if kwargs.get("stream"):
                    return _wrap_async_stream(span, event_logger, response)

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
