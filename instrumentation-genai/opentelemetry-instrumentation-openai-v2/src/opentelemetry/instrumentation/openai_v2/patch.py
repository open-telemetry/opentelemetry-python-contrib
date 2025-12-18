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


from timeit import default_timer
from typing import Any, Optional

from opentelemetry._logs import Logger, LogRecord
from opentelemetry.context import get_current
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.trace import Span, SpanKind, Tracer
from opentelemetry.trace.propagation import set_span_in_context

from .instruments import Instruments
from .streaming import (
    AsyncStreamWrapper,
    StreamWrapper,
    SyncStreamWrapper,
)

# Re-export StreamWrapper for backwards compatibility
__all__ = ["StreamWrapper"]

from .utils import (
    choice_to_event,
    get_llm_request_attributes,
    get_property_value,
    handle_span_exception,
    is_streaming,
    message_to_event,
    set_span_attribute,
)
from .responses import output_to_event, responses_input_to_event


def chat_completions_create(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `create` method of the `ChatCompletion` class to trace it."""

    def traced_method(wrapped, instance, args, kwargs):
        span_attributes = {**get_llm_request_attributes(kwargs, instance)}

        span_name = f"{span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]} {span_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]}"
        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            for message in kwargs.get("messages", []):
                logger.emit(message_to_event(message, capture_content))

            start = default_timer()
            result = None
            error_type = None
            try:
                result = wrapped(*args, **kwargs)
                if hasattr(result, "parse"):
                    # result is of type LegacyAPIResponse, call parse to get the actual response
                    parsed_result = result.parse()
                else:
                    parsed_result = result
                if is_streaming(kwargs):
                    return SyncStreamWrapper(parsed_result, span, logger, capture_content)

                if span.is_recording():
                    _set_response_attributes(
                        span, parsed_result, logger, capture_content
                    )
                for choice in getattr(parsed_result, "choices", []):
                    logger.emit(choice_to_event(choice, capture_content))

                span.end()
                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise
            finally:
                duration = max((default_timer() - start), 0)
                _record_metrics(
                    instruments,
                    duration,
                    result,
                    span_attributes,
                    error_type,
                    GenAIAttributes.GenAiOperationNameValues.CHAT.value,
                )

    return traced_method


def async_chat_completions_create(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `create` method of the `AsyncChatCompletion` class to trace it."""

    async def traced_method(wrapped, instance, args, kwargs):
        span_attributes = {**get_llm_request_attributes(kwargs, instance)}

        span_name = f"{span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]} {span_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]}"
        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            for message in kwargs.get("messages", []):
                logger.emit(message_to_event(message, capture_content))

            start = default_timer()
            result = None
            error_type = None
            try:
                result = await wrapped(*args, **kwargs)
                if hasattr(result, "parse"):
                    # result is of type LegacyAPIResponse, calling parse to get the actual response
                    parsed_result = result.parse()
                else:
                    parsed_result = result
                if is_streaming(kwargs):
                    return AsyncStreamWrapper(parsed_result, span, logger, capture_content)

                if span.is_recording():
                    _set_response_attributes(
                        span, parsed_result, logger, capture_content
                    )
                for choice in getattr(parsed_result, "choices", []):
                    logger.emit(choice_to_event(choice, capture_content))

                span.end()
                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise
            finally:
                duration = max((default_timer() - start), 0)
                _record_metrics(
                    instruments,
                    duration,
                    result,
                    span_attributes,
                    error_type,
                    GenAIAttributes.GenAiOperationNameValues.CHAT.value,
                )

    return traced_method


def embeddings_create(
    tracer: Tracer,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `create` method of the `Embeddings` class to trace it."""

    def traced_method(wrapped, instance, args, kwargs):
        span_attributes = get_llm_request_attributes(
            kwargs,
            instance,
            GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value,
        )
        span_name = _get_embeddings_span_name(span_attributes)
        input_text = kwargs.get("input", "")

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
                    _set_embeddings_response_attributes(
                        span, result, capture_content, input_text
                    )

                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise

            finally:
                duration = max((default_timer() - start), 0)
                _record_metrics(
                    instruments,
                    duration,
                    result,
                    span_attributes,
                    error_type,
                    GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value,
                )

    return traced_method


def async_embeddings_create(
    tracer: Tracer,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `create` method of the `AsyncEmbeddings` class to trace it."""

    async def traced_method(wrapped, instance, args, kwargs):
        span_attributes = get_llm_request_attributes(
            kwargs,
            instance,
            GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value,
        )
        span_name = _get_embeddings_span_name(span_attributes)
        input_text = kwargs.get("input", "")

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
                    _set_embeddings_response_attributes(
                        span, result, capture_content, input_text
                    )

                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise

            finally:
                duration = max((default_timer() - start), 0)
                _record_metrics(
                    instruments,
                    duration,
                    result,
                    span_attributes,
                    error_type,
                    GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value,
                )

    return traced_method


def _log_responses_inputs(
    logger: Logger, kwargs: dict[str, Any], capture_content: bool
) -> None:
    input_value = kwargs.get("input")
    if not input_value:
        return

    if isinstance(input_value, str):
        event = responses_input_to_event(input_value, capture_content)
        if event:
            logger.emit(event)
        return

    if isinstance(input_value, list):
        for item in input_value:
            event = responses_input_to_event(item, capture_content)
            if event:
                logger.emit(event)


def _log_responses_outputs(
    logger: Logger, result: Any, capture_content: bool
) -> None:
    for output in getattr(result, "output", []):
        event = output_to_event(output, capture_content)
        if event:
            logger.emit(event)


def responses_create(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `create` method of the `Responses` class to trace it."""

    def traced_method(wrapped, instance, args, kwargs):
        span_attributes = {**get_llm_request_attributes(kwargs, instance)}
        span_name = f"{span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]} {span_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]}"

        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            instructions = kwargs.get("instructions")
            if capture_content and instructions and span.is_recording():
                set_span_attribute(
                    span,
                    GenAIAttributes.GEN_AI_SYSTEM_INSTRUCTIONS,
                    instructions,
                )

            _log_responses_inputs(logger, kwargs, capture_content)

            start = default_timer()
            result = None
            error_type = None
            stream = is_streaming(kwargs)
            try:
                result = wrapped(*args, **kwargs)
                if stream:
                    return ResponsesStreamWrapper(
                        result,
                        span,
                        logger,
                        instruments,
                        span_attributes,
                        GenAIAttributes.GenAiOperationNameValues.CHAT.value,
                        capture_content,
                    )

                if span.is_recording():
                    _set_responses_response_attributes(
                        span, result, logger, capture_content
                    )

                _log_responses_outputs(logger, result, capture_content)

                span.end()
                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise
            finally:
                if not stream:
                    duration = max((default_timer() - start), 0)
                    _record_metrics(
                        instruments,
                        duration,
                        result,
                        span_attributes,
                        error_type,
                        GenAIAttributes.GenAiOperationNameValues.CHAT.value,
                    )

    return traced_method


def async_responses_create(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `create` method of the `AsyncResponses` class to trace it."""

    async def traced_method(wrapped, instance, args, kwargs):
        span_attributes = {**get_llm_request_attributes(kwargs, instance)}
        span_name = f"{span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]} {span_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]}"

        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            instructions = kwargs.get("instructions")
            if capture_content and instructions and span.is_recording():
                set_span_attribute(
                    span,
                    GenAIAttributes.GEN_AI_SYSTEM_INSTRUCTIONS,
                    instructions,
                )

            _log_responses_inputs(logger, kwargs, capture_content)

            start = default_timer()
            result = None
            error_type = None
            stream = is_streaming(kwargs)
            try:
                result = await wrapped(*args, **kwargs)
                if stream:
                    return ResponsesStreamWrapper(
                        result,
                        span,
                        logger,
                        instruments,
                        span_attributes,
                        GenAIAttributes.GenAiOperationNameValues.CHAT.value,
                        capture_content,
                    )

                if span.is_recording():
                    _set_responses_response_attributes(
                        span, result, logger, capture_content
                    )

                _log_responses_outputs(logger, result, capture_content)

                span.end()
                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise
            finally:
                if not stream:
                    duration = max((default_timer() - start), 0)
                    _record_metrics(
                        instruments,
                        duration,
                        result,
                        span_attributes,
                        error_type,
                        GenAIAttributes.GenAiOperationNameValues.CHAT.value,
                    )

    return traced_method


class ResponsesStreamWrapper:
    """Wrap a Responses API stream and finalize telemetry when the stream completes."""

    def __init__(
        self,
        stream: Any,
        span: Span,
        logger: Logger,
        instruments: Instruments,
        request_attributes: dict,
        operation_name: str,
        capture_content: bool,
    ):
        self.stream = stream
        self.span = span
        self.logger = logger
        self.instruments = instruments
        self.request_attributes = request_attributes
        self.operation_name = operation_name
        self.capture_content = capture_content

        self._start = default_timer()
        self._ended = False
        self._error_type: Optional[str] = None

        self._final_response: Any = None
        self._buffered_text: list[str] = []

    def _process_event(self, event: Any) -> None:
        event_type = get_property_value(event, "type")

        response_obj = get_property_value(event, "response")
        if response_obj is not None:
            self._final_response = response_obj

        if isinstance(event_type, str) and event_type.endswith(".delta"):
            delta = get_property_value(event, "delta")
            if isinstance(delta, str):
                self._buffered_text.append(delta)
                return

            text = get_property_value(delta, "text") or get_property_value(
                delta, "content"
            )
            if isinstance(text, str):
                self._buffered_text.append(text)

    def _emit_output_log(self) -> None:
        body: dict[str, Any] = {}
        message: dict[str, Any] = {"role": "assistant"}
        if self.capture_content and self._buffered_text:
            message["content"] = "".join(self._buffered_text)
        body["message"] = message

        context = set_span_in_context(self.span, get_current())
        self.logger.emit(
            LogRecord(
                event_name="gen_ai.output",
                attributes={
                    GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value
                },
                body=body,
                context=context,
            )
        )

    def _finalize(self) -> None:
        if self._ended:
            return
        self._ended = True

        duration = max((default_timer() - self._start), 0)
        result = self._final_response

        if self.span.is_recording() and result is not None:
            _set_responses_response_attributes(
                self.span, result, self.logger, self.capture_content
            )

        self._emit_output_log()
        self.span.end()

        _record_metrics(
            self.instruments,
            duration,
            result,
            self.request_attributes,
            self._error_type,
            self.operation_name,
        )

    def close(self) -> None:
        try:
            close_fn = getattr(self.stream, "close", None)
            if callable(close_fn):
                close_fn()
        finally:
            self._finalize()

    def __iter__(self):
        return self

    def __next__(self):
        try:
            event = next(self.stream)
            self._process_event(event)
            return event
        except StopIteration:
            self._finalize()
            raise
        except Exception as error:
            self._error_type = type(error).__qualname__
            handle_span_exception(self.span, error)
            self._finalize()
            raise

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            event = await self.stream.__anext__()
            self._process_event(event)
            return event
        except StopAsyncIteration:
            self._finalize()
            raise
        except Exception as error:
            self._error_type = type(error).__qualname__
            handle_span_exception(self.span, error)
            self._finalize()
            raise


def responses_compact(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `compact` method of the `Responses` class to trace it."""

    def traced_method(wrapped, instance, args, kwargs):
        span_attributes = {**get_llm_request_attributes(kwargs, instance)}
        span_name = f"{span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]} {span_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]}"

        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            instructions = kwargs.get("instructions")
            if capture_content and instructions and span.is_recording():
                set_span_attribute(
                    span,
                    GenAIAttributes.GEN_AI_SYSTEM_INSTRUCTIONS,
                    instructions,
                )

            _log_responses_inputs(logger, kwargs, capture_content)

            start = default_timer()
            result = None
            error_type = None
            try:
                result = wrapped(*args, **kwargs)

                if span.is_recording():
                    _set_responses_response_attributes(
                        span, result, logger, capture_content
                    )

                _log_responses_outputs(logger, result, capture_content)

                span.end()
                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise
            finally:
                duration = max((default_timer() - start), 0)
                _record_metrics(
                    instruments,
                    duration,
                    result,
                    span_attributes,
                    error_type,
                    GenAIAttributes.GenAiOperationNameValues.CHAT.value,
                )

    return traced_method


def async_responses_compact(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `compact` method of the `AsyncResponses` class to trace it."""

    async def traced_method(wrapped, instance, args, kwargs):
        span_attributes = {**get_llm_request_attributes(kwargs, instance)}
        span_name = f"{span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]} {span_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]}"

        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            instructions = kwargs.get("instructions")
            if capture_content and instructions and span.is_recording():
                set_span_attribute(
                    span,
                    GenAIAttributes.GEN_AI_SYSTEM_INSTRUCTIONS,
                    instructions,
                )

            _log_responses_inputs(logger, kwargs, capture_content)

            start = default_timer()
            result = None
            error_type = None
            try:
                result = await wrapped(*args, **kwargs)

                if span.is_recording():
                    _set_responses_response_attributes(
                        span, result, logger, capture_content
                    )

                _log_responses_outputs(logger, result, capture_content)

                span.end()
                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise
            finally:
                duration = max((default_timer() - start), 0)
                _record_metrics(
                    instruments,
                    duration,
                    result,
                    span_attributes,
                    error_type,
                    GenAIAttributes.GenAiOperationNameValues.CHAT.value,
                )

    return traced_method


def _get_embeddings_span_name(span_attributes):
    """Get span name for embeddings operations."""
    return f"{span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]} {span_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]}"


def _record_metrics(
    instruments: Instruments,
    duration: float,
    result,
    request_attributes: dict,
    error_type: Optional[str],
    operation_name: str,
):
    common_attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: operation_name,
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value,
        GenAIAttributes.GEN_AI_REQUEST_MODEL: request_attributes[
            GenAIAttributes.GEN_AI_REQUEST_MODEL
        ],
    }

    if "gen_ai.embeddings.dimension.count" in request_attributes:
        common_attributes["gen_ai.embeddings.dimension.count"] = (
            request_attributes["gen_ai.embeddings.dimension.count"]
        )

    if error_type:
        common_attributes["error.type"] = error_type

    if result and getattr(result, "model", None):
        common_attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL] = result.model

    if result and getattr(result, "service_tier", None):
        common_attributes[
            GenAIAttributes.GEN_AI_OPENAI_RESPONSE_SERVICE_TIER
        ] = result.service_tier

    if result and getattr(result, "system_fingerprint", None):
        common_attributes["gen_ai.openai.response.system_fingerprint"] = (
            result.system_fingerprint
        )

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
        # Get input tokens - Responses API uses input_tokens, Chat Completions uses prompt_tokens
        input_tokens = getattr(result.usage, "input_tokens", None) or getattr(
            result.usage, "prompt_tokens", None
        )

        if input_tokens is not None:
            input_attributes = {
                **common_attributes,
                GenAIAttributes.GEN_AI_TOKEN_TYPE: GenAIAttributes.GenAiTokenTypeValues.INPUT.value,
            }
            instruments.token_usage_histogram.record(
                input_tokens,
                attributes=input_attributes,
            )

        # For embeddings, don't record output tokens as all tokens are input tokens
        if (
            operation_name
            != GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value
        ):
            # Get output tokens - Responses API uses output_tokens, Chat Completions uses completion_tokens
            output_tokens = getattr(
                result.usage, "output_tokens", None
            ) or getattr(result.usage, "completion_tokens", None)

            if output_tokens is not None:
                output_attributes = {
                    **common_attributes,
                    GenAIAttributes.GEN_AI_TOKEN_TYPE: GenAIAttributes.GenAiTokenTypeValues.COMPLETION.value,
                }
                instruments.token_usage_histogram.record(
                    output_tokens, attributes=output_attributes
                )


def _set_response_attributes(
    span, result, logger: Logger, capture_content: bool
):
    if getattr(result, "model", None):
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, result.model
        )

    if getattr(result, "choices", None):
        finish_reasons = []
        for choice in result.choices:
            finish_reasons.append(choice.finish_reason or "error")

        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS,
            finish_reasons,
        )

    if getattr(result, "id", None):
        set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_ID, result.id)

    if getattr(result, "service_tier", None):
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_OPENAI_RESPONSE_SERVICE_TIER,
            result.service_tier,
        )

    # Get the usage
    if getattr(result, "usage", None):
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
            result.usage.prompt_tokens,
        )
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS,
            result.usage.completion_tokens,
        )


