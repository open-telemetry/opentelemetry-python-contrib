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

"""Patching functions for IBM WatsonX instrumentation."""

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

from opentelemetry.instrumentation.watsonx.utils import (
    dont_throw,
    is_content_enabled,
    set_span_attribute,
)

logger = logging.getLogger(__name__)


@dont_throw
def _get_model_id(instance):
    """Extract model ID from instance."""
    if hasattr(instance, "model_id"):
        return instance.model_id
    if hasattr(instance, "_model_id"):
        return instance._model_id
    return "unknown"


@dont_throw
def _set_request_attributes(span, instance, kwargs):
    """Set request attributes on span."""
    if not span.is_recording():
        return

    model_id = _get_model_id(instance)
    set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_MODEL, model_id)

    params = kwargs.get("params", {})
    if params:
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS,
            params.get("max_new_tokens"),
        )
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE,
            params.get("temperature"),
        )
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_REQUEST_TOP_P, params.get("top_p")
        )
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_REQUEST_TOP_K, params.get("top_k")
        )


@dont_throw
def _emit_request_events(event_logger, prompt):
    """Emit request events."""
    from opentelemetry._logs import LogRecord

    capture_content = is_content_enabled()

    body = {}
    if capture_content and prompt:
        if isinstance(prompt, str):
            body["content"] = prompt
        elif isinstance(prompt, list):
            body["content"] = "\n".join(str(p) for p in prompt)

    log_record = LogRecord(
        event_name="gen_ai.user.message",
        attributes={GenAIAttributes.GEN_AI_SYSTEM: "ibm.watsonx"},
        body=body if body else None,
    )
    event_logger.emit(log_record)


@dont_throw
def _set_response_attributes(span, response):
    """Set response attributes on span."""
    if not span.is_recording():
        return

    if isinstance(response, dict):
        # Handle results format
        results = response.get("results", [])
        if results:
            result = results[0]
            if "generated_token_count" in result:
                set_span_attribute(
                    span,
                    GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS,
                    result["generated_token_count"],
                )
            if "input_token_count" in result:
                set_span_attribute(
                    span,
                    GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
                    result["input_token_count"],
                )
            if "stop_reason" in result:
                set_span_attribute(
                    span,
                    GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS,
                    [result["stop_reason"]],
                )


@dont_throw
def _emit_response_events(event_logger, response):
    """Emit response events."""
    from opentelemetry._logs import LogRecord

    capture_content = is_content_enabled()

    if isinstance(response, dict):
        results = response.get("results", [])
        for i, result in enumerate(results):
            body = {
                "index": i,
                "finish_reason": result.get("stop_reason", "stop"),
            }

            message = {"role": "assistant"}
            if capture_content:
                generated_text = result.get("generated_text")
                if generated_text:
                    message["content"] = generated_text

            body["message"] = message

            log_record = LogRecord(
                event_name="gen_ai.choice",
                attributes={GenAIAttributes.GEN_AI_SYSTEM: "ibm.watsonx"},
                body=body,
            )
            event_logger.emit(log_record)
    elif isinstance(response, str):
        body = {"index": 0, "finish_reason": "stop"}
        message = {"role": "assistant"}
        if capture_content:
            message["content"] = response
        body["message"] = message

        log_record = LogRecord(
            event_name="gen_ai.choice",
            attributes={GenAIAttributes.GEN_AI_SYSTEM: "ibm.watsonx"},
            body=body,
        )
        event_logger.emit(log_record)


def create_generate_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for WatsonX generate."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        model_id = _get_model_id(instance)
        prompt = args[0] if args else kwargs.get("prompt")

        with tracer.start_as_current_span(
            f"watsonx.generate {model_id}",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "ibm.watsonx",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.TEXT_COMPLETION.value,
            },
        ) as span:
            _set_request_attributes(span, instance, kwargs)
            if event_logger:
                _emit_request_events(event_logger, prompt)

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


def create_generate_text_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for WatsonX generate_text."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        model_id = _get_model_id(instance)
        prompt = args[0] if args else kwargs.get("prompt")

        with tracer.start_as_current_span(
            f"watsonx.generate_text {model_id}",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "ibm.watsonx",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.TEXT_COMPLETION.value,
            },
        ) as span:
            _set_request_attributes(span, instance, kwargs)
            if event_logger:
                _emit_request_events(event_logger, prompt)

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


def create_generate_text_stream_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for WatsonX generate_text_stream."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        model_id = _get_model_id(instance)
        prompt = args[0] if args else kwargs.get("prompt")

        span = tracer.start_span(
            f"watsonx.generate_text_stream {model_id}",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "ibm.watsonx",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.TEXT_COMPLETION.value,
            },
        )

        _set_request_attributes(span, instance, kwargs)
        if event_logger:
            _emit_request_events(event_logger, prompt)

        try:
            response = wrapped(*args, **kwargs)

            def instrumented_stream():
                accumulated_content = []
                try:
                    for chunk in response:
                        if isinstance(chunk, str):
                            accumulated_content.append(chunk)
                        yield chunk

                    if span.is_recording():
                        span.set_status(Status(StatusCode.OK))

                    if event_logger:
                        from opentelemetry._logs import LogRecord

                        body = {"index": 0, "finish_reason": "stop"}
                        message = {"role": "assistant"}
                        if is_content_enabled() and accumulated_content:
                            message["content"] = "".join(accumulated_content)
                        body["message"] = message

                        log_record = LogRecord(
                            event_name="gen_ai.choice",
                            attributes={GenAIAttributes.GEN_AI_SYSTEM: "ibm.watsonx"},
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


def create_chat_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for WatsonX chat."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        model_id = _get_model_id(instance)

        with tracer.start_as_current_span(
            f"watsonx.chat {model_id}",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "ibm.watsonx",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.CHAT.value,
            },
        ) as span:
            _set_request_attributes(span, instance, kwargs)

            # Emit message events
            if event_logger:
                from opentelemetry._logs import LogRecord

                messages = kwargs.get("messages", [])
                for message in messages:
                    role = message.get("role", "user")
                    body = {}
                    if is_content_enabled():
                        content = message.get("content")
                        if content:
                            body["content"] = content

                    log_record = LogRecord(
                        event_name=f"gen_ai.{role}.message",
                        attributes={GenAIAttributes.GEN_AI_SYSTEM: "ibm.watsonx"},
                        body=body if body else None,
                    )
                    event_logger.emit(log_record)

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
