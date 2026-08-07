# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProbabilisticStrategy:
    sampling_rate: float


@dataclass(frozen=True, slots=True)
class RateLimitingStrategy:
    max_traces_per_second: float


@dataclass(frozen=True, slots=True)
class OperationStrategy:
    operation: str
    sampling_rate: float


@dataclass(frozen=True, slots=True)
class PerOperationStrategy:
    default_sampling_probability: float
    default_lower_bound_traces_per_second: float
    operation_strategies: tuple[OperationStrategy, ...] = ()
    default_upper_bound_traces_per_second: float = 0.0


SamplingStrategy = (
    ProbabilisticStrategy | RateLimitingStrategy | PerOperationStrategy
)


class SamplingStrategyProvider(ABC):
    """Fetches the current Jaeger sampling strategy for a service."""

    @abstractmethod
    def get_sampling_strategy(self, service_name: str) -> SamplingStrategy:
        """Fetch the current sampling strategy for `service_name`."""

    def close(self) -> None:
        """Release resources held by this provider (e.g. network connections)."""
