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

"""Patching functions for Together instrumentation."""

from __future__ import annotations

import json
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

from opentelemetry.instrumentation.together.utils import (
    dont_throw,
    is_content_enabled,
    set_span_attribute,
)

logger = logging.getLogger(__name__)


def _get_operation_name(method: str) -> str:
    """Map method to operation name."""
    if "chat" in method:
        return GenAIAttributes.GenAiOperationNameValues.CHAT.value
    return GenAIAttributes.GenAiOperationNameValues.TEXT_COMPLETION.value


@dont_throw
def _set_request_attributes(span, kwargs, operation_name):
    """Set request attributes on span."""
    if not span.is_recording():
        return

    set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_MODEL, kwargs.get("model"))
    set_span_attribute(
        span,
        GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE,
        kwargs.get("temperature"),
    )
    set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_TOP_P, kwargs.get("top_p"))
    set_span_attribute(
        span, GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS, kwargs.get("max_tokens")
    )

    if kwargs.get("stream") is not None:
        set_span_attribute(span, "gen_ai.request.streaming", bool(kwargs.get("stream")))


@dont_throw
def _emit_request_events(event_logger, kwargs, operation_name):
    """Emit request events."""
    from opentelemetry._logs import LogRecord

    capture_content = is_content_enabled()

    if operation_name == GenAIAttributes.GenAiOperationNameValues.CHAT.value:
        for message in kwargs.get("messages", []):
            body = {}
            if capture_content and message.get("content"):
                body["content"] = message.get("content")

            log_record = LogRecord(
                event_name=f"gen_ai.{message.get('role', 'user')}.message",
                attributes={GenAIAttributes.GEN_AI_SYSTEM: "together"},
                body=body if body else None,
            )
            event_logger.emit(log_record)
    else:
        body = {}
        if capture_content and kwargs.get("prompt"):
            body["content"] = kwargs.get("prompt")

        log_record = LogRecord(
            event_name="gen_ai.user.message",
            attributes={GenAIAttributes.GEN_AI_SYSTEM: "together"},
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
        input_tokens = getattr(usage, "prompt_tokens", 0)
        output_tokens = getattr(usage, "completion_tokens", 0)

        set_span_attribute(
            span, GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS, input_tokens
        )
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS, output_tokens
        )

    if response.choices:
        finish_reason = getattr(response.choices[0], "finish_reason", None)
        if finish_reason:
            set_span_attribute(
                span,
                GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS,
                [finish_reason],
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

        message = {}
        if hasattr(choice, "message"):
            message["role"] = "assistant"
            if capture_content:
                content = getattr(choice.message, "content", None)
                if content:
                    message["content"] = content
        elif hasattr(choice, "text"):
            message["role"] = "assistant"
            if capture_content:
                text = getattr(choice, "text", None)
                if text:
                    message["content"] = text

        body["message"] = message

        log_record = LogRecord(
            event_name="gen_ai.choice",
            attributes={GenAIAttributes.GEN_AI_SYSTEM: "together"},
            body=body,
        )
        event_logger.emit(log_record)


def create_wrapper(
    tracer: Tracer, event_logger: Logger, method: str, span_name: str
) -> Callable:
    """Create a wrapper for Together AI methods."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        operation_name = _get_operation_name(method)

        with tracer.start_as_current_span(
            span_name,
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "together",
                GenAIAttributes.GEN_AI_OPERATION_NAME: operation_name,
            },
        ) as span:
            _set_request_attributes(span, kwargs, operation_name)
            if event_logger:
                _emit_request_events(event_logger, kwargs, operation_name)

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
