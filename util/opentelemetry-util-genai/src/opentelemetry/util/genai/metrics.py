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
from opentelemetry.util.genai.types import GenAIInvocation, LLMInvocation
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

        # Set attributes using getattr for fields that may not exist on base class
        operation_name = getattr(invocation, "operation_name", None)
        if operation_name:
            attributes[GenAI.GEN_AI_OPERATION_NAME] = operation_name

        request_model = getattr(invocation, "request_model", None)
        if request_model:
            attributes[GenAI.GEN_AI_REQUEST_MODEL] = request_model

        provider = getattr(invocation, "provider", None)
        if provider:
            attributes[GenAI.GEN_AI_PROVIDER_NAME] = provider

        response_model_name = getattr(invocation, "response_model_name", None)
        if response_model_name:
            attributes[GenAI.GEN_AI_RESPONSE_MODEL] = response_model_name

        server_address = getattr(invocation, "server_address", None)
        if server_address:
            attributes[server_attributes.SERVER_ADDRESS] = server_address

        server_port = getattr(invocation, "server_port", None)
        if server_port is not None:
            attributes[server_attributes.SERVER_PORT] = server_port

        metric_attributes = getattr(invocation, "metric_attributes", None)
        if metric_attributes:
            attributes.update(metric_attributes)

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

        # Only record token metrics for LLMInvocation
        if isinstance(invocation, LLMInvocation):
            token_counts: list[tuple[int, str]] = []
            if invocation.input_tokens is not None:
                token_counts.append(
                    (
                        invocation.input_tokens,
                        GenAI.GenAiTokenTypeValues.INPUT.value,
                    )
                )
            if invocation.output_tokens is not None:
                token_counts.append(
                    (
                        invocation.output_tokens,
                        GenAI.GenAiTokenTypeValues.OUTPUT.value,
                    )
                )

            for token_count, token_type in token_counts:
                self._token_histogram.record(
                    token_count,
                    attributes=attributes
                    | {GenAI.GEN_AI_TOKEN_TYPE: token_type},
                    context=span_context,
                )


__all__ = ["InvocationMetricsRecorder"]
