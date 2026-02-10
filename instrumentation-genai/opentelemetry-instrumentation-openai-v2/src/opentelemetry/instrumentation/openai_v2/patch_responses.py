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

from opentelemetry._logs import Logger
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.trace import Span, SpanKind, Tracer
from opentelemetry.trace.status import Status, StatusCode

from .instruments import Instruments
from .utils import (
    _record_metrics,
    get_llm_request_attributes,
    handle_span_exception,
    is_streaming,
    set_span_attribute,
)


def responses_create(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `create` method of the `Responses` class to trace it."""
    # https://github.com/openai/openai-python/blob/dc68b90655912886bd7a6c7787f96005452ebfc9/src/openai/resources/responses/responses.py#L828
    # TODO: Consider migrating Responses instrumentation to TelemetryHandler
    # once content capture and streaming hooks are available.

    def traced_method(wrapped, instance, args, kwargs):
        span_attributes = get_llm_request_attributes(
            kwargs,
            instance,
            GenAIAttributes.GenAiOperationNameValues.GENERATE_CONTENT.value,
        )
        span_name = f"{span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]} {span_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]}"
        streaming = is_streaming(kwargs)

        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
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

                if streaming:
                    return ResponseStreamWrapper(
                        parsed_result,
                        span,
                        logger,
                        capture_content,
                        record_metrics=True,
                        instruments=instruments,
                        request_attributes=span_attributes,
                        operation_name=GenAIAttributes.GenAiOperationNameValues.GENERATE_CONTENT.value,
                        start_time=start,
                    )

                if span.is_recording():
                    _set_responses_response_attributes(
                        span, parsed_result, capture_content
                    )

                span.end()
                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise
            finally:
                if not streaming or result is None:
                    duration = max((default_timer() - start), 0)
                    _record_metrics(
                        instruments,
                        duration,
                        result,
                        span_attributes,
                        error_type,
                        GenAIAttributes.GenAiOperationNameValues.GENERATE_CONTENT.value,
                    )

    return traced_method


def responses_stream(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `stream` method of the `Responses` class to trace it."""
    # https://github.com/openai/openai-python/blob/dc68b90655912886bd7a6c7787f96005452ebfc9/src/openai/resources/responses/responses.py#L966

    def traced_method(wrapped, instance, args, kwargs):
        # If this is creating a new response, the create() wrapper will handle tracing.
        # This is done to avoid duplicate span creation. https://github.com/openai/openai-python/blob/dc68b90655912886bd7a6c7787f96005452ebfc9/src/openai/resources/responses/responses.py#L1036
        if "response_id" not in kwargs and "starting_after" not in kwargs:
            return wrapped(*args, **kwargs)

        span_attributes = get_llm_request_attributes(
            {},
            instance,
            GenAIAttributes.GenAiOperationNameValues.GENERATE_CONTENT.value,
        )
        span_name = f"{span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]} {span_attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL, 'unknown')}"

        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            error_type = None
            try:
                manager = wrapped(*args, **kwargs)
                return ResponseStreamManagerWrapper(
                    manager,
                    lambda stream: ResponseStreamWrapper(
                        stream,
                        span,
                        logger,
                        capture_content,
                        record_metrics=True,
                        instruments=instruments,
                        request_attributes=span_attributes,
                        operation_name=GenAIAttributes.GenAiOperationNameValues.GENERATE_CONTENT.value,
                        start_time=default_timer(),
                    ),
                )
            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise
            finally:
                if error_type is not None:
                    _record_metrics(
                        instruments,
                        0,
                        None,
                        span_attributes,
                        error_type,
                        GenAIAttributes.GenAiOperationNameValues.GENERATE_CONTENT.value,
                    )

    return traced_method


def responses_retrieve(
    tracer: Tracer,
    logger: Logger,
    instruments: Instruments,
    capture_content: bool,
):
    """Wrap the `retrieve` method of the `Responses` class to trace it."""
    # https://github.com/openai/openai-python/blob/dc68b90655912886bd7a6c7787f96005452ebfc9/src/openai/resources/responses/responses.py#L1417C9-L1417C17
    retrieval_enum = getattr(
        GenAIAttributes.GenAiOperationNameValues, "RETRIEVAL", None
    )
    operation_name = retrieval_enum.value if retrieval_enum else "retrieval"

    def traced_method(wrapped, instance, args, kwargs):
        span_attributes = get_llm_request_attributes(
            {},
            instance,
            operation_name,
        )
        span_name = f"{span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]} {span_attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL, 'unknown')}"
        streaming = is_streaming(kwargs)

        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
            end_on_exit=False,
        ) as span:
            start = default_timer()
            result = None
            error_type = None
            try:
                result = wrapped(*args, **kwargs)
                if hasattr(result, "parse"):
                    parsed_result = result.parse()
                else:
                    parsed_result = result

                if streaming:
                    return ResponseStreamWrapper(
                        parsed_result,
                        span,
                        logger,
                        capture_content,
                        record_metrics=True,
                        instruments=instruments,
                        request_attributes=span_attributes,
                        operation_name=operation_name,
                        start_time=start,
                    )

                if (
                    GenAIAttributes.GEN_AI_REQUEST_MODEL not in span_attributes
                    and getattr(parsed_result, "model", None)
                ):
                    span_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] = (
                        parsed_result.model
                    )
                    if span.is_recording():
                        set_span_attribute(
                            span,
                            GenAIAttributes.GEN_AI_REQUEST_MODEL,
                            parsed_result.model,
                        )
                    if hasattr(span, "update_name"):
                        span.update_name(
                            f"{operation_name} {parsed_result.model}"
                        )

                if span.is_recording():
                    _set_responses_response_attributes(
                        span, parsed_result, capture_content
                    )

                span.end()
                return result

            except Exception as error:
                error_type = type(error).__qualname__
                handle_span_exception(span, error)
                raise
            finally:
                if not streaming or result is None:
                    duration = max((default_timer() - start), 0)
                    _record_metrics(
                        instruments,
                        duration,
                        result,
                        span_attributes,
                        error_type,
                        operation_name,
                    )

    return traced_method


