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

"""Patching functions for AWS Bedrock instrumentation."""

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

from opentelemetry.instrumentation.bedrock.utils import (
    dont_throw,
    get_model_provider,
    is_content_enabled,
    safe_json_loads,
    set_span_attribute,
)

logger = logging.getLogger(__name__)


@dont_throw
def _set_invoke_model_attributes(span, kwargs, body_parsed):
    """Set request attributes for invoke_model."""
    if not span.is_recording():
        return

    model_id = kwargs.get("modelId", "")
    set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_MODEL, model_id)
    set_span_attribute(span, "aws.bedrock.model_provider", get_model_provider(model_id))

    if body_parsed:
        # Anthropic
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS,
            body_parsed.get("max_tokens_to_sample") or body_parsed.get("max_tokens"),
        )
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE,
            body_parsed.get("temperature"),
        )
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_REQUEST_TOP_P, body_parsed.get("top_p")
        )
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_REQUEST_TOP_K, body_parsed.get("top_k")
        )


@dont_throw
def _set_converse_attributes(span, kwargs):
    """Set request attributes for converse."""
    if not span.is_recording():
        return

    model_id = kwargs.get("modelId", "")
    set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_MODEL, model_id)
    set_span_attribute(span, "aws.bedrock.model_provider", get_model_provider(model_id))

    inference_config = kwargs.get("inferenceConfig", {})
    if inference_config:
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS,
            inference_config.get("maxTokens"),
        )
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE,
            inference_config.get("temperature"),
        )
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_REQUEST_TOP_P, inference_config.get("topP")
        )


@dont_throw
def _emit_converse_request_events(event_logger, kwargs):
    """Emit request events for converse."""
    from opentelemetry._logs import LogRecord

    capture_content = is_content_enabled()

    messages = kwargs.get("messages", [])
    for message in messages:
        role = message.get("role", "user")
        body = {}

        if capture_content:
            content = message.get("content", [])
            text_parts = []
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    text_parts.append(part["text"])
            if text_parts:
                body["content"] = "\n".join(text_parts)

        log_record = LogRecord(
            event_name=f"gen_ai.{role}.message",
            attributes={GenAIAttributes.GEN_AI_SYSTEM: "aws.bedrock"},
            body=body if body else None,
        )
        event_logger.emit(log_record)

    # System prompt
    system = kwargs.get("system", [])
    for sys_msg in system:
        if isinstance(sys_msg, dict) and "text" in sys_msg:
            body = {}
            if capture_content:
                body["content"] = sys_msg["text"]

            log_record = LogRecord(
                event_name="gen_ai.system.message",
                attributes={GenAIAttributes.GEN_AI_SYSTEM: "aws.bedrock"},
                body=body if body else None,
            )
            event_logger.emit(log_record)


@dont_throw
def _set_converse_response_attributes(span, response):
    """Set response attributes for converse."""
    if not span.is_recording():
        return

    if "stopReason" in response:
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS, [response["stopReason"]]
        )

    usage = response.get("usage", {})
    if usage:
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS, usage.get("inputTokens")
        )
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS, usage.get("outputTokens")
        )


@dont_throw
def _emit_converse_response_events(event_logger, response):
    """Emit response events for converse."""
    from opentelemetry._logs import LogRecord

    capture_content = is_content_enabled()

    body = {"index": 0, "finish_reason": response.get("stopReason", "stop")}
    message = {"role": "assistant"}

    output = response.get("output", {})
    msg = output.get("message", {})
    content = msg.get("content", [])

    if capture_content and content:
        text_parts = []
        for part in content:
            if isinstance(part, dict) and "text" in part:
                text_parts.append(part["text"])
        if text_parts:
            message["content"] = "\n".join(text_parts)

    body["message"] = message

    log_record = LogRecord(
        event_name="gen_ai.choice",
        attributes={GenAIAttributes.GEN_AI_SYSTEM: "aws.bedrock"},
        body=body,
    )
    event_logger.emit(log_record)


