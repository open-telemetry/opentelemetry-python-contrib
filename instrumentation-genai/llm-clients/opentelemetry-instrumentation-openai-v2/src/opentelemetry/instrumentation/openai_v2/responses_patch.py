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

"""Instrumentation for OpenAI's Responses API."""

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
    LLM_REQUEST_MESSAGES,
    LLM_RESPONSE_CONTENT,
    LLM_USAGE_TOTAL_TOKENS,
    CaptureMode,
    get_base_url,
    get_vendor_from_base_url,
    handle_span_exception,
    set_server_address_and_port,
    set_span_attribute,
    value_is_set,
)

# Operation name for responses API
RESPONSES_OPERATION_NAME = "responses"


def responses_create(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_mode: CaptureMode,
):
    """Wrap the `create` method of the `Responses` class to trace it."""

    def traced_method(wrapped, instance, args, kwargs):
        span_attributes = _get_responses_request_attributes(kwargs, instance)

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
            # Set request content on span (only in ALL mode)
            if span.is_recording() and capture_mode == CaptureMode.ALL:
                _set_responses_request_content(span, kwargs)

            start = default_timer()
            result = None
            error_type = None
            try:
                result = wrapped(*args, **kwargs)

                if span.is_recording():
                    _set_responses_response_attributes(span, result)
                    # Set response content on span (only in ALL mode)
                    if capture_mode == CaptureMode.ALL:
                        _set_responses_response_content(span, result)

                span.end()
                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise
            finally:
                duration = max((default_timer() - start), 0)
                _record_responses_metrics(
                    instruments,
                    duration,
                    result,
                    span_attributes,
                    error_type,
                )

    return traced_method


def async_responses_create(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_mode: CaptureMode,
):
    """Wrap the `create` method of the `AsyncResponses` class to trace it."""

    async def traced_method(wrapped, instance, args, kwargs):
        span_attributes = _get_responses_request_attributes(kwargs, instance)

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
            # Set request content on span (only in ALL mode)
            if span.is_recording() and capture_mode == CaptureMode.ALL:
                _set_responses_request_content(span, kwargs)

            start = default_timer()
            result = None
            error_type = None
            try:
                result = await wrapped(*args, **kwargs)

                if span.is_recording():
                    _set_responses_response_attributes(span, result)
                    # Set response content on span (only in ALL mode)
                    if capture_mode == CaptureMode.ALL:
                        _set_responses_response_content(span, result)

                span.end()
                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise
            finally:
                duration = max((default_timer() - start), 0)
                _record_responses_metrics(
                    instruments,
                    duration,
                    result,
                    span_attributes,
                    error_type,
                )

    return traced_method


def _get_responses_request_attributes(kwargs, client_instance):
    """Get request attributes for responses API."""
    base_url = get_base_url(client_instance)
    vendor = get_vendor_from_base_url(base_url) if base_url else (
        GenAIAttributes.GenAiSystemValues.OPENAI.value
    )

    attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: RESPONSES_OPERATION_NAME,
        GenAIAttributes.GEN_AI_SYSTEM: vendor,
        GenAIAttributes.GEN_AI_REQUEST_MODEL: kwargs.get("model"),
    }

    # Modalities
    modalities = kwargs.get("modalities")
    if modalities:
        attributes["gen_ai.request.modalities"] = modalities

    # Temperature
    temperature = kwargs.get("temperature")
    if value_is_set(temperature):
        attributes[GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE] = temperature

    # Max tokens
    max_tokens = kwargs.get("max_output_tokens")
    if value_is_set(max_tokens):
        attributes[GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS] = max_tokens

    # Top P
    top_p = kwargs.get("top_p")
    if value_is_set(top_p):
        attributes[GenAIAttributes.GEN_AI_REQUEST_TOP_P] = top_p

    # Presence penalty
    presence_penalty = kwargs.get("presence_penalty")
    if value_is_set(presence_penalty):
        attributes[GenAIAttributes.GEN_AI_REQUEST_PRESENCE_PENALTY] = (
            presence_penalty
        )

    # Frequency penalty
    frequency_penalty = kwargs.get("frequency_penalty")
    if value_is_set(frequency_penalty):
        attributes[GenAIAttributes.GEN_AI_REQUEST_FREQUENCY_PENALTY] = (
            frequency_penalty
        )

    # User identifier
    user = kwargs.get("user")
    if value_is_set(user):
        attributes["gen_ai.openai.request.user"] = user

    # Previous response ID (for multi-turn)
    previous_response_id = kwargs.get("previous_response_id")
    if value_is_set(previous_response_id):
        attributes["gen_ai.openai.request.previous_response_id"] = (
            previous_response_id
        )

    set_server_address_and_port(client_instance, attributes)

    return {k: v for k, v in attributes.items() if value_is_set(v)}


