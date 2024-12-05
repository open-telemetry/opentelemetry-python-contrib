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

"""OpenTelemetry Vertex AI instrumentation"""

import logging
import types
from functools import partial
from typing import Collection, Optional

from wrapt import wrap_function_wrapper

from opentelemetry._events import (
    EventLogger,
    EventLoggerProvider,
    get_event_logger,
)
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import (
    is_instrumentation_enabled,
    unwrap,
)
from opentelemetry.instrumentation.vertexai_v2.events import (
    assistant_event,
    user_event,
)
from opentelemetry.instrumentation.vertexai_v2.utils import dont_throw
from opentelemetry.instrumentation.vertexai_v2.version import __version__
from opentelemetry.semconv._incubating.attributes import gen_ai_attributes
from opentelemetry.trace import SpanKind, TracerProvider, get_tracer
from opentelemetry.trace.status import Status, StatusCode

logger = logging.getLogger(__name__)

_instruments = ("google-cloud-aiplatform >= 1.38.1",)

# TODO: span_name should no longer be needed as it comes from `{gen_ai.operation.name} {gen_ai.request.model}`
WRAPPED_METHODS = [
    {
        "package": "vertexai.generative_models",
        "object": "GenerativeModel",
        "method": "generate_content",
        "span_name": "vertexai.generate_content",
        "is_async": False,
    },
    {
        "package": "vertexai.generative_models",
        "object": "GenerativeModel",
        "method": "generate_content_async",
        "span_name": "vertexai.generate_content_async",
        "is_async": True,
    },
    {
        "package": "vertexai.preview.generative_models",
        "object": "GenerativeModel",
        "method": "generate_content",
        "span_name": "vertexai.generate_content",
        "is_async": False,
    },
    {
        "package": "vertexai.preview.generative_models",
        "object": "GenerativeModel",
        "method": "generate_content_async",
        "span_name": "vertexai.generate_content_async",
        "is_async": True,
    },
    {
        "package": "vertexai.language_models",
        "object": "TextGenerationModel",
        "method": "predict",
        "span_name": "vertexai.predict",
        "is_async": False,
    },
    {
        "package": "vertexai.language_models",
        "object": "TextGenerationModel",
        "method": "predict_async",
        "span_name": "vertexai.predict_async",
        "is_async": True,
    },
    {
        "package": "vertexai.language_models",
        "object": "TextGenerationModel",
        "method": "predict_streaming",
        "span_name": "vertexai.predict_streaming",
        "is_async": False,
    },
    {
        "package": "vertexai.language_models",
        "object": "TextGenerationModel",
        "method": "predict_streaming_async",
        "span_name": "vertexai.predict_streaming_async",
        "is_async": True,
    },
    {
        "package": "vertexai.language_models",
        "object": "ChatSession",
        "method": "send_message",
        "span_name": "vertexai.send_message",
        "is_async": False,
    },
    {
        "package": "vertexai.language_models",
        "object": "ChatSession",
        "method": "send_message_streaming",
        "span_name": "vertexai.send_message_streaming",
        "is_async": False,
    },
]


def should_send_prompts():
    # Previously was opt-in by the following check for privacy reasons:
    #
    # return (
    #     os.getenv("TRACELOOP_TRACE_CONTENT") or "true"
    # ).lower() == "true" or context_api.get_value(
    #     "override_enable_content_tracing"
    # )
    return True


def is_streaming_response(response):
    return isinstance(response, types.GeneratorType)


def is_async_streaming_response(response):
    return isinstance(response, types.AsyncGeneratorType)


def _set_span_attribute(span, name, value):
    if value is not None:
        if value != "":
            span.set_attribute(name, value)


