# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from timeit import default_timer
from typing import Any, Callable, Optional

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.trace import Span, SpanKind, Tracer
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.invocation import EmbeddingInvocation
from opentelemetry.util.genai.types import Error

from .instruments import Instruments
from .utils import (
    _VOYAGEAI_PROVIDER,
    create_embedding_invocation,
    get_embeddings_request_attributes,
    handle_span_exception,
    set_span_attribute,
)

_EMBEDDINGS = GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value


def embed_v_old(
    tracer: Tracer,
    instruments: Instruments,
) -> Callable[..., Any]:
    """Wrap the sync ``Client.embed`` on the legacy semconv path."""

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        span_attributes = get_embeddings_request_attributes(
            kwargs, instance, False
        )
        span_name = _get_embeddings_span_name(span_attributes)

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
                if span.is_recording():
                    _set_embeddings_response_attributes(span, result)
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
                )

    return traced_method


def embed_v_new(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Wrap the sync ``Client.embed`` on the experimental semconv path."""

    def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_embedding_invocation(handler, kwargs, instance)

        try:
            result = wrapped(*args, **kwargs)
            _set_embeddings_response_properties(invocation, result)
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def async_embed_v_old(
    tracer: Tracer,
    instruments: Instruments,
) -> Callable[..., Any]:
    """Wrap the async ``AsyncClient.embed`` on the legacy semconv path."""

    async def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        span_attributes = get_embeddings_request_attributes(
            kwargs, instance, False
        )
        span_name = _get_embeddings_span_name(span_attributes)

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
                result = await wrapped(*args, **kwargs)
                if span.is_recording():
                    _set_embeddings_response_attributes(span, result)
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
                )

    return traced_method


def async_embed_v_new(
    handler: TelemetryHandler,
) -> Callable[..., Any]:
    """Wrap the async ``AsyncClient.embed`` on the experimental semconv path."""

    async def traced_method(
        wrapped: Callable[..., Any],
        instance: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        invocation = create_embedding_invocation(handler, kwargs, instance)

        try:
            result = await wrapped(*args, **kwargs)
            _set_embeddings_response_properties(invocation, result)
            invocation.stop()
            return result
        except Exception as error:
            invocation.fail(Error(type=type(error), message=str(error)))
            raise

    return traced_method


def _get_embeddings_span_name(span_attributes: dict[str, Any]) -> str:
    operation_name = span_attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
    model = span_attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL)
    return f"{operation_name} {model}" if model else operation_name


def _get_dimension_count(result: Any) -> Optional[int]:
    """Derive the embedding dimension from a Voyage AI ``EmbeddingsObject``."""
    embeddings = getattr(result, "embeddings", None)
    if embeddings and len(embeddings) > 0 and embeddings[0] is not None:
        return len(embeddings[0])
    return None


def _get_input_tokens(result: Any) -> Optional[int]:
    """The Voyage AI ``EmbeddingsObject`` exposes ``total_tokens`` (all input)."""
    total_tokens = getattr(result, "total_tokens", None)
    if isinstance(total_tokens, int):
        return total_tokens
    return None


def _set_embeddings_response_attributes(span: Span, result: Any) -> None:
    dimension = _get_dimension_count(result)
    if dimension is not None:
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_EMBEDDINGS_DIMENSION_COUNT,
            dimension,
        )

    input_tokens = _get_input_tokens(result)
    if input_tokens is not None:
        # Embeddings tokens are all input tokens; no output tokens are emitted.
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS,
            input_tokens,
        )


def _set_embeddings_response_properties(
    invocation: EmbeddingInvocation, result: Any
) -> EmbeddingInvocation:
    dimension = _get_dimension_count(result)
    if dimension is not None:
        invocation.dimension_count = dimension

    input_tokens = _get_input_tokens(result)
    if input_tokens is not None:
        # Embeddings tokens are all input tokens; no output tokens are emitted.
        invocation.input_tokens = input_tokens

    return invocation


def _record_metrics(
    instruments: Instruments,
    duration: float,
    result: Any,
    request_attributes: dict[str, Any],
    error_type: Optional[str],
) -> None:
    common_attributes: dict[str, Any] = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: _EMBEDDINGS,
        GenAIAttributes.GEN_AI_SYSTEM: _VOYAGEAI_PROVIDER,
    }

    if GenAIAttributes.GEN_AI_REQUEST_MODEL in request_attributes:
        common_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] = (
            request_attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
        )

    if error_type:
        common_attributes[ErrorAttributes.ERROR_TYPE] = error_type

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

    input_tokens = _get_input_tokens(result)
    if input_tokens is not None:
        # For embeddings, only input tokens are recorded; all tokens are input.
        input_attributes = {
            **common_attributes,
            GenAIAttributes.GEN_AI_TOKEN_TYPE: GenAIAttributes.GenAiTokenTypeValues.INPUT.value,
        }
        instruments.token_usage_histogram.record(
            input_tokens,
            attributes=input_attributes,
        )


__all__ = [
    "async_embed_v_new",
    "async_embed_v_old",
    "embed_v_new",
    "embed_v_old",
]
