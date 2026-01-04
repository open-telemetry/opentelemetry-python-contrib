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

"""Patching functions for Cohere instrumentation."""

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

from opentelemetry.instrumentation.cohere.utils import (
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
    set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_TOP_P, kwargs.get("p"))
    set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_TOP_K, kwargs.get("k"))
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

    # Handle V2 API messages format
    messages = kwargs.get("messages", [])
    for message in messages:
        content, role = _extract_message_content(message)
        body = {}

        if capture_content and content:
            body["content"] = content

        log_record = LogRecord(
            event_name=f"gen_ai.{role}.message",
            attributes={GenAIAttributes.GEN_AI_SYSTEM: "cohere"},
            body=body if body else None,
        )
        event_logger.emit(log_record)

    # Handle V1 API message format
    if "message" in kwargs:
        body = {}
        if capture_content:
            body["content"] = kwargs.get("message")

        log_record = LogRecord(
            event_name="gen_ai.user.message",
            attributes={GenAIAttributes.GEN_AI_SYSTEM: "cohere"},
            body=body if body else None,
        )
        event_logger.emit(log_record)


@dont_throw
def _set_response_attributes(span, response):
    """Set response attributes on span."""
    if not span.is_recording():
        return

    if hasattr(response, "id"):
        set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_ID, response.id)

    if hasattr(response, "meta") and response.meta:
        if hasattr(response.meta, "billed_units"):
            billed = response.meta.billed_units
            input_tokens = getattr(billed, "input_tokens", 0)
            output_tokens = getattr(billed, "output_tokens", 0)
            set_span_attribute(
                span, GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS, input_tokens
            )
            set_span_attribute(
                span, GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS, output_tokens
            )

    if hasattr(response, "finish_reason"):
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS, [response.finish_reason]
        )


@dont_throw
def _emit_response_events(event_logger, response):
    """Emit response events."""
    from opentelemetry._logs import LogRecord

    capture_content = is_content_enabled()

    body = {"index": 0, "finish_reason": getattr(response, "finish_reason", "stop")}

    message = {"role": "assistant"}

    # V2 API response
    if hasattr(response, "message") and response.message:
        if capture_content:
            content = getattr(response.message, "content", None)
            if content and isinstance(content, list):
                text_parts = [c.text for c in content if hasattr(c, "text")]
                if text_parts:
                    message["content"] = "".join(text_parts)
            elif content:
                message["content"] = str(content)

    # V1 API response
    elif hasattr(response, "text"):
        if capture_content:
            message["content"] = response.text

    body["message"] = message

    log_record = LogRecord(
        event_name="gen_ai.choice",
        attributes={GenAIAttributes.GEN_AI_SYSTEM: "cohere"},
        body=body,
    )
    event_logger.emit(log_record)


def create_chat_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for Cohere chat."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            "cohere.chat",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "cohere",
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


def create_generate_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for Cohere generate (V1 API)."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            "cohere.generate",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "cohere",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.TEXT_COMPLETION.value,
            },
        ) as span:
            set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_MODEL, kwargs.get("model"))
            set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE, kwargs.get("temperature"))
            set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS, kwargs.get("max_tokens"))

            if event_logger and is_content_enabled():
                from opentelemetry._logs import LogRecord

                log_record = LogRecord(
                    event_name="gen_ai.user.message",
                    attributes={GenAIAttributes.GEN_AI_SYSTEM: "cohere"},
                    body={"content": kwargs.get("prompt", "")},
                )
                event_logger.emit(log_record)

            try:
                response = wrapped(*args, **kwargs)

                if hasattr(response, "generations") and response.generations:
                    gen = response.generations[0]
                    if hasattr(gen, "id"):
                        set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_ID, gen.id)
                    if hasattr(gen, "finish_reason"):
                        set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS, [gen.finish_reason])

                    if event_logger:
                        from opentelemetry._logs import LogRecord

                        body = {"index": 0, "finish_reason": getattr(gen, "finish_reason", "stop")}
                        message = {"role": "assistant"}
                        if is_content_enabled():
                            message["content"] = getattr(gen, "text", "")
                        body["message"] = message

                        log_record = LogRecord(
                            event_name="gen_ai.choice",
                            attributes={GenAIAttributes.GEN_AI_SYSTEM: "cohere"},
                            body=body,
                        )
                        event_logger.emit(log_record)

                if span.is_recording():
                    span.set_status(Status(StatusCode.OK))

                return response
            except Exception as error:
                span.set_status(Status(StatusCode.ERROR, str(error)))
                if span.is_recording():
                    span.set_attribute("error.type", type(error).__qualname__)
                raise

    return wrapper


def create_embed_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for Cohere embed."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            "cohere.embed",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "cohere",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value,
            },
        ) as span:
            set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_MODEL, kwargs.get("model"))

            texts = kwargs.get("texts", [])
            set_span_attribute(span, "gen_ai.embeddings.input_count", len(texts))

            try:
                response = wrapped(*args, **kwargs)

                if hasattr(response, "embeddings"):
                    set_span_attribute(span, "gen_ai.embeddings.output_count", len(response.embeddings))

                if hasattr(response, "meta") and response.meta:
                    if hasattr(response.meta, "billed_units"):
                        set_span_attribute(
                            span,
                            GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
                            getattr(response.meta.billed_units, "input_tokens", 0),
                        )

                if span.is_recording():
                    span.set_status(Status(StatusCode.OK))

                return response
            except Exception as error:
                span.set_status(Status(StatusCode.ERROR, str(error)))
                if span.is_recording():
                    span.set_attribute("error.type", type(error).__qualname__)
                raise

    return wrapper


def create_rerank_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for Cohere rerank."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            "cohere.rerank",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "cohere",
                GenAIAttributes.GEN_AI_OPERATION_NAME: "rerank",
            },
        ) as span:
            set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_MODEL, kwargs.get("model"))

            documents = kwargs.get("documents", [])
            set_span_attribute(span, "gen_ai.rerank.documents_count", len(documents))
            set_span_attribute(span, "gen_ai.rerank.top_n", kwargs.get("top_n"))

            try:
                response = wrapped(*args, **kwargs)

                if hasattr(response, "results"):
                    set_span_attribute(span, "gen_ai.rerank.results_count", len(response.results))

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
    """Create a wrapper for async Cohere chat."""

    async def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return await wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            "cohere.chat",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "cohere",
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