def create_invoke_model_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for Bedrock invoke_model."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        model_id = kwargs.get("modelId", "unknown")
        body = kwargs.get("body", b"{}")
        body_parsed = safe_json_loads(body)

        with tracer.start_as_current_span(
            f"bedrock.invoke_model {model_id}",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "aws.bedrock",
                GenAIAttributes.GEN_AI_OPERATION_NAME: "invoke_model",
            },
        ) as span:
            _set_invoke_model_attributes(span, kwargs, body_parsed)

            # Emit request events
            if event_logger and body_parsed:
                from opentelemetry._logs import LogRecord

                capture_content = is_content_enabled()
                body_content = {}

                if capture_content:
                    prompt = body_parsed.get("prompt") or body_parsed.get("inputText")
                    if prompt:
                        body_content["content"] = prompt

                log_record = LogRecord(
                    event_name="gen_ai.user.message",
                    attributes={GenAIAttributes.GEN_AI_SYSTEM: "aws.bedrock"},
                    body=body_content if body_content else None,
                )
                event_logger.emit(log_record)

            try:
                response = wrapped(*args, **kwargs)

                # Parse response body
                if "body" in response:
                    response_body = response["body"].read()
                    # Reset stream for caller
                    response["body"]._raw_stream.seek(0)

                    response_parsed = safe_json_loads(response_body)
                    if response_parsed and span.is_recording():
                        # Anthropic response
                        if "completion" in response_parsed:
                            set_span_attribute(
                                span,
                                GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS,
                                [response_parsed.get("stop_reason", "stop")],
                            )

                        # Token usage
                        if "usage" in response_parsed:
                            usage = response_parsed["usage"]
                            set_span_attribute(
                                span,
                                GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
                                usage.get("input_tokens"),
                            )
                            set_span_attribute(
                                span,
                                GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS,
                                usage.get("output_tokens"),
                            )

                        # Emit response events
                        if event_logger:
                            from opentelemetry._logs import LogRecord

                            capture_content = is_content_enabled()
                            body_content = {
                                "index": 0,
                                "finish_reason": response_parsed.get("stop_reason", "stop"),
                            }
                            message = {"role": "assistant"}

                            if capture_content:
                                completion = response_parsed.get("completion") or response_parsed.get("content", [{}])[0].get("text")
                                if completion:
                                    message["content"] = completion

                            body_content["message"] = message

                            log_record = LogRecord(
                                event_name="gen_ai.choice",
                                attributes={GenAIAttributes.GEN_AI_SYSTEM: "aws.bedrock"},
                                body=body_content,
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


def create_converse_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for Bedrock converse."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        model_id = kwargs.get("modelId", "unknown")

        with tracer.start_as_current_span(
            f"bedrock.converse {model_id}",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "aws.bedrock",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.CHAT.value,
            },
        ) as span:
            _set_converse_attributes(span, kwargs)
            if event_logger:
                _emit_converse_request_events(event_logger, kwargs)

            try:
                response = wrapped(*args, **kwargs)

                _set_converse_response_attributes(span, response)
                if event_logger:
                    _emit_converse_response_events(event_logger, response)

                if span.is_recording():
                    span.set_status(Status(StatusCode.OK))

                return response
            except Exception as error:
                span.set_status(Status(StatusCode.ERROR, str(error)))
                if span.is_recording():
                    span.set_attribute("error.type", type(error).__qualname__)
                raise

    return wrapper


def create_converse_stream_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for Bedrock converse_stream."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        model_id = kwargs.get("modelId", "unknown")

        span = tracer.start_span(
            f"bedrock.converse_stream {model_id}",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "aws.bedrock",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.CHAT.value,
            },
        )

        _set_converse_attributes(span, kwargs)
        if event_logger:
            _emit_converse_request_events(event_logger, kwargs)

        try:
            response = wrapped(*args, **kwargs)

            # Wrap the stream
            original_stream = response.get("stream")
            if original_stream:
                response["stream"] = _wrap_converse_stream(span, event_logger, original_stream)

            return response
        except Exception as error:
            span.set_status(Status(StatusCode.ERROR, str(error)))
            if span.is_recording():
                span.set_attribute("error.type", type(error).__qualname__)
            span.end()
            raise

    return wrapper


def _wrap_converse_stream(span, event_logger, stream):
    """Wrap the converse stream."""
    accumulated_content = []
    stop_reason = None
    input_tokens = 0
    output_tokens = 0

    for event in stream:
        if "contentBlockDelta" in event:
            delta = event["contentBlockDelta"].get("delta", {})
            text = delta.get("text")
            if text:
                accumulated_content.append(text)

        if "messageStop" in event:
            stop_reason = event["messageStop"].get("stopReason")

        if "metadata" in event:
            usage = event["metadata"].get("usage", {})
            input_tokens = usage.get("inputTokens", 0)
            output_tokens = usage.get("outputTokens", 0)

        yield event

    if span.is_recording():
        if stop_reason:
            set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS, [stop_reason])
        if input_tokens:
            set_span_attribute(span, GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS, input_tokens)
        if output_tokens:
            set_span_attribute(span, GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS, output_tokens)
        span.set_status(Status(StatusCode.OK))

    if event_logger:
        from opentelemetry._logs import LogRecord

        body = {"index": 0, "finish_reason": stop_reason or "stop"}
        message = {"role": "assistant"}
        if is_content_enabled() and accumulated_content:
            message["content"] = "".join(accumulated_content)
        body["message"] = message

        log_record = LogRecord(
            event_name="gen_ai.choice",
            attributes={GenAIAttributes.GEN_AI_SYSTEM: "aws.bedrock"},
            body=body,
        )
        event_logger.emit(log_record)

    span.end()
