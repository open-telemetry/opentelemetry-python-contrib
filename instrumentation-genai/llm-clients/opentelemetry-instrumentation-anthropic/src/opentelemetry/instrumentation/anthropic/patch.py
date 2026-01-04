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

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

from opentelemetry import context as context_api
from opentelemetry._logs import Logger
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.trace.status import Status, StatusCode

from opentelemetry.instrumentation.anthropic.instruments import Instruments
from opentelemetry.instrumentation.anthropic.streaming import (
    AnthropicAsyncStream,
    AnthropicStream,
    WrappedAsyncMessageStreamManager,
    WrappedMessageStreamManager,
)
from opentelemetry.instrumentation.anthropic.utils import (
    GEN_AI_SYSTEM_ANTHROPIC,
    get_llm_request_attributes,
    handle_span_exception,
    is_content_enabled,
    set_request_content_on_span,
    set_response_attributes,
    set_response_content_on_span,
    set_tools_attributes,
)

logger = logging.getLogger(__name__)


def _is_streaming_response(response: Any) -> bool:
    """Check if response is a streaming response."""
    try:
        from anthropic._streaming import AsyncStream, Stream

        return isinstance(response, (Stream, AsyncStream))
    except ImportError:
        # Fallback to class name check
        class_name = response.__class__.__name__
        return class_name in ("Stream", "AsyncStream")


def _is_stream_manager(response: Any) -> bool:
    """Check if response is a MessageStreamManager."""
    try:
        from anthropic.lib.streaming._messages import (
            AsyncMessageStreamManager,
            MessageStreamManager,
        )

        return isinstance(response, (MessageStreamManager, AsyncMessageStreamManager))
    except ImportError:
        # Fallback to class name check
        class_name = response.__class__.__name__
        return class_name in ("MessageStreamManager", "AsyncMessageStreamManager")


def _record_metrics(
    instruments: Instruments,
    duration: float,
    response: Any,
    request_attributes: dict,
    error_type: Optional[str] = None,
) -> None:
    """Record metrics for a non-streaming response."""
    common_attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: request_attributes.get(
            GenAIAttributes.GEN_AI_OPERATION_NAME
        ),
        GenAIAttributes.GEN_AI_SYSTEM: GEN_AI_SYSTEM_ANTHROPIC,
        GenAIAttributes.GEN_AI_REQUEST_MODEL: request_attributes.get(
            GenAIAttributes.GEN_AI_REQUEST_MODEL
        ),
    }

    if error_type:
        common_attributes["error.type"] = error_type

    # Get response model if available
    if response:
        # Handle with_raw_response wrapped responses
        if hasattr(response, "parse") and callable(response.parse):
            try:
                response = response.parse()
            except Exception:
                pass

        model = getattr(response, "model", None)
        if model:
            common_attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL] = model

    # Record operation duration
    instruments.operation_duration_histogram.record(
        duration, attributes=common_attributes
    )

    # Record token usage
    if response:
        usage = getattr(response, "usage", None)
        if usage:
            input_tokens = getattr(usage, "input_tokens", 0)
            output_tokens = getattr(usage, "output_tokens", 0)
            cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
            cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0

            total_input = input_tokens + cache_read + cache_creation

            if total_input > 0:
                instruments.token_usage_histogram.record(
                    total_input,
                    attributes={
                        **common_attributes,
                        GenAIAttributes.GEN_AI_TOKEN_TYPE: "input",
                    },
                )

            if output_tokens > 0:
                instruments.token_usage_histogram.record(
                    output_tokens,
                    attributes={
                        **common_attributes,
                        GenAIAttributes.GEN_AI_TOKEN_TYPE: "output",
                    },
                )