def _set_responses_response_attributes(span, result):
    """Set response attributes for responses API."""
    if getattr(result, "id", None):
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_RESPONSE_ID, result.id
        )

    if getattr(result, "model", None):
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, result.model
        )

    if getattr(result, "status", None):
        set_span_attribute(span, "gen_ai.response.status", result.status)

    # Set usage attributes
    usage = getattr(result, "usage", None)
    if usage:
        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)

        if input_tokens is not None:
            set_span_attribute(
                span, GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS, input_tokens
            )

        if output_tokens is not None:
            set_span_attribute(
                span, GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS, output_tokens
            )

        # Set total tokens
        if input_tokens is not None and output_tokens is not None:
            set_span_attribute(
                span, LLM_USAGE_TOTAL_TOKENS, input_tokens + output_tokens
            )


def _record_responses_metrics(
    instruments: Instruments,
    duration: float,
    result,
    request_attributes: dict,
    error_type: Optional[str],
):
    """Record metrics for responses API."""
    common_attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: RESPONSES_OPERATION_NAME,
        GenAIAttributes.GEN_AI_SYSTEM: request_attributes.get(
            GenAIAttributes.GEN_AI_SYSTEM,
            GenAIAttributes.GenAiSystemValues.OPENAI.value,
        ),
        GenAIAttributes.GEN_AI_REQUEST_MODEL: request_attributes.get(
            GenAIAttributes.GEN_AI_REQUEST_MODEL
        ),
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

    if result:
        usage = getattr(result, "usage", None)
        if usage:
            # Record input tokens
            input_tokens = getattr(usage, "input_tokens", None)
            if input_tokens is not None:
                input_attributes = {
                    **common_attributes,
                    GenAIAttributes.GEN_AI_TOKEN_TYPE: (
                        GenAIAttributes.GenAiTokenTypeValues.INPUT.value
                    ),
                }
                instruments.token_usage_histogram.record(
                    input_tokens, attributes=input_attributes
                )

            # Record output tokens
            output_tokens = getattr(usage, "output_tokens", None)
            if output_tokens is not None:
                output_attributes = {
                    **common_attributes,
                    GenAIAttributes.GEN_AI_TOKEN_TYPE: (
                        GenAIAttributes.GenAiTokenTypeValues.COMPLETION.value
                    ),
                }
                instruments.token_usage_histogram.record(
                    output_tokens, attributes=output_attributes
                )


def _set_responses_request_content(span, kwargs):
    """Set request content on span for responses API."""
    import json

    # The responses API uses 'input' for the user message
    input_content = kwargs.get("input")
    if input_content:
        try:
            if isinstance(input_content, str):
                span.set_attribute(LLM_REQUEST_MESSAGES, input_content)
            else:
                span.set_attribute(
                    LLM_REQUEST_MESSAGES, json.dumps(input_content, default=str)
                )
        except (TypeError, ValueError):
            pass

    # Also capture instructions if present
    instructions = kwargs.get("instructions")
    if instructions:
        span.set_attribute("gen_ai.request.instructions", instructions)


def _set_responses_response_content(span, result):
    """Set response content on span for responses API."""
    import json

    # Get output from response
    output = getattr(result, "output", None)
    if output:
        try:
            # Output is typically a list of output items
            if isinstance(output, list):
                content_parts = []
                for item in output:
                    # Handle different output item types
                    item_type = getattr(item, "type", None)
                    if item_type == "message":
                        content = getattr(item, "content", None)
                        if content:
                            for c in content:
                                text = getattr(c, "text", None)
                                if text:
                                    content_parts.append(text)
                    elif item_type == "function_call":
                        name = getattr(item, "name", "")
                        arguments = getattr(item, "arguments", "")
                        content_parts.append(f"[Tool: {name}({arguments})]")
                    else:
                        # Try to get any text content
                        text = getattr(item, "text", None)
                        if text:
                            content_parts.append(text)
                if content_parts:
                    span.set_attribute(
                        LLM_RESPONSE_CONTENT, "\n---\n".join(content_parts)
                    )
            else:
                span.set_attribute(
                    LLM_RESPONSE_CONTENT, json.dumps(output, default=str)
                )
        except (TypeError, ValueError):
            pass
