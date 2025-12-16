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

"""Patching functions for Anthropic instrumentation."""

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.trace import SpanKind, Tracer

from .utils import (
    get_llm_request_attributes,
    handle_span_exception,
    set_span_attribute,
)


def messages_create(
    tracer: Tracer,
    capture_content: bool,
):
    """Wrap the `create` method of the `Messages` class to trace it."""

    def traced_method(wrapped, instance, args, kwargs):
        span_attributes = {**get_llm_request_attributes(kwargs, instance)}

        span_name = f"{span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]} {span_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]}"
        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            try:
                result = wrapped(*args, **kwargs)

                if span.is_recording():
                    _set_response_attributes(span, result)

                span.end()
                return result

            except Exception as error:
                handle_span_exception(span, error)
                raise

    return traced_method


def _set_response_attributes(span, result):
    """Set span attributes from the Anthropic response."""
    if getattr(result, "model", None):
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, result.model
        )

    if getattr(result, "stop_reason", None):
        # Anthropic uses stop_reason (single string), semantic convention expects array
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS,
            [result.stop_reason],
        )

    if getattr(result, "id", None):
        set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_ID, result.id)

    # Get the usage
    if getattr(result, "usage", None):
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
            result.usage.input_tokens,
        )
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS,
            result.usage.output_tokens,
        )
