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

"""Patching functions for SageMaker instrumentation."""

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

from opentelemetry.instrumentation.sagemaker.utils import (
    dont_throw,
    is_content_enabled,
    safe_json_loads,
    set_span_attribute,
)

logger = logging.getLogger(__name__)


@dont_throw
def _set_request_attributes(span, kwargs):
    """Set request attributes on span."""
    if not span.is_recording():
        return

    endpoint_name = kwargs.get("EndpointName")
    set_span_attribute(span, "aws.sagemaker.endpoint_name", endpoint_name)
    set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_MODEL, endpoint_name)
    set_span_attribute(span, "aws.sagemaker.content_type", kwargs.get("ContentType"))
    set_span_attribute(span, "aws.sagemaker.accept", kwargs.get("Accept"))

    # Try to parse request body for model inference parameters
    body = kwargs.get("Body")
    if body:
        parsed = safe_json_loads(body)
        if parsed:
            # Common inference parameters
            set_span_attribute(
                span,
                GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS,
                parsed.get("max_new_tokens") or parsed.get("max_tokens"),
            )
            set_span_attribute(
                span,
                GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE,
                parsed.get("temperature"),
            )
            set_span_attribute(
                span, GenAIAttributes.GEN_AI_REQUEST_TOP_P, parsed.get("top_p")
            )


@dont_throw
def _emit_request_events(event_logger, kwargs):
    """Emit request events."""
    from opentelemetry._logs import LogRecord

    capture_content = is_content_enabled()

    body = kwargs.get("Body")
    if body:
        parsed = safe_json_loads(body)
        if parsed:
            body_content = {}
            if capture_content:
                # Try common input formats
                inputs = (
                    parsed.get("inputs")
                    or parsed.get("prompt")
                    or parsed.get("input")
                    or parsed.get("text")
                )
                if inputs:
                    body_content["content"] = inputs

            log_record = LogRecord(
                event_name="gen_ai.user.message",
                attributes={GenAIAttributes.GEN_AI_SYSTEM: "aws.sagemaker"},
                body=body_content if body_content else None,
            )
            event_logger.emit(log_record)


@dont_throw
def _set_response_attributes(span, response):
    """Set response attributes on span."""
    if not span.is_recording():
        return

    if "ContentType" in response:
        set_span_attribute(span, "aws.sagemaker.response.content_type", response["ContentType"])

    if "InvokedProductionVariant" in response:
        set_span_attribute(
            span, "aws.sagemaker.invoked_production_variant", response["InvokedProductionVariant"]
        )


@dont_throw
def _emit_response_events(event_logger, response):
    """Emit response events."""
    from opentelemetry._logs import LogRecord

    capture_content = is_content_enabled()

    body = {"index": 0, "finish_reason": "stop"}
    message = {"role": "assistant"}

    if capture_content and "Body" in response:
        response_body = response["Body"].read()
        # Reset the stream position for the caller
        response["Body"]._raw_stream.seek(0)

        parsed = safe_json_loads(response_body)
        if parsed:
            # Try common output formats
            output = (
                parsed.get("generated_text")
                or parsed.get("outputs")
                or parsed.get("output")
                or parsed.get("text")
            )
            if output:
                if isinstance(output, list):
                    output = output[0] if output else ""
                message["content"] = str(output)

    body["message"] = message

    log_record = LogRecord(
        event_name="gen_ai.choice",
        attributes={GenAIAttributes.GEN_AI_SYSTEM: "aws.sagemaker"},
        body=body,
    )
    event_logger.emit(log_record)


