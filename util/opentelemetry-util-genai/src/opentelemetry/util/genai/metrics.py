"""Helpers for emitting GenAI metrics from LLM invocations."""

from __future__ import annotations

import time
import timeit
from numbers import Number
from typing import Dict, Optional

from opentelemetry.metrics import Histogram, Meter
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.trace import Span, set_span_in_context
from opentelemetry.util.genai.instruments import Instruments
from opentelemetry.util.genai.types import LLMInvocation
from opentelemetry.util.types import AttributeValue

_NS_PER_SECOND = 1_000_000_000


def _get_span_start_time_ns(span: Optional[Span]) -> Optional[int]:
    if span is None:
        return None
    for attr in ("start_time", "_start_time"):
        value = getattr(span, attr, None)
        if isinstance(value, int):
            return value
    return None


def _calculate_duration_seconds(
    span: Optional[Span], invocation: Optional[LLMInvocation] = None
) -> Optional[float]:
    """Calculate duration in seconds from a start time to now.

    If `invocation.monotonic_start_ns` is present, use a monotonic
    clock (`perf_counter_ns`) for elapsed time. Otherwise fall back to the
    span's wall-clock start time (epoch ns) and `time_ns()` for now.

    Returns None if no usable start time is available.
    """
    # Prefer an explicit monotonic start on the invocation (seconds)
    if invocation is not None and getattr(
        invocation, "monotonic_start_s", None
    ):
        start_s = invocation.monotonic_start_s
        if isinstance(start_s, (int, float)):
            elapsed_s = max(timeit.default_timer() - float(start_s), 0.0)
            return elapsed_s

    # Fall back to span start_time (wall clock epoch ns)
    start_time_ns = _get_span_start_time_ns(span)
    if start_time_ns is None:
        return None
    elapsed_ns = max(time.time_ns() - start_time_ns, 0)
    return elapsed_ns / _NS_PER_SECOND


class InvocationMetricsRecorder:
    """Records duration and token usage histograms for GenAI invocations."""

    def __init__(self, meter: Meter):
        instruments = Instruments(meter)
        self._duration_histogram: Histogram = (
            instruments.operation_duration_histogram
        )
        self._token_histogram: Histogram = instruments.token_usage_histogram

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
        duration_seconds = _calculate_duration_seconds(span, invocation)

        span_context = set_span_in_context(span)
        if error_type:
            attributes["error.type"] = error_type

        if (
            duration_seconds is not None
            and isinstance(duration_seconds, Number)
            and duration_seconds >= 0
        ):
            duration_attributes: Dict[str, AttributeValue] = dict(attributes)
            self._duration_histogram.record(
                duration_seconds,
                attributes=duration_attributes,
                context=span_context,
            )

        for token_count, token_type in token_counts:
            self._token_histogram.record(
                token_count,
                attributes=attributes | {GenAI.GEN_AI_TOKEN_TYPE: token_type},
                context=span_context,
            )


__all__ = ["InvocationMetricsRecorder"]