def _set_input_attributes(
    span, event_logger: EventLogger, args, kwargs, llm_model
):
    if should_send_prompts() and args is not None and len(args) > 0:
        prompt = ""
        for arg in args:
            if isinstance(arg, str):
                prompt = f"{prompt}{arg}\n"
            elif isinstance(arg, list):
                for subarg in arg:
                    prompt = f"{prompt}{subarg}\n"

        # _set_span_attribute(
        #     span,
        #     f"{SpanAttributes.LLM_PROMPTS}.0.user",
        #     prompt,
        # )
        if prompt:
            event_logger.emit(
                user_event(
                    gen_ai_system=gen_ai_attributes.GenAiSystemValues.VERTEX_AI.value,
                    content=prompt,
                    span_context=span.get_span_context(),
                )
            )

        # Copied from openllmetry logic
        # https://github.com/traceloop/openllmetry/blob/v0.33.12/packages/opentelemetry-instrumentation-vertexai/opentelemetry/instrumentation/vertexai/__init__.py#L141-L143
        # I guess prompt may be in kwargs instead or in addition?
        prompt = kwargs.get("prompt")
        if prompt:
            event_logger.emit(
                user_event(
                    gen_ai_system=gen_ai_attributes.GenAiSystemValues.VERTEX_AI.value,
                    content=prompt,
                    span_context=span.get_span_context(),
                )
            )

    _set_span_attribute(
        span, gen_ai_attributes.GEN_AI_REQUEST_MODEL, llm_model
    )
    _set_span_attribute(
        span,
        gen_ai_attributes.GEN_AI_REQUEST_TEMPERATURE,
        kwargs.get("temperature"),
    )
    _set_span_attribute(
        span,
        gen_ai_attributes.GEN_AI_REQUEST_MAX_TOKENS,
        kwargs.get("max_output_tokens"),
    )
    _set_span_attribute(
        span, gen_ai_attributes.GEN_AI_REQUEST_TOP_P, kwargs.get("top_p")
    )
    _set_span_attribute(
        span, gen_ai_attributes.GEN_AI_REQUEST_TOP_K, kwargs.get("top_k")
    )
    _set_span_attribute(
        span,
        gen_ai_attributes.GEN_AI_REQUEST_PRESENCE_PENALTY,
        kwargs.get("presence_penalty"),
    )
    _set_span_attribute(
        span,
        gen_ai_attributes.GEN_AI_REQUEST_FREQUENCY_PENALTY,
        kwargs.get("frequency_penalty"),
    )


@dont_throw
def _set_response_attributes(
    span, event_logger: EventLogger, llm_model, generation_text, token_usage
):
    _set_span_attribute(
        span, gen_ai_attributes.GEN_AI_RESPONSE_MODEL, llm_model
    )

    if token_usage:
        _set_span_attribute(
            span,
            gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS,
            token_usage.candidates_token_count,
        )
        _set_span_attribute(
            span,
            gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS,
            token_usage.prompt_token_count,
        )

    if generation_text:
        event_logger.emit(
            assistant_event(
                gen_ai_system=gen_ai_attributes.GenAiSystemValues.VERTEX_AI.value,
                content=generation_text,
                span_context=span.get_span_context(),
            )
        )


def _build_from_streaming_response(
    span, event_logger: EventLogger, response, llm_model
):
    complete_response = ""
    token_usage = None
    for item in response:
        item_to_yield = item
        complete_response += str(item.text)
        if item.usage_metadata:
            token_usage = item.usage_metadata

        yield item_to_yield

    _set_response_attributes(
        span, event_logger, llm_model, complete_response, token_usage
    )

    span.set_status(Status(StatusCode.OK))
    span.end()


async def _abuild_from_streaming_response(
    span, event_logger: EventLogger, response, llm_model
):
    complete_response = ""
    token_usage = None
    async for item in response:
        item_to_yield = item
        complete_response += str(item.text)
        if item.usage_metadata:
            token_usage = item.usage_metadata

        yield item_to_yield

    _set_response_attributes(
        span, event_logger, llm_model, complete_response, token_usage
    )

    span.set_status(Status(StatusCode.OK))
    span.end()


@dont_throw
def _handle_request(span, event_logger, args, kwargs, llm_model):
    if span.is_recording():
        _set_input_attributes(span, event_logger, args, kwargs, llm_model)


@dont_throw
def _handle_response(span, event_logger: EventLogger, response, llm_model):
    if span.is_recording():
        _set_response_attributes(
            span,
            event_logger,
            llm_model,
            response.candidates[0].text,
            response.usage_metadata,
        )

        span.set_status(Status(StatusCode.OK))


