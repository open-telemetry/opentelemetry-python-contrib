# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import itertools
import random
import time
from typing import Mapping

import grpc

from opentelemetry.sampler.jaeger.remote._provider import (
    OperationStrategy,
    PerOperationStrategy,
    ProbabilisticStrategy,
    RateLimitingStrategy,
    SamplingStrategy,
    SamplingStrategyProvider,
)
from opentelemetry.sampler.jaeger.remote.proto.sampling_pb2 import (  # pylint: disable=no-name-in-module
    OperationSamplingStrategy,
    SamplingStrategyParameters,
    SamplingStrategyResponse,
    SamplingStrategyType,
)
from opentelemetry.sampler.jaeger.remote.proto.sampling_pb2_grpc import (
    SamplingManagerStub,
)

_DEFAULT_TIMEOUT = 10  # in seconds
_MAX_RETRIES = 3
_JITTER = 0.2
_RETRYABLE_STATUS_CODES = frozenset(
    {
        grpc.StatusCode.CANCELLED,
        grpc.StatusCode.DEADLINE_EXCEEDED,
        grpc.StatusCode.RESOURCE_EXHAUSTED,
        grpc.StatusCode.ABORTED,
        grpc.StatusCode.OUT_OF_RANGE,
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.DATA_LOSS,
    }
)


def _decode_operation_strategy(
    strategy: OperationSamplingStrategy,
) -> OperationStrategy:
    return OperationStrategy(
        operation=strategy.operation,
        sampling_rate=strategy.probabilisticSampling.samplingRate,
    )


def _decode_sampling_strategy(
    response: SamplingStrategyResponse,
) -> SamplingStrategy:
    if response.HasField("operationSampling"):
        operation_sampling = response.operationSampling
        return PerOperationStrategy(
            default_sampling_probability=operation_sampling.defaultSamplingProbability,
            default_lower_bound_traces_per_second=operation_sampling.defaultLowerBoundTracesPerSecond,
            operation_strategies=tuple(
                _decode_operation_strategy(strategy)
                for strategy in operation_sampling.perOperationStrategies
            ),
            default_upper_bound_traces_per_second=operation_sampling.defaultUpperBoundTracesPerSecond,
        )
    if response.strategyType == SamplingStrategyType.RATE_LIMITING:
        return RateLimitingStrategy(
            max_traces_per_second=response.rateLimitingSampling.maxTracesPerSecond
        )
    return ProbabilisticStrategy(
        sampling_rate=response.probabilisticSampling.samplingRate
    )


class GrpcSamplingStrategyProvider(SamplingStrategyProvider):
    """Fetches Jaeger sampling strategies over gRPC.

    Calls ``SamplingManager.GetSamplingStrategy`` against `endpoint`
    using an insecure channel.
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
        self._metadata = (
            tuple((key.lower(), value) for key, value in headers.items())
            if headers
            else ()
        )
        self._channel = grpc.insecure_channel(endpoint)
        self._stub = SamplingManagerStub(self._channel)

    def get_sampling_strategy(self, service_name: str) -> SamplingStrategy:
        request = SamplingStrategyParameters(serviceName=service_name)
        deadline = time.monotonic() + self._timeout
        for attempt in itertools.count():
            try:
                response = self._stub.GetSamplingStrategy(
                    request, metadata=self._metadata, timeout=max(deadline - time.monotonic(), 0)
                )
            except grpc.RpcError as error:
                # pylint: disable=no-member
                if (
                    error.code() not in _RETRYABLE_STATUS_CODES
                    or attempt >= _MAX_RETRIES
                    or deadline < time.monotonic()
                ):
                    raise RuntimeError(
                        f"Jaeger gRPC sampling endpoint {self._endpoint} "
                        f"returned {error.code()}: {error.details()}"
                    ) from error
                backoff = 2**attempt * random.uniform(
                    1 - _JITTER, 1 + _JITTER
                )
                time.sleep(backoff)
                continue
            return _decode_sampling_strategy(response)

    def close(self) -> None:
        self._channel.close()
