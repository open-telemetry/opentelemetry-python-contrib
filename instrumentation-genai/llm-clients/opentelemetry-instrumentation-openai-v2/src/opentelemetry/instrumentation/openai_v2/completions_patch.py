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

"""Instrumentation for OpenAI's legacy Completions API."""

from timeit import default_timer
from typing import Optional

from opentelemetry._logs import Logger
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.trace import SpanKind, Tracer

from .instruments import Instruments
from .utils import (
    CaptureMode,
    get_llm_request_attributes,
    handle_span_exception,
    set_request_content_on_span,
    set_response_attributes,
    set_response_content_on_span,
    set_span_attribute,
)

# Operation name for legacy completions
COMPLETIONS_OPERATION_NAME = "text_completion"


def completions_create(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_mode: CaptureMode,
):
    """Wrap the `create` method of the `Completions` class to trace it."""

    def traced_method(wrapped, instance, args, kwargs):
        span_attributes = _get_completions_request_attributes(kwargs, instance)

        span_name = (
            f"{span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]} "
            f"{span_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]}"
        )
        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            # Set request content on span
            if span.is_recording():
                set_request_content_on_span(span, kwargs, capture_mode)

            start = default_timer()
            result = None
            error_type = None
            try:
                result = wrapped(*args, **kwargs)

                if span.is_recording():
                    _set_completions_response_attributes(
                        span, result, capture_mode
                    )
                    # Set response content on span
                    set_response_content_on_span(span, result, capture_mode)

                span.end()
                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise
            finally:
                duration = max((default_timer() - start), 0)
                _record_completions_metrics(
                    instruments,
                    duration,
                    result,
                    span_attributes,
                    error_type,
                )

    return traced_method


def async_completions_create(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_mode: CaptureMode,
):
    """Wrap the `create` method of the `AsyncCompletions` class to trace it."""

    async def traced_method(wrapped, instance, args, kwargs):
        span_attributes = _get_completions_request_attributes(kwargs, instance)

        span_name = (
            f"{span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]} "
            f"{span_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]}"
        )
        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            # Set request content on span
            if span.is_recording():
                set_request_content_on_span(span, kwargs, capture_mode)

            start = default_timer()
            result = None
            error_type = None
            try:
                result = await wrapped(*args, **kwargs)

                if span.is_recording():
                    _set_completions_response_attributes(
                        span, result, capture_mode
                    )
                    # Set response content on span
                    set_response_content_on_span(span, result, capture_mode)

                span.end()
                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise
            finally:
                duration = max((default_timer() - start), 0)
                _record_completions_metrics(
                    instruments,
                    duration,
                    result,
                    span_attributes,
                    error_type,
                )

    return traced_method


def _get_completions_request_attributes(kwargs, client_instance):
    """Get request attributes for completions API."""
    # Reuse the common attributes function with custom operation name
    attributes = get_llm_request_attributes(
        kwargs, client_instance, COMPLETIONS_OPERATION_NAME
    )

    # Add completions-specific attributes
    if "prompt" in kwargs:
        prompt = kwargs["prompt"]
        if isinstance(prompt, list):
            attributes["gen_ai.request.prompt_count"] = len(prompt)

    # Add max_tokens and other generation parameters
    if "max_tokens" in kwargs:
        attributes[GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS] = kwargs[
            "max_tokens"
        ]

    if "temperature" in kwargs:
        attributes[GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE] = kwargs[
            "temperature"
        ]

    if "top_p" in kwargs:
        attributes[GenAIAttributes.GEN_AI_REQUEST_TOP_P] = kwargs["top_p"]

    if "n" in kwargs and kwargs["n"] != 1:
        attributes[GenAIAttributes.GEN_AI_REQUEST_CHOICE_COUNT] = kwargs["n"]

    if "stop" in kwargs:
        stop = kwargs["stop"]
        if isinstance(stop, str):
            stop = [stop]
        attributes[GenAIAttributes.GEN_AI_REQUEST_STOP_SEQUENCES] = stop

    if "presence_penalty" in kwargs:
        attributes[GenAIAttributes.GEN_AI_REQUEST_PRESENCE_PENALTY] = kwargs[
            "presence_penalty"
        ]

    if "frequency_penalty" in kwargs:
        attributes[GenAIAttributes.GEN_AI_REQUEST_FREQUENCY_PENALTY] = kwargs[
            "frequency_penalty"
        ]

    return attributes


def _set_completions_response_attributes(span, result, capture_mode: CaptureMode):
    """Set response attributes for completions API."""
    # Use common response attributes
    set_response_attributes(span, result)

    # Set finish reasons
    if getattr(result, "choices", None):
        finish_reasons = []
        for choice in result.choices:
            finish_reason = getattr(choice, "finish_reason", None)
            finish_reasons.append(finish_reason or "error")

        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS,
            finish_reasons,
        )


def _record_completions_metrics(
    instruments: Instruments,
    duration: float,
    result,
    request_attributes: dict,
    error_type: Optional[str],
):
    """Record metrics for completions API."""
    common_attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: COMPLETIONS_OPERATION_NAME,
        GenAIAttributes.GEN_AI_SYSTEM: request_attributes.get(
            GenAIAttributes.GEN_AI_SYSTEM,
            GenAIAttributes.GenAiSystemValues.OPENAI.value,
        ),
        GenAIAttributes.GEN_AI_REQUEST_MODEL: request_attributes[
            GenAIAttributes.GEN_AI_REQUEST_MODEL
        ],
    }

    if error_type:
        common_attributes["error.type"] = error_type

    if result and getattr(result, "model", None):
        common_attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL] = result.model

    if ServerAttributes.SERVER_ADDRESS in request_attributes:
        common_attributes[ServerAttributes.SERVER_ADDRESS] = (
            request_attributes[ServerAttributes.SERVER_ADDRESS]
        )

    if ServerAttributes.SERVER_PORT in request_attributes:
        common_attributes[ServerAttributes.SERVER_PORT] = request_attributes[
            ServerAttributes.SERVER_PORT
        ]

    instruments.operation_duration_histogram.record(
        duration,
        attributes=common_attributes,
    )

    if result and getattr(result, "usage", None):
        # Record input tokens
        input_attributes = {
            **common_attributes,
            GenAIAttributes.GEN_AI_TOKEN_TYPE: (
                GenAIAttributes.GenAiTokenTypeValues.INPUT.value
            ),
        }
        instruments.token_usage_histogram.record(
            result.usage.prompt_tokens,
            attributes=input_attributes,
        )

        # Record output tokens
        output_attributes = {
            **common_attributes,
            GenAIAttributes.GEN_AI_TOKEN_TYPE: (
                GenAIAttributes.GenAiTokenTypeValues.COMPLETION.value
            ),
        }
        instruments.token_usage_histogram.record(
            result.usage.completion_tokens, attributes=output_attributes
        )
