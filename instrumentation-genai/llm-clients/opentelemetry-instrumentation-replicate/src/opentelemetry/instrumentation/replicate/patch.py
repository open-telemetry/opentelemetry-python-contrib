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

"""Patching functions for Replicate instrumentation."""

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

from opentelemetry.instrumentation.replicate.utils import (
    dont_throw,
    is_content_enabled,
    set_span_attribute,
)

logger = logging.getLogger(__name__)


@dont_throw
def _set_request_attributes(span, model, input_data):
    """Set request attributes on span."""
    if not span.is_recording():
        return

    set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_MODEL, model)

    if isinstance(input_data, dict):
        if "prompt" in input_data:
            set_span_attribute(
                span,
                GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS,
                input_data.get("max_tokens"),
            )
            set_span_attribute(
                span,
                GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE,
                input_data.get("temperature"),
            )
            set_span_attribute(
                span, GenAIAttributes.GEN_AI_REQUEST_TOP_P, input_data.get("top_p")
            )


@dont_throw
def _emit_request_events(event_logger, model, input_data):
    """Emit request events."""
    from opentelemetry._logs import LogRecord

    capture_content = is_content_enabled()

    body = {}
    if capture_content and isinstance(input_data, dict):
        if "prompt" in input_data:
            body["content"] = input_data.get("prompt")

    log_record = LogRecord(
        event_name="gen_ai.user.message",
        attributes={GenAIAttributes.GEN_AI_SYSTEM: "replicate"},
        body=body if body else None,
    )
    event_logger.emit(log_record)


@dont_throw
def _set_response_attributes(span, response):
    """Set response attributes on span."""
    if not span.is_recording():
        return

    # Replicate responses are typically iterators or lists
    if isinstance(response, (list, tuple)):
        set_span_attribute(span, "gen_ai.response.output_count", len(response))


@dont_throw
def _emit_response_events(event_logger, response):
    """Emit response events."""
    from opentelemetry._logs import LogRecord

    capture_content = is_content_enabled()

    body = {"index": 0, "finish_reason": "stop"}

    message = {"role": "assistant"}
    if capture_content:
        if isinstance(response, str):
            message["content"] = response
        elif isinstance(response, (list, tuple)):
            message["content"] = "".join(str(r) for r in response)

    body["message"] = message

    log_record = LogRecord(
        event_name="gen_ai.choice",
        attributes={GenAIAttributes.GEN_AI_SYSTEM: "replicate"},
        body=body,
    )
    event_logger.emit(log_record)


def create_run_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for replicate.run."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        # Extract model from first positional arg
        model = args[0] if args else kwargs.get("ref")
        input_data = kwargs.get("input", {})

        with tracer.start_as_current_span(
            "replicate.run",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "replicate",
                GenAIAttributes.GEN_AI_OPERATION_NAME: "text_completion",
            },
        ) as span:
            _set_request_attributes(span, model, input_data)
            if event_logger:
                _emit_request_events(event_logger, model, input_data)

            try:
                response = wrapped(*args, **kwargs)

                # Handle iterator responses by consuming them
                if hasattr(response, "__iter__") and not isinstance(
                    response, (str, list, tuple, dict)
                ):
                    response = list(response)

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


def create_stream_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for replicate.stream."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        model = args[0] if args else kwargs.get("ref")
        input_data = kwargs.get("input", {})

        span = tracer.start_span(
            "replicate.stream",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "replicate",
                GenAIAttributes.GEN_AI_OPERATION_NAME: "text_completion",
            },
        )

        _set_request_attributes(span, model, input_data)
        if event_logger:
            _emit_request_events(event_logger, model, input_data)

        try:
            response = wrapped(*args, **kwargs)

            # Wrap the iterator to capture streaming output
            def instrumented_stream():
                chunks = []
                try:
                    for chunk in response:
                        chunks.append(chunk)
                        yield chunk

                    if span.is_recording():
                        span.set_status(Status(StatusCode.OK))
                        _set_response_attributes(span, chunks)
                    if event_logger:
                        _emit_response_events(event_logger, chunks)
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


def create_predictions_create_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for replicate.predictions.create."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        model = kwargs.get("model") or kwargs.get("version")
        input_data = kwargs.get("input", {})

        with tracer.start_as_current_span(
            "replicate.predictions.create",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "replicate",
                GenAIAttributes.GEN_AI_OPERATION_NAME: "text_completion",
            },
        ) as span:
            _set_request_attributes(span, model, input_data)
            if event_logger:
                _emit_request_events(event_logger, model, input_data)

            try:
                response = wrapped(*args, **kwargs)

                if span.is_recording():
                    set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_ID, response.id)
                    span.set_status(Status(StatusCode.OK))

                return response
            except Exception as error:
                span.set_status(Status(StatusCode.ERROR, str(error)))
                if span.is_recording():
                    span.set_attribute("error.type", type(error).__qualname__)
                raise

    return wrapper
