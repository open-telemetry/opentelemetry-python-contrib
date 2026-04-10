"""Helpers for emitting GenAI metrics from invocations."""

from __future__ import annotations

import timeit
from typing import Dict, Optional

from opentelemetry.metrics import Histogram, Meter
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import (
    error_attributes,
    server_attributes,
)
from opentelemetry.trace import Span, set_span_in_context
from opentelemetry.util.genai.instruments import (
    create_duration_histogram,
    create_token_histogram,
)
from opentelemetry.util.genai.types import (
    EmbeddingInvocation,
    GenAIInvocation,
    LLMInvocation,
)
from opentelemetry.util.types import AttributeValue


class InvocationMetricsRecorder:
    """Records duration and token usage histograms for GenAI invocations."""

    def __init__(self, meter: Meter):
        self._duration_histogram: Histogram = create_duration_histogram(meter)
        self._token_histogram: Histogram = create_token_histogram(meter)

    @staticmethod
    def _build_attributes(
        invocation: GenAIInvocation,
        error_type: Optional[str] = None,
    ) -> Dict[str, AttributeValue]:
        """Build metric attributes from an invocation."""
        attributes: Dict[str, AttributeValue] = {}

        if invocation.operation_name:
            attributes[GenAI.GEN_AI_OPERATION_NAME] = invocation.operation_name

        request_model = getattr(invocation, "request_model", None)
        if request_model:
            attributes[GenAI.GEN_AI_REQUEST_MODEL] = request_model

        if invocation.provider:
            attributes[GenAI.GEN_AI_PROVIDER_NAME] = invocation.provider

        response_model_name = getattr(invocation, "response_model_name", None)
        if response_model_name:
            attributes[GenAI.GEN_AI_RESPONSE_MODEL] = response_model_name

        server_address = getattr(invocation, "server_address", None)
        if server_address:
            attributes[server_attributes.SERVER_ADDRESS] = server_address

        server_port = getattr(invocation, "server_port", None)
        if server_port is not None:
            attributes[server_attributes.SERVER_PORT] = server_port

        if invocation.metric_attributes:
            attributes.update(invocation.metric_attributes)

        if error_type:
            attributes[error_attributes.ERROR_TYPE] = error_type

        return attributes

    def record(
        self,
        span: Optional[Span],
        invocation: GenAIInvocation,
        *,
        error_type: Optional[str] = None,
    ) -> None:
        """Record duration and token metrics for an invocation if possible.

        For LLMInvocation: records duration and token (input/output) metrics.
        For EmbeddingInvocation: records duration only.
        """

        # pylint: disable=too-many-branches

        if span is None:
            return

        attributes = self._build_attributes(invocation, error_type)

        # Calculate duration from invocation monotonic start
        duration_seconds: Optional[float] = None
        if invocation.monotonic_start_s is not None:
            duration_seconds = max(
                timeit.default_timer() - invocation.monotonic_start_s,
                0.0,
            )

        span_context = set_span_in_context(span)

        if duration_seconds is not None:
            self._duration_histogram.record(
                duration_seconds,
                attributes=attributes,
                context=span_context,
            )

        # Record token metrics for LLMInvocation and EmbeddingInvocation
        if isinstance(invocation, (LLMInvocation, EmbeddingInvocation)):
            if invocation.input_tokens is not None:
                self._token_histogram.record(
                    invocation.input_tokens,
                    attributes=attributes
                    | {
                        GenAI.GEN_AI_TOKEN_TYPE: GenAI.GenAiTokenTypeValues.INPUT.value
                    },
                    context=span_context,
                )

        # Only LLMInvocation has output tokens
        if isinstance(invocation, LLMInvocation):
            if invocation.output_tokens is not None:
                self._token_histogram.record(
                    invocation.output_tokens,
                    attributes=attributes
                    | {
                        GenAI.GEN_AI_TOKEN_TYPE: GenAI.GenAiTokenTypeValues.OUTPUT.value
                    },
                    context=span_context,
                )


__all__ = ["InvocationMetricsRecorder"]
