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

"""Patching functions for Ollama instrumentation."""

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

from opentelemetry.instrumentation.ollama.utils import (
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

    options = kwargs.get("options", {})
    if options:
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE, options.get("temperature")
        )
        set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_TOP_P, options.get("top_p"))
        set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_TOP_K, options.get("top_k"))
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS, options.get("num_predict")
        )

    if kwargs.get("stream"):
        set_span_attribute(span, "gen_ai.request.streaming", True)


@dont_throw
def _emit_chat_request_events(event_logger, kwargs):
    """Emit request events for chat."""
    from opentelemetry._logs import LogRecord

    capture_content = is_content_enabled()

    for message in kwargs.get("messages", []):
        role = message.get("role", "user")
        body = {}

        if capture_content:
            content = message.get("content")
            if content:
                body["content"] = content

        log_record = LogRecord(
            event_name=f"gen_ai.{role}.message",
            attributes={GenAIAttributes.GEN_AI_SYSTEM: "ollama"},
            body=body if body else None,
        )
        event_logger.emit(log_record)


@dont_throw
def _emit_generate_request_events(event_logger, kwargs):
    """Emit request events for generate."""
    from opentelemetry._logs import LogRecord

    capture_content = is_content_enabled()

    body = {}
    if capture_content:
        prompt = kwargs.get("prompt")
        if prompt:
            body["content"] = prompt

    log_record = LogRecord(
        event_name="gen_ai.user.message",
        attributes={GenAIAttributes.GEN_AI_SYSTEM: "ollama"},
        body=body if body else None,
    )
    event_logger.emit(log_record)


@dont_throw
def _set_response_attributes(span, response):
    """Set response attributes on span."""
    if not span.is_recording():
        return

    if isinstance(response, dict):
        set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, response.get("model"))

        if "prompt_eval_count" in response:
            set_span_attribute(
                span,
                GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
                response.get("prompt_eval_count"),
            )
        if "eval_count" in response:
            set_span_attribute(
                span,
                GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS,
                response.get("eval_count"),
            )

        if response.get("done"):
            set_span_attribute(
                span,
                GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS,
                [response.get("done_reason", "stop")],
            )


@dont_throw
def _emit_chat_response_events(event_logger, response):
    """Emit response events for chat."""
    from opentelemetry._logs import LogRecord

    capture_content = is_content_enabled()

    if isinstance(response, dict):
        body = {"index": 0, "finish_reason": response.get("done_reason", "stop")}

        message = {"role": "assistant"}
        if capture_content:
            msg = response.get("message", {})
            content = msg.get("content")
            if content:
                message["content"] = content

        body["message"] = message

        log_record = LogRecord(
            event_name="gen_ai.choice",
            attributes={GenAIAttributes.GEN_AI_SYSTEM: "ollama"},
            body=body,
        )
        event_logger.emit(log_record)


@dont_throw
def _emit_generate_response_events(event_logger, response):
    """Emit response events for generate."""
    from opentelemetry._logs import LogRecord

    capture_content = is_content_enabled()

    if isinstance(response, dict):
        body = {"index": 0, "finish_reason": response.get("done_reason", "stop")}

        message = {"role": "assistant"}
        if capture_content:
            content = response.get("response")
            if content:
                message["content"] = content

        body["message"] = message

        log_record = LogRecord(
            event_name="gen_ai.choice",
            attributes={GenAIAttributes.GEN_AI_SYSTEM: "ollama"},
            body=body,
        )
        event_logger.emit(log_record)


def create_chat_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for Ollama chat."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            "ollama.chat",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "ollama",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.CHAT.value,
            },
        ) as span:
            _set_request_attributes(span, kwargs)
            if event_logger:
                _emit_chat_request_events(event_logger, kwargs)

            try:
                response = wrapped(*args, **kwargs)

                # Handle streaming
                if kwargs.get("stream"):
                    return _wrap_chat_stream(span, event_logger, response)

                _set_response_attributes(span, response)
                if event_logger:
                    _emit_chat_response_events(event_logger, response)

                if span.is_recording():
                    span.set_status(Status(StatusCode.OK))

                return response
            except Exception as error:
                span.set_status(Status(StatusCode.ERROR, str(error)))
                if span.is_recording():
                    span.set_attribute("error.type", type(error).__qualname__)
                raise

    return wrapper