def _set_responses_response_attributes(
    span, result, logger: Logger, capture_content: bool
):
    """Set span attributes from a Responses API result."""
    set_span_attribute(
        span,
        GenAIAttributes.GEN_AI_RESPONSE_MODEL,
        getattr(result, "model", None),
    )

    if getattr(result, "id", None):
        set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_ID, result.id)

    # Responses API uses "output" instead of "choices", and "status" instead of "finish_reason"
    if getattr(result, "output", None):
        finish_reasons = []
        for output_item in result.output:
            status = getattr(output_item, "status", None)
            finish_reasons.append(status or "error")
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS,
            finish_reasons,
        )

    # Get the usage - Responses API uses input_tokens/output_tokens
    if getattr(result, "usage", None):
        input_tokens = getattr(result.usage, "input_tokens", None)
        if input_tokens is not None:
            set_span_attribute(
                span,
                GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
                input_tokens,
            )

        output_tokens = getattr(result.usage, "output_tokens", None)
        if output_tokens is not None:
            set_span_attribute(
                span,
                GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS,
                output_tokens,
            )


def _set_embeddings_response_attributes(
    span: Span,
    result: Any,
    capture_content: bool,
    input_text: str,
):
    set_span_attribute(
        span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, result.model
    )

    # Set embeddings dimensions if we can determine it from the response
    if getattr(result, "data", None) and len(result.data) > 0:
        first_embedding = result.data[0]
        if getattr(first_embedding, "embedding", None):
            set_span_attribute(
                span,
                "gen_ai.embeddings.dimension.count",
                len(first_embedding.embedding),
            )

    # Get the usage
    if getattr(result, "usage", None):
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
            result.usage.prompt_tokens,
        )
        # Don't set output tokens for embeddings as all tokens are input tokens