def _set_responses_response_attributes(
    span: Span,
    result: Any,
    capture_content: bool,
):
    if getattr(result, "model", None):
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, result.model
        )

    if getattr(result, "id", None):
        set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_ID, result.id)

    if getattr(result, "service_tier", None):
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_OPENAI_RESPONSE_SERVICE_TIER,
            result.service_tier,
        )

    if getattr(result, "usage", None):
        input_tokens = getattr(result.usage, "input_tokens", None)
        if input_tokens is None:
            input_tokens = getattr(result.usage, "prompt_tokens", None)
        if input_tokens is not None:
            set_span_attribute(
                span,
                GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
                input_tokens,
            )

        output_tokens = getattr(result.usage, "output_tokens", None)
        if output_tokens is None:
            output_tokens = getattr(result.usage, "completion_tokens", None)
        if output_tokens is not None:
            set_span_attribute(
                span,
                GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS,
                output_tokens,
            )


class _ResponseProxy:
    def __init__(self, response, finalize):
        self._response = response
        self._finalize = finalize

    def close(self):
        try:
            self._response.close()
        finally:
            self._finalize(None, None)

    def __getattr__(self, name):
        return getattr(self._response, name)


class ResponseStreamWrapper:
    def __init__(
        self,
        stream: Any,
        span: Span,
        logger: Logger,
        capture_content: bool,
        *,
        record_metrics: bool,
        instruments: Instruments,
        request_attributes: dict,
        operation_name: str,
        start_time: Optional[float] = None,
    ):
        self.stream = stream
        self.span = span
        self.logger = logger
        self.capture_content = capture_content
        self.record_metrics = record_metrics
        self.instruments = instruments
        self.request_attributes = request_attributes
        self.operation_name = operation_name
        self.start_time = (
            start_time if start_time is not None else default_timer()
        )
        self._span_ended = False
        self._span_name_updated = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                self._handle_exception(exc_val)
        finally:
            self.close()
        return False  # Propagate the exception

    def close(self):
        if hasattr(self.stream, "close"):
            self.stream.close()
        self._finalize(None, None)

    def __iter__(self):
        return self

    def __next__(self):
        try:
            event = next(self.stream)
            self.process_event(event)
            return event
        except StopIteration:
            self._finalize(None, None)
            raise
        except Exception as error:
            self._handle_exception(error)
            raise

    def get_final_response(self):
        if not hasattr(self.stream, "get_final_response"):
            raise AttributeError("get_final_response is not available")
        self.until_done()
        return self.stream.get_final_response()

    def until_done(self):
        for _ in self:
            pass
        return self

    def parse(self):
        """Called when using with_raw_response with stream=True"""
        return self

    def __getattr__(self, name):
        return getattr(self.stream, name)

    @property
    def response(self):
        response = getattr(self.stream, "response", None)
        if response is None:
            return None
        return _ResponseProxy(response, self._finalize)

    def _handle_exception(self, error):
        if self._span_ended:
            return
        handle_span_exception(self.span, error)
        self._span_ended = True
        self._record_metrics(None, type(error).__qualname__)

    def _mark_span_error(self, error_type: str, message: str):
        self.span.set_status(Status(StatusCode.ERROR, message))
        if self.span.is_recording() and error_type:
            self.span.set_attribute(ErrorAttributes.ERROR_TYPE, error_type)

    def _record_metrics(self, result, error_type: Optional[str]):
        if not self.record_metrics:
            return
        duration = max((default_timer() - self.start_time), 0)
        _record_metrics(
            self.instruments,
            duration,
            result,
            self.request_attributes,
            error_type,
            self.operation_name,
        )

    def _finalize(
        self,
        result,
        error_type: Optional[str],
        error_message: Optional[str] = None,
    ):
        if self._span_ended:
            return
        if result and self.span.is_recording():
            _set_responses_response_attributes(
                self.span, result, self.capture_content
            )
        if error_type:
            self._mark_span_error(error_type, error_message or error_type)
        self.span.end()
        self._span_ended = True
        self._record_metrics(result, error_type)

    def _maybe_update_request_model(self, response):
        if (
            response
            and GenAIAttributes.GEN_AI_REQUEST_MODEL
            not in self.request_attributes
            and getattr(response, "model", None)
        ):
            self.request_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] = (
                response.model
            )
            if self.span.is_recording():
                set_span_attribute(
                    self.span,
                    GenAIAttributes.GEN_AI_REQUEST_MODEL,
                    response.model,
                )
            if not self._span_name_updated and hasattr(
                self.span, "update_name"
            ):
                self.span.update_name(
                    f"{self.operation_name} {response.model}"
                )
                self._span_name_updated = True

    def process_event(self, event):
        event_type = getattr(event, "type", None)
        if event_type in {"response.created", "response.completed"}:
            response = getattr(event, "response", None)
            self._maybe_update_request_model(response)
            if response and self.span.is_recording():
                _set_responses_response_attributes(
                    self.span, response, self.capture_content
                )
            if event_type == "response.completed":
                self._finalize(response, None)
            return

        if event_type in {"response.failed", "response.incomplete"}:
            response = getattr(event, "response", None)
            self._maybe_update_request_model(response)
            if response and self.span.is_recording():
                _set_responses_response_attributes(
                    self.span, response, self.capture_content
                )
            self._finalize(response, event_type)
            return

        if event_type == "error":
            error_type = getattr(event, "code", None) or "response.error"
            message = getattr(event, "message", None) or error_type
            self._finalize(None, error_type, message)
            return


class ResponseStreamManagerWrapper:
    def __init__(self, manager, wrapper_factory):
        self._manager = manager
        self._wrapper_factory = wrapper_factory
        self._stream = None

    def __enter__(self):
        stream = self._manager.__enter__()
        self._stream = self._wrapper_factory(stream)
        return self._stream

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._stream is not None:
            return self._stream.__exit__(exc_type, exc_val, exc_tb)
        return self._manager.__exit__(exc_type, exc_val, exc_tb)

    def __getattr__(self, name):
        return getattr(self._manager, name)
