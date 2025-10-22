"""Helpers for emitting GenAI metrics from LLM invocations."""

from __future__ import annotations

import time
from dataclasses import dataclass
from numbers import Number
from typing import Dict, Optional, Sequence

from opentelemetry.metrics import Histogram, Meter
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.trace import Span, set_span_in_context
from opentelemetry.util.genai.instruments import Instruments
from opentelemetry.util.genai.types import LLMInvocation
from opentelemetry.util.types import AttributeValue

_NS_PER_SECOND = 1_000_000_000


def _now_ns() -> int:
    return time.time_ns()


def _get_span_start_time_ns(span: Optional[Span]) -> Optional[int]:
    if span is None:
        return None
    for attr in ("start_time", "_start_time"):
        value = getattr(span, attr, None)
        if isinstance(value, int):
            return value
    return None


def _calculate_duration_seconds(span: Optional[Span]) -> Optional[float]:
    """Calculate duration in seconds from span start time to now."""
    start_time_ns = _get_span_start_time_ns(span)
    if start_time_ns is None:
        return None
    elapsed_ns = max(_now_ns() - start_time_ns, 0)
    return elapsed_ns / _NS_PER_SECOND


@dataclass(frozen=True)
class _TokenRecord:
    value: float
    token_type: str


@dataclass(frozen=True)
class _MetricPayload:
    attributes: Dict[str, AttributeValue]
    tokens: Sequence[_TokenRecord]


def _build_llm_metric_payload(invocation: LLMInvocation) -> _MetricPayload:
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

    tokens: list[_TokenRecord] = []
    if isinstance(invocation.input_tokens, Number):
        tokens.append(
            _TokenRecord(
                float(invocation.input_tokens),
                GenAI.GenAiTokenTypeValues.INPUT.value,
            )
        )
    if isinstance(invocation.output_tokens, Number):
        tokens.append(
            _TokenRecord(
                float(invocation.output_tokens),
                GenAI.GenAiTokenTypeValues.COMPLETION.value,
            )
        )

    return _MetricPayload(attributes=attributes, tokens=tokens)


def _extract_metric_payload(invocation: object) -> Optional[_MetricPayload]:
    if isinstance(invocation, LLMInvocation):
        return _build_llm_metric_payload(invocation)
    return None


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
        invocation: object,
        *,
        error_type: Optional[str] = None,
    ) -> None:
        """Record duration and token metrics for an invocation if possible."""
        if span is None:
            return

        payload = _extract_metric_payload(invocation)
        if payload is None:
            return

        # Calculate duration from span timing
        duration_seconds = _calculate_duration_seconds(span)

        span_context = set_span_in_context(span)
        common_attributes: Dict[str, AttributeValue] = dict(payload.attributes)
        if error_type:
            common_attributes["error.type"] = error_type

        if (
            duration_seconds is not None
            and isinstance(duration_seconds, Number)
            and duration_seconds >= 0
        ):
            duration_attributes: Dict[str, AttributeValue] = dict(
                common_attributes
            )
            self._duration_histogram.record(
                float(duration_seconds),
                attributes=duration_attributes,
                context=span_context,
            )

        for token in payload.tokens:
            token_attributes: Dict[str, AttributeValue] = dict(
                common_attributes
            )
            token_attributes[GenAI.GEN_AI_TOKEN_TYPE] = token.token_type
            self._token_histogram.record(
                token.value,
                attributes=token_attributes,
                context=span_context,
            )


__all__ = ["InvocationMetricsRecorder"]
