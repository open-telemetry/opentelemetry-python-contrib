"""Helpers for emitting GenAI metrics from LLM invocations."""

from __future__ import annotations

import timeit
from numbers import Number
from typing import Dict, Optional

from opentelemetry.metrics import Histogram, Meter
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.trace import Span, set_span_in_context
from opentelemetry.util.genai.instruments import (
    create_duration_histogram,
    create_token_histogram,
)
from opentelemetry.util.genai.types import LLMInvocation
from opentelemetry.util.types import AttributeValue


class InvocationMetricsRecorder:
    """Records duration and token usage histograms for GenAI invocations."""

    def __init__(self, meter: Meter):
        self._duration_histogram: Histogram = create_duration_histogram(meter)
        self._token_histogram: Histogram = create_token_histogram(meter)

    def record(
        self,
        span: Optional[Span],
        invocation: LLMInvocation,
        *,
        error_type: Optional[str] = None,
    ) -> None:
        """Record duration and token metrics for an invocation if possible."""
        if span is None:
            return

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

        attributes: Dict[str, AttributeValue] = {
            GenAI.GEN_AI_OPERATION_NAME: GenAI.GenAiOperationNameValues.CHAT.value
        }
        if invocation.request_model:
            attributes[GenAI.GEN_AI_REQUEST_MODEL] = invocation.request_model
        if invocation.provider:
            attributes[GenAI.GEN_AI_PROVIDER_NAME] = invocation.provider
        if invocation.response_model_name:
            attributes[GenAI.GEN_AI_RESPONSE_MODEL] = (
                invocation.response_model_name
            )

        # Calculate duration from span timing or invocation monotonic start
        duration_seconds: Optional[float] = None
        if invocation.monotonic_start_s is not None:  # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue]
            duration_seconds = max(
                timeit.default_timer() - invocation.monotonic_start_s,  # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue,reportUnknownArgumentType]
                0.0,
            )

        span_context = set_span_in_context(span)
        if error_type:
            attributes["error.type"] = error_type

        if (
            duration_seconds is not None
            and isinstance(duration_seconds, Number)
            and duration_seconds >= 0
        ):
            self._duration_histogram.record(
                duration_seconds,
                attributes=attributes,
                context=span_context,
            )

        for token_count, token_type in token_counts:
            self._token_histogram.record(
                token_count,
                attributes=attributes | {GenAI.GEN_AI_TOKEN_TYPE: token_type},
                context=span_context,
            )


__all__ = ["InvocationMetricsRecorder"]
