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

"""Instrumentation for OpenAI's Images API."""

from timeit import default_timer
from typing import Optional

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
    get_base_url,
    get_vendor_from_base_url,
    handle_span_exception,
    set_server_address_and_port,
    set_span_attribute,
    value_is_set,
)

# Operation name for image generation
IMAGE_GENERATION_OPERATION_NAME = "image_generation"


def images_generate(
    tracer: Tracer,
    instruments: Instruments,
    capture_mode: CaptureMode,
):
    """Wrap the `generate` method of the `Images` class to trace it."""

    def traced_method(wrapped, instance, args, kwargs):
        span_attributes = _get_images_request_attributes(kwargs, instance)

        span_name = (
            f"{span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]} "
            f"{span_attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL, 'dall-e')}"
        )
        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=True,
        ) as span:
            start = default_timer()
            result = None
            error_type = None
            try:
                result = wrapped(*args, **kwargs)

                if span.is_recording():
                    _set_images_response_attributes(span, result)

                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise
            finally:
                duration = max((default_timer() - start), 0)
                _record_images_metrics(
                    instruments,
                    duration,
                    result,
                    span_attributes,
                    error_type,
                )

    return traced_method


def async_images_generate(
    tracer: Tracer,
    instruments: Instruments,
    capture_mode: CaptureMode,
):
    """Wrap the `generate` method of the `AsyncImages` class to trace it."""

    async def traced_method(wrapped, instance, args, kwargs):
        span_attributes = _get_images_request_attributes(kwargs, instance)

        span_name = (
            f"{span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]} "
            f"{span_attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL, 'dall-e')}"
        )
        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=True,
        ) as span:
            start = default_timer()
            result = None
            error_type = None
            try:
                result = await wrapped(*args, **kwargs)

                if span.is_recording():
                    _set_images_response_attributes(span, result)

                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise
            finally:
                duration = max((default_timer() - start), 0)
                _record_images_metrics(
                    instruments,
                    duration,
                    result,
                    span_attributes,
                    error_type,
                )

    return traced_method


def _get_images_request_attributes(kwargs, client_instance):
    """Get request attributes for images API."""
    base_url = get_base_url(client_instance)
    vendor = get_vendor_from_base_url(base_url) if base_url else (
        GenAIAttributes.GenAiSystemValues.OPENAI.value
    )

    attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: IMAGE_GENERATION_OPERATION_NAME,
        GenAIAttributes.GEN_AI_SYSTEM: vendor,
    }

    # Model (defaults to dall-e-2 if not specified)
    model = kwargs.get("model", "dall-e-2")
    attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] = model

    # Image size
    size = kwargs.get("size")
    if value_is_set(size):
        attributes["gen_ai.request.image.size"] = size

    # Quality (for dall-e-3)
    quality = kwargs.get("quality")
    if value_is_set(quality):
        attributes["gen_ai.request.image.quality"] = quality

    # Style (for dall-e-3)
    style = kwargs.get("style")
    if value_is_set(style):
        attributes["gen_ai.request.image.style"] = style

    # Number of images to generate
    n = kwargs.get("n")
    if n is not None and n != 1:
        attributes["gen_ai.request.image.count"] = n

    # Response format
    response_format = kwargs.get("response_format")
    if value_is_set(response_format):
        attributes["gen_ai.request.image.response_format"] = response_format

    # User identifier
    user = kwargs.get("user")
    if value_is_set(user):
        attributes["gen_ai.openai.request.user"] = user

    set_server_address_and_port(client_instance, attributes)

    return {k: v for k, v in attributes.items() if value_is_set(v)}


def _set_images_response_attributes(span, result):
    """Set response attributes for images API."""
    if getattr(result, "created", None):
        set_span_attribute(span, "gen_ai.response.created", result.created)

    if getattr(result, "data", None):
        set_span_attribute(
            span, "gen_ai.response.image.count", len(result.data)
        )


def _record_images_metrics(
    instruments: Instruments,
    duration: float,
    result,
    request_attributes: dict,
    error_type: Optional[str],
):
    """Record metrics for images API."""
    common_attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: IMAGE_GENERATION_OPERATION_NAME,
        GenAIAttributes.GEN_AI_SYSTEM: request_attributes.get(
            GenAIAttributes.GEN_AI_SYSTEM,
            GenAIAttributes.GenAiSystemValues.OPENAI.value,
        ),
        GenAIAttributes.GEN_AI_REQUEST_MODEL: request_attributes.get(
            GenAIAttributes.GEN_AI_REQUEST_MODEL, "dall-e-2"
        ),
    }

    if error_type:
        common_attributes["error.type"] = error_type

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