def messages_create_wrapper(
    tracer: Tracer,
    instruments: Instruments,
    event_logger: Optional[Logger],
) -> Callable:
    """Create a wrapper for Messages.create method."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        capture_content = is_content_enabled()

        # Get request attributes
        request_attributes = get_llm_request_attributes(
            kwargs,
            instance,
            operation_name=GenAIAttributes.GenAiOperationNameValues.CHAT.value,
        )

        # Create span name
        model = kwargs.get("model", "unknown")
        span_name = f"chat {model}"

        with tracer.start_as_current_span(
            span_name,
            kind=SpanKind.CLIENT,
            attributes=request_attributes,
        ) as span:
            # Set tools attributes
            set_tools_attributes(span, kwargs)

            # Set request content if enabled
            set_request_content_on_span(span, kwargs, capture_content)

            start_time = time.time()
            try:
                response = wrapped(*args, **kwargs)
            except Exception as error:
                duration = time.time() - start_time
                _record_metrics(
                    instruments,
                    duration,
                    None,
                    request_attributes,
                    error_type=type(error).__qualname__,
                )
                handle_span_exception(span, error)
                raise

            duration = time.time() - start_time

            # Handle streaming response
            if _is_streaming_response(response):
                return AnthropicStream(
                    response,
                    span,
                    instruments,
                    request_attributes,
                    capture_content,
                    event_logger,
                )

            # Handle stream manager
            if _is_stream_manager(response):
                if response.__class__.__name__ == "AsyncMessageStreamManager":
                    return WrappedAsyncMessageStreamManager(
                        response,
                        span,
                        instruments,
                        request_attributes,
                        capture_content,
                        event_logger,
                    )
                return WrappedMessageStreamManager(
                    response,
                    span,
                    instruments,
                    request_attributes,
                    capture_content,
                    event_logger,
                )

            # Non-streaming response
            set_response_attributes(span, response)
            set_response_content_on_span(span, response, capture_content)
            _record_metrics(instruments, duration, response, request_attributes)
            span.set_status(Status(StatusCode.OK))

            return response

    return wrapper


def messages_stream_wrapper(
    tracer: Tracer,
    instruments: Instruments,
    event_logger: Optional[Logger],
) -> Callable:
    """Create a wrapper for Messages.stream method."""

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        capture_content = is_content_enabled()

        # Get request attributes
        request_attributes = get_llm_request_attributes(
            kwargs,
            instance,
            operation_name=GenAIAttributes.GenAiOperationNameValues.CHAT.value,
        )
        # Force streaming attribute
        request_attributes["gen_ai.request.streaming"] = True

        # Create span name
        model = kwargs.get("model", "unknown")
        span_name = f"chat {model}"

        span = tracer.start_span(
            span_name,
            kind=SpanKind.CLIENT,
            attributes=request_attributes,
        )

        # Set tools attributes
        set_tools_attributes(span, kwargs)

        # Set request content if enabled
        set_request_content_on_span(span, kwargs, capture_content)

        try:
            response = wrapped(*args, **kwargs)
        except Exception as error:
            handle_span_exception(span, error)
            raise

        # The response should be a MessageStreamManager
        if _is_stream_manager(response):
            if response.__class__.__name__ == "AsyncMessageStreamManager":
                return WrappedAsyncMessageStreamManager(
                    response,
                    span,
                    instruments,
                    request_attributes,
                    capture_content,
                    event_logger,
                )
            return WrappedMessageStreamManager(
                response,
                span,
                instruments,
                request_attributes,
                capture_content,
                event_logger,
            )

        # Fallback for unexpected response type
        return response

    return wrapper


def async_messages_create_wrapper(
    tracer: Tracer,
    instruments: Instruments,
    event_logger: Optional[Logger],
) -> Callable:
    """Create an async wrapper for AsyncMessages.create method."""

    async def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return await wrapped(*args, **kwargs)

        capture_content = is_content_enabled()

        # Get request attributes
        request_attributes = get_llm_request_attributes(
            kwargs,
            instance,
            operation_name=GenAIAttributes.GenAiOperationNameValues.CHAT.value,
        )

        # Create span name
        model = kwargs.get("model", "unknown")
        span_name = f"chat {model}"

        span = tracer.start_span(
            span_name,
            kind=SpanKind.CLIENT,
            attributes=request_attributes,
        )

        # Set tools attributes
        set_tools_attributes(span, kwargs)

        # Set request content if enabled
        set_request_content_on_span(span, kwargs, capture_content)

        start_time = time.time()
        try:
            response = await wrapped(*args, **kwargs)
        except Exception as error:
            duration = time.time() - start_time
            _record_metrics(
                instruments,
                duration,
                None,
                request_attributes,
                error_type=type(error).__qualname__,
            )
            handle_span_exception(span, error)
            raise

        duration = time.time() - start_time

        # Handle streaming response
        if _is_streaming_response(response):
            return AnthropicAsyncStream(
                response,
                span,
                instruments,
                request_attributes,
                capture_content,
                event_logger,
            )

        # Handle stream manager
        if _is_stream_manager(response):
            return WrappedAsyncMessageStreamManager(
                response,
                span,
                instruments,
                request_attributes,
                capture_content,
                event_logger,
            )

        # Non-streaming response
        set_response_attributes(span, response)
        set_response_content_on_span(span, response, capture_content)
        _record_metrics(instruments, duration, response, request_attributes)
        span.set_status(Status(StatusCode.OK))
        span.end()

        return response

    return wrapper


def async_messages_stream_wrapper(
    tracer: Tracer,
    instruments: Instruments,
    event_logger: Optional[Logger],
) -> Callable:
    """Create a wrapper for AsyncMessages.stream method.

    Note: AsyncMessages.stream is actually a sync method that returns
    an async context manager, so we don't await wrapped().
    """

    def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return wrapped(*args, **kwargs)

        capture_content = is_content_enabled()

        # Get request attributes
        request_attributes = get_llm_request_attributes(
            kwargs,
            instance,
            operation_name=GenAIAttributes.GenAiOperationNameValues.CHAT.value,
        )
        # Force streaming attribute
        request_attributes["gen_ai.request.streaming"] = True

        # Create span name
        model = kwargs.get("model", "unknown")
        span_name = f"chat {model}"

        span = tracer.start_span(
            span_name,
            kind=SpanKind.CLIENT,
            attributes=request_attributes,
        )

        # Set tools attributes
        set_tools_attributes(span, kwargs)

        # Set request content if enabled
        set_request_content_on_span(span, kwargs, capture_content)

        try:
            response = wrapped(*args, **kwargs)
        except Exception as error:
            handle_span_exception(span, error)
            raise

        # The response should be an AsyncMessageStreamManager
        return WrappedAsyncMessageStreamManager(
            response,
            span,
            instruments,
            request_attributes,
            capture_content,
            event_logger,
        )

    return wrapper