def _wrap_chat_stream(span, event_logger, response):
    """Wrap chat streaming response."""
    accumulated_content = []
    final_response = None

    for chunk in response:
        if isinstance(chunk, dict):
            final_response = chunk
            msg = chunk.get("message", {})
            content = msg.get("content")
            if content:
                accumulated_content.append(content)
        yield chunk

    if final_response and span.is_recording():
        _set_response_attributes(span, final_response)
        span.set_status(Status(StatusCode.OK))

    if event_logger and final_response:
        from opentelemetry._logs import LogRecord

        body = {"index": 0, "finish_reason": final_response.get("done_reason", "stop")}
        message = {"role": "assistant"}
        if is_content_enabled() and accumulated_content:
            message["content"] = "".join(accumulated_content)
        body["message"] = message

        log_record = LogRecord(
            event_name="gen_ai.choice",
            attributes={GenAIAttributes.GEN_AI_SYSTEM: "ollama"},
            body=body,
        )
        event_logger.emit(log_record)

    span.end()


def create_generate_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for Ollama generate."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            "ollama.generate",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "ollama",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.TEXT_COMPLETION.value,
            },
        ) as span:
            _set_request_attributes(span, kwargs)
            if event_logger:
                _emit_generate_request_events(event_logger, kwargs)

            try:
                response = wrapped(*args, **kwargs)

                # Handle streaming
                if kwargs.get("stream"):
                    return _wrap_generate_stream(span, event_logger, response)

                _set_response_attributes(span, response)
                if event_logger:
                    _emit_generate_response_events(event_logger, response)

                if span.is_recording():
                    span.set_status(Status(StatusCode.OK))

                return response
            except Exception as error:
                span.set_status(Status(StatusCode.ERROR, str(error)))
                if span.is_recording():
                    span.set_attribute("error.type", type(error).__qualname__)
                raise

    return wrapper


def _wrap_generate_stream(span, event_logger, response):
    """Wrap generate streaming response."""
    accumulated_content = []
    final_response = None

    for chunk in response:
        if isinstance(chunk, dict):
            final_response = chunk
            content = chunk.get("response")
            if content:
                accumulated_content.append(content)
        yield chunk

    if final_response and span.is_recording():
        _set_response_attributes(span, final_response)
        span.set_status(Status(StatusCode.OK))

    if event_logger and final_response:
        from opentelemetry._logs import LogRecord

        body = {"index": 0, "finish_reason": final_response.get("done_reason", "stop")}
        message = {"role": "assistant"}
        if is_content_enabled() and accumulated_content:
            message["content"] = "".join(accumulated_content)
        body["message"] = message

        log_record = LogRecord(
            event_name="gen_ai.choice",
            attributes={GenAIAttributes.GEN_AI_SYSTEM: "ollama"},
            body=body,
        )
        event_logger.emit(log_record)

    span.end()


def create_embeddings_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for Ollama embeddings."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            "ollama.embeddings",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "ollama",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value,
            },
        ) as span:
            set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_MODEL, kwargs.get("model"))

            prompt = kwargs.get("prompt")
            if isinstance(prompt, list):
                set_span_attribute(span, "gen_ai.embeddings.input_count", len(prompt))
            else:
                set_span_attribute(span, "gen_ai.embeddings.input_count", 1)

            try:
                response = wrapped(*args, **kwargs)

                if isinstance(response, dict):
                    embedding = response.get("embedding")
                    if embedding:
                        set_span_attribute(span, "gen_ai.embeddings.dimension", len(embedding))

                if span.is_recording():
                    span.set_status(Status(StatusCode.OK))

                return response
            except Exception as error:
                span.set_status(Status(StatusCode.ERROR, str(error)))
                if span.is_recording():
                    span.set_attribute("error.type", type(error).__qualname__)
                raise

    return wrapper


def create_async_chat_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for async Ollama chat."""

    async def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return await wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            "ollama.chat",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "ollama",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.CHAT.value,
            },
        ) as span:
            _set_request_attributes(span, kwargs)
            if event_logger:
                _emit_chat_request_events(event_logger, kwargs)

            try:
                response = await wrapped(*args, **kwargs)

                _set_response_attributes(span, response)
                if event_logger:
                    _emit_chat_response_events(event_logger, response)

                if span.is_recording():
                    span.set_status(Status(StatusCode.OK))

                return response
            except Exception as error:
                span.set_status(Status(StatusCode.ERROR, str(error)))
                if span.is_recording():
                    span.set_attribute("error.type", type(error).__qualname__)
                raise

    return wrapper


def create_async_generate_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for async Ollama generate."""

    async def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return await wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            "ollama.generate",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "ollama",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.TEXT_COMPLETION.value,
            },
        ) as span:
            _set_request_attributes(span, kwargs)
            if event_logger:
                _emit_generate_request_events(event_logger, kwargs)

            try:
                response = await wrapped(*args, **kwargs)

                _set_response_attributes(span, response)
                if event_logger:
                    _emit_generate_response_events(event_logger, response)

                if span.is_recording():
                    span.set_status(Status(StatusCode.OK))

                return response
            except Exception as error:
                span.set_status(Status(StatusCode.ERROR, str(error)))
                if span.is_recording():
                    span.set_attribute("error.type", type(error).__qualname__)
                raise

    return wrapper
