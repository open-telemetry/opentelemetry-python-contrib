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

"""Patching functions for Transformers instrumentation."""

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

from opentelemetry.instrumentation.transformers.utils import (
    dont_throw,
    is_content_enabled,
    set_span_attribute,
)

logger = logging.getLogger(__name__)


@dont_throw
def _get_model_name(instance):
    """Extract model name from pipeline instance."""
    if hasattr(instance, "model"):
        model = instance.model
        if hasattr(model, "config"):
            config = model.config
            if hasattr(config, "_name_or_path"):
                return config._name_or_path
            if hasattr(config, "name_or_path"):
                return config.name_or_path
        if hasattr(model, "name_or_path"):
            return model.name_or_path
    return "unknown"


@dont_throw
def _set_request_attributes(span, instance, kwargs):
    """Set request attributes on span."""
    if not span.is_recording():
        return

    model_name = _get_model_name(instance)
    set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_MODEL, model_name)

    if "max_new_tokens" in kwargs:
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS, kwargs["max_new_tokens"]
        )
    elif "max_length" in kwargs:
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS, kwargs["max_length"]
        )

    if "temperature" in kwargs:
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE, kwargs["temperature"]
        )
    if "top_p" in kwargs:
        set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_TOP_P, kwargs["top_p"])
    if "top_k" in kwargs:
        set_span_attribute(span, GenAIAttributes.GEN_AI_REQUEST_TOP_K, kwargs["top_k"])


@dont_throw
def _emit_request_events(event_logger, prompts):
    """Emit request events."""
    from opentelemetry._logs import LogRecord

    capture_content = is_content_enabled()

    if isinstance(prompts, str):
        prompts = [prompts]

    for prompt in prompts:
        body = {}
        if capture_content:
            body["content"] = prompt if isinstance(prompt, str) else str(prompt)

        log_record = LogRecord(
            event_name="gen_ai.user.message",
            attributes={GenAIAttributes.GEN_AI_SYSTEM: "transformers"},
            body=body if body else None,
        )
        event_logger.emit(log_record)


@dont_throw
def _set_response_attributes(span, response):
    """Set response attributes on span."""
    if not span.is_recording():
        return

    if isinstance(response, list):
        set_span_attribute(span, "gen_ai.response.output_count", len(response))


@dont_throw
def _emit_response_events(event_logger, response):
    """Emit response events."""
    from opentelemetry._logs import LogRecord

    capture_content = is_content_enabled()

    if not isinstance(response, list):
        response = [response]

    for i, result in enumerate(response):
        body = {"index": i, "finish_reason": "stop"}

        message = {"role": "assistant"}
        if capture_content:
            if isinstance(result, dict) and "generated_text" in result:
                message["content"] = result["generated_text"]
            elif isinstance(result, list) and result:
                if isinstance(result[0], dict) and "generated_text" in result[0]:
                    message["content"] = result[0]["generated_text"]

        body["message"] = message

        log_record = LogRecord(
            event_name="gen_ai.choice",
            attributes={GenAIAttributes.GEN_AI_SYSTEM: "transformers"},
            body=body,
        )
        event_logger.emit(log_record)


def create_text_generation_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for TextGenerationPipeline.__call__."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        # Get prompts from args
        prompts = args[0] if args else kwargs.get("text_inputs")

        with tracer.start_as_current_span(
            "transformers.text_generation",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "transformers",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.TEXT_COMPLETION.value,
            },
        ) as span:
            _set_request_attributes(span, instance, kwargs)
            if event_logger:
                _emit_request_events(event_logger, prompts)

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


def create_text2text_generation_wrapper(
    tracer: Tracer, event_logger: Logger
) -> Callable:
    """Create a wrapper for Text2TextGenerationPipeline.__call__."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        prompts = args[0] if args else kwargs.get("text_inputs")

        with tracer.start_as_current_span(
            "transformers.text2text_generation",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "transformers",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.TEXT_COMPLETION.value,
            },
        ) as span:
            _set_request_attributes(span, instance, kwargs)
            if event_logger:
                _emit_request_events(event_logger, prompts)

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


def create_conversational_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for ConversationalPipeline.__call__."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        conversation = args[0] if args else kwargs.get("conversations")

        with tracer.start_as_current_span(
            "transformers.conversational",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "transformers",
                GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.CHAT.value,
            },
        ) as span:
            _set_request_attributes(span, instance, kwargs)

            if event_logger and is_content_enabled():
                from opentelemetry._logs import LogRecord

                # Log conversation history if available
                if hasattr(conversation, "past_user_inputs"):
                    for msg in conversation.past_user_inputs:
                        log_record = LogRecord(
                            event_name="gen_ai.user.message",
                            attributes={GenAIAttributes.GEN_AI_SYSTEM: "transformers"},
                            body={"content": msg},
                        )
                        event_logger.emit(log_record)

            try:
                response = wrapped(*args, **kwargs)

                if span.is_recording():
                    span.set_status(Status(StatusCode.OK))

                if event_logger:
                    from opentelemetry._logs import LogRecord

                    body = {"index": 0, "finish_reason": "stop"}
                    message = {"role": "assistant"}
                    if is_content_enabled() and hasattr(
                        response, "generated_responses"
                    ):
                        if response.generated_responses:
                            message["content"] = response.generated_responses[-1]
                    body["message"] = message

                    log_record = LogRecord(
                        event_name="gen_ai.choice",
                        attributes={GenAIAttributes.GEN_AI_SYSTEM: "transformers"},
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
