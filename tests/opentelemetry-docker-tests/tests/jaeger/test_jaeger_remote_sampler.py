# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

import pytest

from opentelemetry.sampler.jaeger.remote import JaegerRemoteSampler
from opentelemetry.sampler.jaeger.remote._samplers import (
    PerOperationSampler,
    ProbabilisticSampler,
    RateLimitingSampler,
)
from opentelemetry.sdk.trace.sampling import Sampler

_HTTP_ENDPOINT = "http://localhost:5778/sampling"
_GRPC_ENDPOINT = "localhost:14250"
_STRATEGIES_FILE = (
    Path(__file__).parent / "resources" / "sampling_strategies.json"
)
_ORIGINAL_STRATEGIES_FILE_CONTENT = _STRATEGIES_FILE.read_bytes()

_POLLING_INTERVAL = 1.0
_WAIT_TIMEOUT = 10.0
_WAIT_INTERVAL = 0.5

_BASELINE_STRATEGY: dict[str, Any] = {"type": "probabilistic", "param": 0.001}

_STRATEGIES: dict[str, tuple[dict[str, Any], Callable[[Sampler], bool]]] = {
    "probabilistic": (
        {"type": "probabilistic", "param": 1.0},
        lambda s: isinstance(s, ProbabilisticSampler) and s.rate == 1.0,
    ),
    "ratelimiting": (
        {"type": "ratelimiting", "param": 3},
        lambda s: isinstance(s, RateLimitingSampler)
        and s.max_traces_per_second == 3,
    ),
    "per_operation": (
        {
            "type": "probabilistic",
            "param": 0.1,
            "operation_strategies": [
                {"operation": "op1", "type": "probabilistic", "param": 1.0}
            ],
        },
        lambda s: isinstance(s, PerOperationSampler)
        # pylint: disable-next=protected-access
        and s._operation_samplers["op1"]._probabilistic.rate == 1.0,
    ),
}


def _wait_until(
    predicate: Callable[[], bool],
    timeout: float = _WAIT_TIMEOUT,
    interval: float = _WAIT_INTERVAL,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    assert predicate(), f"condition not met within {timeout} seconds"


class _StrategiesFile:
    def write(
        self,
        default_strategy: dict[str, Any],
        service_strategies: list[dict[str, Any]],
    ) -> None:
        _STRATEGIES_FILE.write_text(
            json.dumps(
                {
                    "default_strategy": default_strategy,
                    "service_strategies": service_strategies,
                }
            )
        )


@pytest.fixture
def strategies_file():
    yield _StrategiesFile()
    _STRATEGIES_FILE.write_bytes(_ORIGINAL_STRATEGIES_FILE_CONTENT)


@pytest.fixture
def sampler():
    samplers: list[JaegerRemoteSampler] = []

    def _make(protocol: str, service_name: str) -> JaegerRemoteSampler:
        endpoint = _HTTP_ENDPOINT if protocol == "http" else _GRPC_ENDPOINT
        instance = JaegerRemoteSampler(
            endpoint,
            service_name,
            protocol=protocol,
            polling_interval=_POLLING_INTERVAL,
        )
        samplers.append(instance)
        return instance

    yield _make
    for instance in samplers:
        instance.close()


@pytest.mark.parametrize("protocol", ["http", "grpc"])
@pytest.mark.parametrize("strategy_name", sorted(_STRATEGIES))
def test_refresh(protocol, strategy_name, strategies_file, sampler):
    """Sampler picks up a strategy change without being recreated."""
    strategy, matches = _STRATEGIES[strategy_name]
    service_name = f"refresh-{strategy_name}-{protocol}"

    strategies_file.write(
        default_strategy=_BASELINE_STRATEGY,
        service_strategies=[{"service": service_name, **_BASELINE_STRATEGY}],
    )
    instance = sampler(protocol, service_name)
    _wait_until(
        lambda: isinstance(instance._sampler, ProbabilisticSampler)
        and instance._sampler.rate == _BASELINE_STRATEGY["param"]
    )

    strategies_file.write(
        default_strategy=_BASELINE_STRATEGY,
        service_strategies=[{"service": service_name, **strategy}],
    )
    _wait_until(lambda: matches(instance._sampler))


@pytest.mark.parametrize("protocol", ["http", "grpc"])
@pytest.mark.parametrize("strategy_name", sorted(_STRATEGIES))
def test_matches(protocol, strategy_name, strategies_file, sampler):
    """Sampler reflects its configured strategy without a refresh."""
    strategy, matches = _STRATEGIES[strategy_name]
    service_name = f"matches-{strategy_name}-{protocol}"

    strategies_file.write(
        default_strategy=_BASELINE_STRATEGY,
        service_strategies=[{"service": service_name, **strategy}],
    )
    instance = sampler(protocol, service_name)
    _wait_until(lambda: matches(instance._sampler))