def create_invoke_endpoint_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for SageMaker invoke_endpoint."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        endpoint_name = kwargs.get("EndpointName", "unknown")

        with tracer.start_as_current_span(
            f"sagemaker.invoke_endpoint {endpoint_name}",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "aws.sagemaker",
                GenAIAttributes.GEN_AI_OPERATION_NAME: "invoke_endpoint",
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


def create_invoke_endpoint_async_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for SageMaker invoke_endpoint_async."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        endpoint_name = kwargs.get("EndpointName", "unknown")

        with tracer.start_as_current_span(
            f"sagemaker.invoke_endpoint_async {endpoint_name}",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "aws.sagemaker",
                GenAIAttributes.GEN_AI_OPERATION_NAME: "invoke_endpoint_async",
            },
        ) as span:
            _set_request_attributes(span, kwargs)
            set_span_attribute(span, "aws.sagemaker.input_location", kwargs.get("InputLocation"))

            try:
                response = wrapped(*args, **kwargs)

                if span.is_recording():
                    set_span_attribute(
                        span, "aws.sagemaker.output_location", response.get("OutputLocation")
                    )
                    set_span_attribute(
                        span, "aws.sagemaker.inference_id", response.get("InferenceId")
                    )
                    span.set_status(Status(StatusCode.OK))

                return response
            except Exception as error:
                span.set_status(Status(StatusCode.ERROR, str(error)))
                if span.is_recording():
                    span.set_attribute("error.type", type(error).__qualname__)
                raise

    return wrapper


def create_invoke_endpoint_with_response_stream_wrapper(
    tracer: Tracer, event_logger: Logger
) -> Callable:
    """Create a wrapper for SageMaker invoke_endpoint_with_response_stream."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        endpoint_name = kwargs.get("EndpointName", "unknown")

        span = tracer.start_span(
            f"sagemaker.invoke_endpoint_stream {endpoint_name}",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "aws.sagemaker",
                GenAIAttributes.GEN_AI_OPERATION_NAME: "invoke_endpoint_stream",
            },
        )

        _set_request_attributes(span, kwargs)
        if event_logger:
            _emit_request_events(event_logger, kwargs)

        try:
            response = wrapped(*args, **kwargs)

            # Wrap the streaming body
            original_body = response.get("Body")
            if original_body:
                response["Body"] = _wrap_stream_body(span, event_logger, original_body)

            return response
        except Exception as error:
            span.set_status(Status(StatusCode.ERROR, str(error)))
            if span.is_recording():
                span.set_attribute("error.type", type(error).__qualname__)
            span.end()
            raise

    return wrapper


def _wrap_stream_body(span, event_logger, body):
    """Wrap the streaming body to instrument it."""

    class InstrumentedStreamBody:
        def __init__(self, original_body, span, event_logger):
            self._original_body = original_body
            self._span = span
            self._event_logger = event_logger
            self._accumulated_content = []

        def __iter__(self):
            try:
                for event in self._original_body:
                    # Extract payload from event
                    if "PayloadPart" in event:
                        payload = event["PayloadPart"].get("Bytes", b"")
                        if payload and is_content_enabled():
                            parsed = safe_json_loads(payload)
                            if parsed:
                                output = parsed.get("outputs") or parsed.get("generated_text")
                                if output:
                                    self._accumulated_content.append(str(output))
                    yield event

                if self._span.is_recording():
                    self._span.set_status(Status(StatusCode.OK))

                if self._event_logger:
                    from opentelemetry._logs import LogRecord

                    body = {"index": 0, "finish_reason": "stop"}
                    message = {"role": "assistant"}
                    if is_content_enabled() and self._accumulated_content:
                        message["content"] = "".join(self._accumulated_content)
                    body["message"] = message

                    log_record = LogRecord(
                        event_name="gen_ai.choice",
                        attributes={GenAIAttributes.GEN_AI_SYSTEM: "aws.sagemaker"},
                        body=body,
                    )
                    self._event_logger.emit(log_record)

            except Exception as error:
                self._span.set_status(Status(StatusCode.ERROR, str(error)))
                if self._span.is_recording():
                    self._span.set_attribute("error.type", type(error).__qualname__)
                raise
            finally:
                self._span.end()

        def close(self):
            if hasattr(self._original_body, "close"):
                self._original_body.close()

    return InstrumentedStreamBody(body, span, event_logger)
