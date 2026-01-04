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

"""Method wrappers for Haystack instrumentation."""

from __future__ import annotations

import logging
from typing import Any, Callable

from opentelemetry import context as context_api
from opentelemetry.context import attach, set_value
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.trace.status import Status, StatusCode

from opentelemetry.instrumentation.haystack.utils import (
    dont_throw,
    safe_json_serialize,
    set_span_attribute,
    should_capture_content,
    with_tracer_wrapper,
)

logger = logging.getLogger(__name__)

# Custom semantic attributes for Haystack (following gen_ai.* namespace)
# Operation name attribute (OTel standard)
GENAI_OPERATION_NAME = "gen_ai.operation.name"

# Pipeline attributes
HAYSTACK_PIPELINE_NAME = "gen_ai.haystack.pipeline.name"
HAYSTACK_ENTITY_NAME = "gen_ai.haystack.entity.name"
HAYSTACK_ENTITY_INPUT = "gen_ai.haystack.entity.input"
HAYSTACK_ENTITY_OUTPUT = "gen_ai.haystack.entity.output"

# Generator attributes
HAYSTACK_REQUEST_TYPE = "gen_ai.haystack.request.type"


class LLMRequestTypeValues:
    """LLM request type values."""

    COMPLETION = "completion"
    CHAT = "chat"
    UNKNOWN = "unknown"