async def _awrap(
    tracer, event_logger: EventLogger, to_wrap, wrapped, instance, args, kwargs
):
    """Instruments and calls every function defined in TO_WRAP."""
    if not is_instrumentation_enabled():
        return await wrapped(*args, **kwargs)

    llm_model = "unknown"
    if hasattr(instance, "_model_id"):
        llm_model = instance._model_id
    if hasattr(instance, "_model_name"):
        llm_model = instance._model_name.replace(
            "publishers/google/models/", ""
        )

    operation_name = (
        gen_ai_attributes.GenAiOperationNameValues.TEXT_COMPLETION.value
    )
    name = f"{operation_name} {llm_model}"
    span = tracer.start_span(
        name,
        kind=SpanKind.CLIENT,
        attributes={
            gen_ai_attributes.GEN_AI_SYSTEM: gen_ai_attributes.GenAiSystemValues.VERTEX_AI.value,
            gen_ai_attributes.GEN_AI_OPERATION_NAME: operation_name,
        },
    )

    _handle_request(span, event_logger, args, kwargs, llm_model)

    response = await wrapped(*args, **kwargs)

    if response:
        if is_streaming_response(response):
            return _build_from_streaming_response(
                span, event_logger, response, llm_model
            )
        if is_async_streaming_response(response):
            return _abuild_from_streaming_response(
                span, event_logger, response, llm_model
            )
        _handle_response(span, event_logger, response, llm_model)

    span.end()
    return response


def _wrap(
    tracer, event_logger: EventLogger, to_wrap, wrapped, instance, args, kwargs
):
    """Instruments and calls every function defined in TO_WRAP."""
    if not is_instrumentation_enabled():
        return wrapped(*args, **kwargs)

    llm_model = "unknown"
    if hasattr(instance, "_model_id"):
        llm_model = instance._model_id
    if hasattr(instance, "_model_name"):
        llm_model = instance._model_name.replace(
            "publishers/google/models/", ""
        )

    operation_name = (
        gen_ai_attributes.GenAiOperationNameValues.TEXT_COMPLETION.value
    )
    name = f"{operation_name} {llm_model}"
    span = tracer.start_span(
        name,
        kind=SpanKind.CLIENT,
        attributes={
            gen_ai_attributes.GEN_AI_SYSTEM: gen_ai_attributes.GenAiSystemValues.VERTEX_AI.value,
            gen_ai_attributes.GEN_AI_OPERATION_NAME: operation_name,
        },
    )

    _handle_request(span, event_logger, args, kwargs, llm_model)

    response = wrapped(*args, **kwargs)

    if response:
        if is_streaming_response(response):
            return _build_from_streaming_response(
                span, event_logger, response, llm_model
            )
        if is_async_streaming_response(response):
            return _abuild_from_streaming_response(
                span, event_logger, response, llm_model
            )
        _handle_response(span, event_logger, response, llm_model)

    span.end()
    return response


class VertexAIInstrumentor(BaseInstrumentor):
    """An instrumentor for VertextAI's client library."""

    def __init__(self, exception_logger=None):
        super().__init__()

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(
        self,
        *,
        tracer_provider: Optional[TracerProvider] = None,
        event_logger_provider: Optional[EventLoggerProvider] = None,
        **kwargs,
    ):
        tracer = get_tracer(
            __name__, __version__, tracer_provider=tracer_provider
        )
        event_logger = get_event_logger(
            __name__,
            version=__version__,
            event_logger_provider=event_logger_provider,
        )
        for wrapped_method in WRAPPED_METHODS:
            wrap_package = wrapped_method.get("package")
            wrap_object = wrapped_method.get("object")
            wrap_method = wrapped_method.get("method")

            wrap_function_wrapper(
                wrap_package,
                f"{wrap_object}.{wrap_method}",
                (
                    partial(_awrap, tracer, event_logger, wrapped_method)
                    if wrapped_method.get("is_async")
                    else partial(_wrap, tracer, event_logger, wrapped_method)
                ),
            )

    def _uninstrument(self, **kwargs):
        for wrapped_method in WRAPPED_METHODS:
            wrap_package = wrapped_method.get("package")
            wrap_object = wrapped_method.get("object")
            unwrap(
                f"{wrap_package}.{wrap_object}",
                wrapped_method.get("method", ""),
            )
