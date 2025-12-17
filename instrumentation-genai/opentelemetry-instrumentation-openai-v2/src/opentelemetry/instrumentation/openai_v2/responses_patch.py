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

from __future__ import annotations

from timeit import default_timer
from typing import Any, Optional

from opentelemetry._logs import Logger, LogRecord
from opentelemetry.context import get_current
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.trace import Span, SpanKind, Tracer
from opentelemetry.trace.propagation import set_span_in_context

from .instruments import Instruments
from .patch import _record_metrics, _set_responses_response_attributes
from .responses import output_to_event, responses_input_to_event
from .utils import (
    get_llm_request_attributes,
    get_property_value,
    handle_span_exception,
    is_streaming,
    set_span_attribute,
)


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
    """
    Wrap a Responses API stream and finalize telemetry when the stream completes.

    The Responses streaming API yields `ResponseStreamEvent` items (not Chat Completion chunks),
    so we parse events defensively and record usage/metrics at stream completion.
    """

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
                event_name="gen_ai.output",  # type: ignore[call-arg]
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
            event = await self.stream.__anext__()  # type: ignore[attr-defined]
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
