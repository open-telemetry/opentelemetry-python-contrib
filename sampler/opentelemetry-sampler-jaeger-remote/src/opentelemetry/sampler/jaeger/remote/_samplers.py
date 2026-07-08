# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import time
from typing import Callable, Iterable, Sequence

from opentelemetry.context import Context
from opentelemetry.sampler.jaeger.remote._ratelimiter import RateLimiter
from opentelemetry.sdk.trace.sampling import (
    Decision,
    Sampler,
    SamplingResult,
    TraceIdRatioBased,
)
from opentelemetry.trace import Link, SpanKind
from opentelemetry.trace.span import TraceState
from opentelemetry.util.types import Attributes

_SAMPLER_TYPE_KEY = "sampler.type"
_SAMPLER_PARAM_KEY = "sampler.param"
_DEFAULT_MAX_OPERATIONS = 2000


def _sampler_result(
    decision: Decision,
    trace_state: TraceState | None,
    sampler_type: str,
    param: float,
) -> SamplingResult:
    return SamplingResult(
        decision,
        {_SAMPLER_TYPE_KEY: sampler_type, _SAMPLER_PARAM_KEY: param},
        trace_state,
    )


class ProbabilisticSampler(Sampler):
    """Sampler for Jaeger's ProbabilisticSamplingStrategy.

    Delegates the actual sampling decision to `TraceIdRatioBased`, which
    already implements the same trace ID bound algorithm Jaeger's
    probabilistic sampler uses. This wrapper exists to give the sampler a
    Jaeger-flavored description, attach `sampler.type`/`sampler.param`
    attributes, and provide an `update` method for reconfiguring it in
    place as new sampling strategies are polled from the remote server.
    """

    def __init__(self, rate: float) -> None:
        self._inner = TraceIdRatioBased(rate)

    @property
    def rate(self) -> float:
        return self._inner.rate

    def update(self, rate: float) -> None:
        """Reconfigure the sampling rate in place."""
        self._inner = TraceIdRatioBased(rate)

    def should_sample(
        self,
        parent_context: Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Attributes | None = None,
        links: Sequence[Link] | None = None,
        trace_state: TraceState | None = None,
    ) -> SamplingResult:
        result = self._inner.should_sample(
            parent_context,
            trace_id,
            name,
            kind=kind,
            attributes=attributes,
            links=links,
            trace_state=trace_state,
        )
        return _sampler_result(
            result.decision, result.trace_state, "probabilistic", self.rate
        )

    def get_description(self) -> str:
        return f"ProbabilisticSampler{{{self.rate}}}"


class RateLimitingSampler(Sampler):
    """Sampler for Jaeger's RateLimitingSamplingStrategy.

    Samples at most `max_traces_per_second`, using a token bucket
    (`RateLimiter`) with one credit spent per span. Burst capacity is
    floored at 1.0 so that sub-1/sec rates still get an immediate credit
    rather than starting starved.
    """

    def __init__(
        self,
        max_traces_per_second: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_traces_per_second = max_traces_per_second
        self._rate_limiter = RateLimiter(
            max_traces_per_second,
            max(max_traces_per_second, 1.0),
            clock=clock,
        )

    @property
    def max_traces_per_second(self) -> float:
        return self._max_traces_per_second

    def update(self, max_traces_per_second: float) -> None:
        """Reconfigure the rate in place."""
        self._max_traces_per_second = max_traces_per_second
        self._rate_limiter.update(
            max_traces_per_second, max(max_traces_per_second, 1.0)
        )

    def should_sample(
        self,
        parent_context: Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Attributes | None = None,
        links: Sequence[Link] | None = None,
        trace_state: TraceState | None = None,
    ) -> SamplingResult:
        decision = (
            Decision.RECORD_AND_SAMPLE
            if self._rate_limiter.try_spend(1.0)
            else Decision.DROP
        )
        return _sampler_result(
            decision, trace_state, "ratelimiting", self._max_traces_per_second
        )

    def get_description(self) -> str:
        return f"RateLimitingSampler{{{self._max_traces_per_second}}}"


class GuaranteedThroughputSampler(Sampler):
    """Probabilistic sampling with a guaranteed minimum rate.

    Combines a `ProbabilisticSampler(rate)` with a lower-bound `RateLimiter`
    (when `lower_bound > 0`): the probabilistic decision wins whenever it
    samples, but a lower bound credit is always spent regardless, so an
    operation that would otherwise never be sampled probabilistically is
    still guaranteed to fire at least `lower_bound` times per second. A
    `lower_bound` of 0 disables the guarantee entirely.
    """

    def __init__(
        self,
        rate: float,
        lower_bound: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self._probabilistic = ProbabilisticSampler(rate)
        self._lower_bound = lower_bound
        self._rate_limiter = self._make_rate_limiter(lower_bound)

    def _make_rate_limiter(self, lower_bound: float) -> RateLimiter | None:
        if lower_bound <= 0:
            return None
        return RateLimiter(lower_bound, max(lower_bound, 1.0), clock=self._clock)

    def update(self, rate: float, lower_bound: float) -> None:
        """Reconfigure the rate/lower bound in place."""
        self._probabilistic.update(rate)
        self._lower_bound = lower_bound
        if self._rate_limiter is None:
            self._rate_limiter = self._make_rate_limiter(lower_bound)
        elif lower_bound <= 0:
            self._rate_limiter = None
        else:
            self._rate_limiter.update(lower_bound, max(lower_bound, 1.0))

    def should_sample(
        self,
        parent_context: Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Attributes | None = None,
        links: Sequence[Link] | None = None,
        trace_state: TraceState | None = None,
    ) -> SamplingResult:
        result = self._probabilistic.should_sample(
            parent_context,
            trace_id,
            name,
            kind=kind,
            attributes=attributes,
            links=links,
            trace_state=trace_state,
        )
        # Always spend a lower bound credit, even if the probabilistic
        # decision already samples, so the limiter stays ticking in sync
        # with elapsed time rather than stockpiling unused credits.
        spent = (
            self._rate_limiter.try_spend(1.0)
            if self._rate_limiter is not None
            else False
        )
        if result.decision != Decision.DROP:
            return result
        decision = Decision.RECORD_AND_SAMPLE if spent else Decision.DROP
        return _sampler_result(
            decision, result.trace_state, "lowerbound", self._lower_bound
        )

    def get_description(self) -> str:
        return f"GuaranteedThroughputSampler{{rate={self._probabilistic.rate}, lowerBound={self._lower_bound}}}"


class PerOperationSampler(Sampler):
    """Sampler for Jaeger's PerOperationSamplingStrategies.

    Each operation gets its own `GuaranteedThroughputSampler`. Operations
    without a specific strategy or seen after `max_operations` distinct
    operations are already tracked fall back to a shared default sampler
    built from `default_sampling_probability`/`default_lower_bound_traces_per_second`.
    """

    def __init__(
        self,
        default_sampling_probability: float,
        default_lower_bound_traces_per_second: float,
        per_operation_strategies: Iterable[tuple[str, float]] = (),
        max_operations: int = _DEFAULT_MAX_OPERATIONS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self._max_operations = max_operations
        self._default_sampling_probability = default_sampling_probability
        self._default_lower_bound_traces_per_second = (
            default_lower_bound_traces_per_second
        )
        self._default_sampler = GuaranteedThroughputSampler(
            default_sampling_probability,
            default_lower_bound_traces_per_second,
            clock=clock,
        )
        self._operation_samplers: dict[str, GuaranteedThroughputSampler] = {}
        for operation, rate in per_operation_strategies:
            self._operation_samplers[operation] = GuaranteedThroughputSampler(
                rate, default_lower_bound_traces_per_second, clock=clock
            )

    def update(
        self,
        default_sampling_probability: float,
        default_lower_bound_traces_per_second: float,
        per_operation_strategies: Iterable[tuple[str, float]] = (),
    ) -> None:
        """Reconfigure the default and per-operation samplers in place.

        Operations absent from `per_operation_strategies` keep whatever
        configuration they already have (not pruned).
        """
        self._default_sampling_probability = default_sampling_probability
        self._default_lower_bound_traces_per_second = (
            default_lower_bound_traces_per_second
        )
        self._default_sampler.update(
            default_sampling_probability, default_lower_bound_traces_per_second
        )

        for operation, rate in per_operation_strategies:
            existing = self._operation_samplers.get(operation)
            if existing is not None:
                existing.update(rate, default_lower_bound_traces_per_second)
            elif len(self._operation_samplers) < self._max_operations:
                self._operation_samplers[operation] = (
                    GuaranteedThroughputSampler(
                        rate,
                        default_lower_bound_traces_per_second,
                        clock=self._clock,
                    )
                )

    def should_sample(
        self,
        parent_context: Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Attributes | None = None,
        links: Sequence[Link] | None = None,
        trace_state: TraceState | None = None,
    ) -> SamplingResult:
        sampler = self._operation_samplers.get(name)
        if sampler is None:
            if len(self._operation_samplers) < self._max_operations:
                sampler = GuaranteedThroughputSampler(
                    self._default_sampling_probability,
                    self._default_lower_bound_traces_per_second,
                    clock=self._clock,
                )
                self._operation_samplers[name] = sampler
            else:
                sampler = self._default_sampler
        return sampler.should_sample(
            parent_context,
            trace_id,
            name,
            kind=kind,
            attributes=attributes,
            links=links,
            trace_state=trace_state,
        )

    def get_description(self) -> str:
        per_operation = ", ".join(
            f"{operation}: {sampler.get_description()}"
            for operation, sampler in self._operation_samplers.items()
        )
        return (
            f"PerOperationSampler{{default={self._default_sampler.get_description()}, "
            f"perOperation={{{per_operation}}}}}"
        )
