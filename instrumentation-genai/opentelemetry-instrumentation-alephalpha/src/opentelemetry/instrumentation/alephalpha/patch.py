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

"""Patching functions for Aleph Alpha instrumentation."""

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

from opentelemetry.instrumentation.alephalpha.utils import (
    dont_throw,
    is_content_enabled,
    set_span_attribute,
)

logger = logging.getLogger(__name__)


@dont_throw
def _set_request_attributes(span, model, request):
    """Set request attributes on span."""
    if not span.is_recording():
        return

    set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_MODEL, model)

    if hasattr(request, "maximum_tokens"):
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS, request.maximum_tokens
        )
    if hasattr(request, "temperature"):
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE, request.temperature
        )
    if hasattr(request, "top_p"):
        set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_TOP_P, request.top_p)
    if hasattr(request, "top_k"):
        set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_TOP_K, request.top_k)


@dont_throw
def _emit_request_events(event_logger, request):
    """Emit request events."""
    from opentelemetry._logs import LogRecord

    capture_content = is_content_enabled()

    body = {}
    if capture_content and hasattr(request, "prompt"):
        prompt = request.prompt
        if hasattr(prompt, "items") and prompt.items:
            # Extract text from prompt items
            text_content = []
            for item in prompt.items:
                if hasattr(item, "text"):
                    text_content.append(item.text)
            if text_content:
                body["content"] = "\n".join(text_content)

    log_record = LogRecord(
        event_name="gen_ai.user.message",
        attributes={GenAIAttributes.GEN_AI_SYSTEM: "aleph_alpha"},
        body=body if body else None,
    )
    event_logger.emit(log_record)


@dont_throw
def _set_response_attributes(span, response):
    """Set response attributes on span."""
    if not span.is_recording():
        return

    if hasattr(response, "model_version"):
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, response.model_version
        )

    # Extract completion tokens from response
    if hasattr(response, "completions") and response.completions:
        completion = response.completions[0]
        if hasattr(completion, "finish_reason"):
            set_span_attribute(
                span,
                GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS,
                [completion.finish_reason],
            )


@dont_throw
def _emit_response_events(event_logger, response):
    """Emit response events."""
    from opentelemetry._logs import LogRecord

    capture_content = is_content_enabled()

    if hasattr(response, "completions"):
        for i, completion in enumerate(response.completions):
            body = {
                "index": i,
                "finish_reason": getattr(completion, "finish_reason", "unknown"),
            }

            message = {"role": "assistant"}
            if capture_content and hasattr(completion, "completion"):
                message["content"] = completion.completion

            body["message"] = message

            log_record = LogRecord(
                event_name="gen_ai.choice",
                attributes={GenAIAttributes.GEN_AI_SYSTEM: "aleph_alpha"},
                body=body,
            )
            event_logger.emit(log_record)


def create_complete_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for Client.complete."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        model = kwargs.get("model") or (args[1] if len(args) > 1 else None)
        request = kwargs.get("request") or (args[0] if args else None)

        with tracer.start_as_current_span(
            "aleph_alpha.completion",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "aleph_alpha",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.TEXT_COMPLETION.value,
            },
        ) as span:
            _set_request_attributes(span, model, request)
            if event_logger:
                _emit_request_events(event_logger, request)

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


def create_chat_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for Client.chat."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        model = kwargs.get("model")
        request = kwargs.get("request") or (args[0] if args else None)

        with tracer.start_as_current_span(
            "aleph_alpha.chat",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "aleph_alpha",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.CHAT.value,
            },
        ) as span:
            set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_MODEL, model)

            if event_logger and is_content_enabled():
                from opentelemetry._logs import LogRecord

                if hasattr(request, "messages"):
                    for message in request.messages:
                        body = {}
                        if hasattr(message, "content"):
                            body["content"] = message.content

                        log_record = LogRecord(
                            event_name=f"gen_ai.{getattr(message, 'role', 'user')}.message",
                            attributes={GenAIAttributes.GEN_AI_SYSTEM: "aleph_alpha"},
                            body=body if body else None,
                        )
                        event_logger.emit(log_record)

            try:
                response = wrapped(*args, **kwargs)

                if span.is_recording():
                    span.set_status(Status(StatusCode.OK))

                if event_logger and hasattr(response, "message"):
                    from opentelemetry._logs import LogRecord

                    body = {"index": 0, "finish_reason": "stop"}
                    message = {"role": "assistant"}
                    if is_content_enabled() and hasattr(response.message, "content"):
                        message["content"] = response.message.content
                    body["message"] = message

                    log_record = LogRecord(
                        event_name="gen_ai.choice",
                        attributes={GenAIAttributes.GEN_AI_SYSTEM: "aleph_alpha"},
                        body=body,
                    )
                    event_logger.emit(log_record)

                return response
            except Exception as error:
                span.set_status(Status(StatusCode.ERROR, str(error)))
                if span.is_recording():
                    span.set_attribute("error.type", type(error).__qualname__)
                raise

    return wrapper
