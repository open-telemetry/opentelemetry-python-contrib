# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Mapping

import urllib3

from opentelemetry.sampler.jaeger.remote._provider import (
    OperationStrategy,
    PerOperationStrategy,
    ProbabilisticStrategy,
    RateLimitingStrategy,
    SamplingStrategy,
    SamplingStrategyProvider,
)
from opentelemetry.sampler.jaeger.remote.proto_json.sampling import (
    OperationSamplingStrategy,
    SamplingStrategyResponse,
    SamplingStrategyType,
)

_DEFAULT_TIMEOUT = 10  # in seconds
_MAX_RETRIES = 3
_RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


def _decode_operation_strategy(strategy: OperationSamplingStrategy) -> OperationStrategy:
    sampling_rate = 0.0
    if strategy.probabilisticSampling is not None:
        sampling_rate = strategy.probabilisticSampling.samplingRate or 0.0
    return OperationStrategy(
        operation=strategy.operation or "", sampling_rate=sampling_rate
    )


def _decode_sampling_strategy(response: SamplingStrategyResponse) -> SamplingStrategy:
    if response.operationSampling is not None:
        operation_sampling = response.operationSampling
        return PerOperationStrategy(
            default_sampling_probability=operation_sampling.defaultSamplingProbability
            or 0.0,
            default_lower_bound_traces_per_second=operation_sampling.defaultLowerBoundTracesPerSecond
            or 0.0,
            operation_strategies=tuple(
                _decode_operation_strategy(strategy)
                for strategy in operation_sampling.perOperationStrategies
            ),
            default_upper_bound_traces_per_second=operation_sampling.defaultUpperBoundTracesPerSecond
            or 0.0,
        )
    if response.strategyType == SamplingStrategyType.RATE_LIMITING:
        rate_limiting = response.rateLimitingSampling
        max_traces_per_second = (
            rate_limiting.maxTracesPerSecond if rate_limiting is not None else 0
        )
        return RateLimitingStrategy(
            max_traces_per_second=max_traces_per_second or 0
        )
    probabilistic = response.probabilisticSampling
    sampling_rate = (
        probabilistic.samplingRate if probabilistic is not None else 0.0
    )
    return ProbabilisticStrategy(sampling_rate=sampling_rate or 0.0)


class HttpSamplingStrategyProvider(SamplingStrategyProvider):
    """Fetches Jaeger sampling strategies over HTTP using the protobuf-JSON encoding.

    Polls ``GET {endpoint}?service={service_name}``, matching the sampling endpoint
    exposed by Jaeger agents/collectors, and decodes the response body as a
    `SamplingStrategyResponse` using the protobuf-JSON encoding.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._timeout = timeout if timeout is not None else _DEFAULT_TIMEOUT
        self._pool = urllib3.PoolManager(
            headers=dict(headers) if headers is not None else None,
            timeout=self._timeout,
            retries=urllib3.Retry(
                total=_MAX_RETRIES, status_forcelist=_RETRYABLE_STATUSES
            ),
        )

    def get_sampling_strategy(self, service_name: str) -> SamplingStrategy:
        response = self._pool.request(
            "GET", self._endpoint, fields={"service": service_name}
        )
        if response.status != 200:
            raise RuntimeError(
                f"Jaeger sampling endpoint {self._endpoint} returned "
                f"HTTP {response.status}"
            )
        return _decode_sampling_strategy(
            SamplingStrategyResponse.from_json(response.data)
        )

    def close(self) -> None:
        self._pool.clear()