@dont_throw
def _process_pipeline_request(
    span: Any, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    """Process and set pipeline request attributes.

    Args:
        span: The OpenTelemetry span.
        args: Positional arguments to the pipeline.
        kwargs: Keyword arguments to the pipeline.
    """
    if not should_capture_content():
        return

    kwargs_to_serialize = kwargs.copy()
    for arg in args:
        if arg and isinstance(arg, dict):
            for key, value in arg.items():
                kwargs_to_serialize[key] = value

    args_to_serialize = [arg for arg in args if not isinstance(arg, dict)]
    input_entity = {"args": args_to_serialize, "kwargs": kwargs_to_serialize}
    set_span_attribute(span, HAYSTACK_ENTITY_INPUT, safe_json_serialize(input_entity))


@dont_throw
def _process_pipeline_response(span: Any, response: Any) -> None:
    """Process and set pipeline response attributes.

    Args:
        span: The OpenTelemetry span.
        response: The pipeline response.
    """
    if not should_capture_content():
        return

    set_span_attribute(span, HAYSTACK_ENTITY_OUTPUT, safe_json_serialize(response))


@with_tracer_wrapper
def wrap_pipeline(
    tracer: Tracer,
    to_wrap: dict[str, Any],
    wrapped: Callable[..., Any],
    instance: Any,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    """Wrapper for Pipeline.run method.

    Args:
        tracer: The OpenTelemetry tracer.
        to_wrap: Metadata about the wrapped method.
        wrapped: The original method.
        instance: The Pipeline instance.
        args: Positional arguments.
        kwargs: Keyword arguments.

    Returns:
        The result of the wrapped method.
    """
    if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
        return wrapped(*args, **kwargs)

    name = "haystack_pipeline"
    attach(set_value("workflow_name", name))

    with tracer.start_as_current_span(
        f"{name}.workflow",
        kind=SpanKind.INTERNAL,
    ) as span:
        # Set standard GenAI attributes
        span.set_attribute(GenAIAttributes.GEN_AI_SYSTEM, "haystack")
        span.set_attribute(GENAI_OPERATION_NAME, "workflow")
        span.set_attribute(HAYSTACK_ENTITY_NAME, name)

        # Process request if recording
        if span.is_recording():
            _process_pipeline_request(span, args, kwargs)

        try:
            response = wrapped(*args, **kwargs)

            # Process response if recording
            if span.is_recording() and response:
                _process_pipeline_response(span, response)
                span.set_status(Status(StatusCode.OK))

            return response

        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise


def _llm_request_type_by_object(object_name: str) -> str:
    """Determine LLM request type based on generator class name.

    Args:
        object_name: The generator class name.

    Returns:
        The LLM request type value.
    """
    if object_name == "OpenAIGenerator":
        return LLMRequestTypeValues.COMPLETION
    elif object_name == "OpenAIChatGenerator":
        return LLMRequestTypeValues.CHAT
    else:
        return LLMRequestTypeValues.UNKNOWN


@dont_throw
def _set_openai_input_attributes(
    span: Any, llm_request_type: str, kwargs: dict[str, Any]
) -> None:
    """Set input attributes for OpenAI generators.

    Args:
        span: The OpenTelemetry span.
        llm_request_type: The type of LLM request.
        kwargs: The keyword arguments to the generator.
    """
    if not should_capture_content():
        return

    if llm_request_type == LLMRequestTypeValues.COMPLETION:
        prompt = kwargs.get("prompt")
        if prompt:
            set_span_attribute(
                span, f"{GenAIAttributes.GEN_AI_PROMPT}.0.user", prompt
            )
    elif llm_request_type == LLMRequestTypeValues.CHAT:
        messages = kwargs.get("messages")
        if messages:
            content = [
                getattr(msg, "content", str(msg))
                for msg in messages
            ]
            set_span_attribute(
                span, f"{GenAIAttributes.GEN_AI_PROMPT}.0.user", str(content)
            )

    # Process generation_kwargs
    generation_kwargs = kwargs.get("generation_kwargs")
    if generation_kwargs:
        if "model" in generation_kwargs:
            set_span_attribute(
                span, GenAIAttributes.GEN_AI_REQUEST_MODEL, generation_kwargs["model"]
            )
        if "temperature" in generation_kwargs:
            set_span_attribute(
                span,
                GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE,
                generation_kwargs["temperature"],
            )
        if "top_p" in generation_kwargs:
            set_span_attribute(
                span, GenAIAttributes.GEN_AI_REQUEST_TOP_P, generation_kwargs["top_p"]
            )
        if "frequency_penalty" in generation_kwargs:
            set_span_attribute(
                span,
                GenAIAttributes.GEN_AI_REQUEST_FREQUENCY_PENALTY,
                generation_kwargs["frequency_penalty"],
            )
        if "presence_penalty" in generation_kwargs:
            set_span_attribute(
                span,
                GenAIAttributes.GEN_AI_REQUEST_PRESENCE_PENALTY,
                generation_kwargs["presence_penalty"],
            )


@dont_throw
def _set_openai_response_attributes(
    span: Any, llm_request_type: str, response: Any
) -> None:
    """Set response attributes for OpenAI generators.

    Args:
        span: The OpenTelemetry span.
        llm_request_type: The type of LLM request.
        response: The generator response.
    """
    if not should_capture_content():
        return

    if response is None:
        return

    # Handle different response formats
    choices = None
    if isinstance(response, dict):
        choices = response.get("replies") or response.get("choices")
    elif isinstance(response, list):
        choices = response

    if choices is None:
        return

    for index, message in enumerate(choices):
        prefix = f"{GenAIAttributes.GEN_AI_COMPLETION}.{index}"

        if llm_request_type == LLMRequestTypeValues.CHAT:
            if message is not None:
                set_span_attribute(span, f"{prefix}.role", "assistant")
                content = getattr(message, "content", str(message))
                set_span_attribute(span, f"{prefix}.content", content)
        elif llm_request_type == LLMRequestTypeValues.COMPLETION:
            content = getattr(message, "content", str(message))
            set_span_attribute(span, f"{prefix}.content", content)


@with_tracer_wrapper
def wrap_openai_generator(
    tracer: Tracer,
    to_wrap: dict[str, Any],
    wrapped: Callable[..., Any],
    instance: Any,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    """Wrapper for OpenAI generator run methods.

    Args:
        tracer: The OpenTelemetry tracer.
        to_wrap: Metadata about the wrapped method.
        wrapped: The original method.
        instance: The generator instance.
        args: Positional arguments.
        kwargs: Keyword arguments.

    Returns:
        The result of the wrapped method.
    """
    if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
        return wrapped(*args, **kwargs)

    object_name = to_wrap.get("object", "")
    llm_request_type = _llm_request_type_by_object(object_name)

    # Determine span name based on request type
    if llm_request_type == LLMRequestTypeValues.CHAT:
        span_name = "haystack.openai.chat"
        operation_name = "chat"
    else:
        span_name = "haystack.openai.completion"
        operation_name = "text_completion"

    with tracer.start_as_current_span(
        span_name,
        kind=SpanKind.CLIENT,
    ) as span:
        # Set standard GenAI attributes
        span.set_attribute(GenAIAttributes.GEN_AI_SYSTEM, "openai")
        span.set_attribute(GENAI_OPERATION_NAME, operation_name)
        span.set_attribute(HAYSTACK_REQUEST_TYPE, llm_request_type)

        # Set input attributes if recording
        if span.is_recording():
            _set_openai_input_attributes(span, llm_request_type, kwargs)

        try:
            response = wrapped(*args, **kwargs)

            # Set response attributes if recording
            if span.is_recording() and response:
                _set_openai_response_attributes(span, llm_request_type, response)
                span.set_status(Status(StatusCode.OK))

            return response

        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise
